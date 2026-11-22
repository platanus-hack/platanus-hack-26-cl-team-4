"""Calidad del agente Tarea: problemas_calidad() (docs/agentes/tarea.md §9) y su reintento. Sin llamar a la API."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from viaz import agentes

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import plan  # noqa: E402


def _f(nombre: str) -> dict:
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def _parque(largo_m: float | None = None) -> dict:
    e = _f("entorno")
    if largo_m is not None:
        e["filas"]["largo_m"] = largo_m
    return e


def _panel(cantidad=5, ciclo_s=60, pila=5, restricciones=None) -> dict:
    t = _f("tarea")
    t["objetivo"] = {"cantidad": cantidad, "ciclo_s": ciclo_s}
    t["pila_paneles"]["cantidad"] = pila
    if restricciones is not None:
        t["restricciones"] = restricciones
    return t


def _sala(**objetivo) -> dict:
    t = _f("tarea_sala")
    t["objetivo"].update(objetivo)
    return t


NO_CHOCAR = {"tipo": "no_chocar", "valor": None, "detalle": "no chocar con las estructuras"}
HORIZONTAL = {"tipo": "orientacion_fija", "valor": None, "detalle": "panel horizontal durante el traslado"}


def test_misma_geometria_que_el_plan():
    assert (agentes.INICIO_FILA_M, agentes.HOLGURA_PANEL_M) == (plan.INICIO_X, plan.HOLGURA_SLOT)
    for largo in (5, 7, 30, 500):
        assert agentes.paneles_que_caben(_parque(largo)) == plan.caben(_parque(largo))


def test_los_fixtures_cumplen():
    assert agentes.problemas_calidad(_f("tarea"), _f("entorno")) == []
    assert agentes.problemas_calidad(_f("tarea_sala"), _f("entorno_sala")) == []


# Salidas esperadas de los casos de panel del contrato (§9.4): deben cumplir.
@pytest.mark.parametrize("caso,largo,cantidad,ciclo,pila", [
    ("C1", None, 5, 60, 5), ("C2", None, 8, 45, 8), ("C3", None, 5, 120, 5), ("C4", None, 5, 30, 5), ("C5", 7, 4, 60, 4),
])
def test_casos_de_panel_del_contrato_cumplen(caso, largo, cantidad, ciclo, pila):
    assert agentes.problemas_calidad(_panel(cantidad, ciclo, pila), _parque(largo)) == [], caso


@pytest.mark.parametrize("tarea,entorno,frase", [
    (_sala(cantidad=20, ciclo_s=45), "entorno_sala", "no cabe en una demo corta"),
    (_panel(cantidad=10, ciclo_s=120, pila=10), "entorno", "no cabe en una demo corta"),
    (_panel(restricciones=[HORIZONTAL]), "entorno", "falta la restricción no_chocar"),
    (_panel(restricciones=[]), "entorno", "deben ser de 1 a 5"),
    (_panel(restricciones=[NO_CHOCAR, HORIZONTAL] + [{"tipo": "otra", "valor": None, "detalle": str(i)} for i in range(4)]),
     "entorno", "deben ser de 1 a 5"),
    (_panel(restricciones=[NO_CHOCAR, HORIZONTAL, {**NO_CHOCAR, "detalle": "No chocar con las estructuras."}]),
     "entorno", "repetidas"),
    (_panel(cantidad=2, pila=2), "entorno", "entre 3 y 10"),
    (_panel(cantidad=3, ciclo_s=150, pila=3), "entorno", "entre 30 y 120"),
    (_panel(restricciones=[NO_CHOCAR]), "entorno", "falta la restricción orientacion_fija"),
])
def test_detecta_cada_regla(tarea, entorno, frase):
    problemas = agentes.problemas_calidad(tarea, _f(entorno))
    assert any(frase in p for p in problemas), problemas


def test_cabe_en_la_fila():
    assert agentes.problemas_calidad(_panel(), _parque(largo_m=7)) == [
        "objetivo.cantidad es 5, pero en una fila caben 4 paneles"]


def test_las_reglas_de_panel_no_se_aplican_a_otras_tareas():
    t = _sala(cantidad=2, ciclo_s=200)   # 400 s: dura poco y no es panel
    assert agentes.problemas_calidad(t, _f("entorno_sala")) == []


def test_validar_rechaza_un_tarea_escrito_a_mano_que_no_cumple():
    with pytest.raises(agentes.ErrorAgente, match="no cabe en una demo corta"):
        agentes.validar_tarea(_panel(cantidad=10, ciclo_s=120, pila=10), _f("entorno"))


def test_reintenta_con_el_problema_de_calidad(monkeypatch):
    buena = _f("tarea_sala")
    mala = copy.deepcopy(buena)
    mala["restricciones"] = [r for r in mala["restricciones"] if r["tipo"] != "no_chocar"]
    respuestas, pedidos = [mala, buena], []

    def pedir_json(*, contenido, **_):
        pedidos.append(contenido[-1]["text"])
        r = copy.deepcopy(respuestas[len(pedidos) - 1])
        r.pop("version", None)
        return {**r, "pila_paneles": None}

    monkeypatch.setattr(agentes, "pedir_json", pedir_json)
    t = agentes.tarea("claude", "x", {"descripcion": "mover la caja al estante"}, _f("entorno_sala"), None)
    assert any(r["tipo"] == "no_chocar" for r in t["restricciones"])
    assert len(pedidos) == 2 and "falta la restricción no_chocar" in pedidos[1]
