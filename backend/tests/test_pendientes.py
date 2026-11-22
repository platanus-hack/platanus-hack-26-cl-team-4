"""Pruebas de los pendientes para una corrida real con Claude (docs/pendientes-corrida-real.md). Sin red."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from viaz import agentes, comparacion, monitor, orquestador
from viaz.agentes import base, busqueda, perfiles, seleccion
from viaz.config import Config
from viaz.esquemas import para_api, validar

FIXTURES = Path(__file__).resolve().parents[1] / "viaz" / "fixtures"


def _fixture(n: str) -> dict:
    return json.loads((FIXTURES / f"{n}.json").read_text(encoding="utf-8"))


ESQUEMA = {"type": "object", "additionalProperties": False, "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}


# ---------- Problema 5: errores de la API como ErrorAgente, con reintentos ----------

class _Flujo:
    def __init__(self, resp):
        self.resp = resp

    def __enter__(self):
        if isinstance(self.resp, Exception):
            raise self.resp
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.resp


def _respuesta(texto: str = '{"ok": true}', stop: str = "end_turn", salida: int = 10):
    return types.SimpleNamespace(stop_reason=stop, content=[types.SimpleNamespace(type="text", text=texto)],
                                 usage=types.SimpleNamespace(input_tokens=5, output_tokens=salida), stop_details=None)


def _error(estado: int):
    import anthropic
    import httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError(f"error {estado}", response=httpx.Response(estado, request=req), body=None)


@pytest.fixture
def api(monkeypatch):
    """Cliente falso de anthropic. Devuelve la lista de respuestas que se van consumiendo, una por llamada."""
    import anthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    monkeypatch.delenv("VIAZ_CLAUDE", raising=False)
    respuestas: list = []
    llamadas: list = []

    class Cliente:
        def __init__(self, **kw):
            self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(stream=self.stream))

        def stream(self, **kw):
            llamadas.append(kw)
            return _Flujo(respuestas.pop(0))

    monkeypatch.setattr(anthropic, "Anthropic", Cliente)
    return respuestas, llamadas


def _pedir(**kw):
    return base._pedir_api(modelo="m", sistema="s", contenido=[], esquema=ESQUEMA, effort="low", tiempo_s=None,
                           max_tokens=1000, etiqueta="prueba", dormir=lambda s: None, **kw)


def test_un_529_se_reintenta_y_despues_responde(api):
    respuestas, llamadas = api
    respuestas += [_error(529), _error(429), _respuesta()]
    assert _pedir() == {"ok": True}
    assert len(llamadas) == 3


def test_errores_pasajeros_sin_fin_terminan_en_error_agente(api):
    respuestas, _ = api
    respuestas += [_error(529)] * 4
    with pytest.raises(base.ErrorAgente, match="529"):
        _pedir()


def test_un_400_no_se_reintenta_y_sale_como_error_agente(api):
    respuestas, llamadas = api
    respuestas += [_error(400)]
    with pytest.raises(base.ErrorAgente, match="400"):
        _pedir()
    assert len(llamadas) == 1


def test_con_tiempo_tope_no_hay_reintentos(api):
    respuestas, llamadas = api
    respuestas += [_error(529), _respuesta()]
    with pytest.raises(base.ErrorAgente):
        base._pedir_api(modelo="m", sistema="s", contenido=[], esquema=ESQUEMA, effort="low", tiempo_s=5,
                        max_tokens=1000, etiqueta="x", dormir=lambda s: None)
    assert len(llamadas) == 1 and llamadas[0]["timeout"] == 5


def test_json_roto_y_corte_por_max_tokens_son_error_agente(api):
    respuestas, _ = api
    respuestas += [_respuesta("{roto"), _respuesta(stop="max_tokens")]
    with pytest.raises(base.ErrorAgente, match="JSON"):
        _pedir()
    with pytest.raises(base.ErrorAgente, match="max_tokens"):
        _pedir()


def test_el_constructor_pasa_al_respaldo_cuando_la_api_falla(monkeypatch):
    """Con el error convertido en ErrorAgente, construir_robot ya lo atrapa (orquestador.py)."""
    import inspect
    assert "except agentes.ErrorAgente" in inspect.getsource(orquestador.construir_robot)


# ---------- Problema 8: max_tokens por agente y streaming ----------

def test_cada_agente_tiene_su_tope_y_la_llamada_va_por_streaming(api, caplog):
    respuestas, llamadas = api
    respuestas += [_respuesta(salida=900)]
    _pedir()
    assert llamadas[0]["max_tokens"] == 1000
    assert "sube su max_tokens" in caplog.text       # 900 de 1000 > 80 %
    assert agentes.MAX_TOKENS_AGENTE["entorno"] >= 32000


# ---------- Problemas 2 y 3: proveedor de suscripción, solo local ----------

def test_suscripcion_se_rechaza_en_render_y_con_clave_de_api(monkeypatch):
    monkeypatch.setenv("VIAZ_CLAUDE", "suscripcion")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    p = base.problemas_credenciales()
    assert any("Render" in x for x in p) and any("ANTHROPIC_API_KEY" in x for x in p)
    with pytest.raises(base.ErrorAgente, match="Render"):
        base.pedir_json(modelo="m", sistema="s", contenido=[], esquema=ESQUEMA)


def test_sin_credenciales_el_error_dice_que_falta(monkeypatch):
    monkeypatch.delenv("VIAZ_CLAUDE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(base.ErrorAgente, match="ANTHROPIC_API_KEY"):
        base.pedir_json(modelo="m", sistema="s", contenido=[], esquema=ESQUEMA)
    monkeypatch.setenv("VIAZ_CLAUDE", "otro")
    with pytest.raises(base.ErrorAgente, match="VIAZ_CLAUDE"):
        base.proveedor()


def test_suscripcion_usa_el_agent_sdk_sin_herramientas_ni_configuracion(monkeypatch):
    """Agent SDK falso: revisa las opciones y devuelve structured_output."""
    monkeypatch.setenv("VIAZ_CLAUDE", "suscripcion")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    vistas = {}

    class Opciones:
        def __init__(self, **kw):
            vistas.update(kw)

    class Resultado:
        def __init__(self):
            self.is_error, self.structured_output, self.usage = False, {"ok": True}, {}

    async def query(prompt, options):
        async for m in prompt:
            vistas["mensaje"] = m
        yield Resultado()

    sdk = types.ModuleType("claude_agent_sdk")
    sdk.ClaudeAgentOptions, sdk.ResultMessage, sdk.query = Opciones, Resultado, query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", sdk)
    imagen = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AA=="}}
    assert base.pedir_json(modelo="m", sistema="s", contenido=[imagen], esquema=ESQUEMA) == {"ok": True}
    assert vistas["tools"] == [] and vistas["setting_sources"] == []
    assert vistas["output_format"]["type"] == "json_schema"
    assert vistas["mensaje"]["message"]["content"][0]["type"] == "image"   # las imágenes llegan al SDK


def test_con_suscripcion_la_busqueda_queda_omitida_con_motivo(monkeypatch):
    """Problema 4: el CLI no entrega citas literales; la búsqueda no corre y lo dice."""
    monkeypatch.setenv("VIAZ_CLAUDE", "suscripcion")
    r = busqueda.buscar("claude", "m", {}, {}, {}, busqueda.Parametros(True, 3, 6, 180))
    assert r.estado == "omitida" and "suscripcion" in r.detalle


# ---------- Problema 6: chequeo previo y fuente de cada artefacto ----------

def test_el_orquestador_no_arranca_si_claude_no_responde(monkeypatch):
    def falla(**kw):
        raise base.ErrorAgente("401 clave inválida")
    monkeypatch.setattr(base, "pedir_json", falla)
    with pytest.raises(base.ErrorAgente, match="401"):
        orquestador.comprobar_claude(Config(agentes="claude"))
    orquestador.comprobar_claude(Config(agentes="fijo"))   # en modo fijo no llama


def _metricas(n: int = 30) -> list[dict]:
    return [{"iteracion": i, "pasos": i * 100, "tiempo_s": i * 10.0, "recompensa_media": float(i), "tasa_exito": i / 40,
             "largo_episodio": 100.0, "perdida_valor": 0.1, "perdida_politica": 0.1, "entropia": 1.0} for i in range(n)]


def test_el_monitor_dice_si_el_chequeo_es_de_claude_o_de_reglas(monkeypatch):
    m = _metricas()
    ch = monitor.chequear("fijo", "m", m, m, [], 1.0)
    assert ch["fuente"] == "reglas" and ch["motivo_reglas"] is None
    validar("monitoreo", ch)

    def falla(**kw):
        raise base.ErrorAgente("sin cupo")
    monkeypatch.setattr(base, "pedir_json", falla)
    ch = monitor.chequear("claude", "m", m, m, [], 1.0)
    assert ch["fuente"] == "reglas" and "sin cupo" in ch["motivo_reglas"]


def test_el_monitor_usa_tiempo_tope_y_respeta_su_cupo(monkeypatch):
    """Problemas 13 y 12: la llamada lleva tiempo tope; agotado el cupo, no llama más."""
    m = _metricas()
    vistos = []

    def responde(**kw):
        vistos.append(kw)
        return {"estado": "mejorando", "evidencia": {}, "recomendacion": "seguir", "detalle": "ok", "hito": "ninguno",
                "checkpoint_recomendado": "ninguno", "iteracion": 29}
    monkeypatch.setattr(base, "pedir_json", responde)
    ch = monitor.chequear("claude", "m", m, m, [], 1.0, tiempo_s=30, max_llamadas=1)
    assert ch["fuente"] == "claude" and vistos[0]["tiempo_s"] == 30
    ch2 = monitor.chequear("claude", "m", m, m, [ch], 1.0, tiempo_s=30, max_llamadas=1)
    assert ch2["fuente"] == "reglas" and "cupo" in ch2["motivo_reglas"] and len(vistos) == 1


def test_el_prompt_del_monitor_no_fija_la_tolerancia_del_panel():
    texto = (Path(agentes.__file__).parent / "prompts" / "monitor.md").read_text(encoding="utf-8")
    assert "dejar un panel solar sobre la estructura." not in texto.splitlines()[1]


# ---------- Tolerancia fina por tarea (RF-INT-20) ----------

def test_la_tolerancia_fina_sale_del_perfil_de_la_tarea():
    assert orquestador.tolerancias(_fixture("tarea"))[2] == "0.05:5,0.02:2"
    assert orquestador.tolerancias(_fixture("tarea_animar"))[2] == "0.5:30"


# ---------- Problema 7B: límites de complejidad de los esquemas de la API ----------

LIMITE_OPCIONALES = 24      # platform.claude.com/docs/en/build-with-claude/structured-outputs#schema-complexity-limits
LIMITE_UNIONES = 16


def _contar(nodo, opcionales=0, uniones=0):
    if isinstance(nodo, dict):
        if isinstance(nodo.get("type"), list) or "anyOf" in nodo:
            uniones += 1
        if nodo.get("type") == "object" and "properties" in nodo:
            opcionales += len(set(nodo["properties"]) - set(nodo.get("required", [])))
        for v in nodo.values():
            opcionales, uniones = _contar(v, opcionales, uniones)
    elif isinstance(nodo, list):
        for v in nodo:
            opcionales, uniones = _contar(v, opcionales, uniones)
    return opcionales, uniones


ESQUEMAS_API = {
    "entorno": agentes.esquema_agente_entorno,
    "tarea": agentes.esquema_agente_tarea,
    "seleccion": lambda: seleccion.esquema_eleccion(["a-1", "b-2", "c-3"]),
    "justificacion": lambda: seleccion.ESQUEMA_JUSTIFICACION,
    "fichas": busqueda.esquema_borradores,
    "constructor": lambda: agentes.esquema_agente_constructor(__import__("viaz.robot_cfg", fromlist=["x"]).cargar_assets()),
    "monitor": monitor.esquema_agente,
    "comparacion": lambda: comparacion.ESQUEMA_EXPLICACION,
}


@pytest.mark.parametrize("nombre", list(ESQUEMAS_API))
def test_cada_esquema_que_va_a_la_api_cabe_en_los_limites(nombre):
    opcionales, uniones = _contar(para_api(ESQUEMAS_API[nombre]()))
    assert opcionales <= LIMITE_OPCIONALES, f"{nombre}: {opcionales} parámetros opcionales"
    assert uniones <= LIMITE_UNIONES, f"{nombre}: {uniones} tipos de unión"


# ---------- Problema 1: el flujo rl puede pedir la tarea al agente ----------

def test_el_flujo_rl_llama_al_agente_tarea_si_se_pide(monkeypatch):
    import inspect
    fuente = inspect.getsource(orquestador.procesar_rl)
    assert "cfg.tarea_agente" in fuente and "agentes.tarea(" in fuente
    monkeypatch.setenv("VIAZ_TAREA_AGENTE", "1")
    assert Config().tarea_agente is True
    monkeypatch.setenv("VIAZ_TAREA_AGENTE", "talvez")
    with pytest.raises(ValueError):
        Config()
