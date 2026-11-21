"""Calidad del agente Tarea: reglas 2 a 6 de docs/agentes/tarea.md §8.1 y reintentos (sin llamar a la API)."""
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

OBLIGATORIAS = ["no chocar con las estructuras", "panel horizontal durante el traslado"]


def _entorno(largo_m: float | None = None) -> dict:
    e = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    if largo_m is not None:
        e["filas"]["largo_m"] = largo_m
    return e


def _tarea(paneles=5, ciclo_s=60, pila=5, restricciones=None) -> dict:
    return {"version": 1, "tarea": "instalar_panel",
            "descripcion": "Tomar un panel de la pila del robot y dejarlo sobre el tubo de torsión de la fila 1",
            "pila_paneles": {"en_robot": True, "cantidad": pila},
            "objetivo": {"paneles": paneles, "ciclo_s": ciclo_s},
            "restricciones": list(OBLIGATORIAS) if restricciones is None else restricciones}


def test_misma_geometria_que_el_plan():
    assert (agentes.INICIO_FILA_M, agentes.HOLGURA_PANEL_M) == (plan.INICIO_X, plan.HOLGURA_SLOT)
    for largo in (5, 7, 30, 500):
        assert agentes.paneles_que_caben(_entorno(largo)) == plan.caben(_entorno(largo))


def test_fixture_cumple_el_contrato():
    t = json.loads((agentes.FIXTURES / "tarea.json").read_text(encoding="utf-8"))
    assert agentes.problemas_tarea(t, _entorno()) == []
    assert agentes.tarea("fijo", "x", {"descripcion": ""}, _entorno(), None)["objetivo"]["paneles"] == 5


# Salidas esperadas de los casos C1 a C5 del contrato (§8.5): deben cumplir las reglas.
@pytest.mark.parametrize("caso,largo,paneles,ciclo,pila", [
    ("C1", None, 5, 60, 5), ("C2", None, 8, 45, 8), ("C3", None, 5, 120, 5), ("C4", None, 5, 30, 5), ("C5", 7, 4, 60, 4),
])
def test_casos_del_contrato_cumplen(caso, largo, paneles, ciclo, pila):
    assert agentes.problemas_tarea(_tarea(paneles, ciclo, pila), _entorno(largo)) == [], caso


@pytest.mark.parametrize("tarea,regla", [
    (_tarea(paneles=3, ciclo_s=150, pila=3), "regla 2"),   # 3 × 150 s = 450 s: solo falla el ritmo
    (_tarea(ciclo_s=10), "regla 2"),
    (_tarea(paneles=2, pila=2), "regla 3"),
    (_tarea(paneles=6, pila=5), "regla 3"),
    (_tarea(paneles=10, ciclo_s=120, pila=10), "regla 5"),
    (_tarea(restricciones=["no chocar con las estructuras"]), "regla 6"),
    (_tarea(restricciones=OBLIGATORIAS + ["a", "b", "c", "d"]), "regla 6"),
    (_tarea(restricciones=OBLIGATORIAS + ["No chocar con las estructuras."]), "regla 6"),
])
def test_detecta_cada_regla(tarea, regla):
    problemas = agentes.problemas_tarea(tarea, _entorno())
    assert problemas and all(p.startswith(regla) for p in problemas), problemas


def test_regla_4_usa_el_largo_de_la_fila():
    p = agentes.problemas_tarea(_tarea(), _entorno(largo_m=7))   # caben 4
    assert p == ["regla 4: objetivo.paneles es 5, pero en una fila caben 4"]


def test_restricciones_sin_contar_mayusculas_ni_punto():
    t = _tarea(restricciones=["No chocar con las estructuras.", "  Panel horizontal  durante el traslado "])
    assert agentes.problemas_tarea(t, _entorno()) == []


def test_revisar_rechaza_un_tarea_escrito_a_mano_que_no_cumple():
    with pytest.raises(agentes.ErrorAgente, match="regla 5"):
        agentes.revisar_tarea(_tarea(paneles=10, ciclo_s=120, pila=10), _entorno())


def _falso_modelo(monkeypatch, respuestas: list[dict]) -> list[str]:
    """Reemplaza la API: devuelve las respuestas en orden y guarda el texto de cada pedido."""
    pedidos: list[str] = []

    def pedir_json(*, contenido, **_):
        pedidos.append(contenido[-1]["text"])
        r = copy.deepcopy(respuestas[len(pedidos) - 1])
        r.pop("version", None)
        return r

    monkeypatch.setattr(agentes, "pedir_json", pedir_json)
    return pedidos


def test_reintenta_con_los_problemas_y_acepta_la_correccion(monkeypatch):
    mala, buena = _tarea(paneles=10, ciclo_s=120, pila=10), _tarea(paneles=5, ciclo_s=120, pila=5)
    pedidos = _falso_modelo(monkeypatch, [mala, buena])
    t = agentes.tarea("claude", "x", {"descripcion": "20 paneles, 2 minutos por panel"}, _entorno(), None)
    assert t["objetivo"] == {"paneles": 5, "ciclo_s": 120} and t["version"] == 1
    assert len(pedidos) == 2
    assert "Intento 1 de 3" in pedidos[0] and "Tu respuesta anterior" not in pedidos[0]
    assert "Intento 2 de 3" in pedidos[1] and "Tu respuesta anterior" in pedidos[1] and "regla 5" in pedidos[1]


def test_falla_despues_de_3_intentos(monkeypatch):
    mala = _tarea(ciclo_s=200)
    pedidos = _falso_modelo(monkeypatch, [mala, mala, mala])
    with pytest.raises(agentes.ErrorAgente, match="3 intentos.*regla 2"):
        agentes.tarea("claude", "x", {"descripcion": ""}, _entorno(), None)
    assert len(pedidos) == 3
