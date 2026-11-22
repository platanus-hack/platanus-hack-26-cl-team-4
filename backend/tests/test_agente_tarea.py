"""Agente Tarea genérico: núcleo para cualquier espacio, perfil instalar_panel y reglas contra entorno.json."""
from __future__ import annotations

import copy
import json

import pytest

from viaz import agentes, orquestador
from viaz.esquemas import ErrorEsquema, validar

PROYECTO = {"nombre": "Sala de prueba", "descripcion": "", "videos": []}


def _fixture(nombre):
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def _respuesta(tarea: dict, **cambios) -> dict:
    """Lo que devolvería Claude: sin version y con el perfil como null si no aplica."""
    r = {k: copy.deepcopy(v) for k, v in tarea.items() if k != "version"}
    r.setdefault("pila_paneles", None)
    for ruta, valor in cambios.items():
        a, b = ruta.split("__")
        r[a][b] = valor
    return r


def test_fixtures_cumplen_esquema_y_calzan_con_su_entorno():
    agentes.validar_tarea(_fixture("tarea"), _fixture("entorno"))
    agentes.validar_tarea(_fixture("tarea_sala"), _fixture("entorno_sala"))


def test_perfil_pila_solo_en_instalar_panel():
    t = _fixture("tarea")
    del t["pila_paneles"]
    with pytest.raises(ErrorEsquema):
        validar("tarea", t)
    s = _fixture("tarea_sala")
    s["pila_paneles"] = {"en_robot": True, "cantidad": 3}
    with pytest.raises(ErrorEsquema):
        validar("tarea", s)


@pytest.mark.parametrize("cambio, mensaje", [
    (lambda t: t["objeto"].update(elemento="robot_volador"), "no existe en entorno.json"),
    (lambda t: t["objeto"].update(elemento="mesa_central"), "marcado fijo"),
    (lambda t: t["destino"].update(elemento="mesa_central"), "mismo elemento"),
    (lambda t: t["criterios_exito"].update(tiempo_max_s=10), "menor que objetivo.ciclo_s"),
    (lambda t: t["restricciones"].append({"tipo": "fuerza_max_n", "valor": None, "detalle": "x"}), "necesita un valor"),
])
def test_reglas_contra_entorno(cambio, mensaje):
    t = _fixture("tarea_sala")
    cambio(t)
    problemas = agentes.problemas_tarea(t, _fixture("entorno_sala"))
    assert any(mensaje in p for p in problemas), problemas


def test_instalar_panel_exige_parque_solar_y_pila_suficiente():
    t = _fixture("tarea")
    t["objetivo"]["cantidad"] = 9
    problemas = agentes.problemas_tarea(t, _fixture("entorno_sala"))
    assert any("necesita un entorno parque_solar" in p for p in problemas)
    assert any("mayor que la pila" in p for p in problemas)


def test_modo_fijo_elige_la_tarea_del_tipo_de_espacio():
    assert agentes.tarea("fijo", "x", PROYECTO, _fixture("entorno"), None)["tarea"] == "instalar_panel"
    assert agentes.tarea("fijo", "x", PROYECTO, _fixture("entorno_sala"), None)["tarea"] == "tomar_y_dejar"


def test_reintenta_con_los_problemas_y_acepta_la_correccion(monkeypatch):
    sala = _fixture("tarea_sala")
    respuestas = [_respuesta(sala, objeto__elemento="caja_inexistente"), _respuesta(sala)]
    vistos = []

    def falso(**kw):
        vistos.append(kw["contenido"][-1]["text"])
        return respuestas.pop(0)

    monkeypatch.setattr(agentes, "pedir_json", falso)
    t = agentes.tarea("claude", "x", PROYECTO, _fixture("entorno_sala"), None)
    assert t["objeto"]["elemento"] == "caja_carton_1" and "pila_paneles" not in t
    assert "caja_carton_1" in vistos[0]                       # el agente ve los nombres de los elementos
    assert "caja_inexistente" in vistos[1] and "Corrige" in vistos[1]


def test_falla_si_tras_los_intentos_no_calza(monkeypatch):
    mala = _respuesta(_fixture("tarea_sala"), destino__elemento="mesa_central", origen__elemento="mesa_central")
    monkeypatch.setattr(agentes, "pedir_json", lambda **kw: copy.deepcopy(mala))
    with pytest.raises(agentes.ErrorAgente, match="mismo elemento"):
        agentes.tarea("claude", "x", PROYECTO, _fixture("entorno_sala"), None)


def test_orquestador_usa_las_tolerancias_de_la_tarea_y_corta_tareas_sin_simulacion():
    t = _fixture("tarea")
    t["criterios_exito"].update(tolerancia_pos_m=0.03, tolerancia_ang_grados=4)
    assert orquestador.tolerancias(t) == (0.03, 4, "0.03:4,0.02:2")
    orquestador.exigir_pipeline(_fixture("entorno"), _fixture("tarea"))
    with pytest.raises(agentes.ErrorAgente, match="tomar_y_dejar"):
        orquestador.exigir_pipeline(_fixture("entorno"), _fixture("tarea_sala"))
