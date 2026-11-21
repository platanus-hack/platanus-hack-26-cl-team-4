"""Contrato y esquemas para la API de Claude (sin llamar a la API)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from viaz import agentes, catalogo, urdf
from viaz.esquemas import NOMBRES, ErrorEsquema, esquema, para_api, sin_campos, validar

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import generar_escena  # noqa: E402
import plan  # noqa: E402

PROHIBIDAS = {"minimum", "maximum", "minItems", "maxItems", "pattern", "const", "$schema"}


def _objetos(n):
    if isinstance(n, dict):
        if n.get("type") == "object":
            yield n
        for v in n.values():
            yield from _objetos(v)
    elif isinstance(n, list):
        for v in n:
            yield from _objetos(v)


def _claves(n):
    if isinstance(n, dict):
        for k, v in n.items():
            yield k
            yield from _claves(v)
    elif isinstance(n, list):
        for v in n:
            yield from _claves(v)


@pytest.mark.parametrize("esq", [
    agentes.esquema_agente_entorno(),
    sin_campos(esquema("tarea"), ["version"]),
], ids=["entorno", "tarea"])
def test_esquemas_de_agentes_sirven_para_structured_outputs(esq):
    api = para_api(esq)
    assert not PROHIBIDAS & set(_claves(api))
    for obj in _objetos(api):
        assert obj.get("additionalProperties") is False, obj
        assert set(obj.get("required", [])) == set(obj.get("properties", {})), obj


def test_fixtures_y_catalogo_cumplen_el_contrato():
    for n in ("entorno", "tarea"):
        validar(n, json.loads((agentes.FIXTURES / f"{n}.json").read_text(encoding="utf-8")))
    robots = catalogo.cargar()
    assert "viaz-instalador-ficticio" in robots
    assert all(r["ficticio"] or r["fuente"]["url"] for r in robots.values())


def test_validar_rechaza_datos_fuera_de_contrato():
    with pytest.raises(ErrorEsquema):
        validar("tarea", {"version": 1})
    assert {"entorno", "tarea", "robot", "clon", "resultado", "trayectoria"} <= set(NOMBRES)
    for n in NOMBRES:
        esquema(n)  # todos los esquemas cargan


def test_robot_fijo_toma_las_specs_del_catalogo():
    e = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    t = json.loads((agentes.FIXTURES / "tarea.json").read_text(encoding="utf-8"))
    r = agentes.robot("fijo", "x", e, t, catalogo.cargar())
    assert r["carga_util_kg"] == catalogo.cargar()[r["id"]]["carga_util_kg"]


def test_plan_llega_a_la_estructura_y_a_la_pila():
    e = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    t = json.loads((agentes.FIXTURES / "tarea.json").read_text(encoding="utf-8"))
    clon, texto_urdf = agentes.clon(agentes.robot("fijo", "x", e, t, catalogo.cargar()))
    assert plan.validar(e, t, clon)["ok"]
    tray = plan.generar(e, t, clon)
    validar("trayectoria", tray)
    assert len(tray["frames"]) > 100
    for j in urdf.ARTICULACIONES:
        assert f'joint name="{j}"' in texto_urdf


def test_escena_tiene_una_fila_por_entorno():
    e = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    usda = generar_escena.escena_usda(e)
    assert usda.startswith("#usda 1.0")
    assert usda.count('_Tubo"') == e["filas"]["cantidad"]
