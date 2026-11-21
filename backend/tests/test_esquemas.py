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


# ---------- Entorno genérico (cualquier espacio, no solo parque solar) ----------

def _fixture(nombre):
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def test_entorno_generico_cumple_el_contrato_sin_perfil_solar():
    sala = validar("entorno", _fixture("entorno_sala"))
    assert sala["tipo"] == "sala" and "filas" not in sala


def test_perfil_solar_es_obligatorio_solo_en_parque_solar():
    solar = _fixture("entorno")
    del solar["panel"]
    with pytest.raises(ErrorEsquema):
        validar("entorno", solar)
    sala = _fixture("entorno_sala")
    sala["filas"] = _fixture("entorno")["filas"]
    with pytest.raises(ErrorEsquema):
        validar("entorno", sala)


def test_normalizar_entorno_quita_perfiles_nulos_y_arma_confianza():
    resp = {k: v for k, v in _fixture("entorno_sala").items()
            if k not in ("version", "videos", "escena_usd", "fondo_reconstruido_usd")}
    resp.update(filas=None, estructura=None, panel=None,
                confianza=[{"campo": "espacio.largo_m", "valor": 0.8}])
    datos = agentes.normalizar_entorno(resp)
    assert not {"filas", "estructura", "panel"} & set(datos)
    assert datos["confianza"] == {"espacio.largo_m": 0.8}


def test_escena_generica_tiene_paredes_y_elementos():
    sala = _fixture("entorno_sala")
    usda = generar_escena.escena_usda(sala)
    assert usda.count('"Pared_') == 4
    solidos = [el for el in sala["elementos"] if el["categoria"] != "abertura"]
    assert usda.count('"E0') == len(solidos)
    assert "def Cylinder" in usda
    movibles = [el for el in solidos if not el["fijo"] and el["masa_kg"]]
    assert usda.count("physics:mass") == len(movibles)
    assert "_Tubo" not in usda


def test_medidas_solares_no_se_aplican_a_otro_tipo():
    medidas = {"version": 1, "disponible": True, "fuente": "x", "frames": 1, "avisos": [],
               "campos": {"filas.cantidad": {"valor": 4, "error": 0, "confianza": 0.9, "metodo": "m", "muestras": 1}}}
    sala = agentes.aplicar_medidas(_fixture("entorno_sala"), medidas)
    assert "filas" not in sala and "mediciones" not in sala
    validar("entorno", sala)


def test_orquestador_corta_tipos_sin_pipeline():
    from viaz import orquestador
    orquestador.exigir_pipeline(_fixture("entorno"))
    with pytest.raises(agentes.ErrorAgente, match="sala"):
        orquestador.exigir_pipeline(_fixture("entorno_sala"))
