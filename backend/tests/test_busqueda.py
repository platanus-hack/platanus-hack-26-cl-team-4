"""Paso 2 de la selección v3: búsqueda web de robots fuera del catálogo (docs/agentes/seleccion-robot.md).

Las dos llamadas (investigar y fichar) se reemplazan por falsos: estos tests no usan la red ni la API.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from viaz import agentes, catalogo, orquestador
from viaz import almacen as alm
from viaz.agentes import busqueda
from viaz.catalogo import encontrados
from viaz.config import Config, cargar
from viaz.esquemas import validar

HOY = "2026-11-21"
URL = "https://ejemplo.com/instalador-7"
ID_PRUEBA = "robotica-ejemplo-s-a-instalador-prueba-7"
SPECS = ("carga_util_kg", "alcance_m", "velocidad_base_m_s", "efector")
NUCLEO = {"largo_m": 3.0, "ancho_m": 1.8, "masa_kg": 3000, "altura_cubierta_m": 1.0}


def _fixture(nombre: str) -> dict:
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def _evidencia(campo: str, url: str = URL) -> dict:
    return {"campo": campo, "url": url, "cita": f"La ficha publica {campo}."}


def _borrador(**cambios) -> dict:
    base = {
        "nombre": "Instalador Prueba 7", "fabricante": "Robótica Ejemplo S.A.",
        "tipo": "base_movil_brazo", "efector": "ventosa",
        "carga_util_kg": 60, "alcance_m": 4.0, "velocidad_base_m_s": 0.8,
        "fuente_url": URL, "capacidades": ["instalar_panel"],
        "evidencias": [_evidencia(c) for c in (*SPECS, "tipo", *(f"fisica.{k}" for k in NUCLEO), "fisica.traccion")],
        "estimados": [],
        "fisica": [{"campo": k, "valor": v} for k, v in NUCLEO.items()],
        "traccion": "orugas",
    }
    return {**base, **cambios}


def _sin_evidencia(campo: str) -> list[dict]:
    return [e for e in _borrador()["evidencias"] if e["campo"] != campo]


@pytest.fixture
def conocidas() -> dict[str, dict]:
    return catalogo.cargar()


@pytest.fixture
def requisitos(conocidas) -> dict:
    return agentes.perfiles.requisitos(_fixture("entorno"), _fixture("tarea"), list(conocidas.values()))


ACTIVA = busqueda.Parametros(activa=True, max_robots=3, max_consultas=6, tiempo_s=180)


# ---------- Del borrador a la ficha ----------

def test_un_buen_borrador_es_una_ficha_valida():
    ficha = busqueda.ficha_desde_borrador(_borrador(), HOY)
    assert ficha["id"] == ID_PRUEBA
    assert (ficha["version"], ficha["origen"], ficha["ficticio"]) == (1, "busqueda", False)
    assert ficha["fuente"] == {"url": URL, "consultado": HOY}
    assert ficha["carga_util_kg"] == 60 and ficha["efector"] == "ventosa"
    assert set(SPECS) <= set(ficha["evidencia"])
    assert ficha["evidencia"]["alcance_m"] == {"url": URL, "cita": "La ficha publica alcance_m."}
    assert ficha["fisica"] == {**NUCLEO, "traccion": "orugas"}
    assert ficha["capacidades"] == ["instalar_panel"]
    encontrados.validar_ficha(ficha)


def test_el_borrador_no_cambia():
    b = _borrador()
    antes = copy.deepcopy(b)
    busqueda.ficha_desde_borrador(b, HOY)
    assert b == antes


def test_una_spec_estimada_con_motivo_reemplaza_la_evidencia():
    b = _borrador(evidencias=_sin_evidencia("alcance_m"),
                  estimados=[{"campo": "alcance_m", "motivo": "La nota dice 'más de 4 m'; usamos 4,0 m."}])
    ficha = busqueda.ficha_desde_borrador(b, HOY)
    assert "alcance_m" not in ficha["evidencia"]
    assert ficha["estimados"] == {"alcance_m": "La nota dice 'más de 4 m'; usamos 4,0 m."}


def test_un_alcance_estimado_con_base_entra_como_candidato(conocidas):
    motivo = "No publicado. Instala módulos en trackers; la tarea pide 3,8 m de alcance: cota inferior 4,0 m."
    b = _borrador(evidencias=_sin_evidencia("alcance_m"), estimados=[{"campo": "alcance_m", "motivo": motivo}])
    r = busqueda.revisar([b], conocidas, HOY, max_robots=3)
    assert r.invalidas == []
    [ficha] = r.fichas
    assert ficha["alcance_m"] == 4.0
    assert ficha["estimados"] == {"alcance_m": motivo}
    encontrados.validar_ficha(ficha)


@pytest.mark.parametrize("motivo", ["", "   ", "valor típico", "estimado \x00\x07  aprox"])
def test_un_estimado_sin_base_rechaza_el_borrador(conocidas, motivo):
    b = _borrador(evidencias=_sin_evidencia("alcance_m"), estimados=[{"campo": "alcance_m", "motivo": motivo}])
    r = busqueda.revisar([b], conocidas, HOY, max_robots=3)
    assert r.fichas == []
    assert len(r.invalidas) == 1
    assert "alcance_m" in r.invalidas[0]["motivo"] and "no dice de dónde sale" in r.invalidas[0]["motivo"]


@pytest.mark.parametrize(("cambios", "motivo"), [
    ({"alcance_m": 9.0}, "robot.schema.json"),
    ({"fuente_url": ""}, "sin URL de fuente"),
    ({"fuente_url": "ftp://ejemplo.com/x"}, "no es http(s)"),
    ({"evidencias": [*_sin_evidencia("efector"), _evidencia("efector", "javascript:alert(1)")]}, "no es http(s)"),
    ({"evidencias": _sin_evidencia("carga_util_kg")}, "carga_util_kg sin evidencia ni estimado"),
    ({"carga_util_kg": None}, "carga_util_kg sin valor"),
    ({"efector": None}, "efector sin valor"),
    ({"nombre": "\x00\x07 "}, "sin nombre"),
])
def test_cada_borrador_invalido_queda_registrado_con_su_motivo(conocidas, cambios, motivo):
    malo = _borrador(**cambios)
    bueno = _borrador(nombre="Otro Instalador", fuente_url="https://otro.example.org/robot")
    r = busqueda.revisar([malo, bueno], conocidas, HOY, max_robots=3)
    assert [f["id"] for f in r.fichas] == ["robotica-ejemplo-s-a-otro-instalador"]
    assert len(r.invalidas) == 1 and motivo in r.invalidas[0]["motivo"]
    assert r.sobrantes == []


def test_un_nucleo_de_fisica_incompleto_se_bota_y_la_ficha_sigue_valida():
    b = _borrador(fisica=[f for f in _borrador()["fisica"] if f["campo"] != "masa_kg"],
                  estimados=[{"campo": "fisica.largo_m", "motivo": "medido en una foto"}])
    ficha = busqueda.ficha_desde_borrador(b, HOY)
    assert "fisica" not in ficha
    assert not any(k.startswith("fisica.") for k in [*ficha["evidencia"], *ficha.get("estimados", {})])
    encontrados.validar_ficha(ficha)


def test_un_dato_de_fisica_sin_evidencia_ni_estimado_no_entra():
    b = _borrador(evidencias=_sin_evidencia("fisica.ancho_m"))
    assert "fisica" not in busqueda.ficha_desde_borrador(b, HOY)
    con_estimado = _borrador(evidencias=_sin_evidencia("fisica.ancho_m"),
                             estimados=[{"campo": "fisica.ancho_m", "motivo": "medido en la foto lateral"}])
    assert busqueda.ficha_desde_borrador(con_estimado, HOY)["fisica"]["ancho_m"] == 1.8


def test_el_texto_de_la_web_se_limpia_y_se_acorta():
    b = _borrador(nombre="Instalador\x1b[31m Prueba 7" + "x" * 300,
                  evidencias=[{**e, "cita": "Cita\u0000 larga " + "y" * 500} for e in _borrador()["evidencias"]])
    ficha = busqueda.ficha_desde_borrador(b, HOY)
    assert len(ficha["nombre"]) <= 120 and "\x1b" not in ficha["nombre"]
    assert all(len(e["cita"]) <= 300 and "\u0000" not in e["cita"] for e in ficha["evidencia"].values())


def test_duplicados_por_id_y_por_fabricante_y_nombre(conocidas):
    ya = {**conocidas, ID_PRUEBA: busqueda.ficha_desde_borrador(_borrador(), HOY)}
    leapting = conocidas["leapting-mmr"]
    por_nombre = _borrador(nombre=leapting["nombre"].upper() + "!", fabricante=leapting["fabricante"].lower())
    r = busqueda.revisar([_borrador(), por_nombre], ya, HOY, max_robots=3)
    assert r.fichas == []
    assert [i["motivo"] for i in r.invalidas] == ["duplicado de un robot conocido (robotica-ejemplo-s-a-instalador-prueba-7)",
                                                  "duplicado de un robot conocido (leapting-mmr)"]


def test_dos_borradores_del_mismo_robot_dejan_uno(conocidas):
    r = busqueda.revisar([_borrador(), _borrador(nombre="Instalador PRUEBA-7")], conocidas, HOY, max_robots=3)
    assert [f["id"] for f in r.fichas] == [ID_PRUEBA]
    assert "duplicado" in r.invalidas[0]["motivo"]


# ---------- buscar(): estados ----------

def _falsos(monkeypatch, borradores: list[dict] | None = None, notas: str = "notas con fuentes", cortada: bool = False,
            error_en: str | None = None) -> list[tuple[str, dict]]:
    llamadas: list[tuple[str, dict]] = []

    def investigar(**kw):
        llamadas.append(("investigar", kw))
        if error_en == "investigar":
            raise RuntimeError("la API no respondió")
        return busqueda.Notas(notas, cortada)

    def fichar(**kw):
        llamadas.append(("fichar", kw))
        if error_en == "fichar":
            raise json.JSONDecodeError("respuesta ilegible", "{", 0)
        return copy.deepcopy(borradores if borradores is not None else [_borrador()])
    monkeypatch.setattr(busqueda, "investigar", investigar)
    monkeypatch.setattr(busqueda, "fichar", fichar)
    return llamadas


def test_una_busqueda_completa(monkeypatch, requisitos, conocidas):
    llamadas = _falsos(monkeypatch)
    r = busqueda.buscar("claude", "m", requisitos, _fixture("tarea"), conocidas, ACTIVA, hoy=HOY)
    assert r.estado == "completa" and [f["id"] for f in r.fichas] == [ID_PRUEBA]
    assert [n for n, _ in llamadas] == ["investigar", "fichar"]
    texto = llamadas[0][1]["texto"]
    assert "requisitos.json" in texto and "leapting-mmr" in texto and "instalar_panel" in texto
    assert llamadas[0][1]["max_consultas"] == 6 and llamadas[1][1]["max_robots"] == 3
    assert llamadas[1][1]["notas"] == "notas con fuentes"
    bloque = r.bloque()
    assert bloque["estado"] == "completa" and bloque["invalidas"] == []


def test_el_tope_de_robots_da_cortada(monkeypatch, requisitos, conocidas):
    _falsos(monkeypatch, [_borrador(), _borrador(nombre="Otro Instalador")])
    r = busqueda.buscar("claude", "m", requisitos, _fixture("tarea"), conocidas, ACTIVA._replace(max_robots=1), hoy=HOY)
    assert r.estado == "cortada" and len(r.fichas) == 1
    assert "Otro Instalador" in r.detalle


def test_el_tiempo_agotado_con_notas_da_cortada(monkeypatch, requisitos, conocidas):
    _falsos(monkeypatch, cortada=True)
    r = busqueda.buscar("claude", "m", requisitos, _fixture("tarea"), conocidas, ACTIVA, hoy=HOY)
    assert r.estado == "cortada" and len(r.fichas) == 1 and "tiempo" in r.detalle


@pytest.mark.parametrize(("kw", "texto"), [
    ({"error_en": "investigar"}, "la API no respondió"),
    ({"error_en": "fichar"}, "respuesta ilegible"),
    ({"notas": "", "cortada": True}, "sin notas"),
])
def test_cualquier_falla_da_fallida(monkeypatch, requisitos, conocidas, kw, texto):
    _falsos(monkeypatch, **kw)
    r = busqueda.buscar("claude", "m", requisitos, _fixture("tarea"), conocidas, ACTIVA, hoy=HOY)
    assert r.estado == "fallida" and r.fichas == [] and texto in r.detalle


def test_el_tiempo_se_acaba_antes_de_fichar(monkeypatch, requisitos, conocidas):
    llamadas = _falsos(monkeypatch)
    horas = iter([0.0, 500.0])
    r = busqueda.buscar("claude", "m", requisitos, _fixture("tarea"), conocidas, ACTIVA, hoy=HOY,
                        reloj=lambda: next(horas))
    assert r.estado == "fallida" and [n for n, _ in llamadas] == ["investigar"]


@pytest.mark.parametrize(("modo", "parametros", "texto"), [
    ("fijo", ACTIVA, "fijo"),
    ("claude", ACTIVA._replace(activa=False), "VIAZ_BUSQUEDA=0"),
])
def test_sin_busqueda_queda_omitida_y_no_llama(monkeypatch, requisitos, conocidas, modo, parametros, texto):
    llamadas = _falsos(monkeypatch)
    r = busqueda.buscar(modo, "m", requisitos, _fixture("tarea"), conocidas, parametros, hoy=HOY)
    assert r.estado == "omitida" and texto in r.detalle and llamadas == []


# ---------- Las dos llamadas, con un cliente falso ----------

def _texto(texto: str, citas: tuple[tuple[str, str], ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=texto, citations=[
        SimpleNamespace(type="web_search_result_location", url=u, cited_text=c, title="t") for u, c in citas])


class ClienteFalso:
    def __init__(self, respuestas: list[SimpleNamespace]):
        self.respuestas, self.pedidos = list(respuestas), []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.pedidos.append(copy.deepcopy({k: v for k, v in kw.items() if k != "messages"}) | {"messages": kw["messages"]})
        return self.respuestas.pop(0)


def test_investigar_usa_la_busqueda_web_y_junta_las_citas(monkeypatch):
    pausa = SimpleNamespace(stop_reason="pause_turn", content=[_texto("Busco robots.")])
    fin = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="server_tool_use", name="web_search", input={"query": "x"}),
        _texto("El Instalador 7 carga 60 kg.", ((URL, "carga útil de 60 kg"),))])
    cliente = ClienteFalso([pausa, fin])
    monkeypatch.setattr(busqueda, "_cliente", lambda: cliente)
    notas = busqueda.investigar(modelo="m", texto="pedido", max_consultas=4, tiempo_s=60)
    assert not notas.cortada
    assert "Busco robots." in notas.texto and "carga 60 kg" in notas.texto
    assert URL in notas.texto and "carga útil de 60 kg" in notas.texto
    herramienta = cliente.pedidos[0]["tools"]
    assert herramienta == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
    assert "output_config" not in cliente.pedidos[0]
    assert cliente.pedidos[1]["messages"][-1] == {"role": "assistant", "content": pausa.content}
    assert 0 < cliente.pedidos[0]["timeout"] <= 60


def test_investigar_rechazado_es_un_error(monkeypatch):
    cliente = ClienteFalso([SimpleNamespace(stop_reason="refusal", content=[], stop_details=None)])
    monkeypatch.setattr(busqueda, "_cliente", lambda: cliente)
    with pytest.raises(agentes.ErrorAgente, match="rechazó"):
        busqueda.investigar(modelo="m", texto="pedido", max_consultas=4, tiempo_s=60)


def test_investigar_sin_tiempo_corta_con_lo_que_tiene(monkeypatch):
    pausa = SimpleNamespace(stop_reason="pause_turn", content=[_texto("Parcial.")])
    cliente = ClienteFalso([pausa])
    monkeypatch.setattr(busqueda, "_cliente", lambda: cliente)
    horas = iter([0.0, 1.0, 100.0])
    notas = busqueda.investigar(modelo="m", texto="pedido", max_consultas=4, tiempo_s=60, reloj=lambda: next(horas))
    assert notas == busqueda.Notas("Parcial.", True)


def _sin_claves_libres(nodo) -> bool:
    if isinstance(nodo, dict):
        if "additionalProperties" in nodo and nodo["additionalProperties"] is not False:
            return False
        return all(_sin_claves_libres(v) for v in nodo.values())
    if isinstance(nodo, list):
        return all(_sin_claves_libres(v) for v in nodo)
    return True


def test_fichar_pide_borradores_con_salida_estructurada(monkeypatch):
    llamadas = []

    def falso(**kw):
        llamadas.append(kw)
        return {"robots": [_borrador()]}
    monkeypatch.setattr(busqueda, "pedir_json", falso)
    borradores = busqueda.fichar(modelo="m", notas="notas de la web", max_robots=2, tiempo_s=30)
    assert borradores == [_borrador()]
    kw = llamadas[0]
    assert "notas de la web" in kw["contenido"][-1]["text"] and kw["tiempo_s"] == 30
    assert _sin_claves_libres(kw["esquema"])
    campo = kw["esquema"]["properties"]["robots"]["items"]["properties"]["evidencias"]["items"]["properties"]["campo"]
    assert set(SPECS) <= set(campo["enum"])


def test_los_prompts_no_nombran_el_dominio():
    for texto in (busqueda.SISTEMA_INVESTIGAR, busqueda.SISTEMA_FICHAR):
        for palabra in ("panel", "solar", "tubo", "parque"):
            assert palabra not in texto.lower()


# ---------- Catálogo compartido en el almacén ----------

@pytest.fixture
def store(tmp_path) -> alm.AlmacenLocal:
    return alm.AlmacenLocal(tmp_path / "archivos", "http://x")


def test_listar_devuelve_las_claves_bajo_un_prefijo(store):
    assert store.listar("catalogo/encontrados/") == []
    store.escribir("catalogo/encontrados/b.json", b"{}")
    store.escribir("catalogo/encontrados/a.json", b"{}")
    store.escribir("corridas/x/robot.json", b"{}")
    assert store.listar("catalogo/encontrados/") == ["catalogo/encontrados/a.json", "catalogo/encontrados/b.json"]


def test_guardar_y_cargar_el_catalogo_compartido(store):
    ficha = busqueda.ficha_desde_borrador(_borrador(), HOY)
    encontrados.guardar(store, ficha)
    assert store.existe(f"catalogo/encontrados/{ID_PRUEBA}.json")
    store.escribir("catalogo/encontrados/roto.json", b"{no es json")
    store.escribir("catalogo/encontrados/sin-fuente.json", json.dumps({**ficha, "id": "sin-fuente", "fuente": {}}).encode())
    store.escribir("catalogo/encontrados/otro-id.json", json.dumps(ficha).encode())
    assert encontrados.cargar(store) == {ID_PRUEBA: ficha}


def test_el_catalogo_del_repo_gana_un_choque_de_id(store, conocidas):
    falsa = {**conocidas["leapting-mmr"], "carga_util_kg": 999, "origen": "busqueda"}
    store.escribir("catalogo/encontrados/leapting-mmr.json", json.dumps(falsa).encode())
    unidas = encontrados.unir(conocidas, encontrados.cargar(store))
    assert unidas["leapting-mmr"] == conocidas["leapting-mmr"]


# ---------- Flujo de la etapa robot ----------

def _seleccion_falsa(monkeypatch, primero: str) -> None:
    def falso(**kw):
        ids = kw["esquema"]["properties"]["finalistas"]["items"]["properties"]["id"]["enum"]
        finales = list(dict.fromkeys([primero, "leapting-mmr"]))
        return {"finalistas": [{"id": i, "puesto": n, "justificacion": f"Puesto {n}."} for n, i in enumerate(finales, 1)],
                "alternativas": [{"id": i, "por_que_no": "otro"} for i in ids if i not in finales]}
    monkeypatch.setattr(agentes, "pedir_json", falso)


def _cfg(**kw) -> Config:
    return Config(agentes="claude", busqueda=True, busqueda_max_robots=3, busqueda_max_consultas=6,
                  busqueda_tiempo_s=180, **kw)


def test_un_robot_encontrado_puede_ser_finalista(monkeypatch, store):
    _falsos(monkeypatch)
    _seleccion_falsa(monkeypatch, ID_PRUEBA)
    r, nuevas = orquestador.seleccionar_robot(_cfg(), store, _fixture("entorno"), _fixture("tarea"))
    sel = validar("seleccion", r.seleccion)
    assert sel["busqueda"]["estado"] == "completa" and sel["encontrados"] == [ID_PRUEBA]
    assert [f["id"] for f in nuevas] == [ID_PRUEBA]
    assert ID_PRUEBA in {f["id"] for f in r.requisitos["por_robot"]}
    primero = r.robots_por_puesto[0]
    assert primero["id"] == ID_PRUEBA and primero["origen"] == "busqueda"
    validar("robot", primero)
    assert store.existe(f"catalogo/encontrados/{ID_PRUEBA}.json")


def test_una_segunda_corrida_reusa_la_ficha_sin_buscarla(monkeypatch, store):
    _falsos(monkeypatch)
    _seleccion_falsa(monkeypatch, "leapting-mmr")
    orquestador.seleccionar_robot(_cfg(), store, _fixture("entorno"), _fixture("tarea"))
    llamadas = _falsos(monkeypatch)
    r, nuevas = orquestador.seleccionar_robot(_cfg(), store, _fixture("entorno"), _fixture("tarea"))
    assert nuevas == [] and r.seleccion["encontrados"] == []
    assert ID_PRUEBA in llamadas[0][1]["texto"]
    assert "duplicado" in r.seleccion["busqueda"]["invalidas"][0]["motivo"]
    candidatos = {a["id"] for a in r.seleccion["alternativas"]} | {f["id"] for f in r.seleccion["finalistas"]}
    assert ID_PRUEBA in candidatos


@pytest.mark.parametrize("error_en", ["investigar", "fichar"])
def test_una_busqueda_fallida_no_detiene_la_seleccion(monkeypatch, store, error_en):
    _falsos(monkeypatch, error_en=error_en)
    _seleccion_falsa(monkeypatch, "leapting-mmr")
    r, nuevas = orquestador.seleccionar_robot(_cfg(), store, _fixture("entorno"), _fixture("tarea"))
    sel = validar("seleccion", r.seleccion)
    assert sel["busqueda"]["estado"] == "fallida" and nuevas == []
    assert [f["id"] for f in sel["finalistas"]] == ["leapting-mmr"]


def test_en_modo_fijo_la_busqueda_queda_omitida(monkeypatch, store):
    llamadas = _falsos(monkeypatch)
    r, nuevas = orquestador.seleccionar_robot(Config(agentes="fijo"), store, _fixture("entorno"), _fixture("tarea"))
    assert r.seleccion["busqueda"]["estado"] == "omitida" and nuevas == [] and llamadas == []


# ---------- Configuración ----------

@pytest.mark.parametrize(("variable", "valor"), [
    ("VIAZ_BUSQUEDA", "tal vez"),
    ("VIAZ_BUSQUEDA_MAX_ROBOTS", "0"), ("VIAZ_BUSQUEDA_MAX_ROBOTS", "6"),
    ("VIAZ_BUSQUEDA_MAX_CONSULTAS", "0"), ("VIAZ_BUSQUEDA_MAX_CONSULTAS", "16"),
    ("VIAZ_BUSQUEDA_TIEMPO_S", "0"), ("VIAZ_BUSQUEDA_TIEMPO_S", "diez"),
])
def test_cada_limite_fuera_de_rango_se_rechaza_al_partir(monkeypatch, variable, valor):
    monkeypatch.setenv(variable, valor)
    with pytest.raises(ValueError, match=variable):
        cargar()


def test_los_valores_por_defecto_de_la_busqueda(monkeypatch):
    for v in ("VIAZ_BUSQUEDA", "VIAZ_BUSQUEDA_MAX_ROBOTS", "VIAZ_BUSQUEDA_MAX_CONSULTAS", "VIAZ_BUSQUEDA_TIEMPO_S"):
        monkeypatch.delenv(v, raising=False)
    c = cargar()
    assert (c.busqueda, c.busqueda_max_robots, c.busqueda_max_consultas, c.busqueda_tiempo_s) == (True, 3, 6, 180)
    monkeypatch.setenv("VIAZ_BUSQUEDA", "0")
    assert cargar().busqueda is False
