"""Agente Entorno con medidas (medidas_entorno.json): lo medido manda y el agente solo lo cambia con una razón."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from viaz import agentes
from viaz.esquemas import para_api, validar

RAIZ = Path(__file__).resolve().parents[2]
PROYECTO = {"nombre": "Parque de prueba", "descripcion": "", "videos": ["proyectos/p1/videos/recorrido.mp4"]}


def _campo(valor, error, confianza, metodo="nube_metrica"):
    return {"valor": valor, "error": error, "confianza": confianza, "metodo": metodo, "muestras": 3}


@pytest.fixture
def medidas():
    return validar("medidas_entorno", {
        "version": 1, "disponible": True, "fuente": "map-anything-apache+sam3", "frames": 32, "segundos": 41.0,
        "campos": {
            "filas.cantidad": _campo(4, 0.0, 0.95),
            "filas.separacion_m": _campo(5.2, 0.12, 0.75),
            "filas.largo_m": _campo(24.0, 2.4, 0.55),
            "estructura.tipo": _campo("tracker_1_eje", 0.05, 0.93),
            "estructura.altura_m": _campo(1.32, 0.05, 0.7),
            "estructura.inclinacion_grados": _campo(0.4, 1.0, 0.78),
            "panel.largo_m": _campo(2.28, 0.04, 0.7),
            "panel.ancho_m": _campo(1.13, 0.03, 0.65),
            "terreno.pendiente_grados": _campo(6.0, 4.0, 0.1),
        },
        "avisos": ["SAM 3 no cargó: se mide solo con la nube"],
    })


def test_modo_fijo_usa_lo_medido(medidas):
    e = agentes.entorno("fijo", "x", PROYECTO, None, medidas)
    assert e["filas"]["cantidad"] == 4 and isinstance(e["filas"]["cantidad"], int)
    assert e["filas"]["separacion_m"] == 5.2
    assert e["estructura"]["altura_m"] == 1.32
    assert e["panel"]["largo_m"] == 2.28
    assert e["confianza"]["filas.separacion_m"] == 0.75
    # La pendiente medida tiene confianza 0,1: no manda, queda la del fixture.
    assert e["terreno"]["pendiente_grados"] == 0
    assert "terreno.pendiente_grados" not in e["mediciones"]["medidos"]
    assert e["mediciones"]["fuente"] == "map-anything-apache+sam3"
    assert e["mediciones"]["avisos"] == medidas["avisos"]


def test_sin_medidas_limita_la_confianza():
    e = agentes.entorno("fijo", "x", PROYECTO, None, None)
    assert "mediciones" not in e
    assert max(e["confianza"].values()) <= agentes.CONFIANZA_MAX_ESTIMADA


def test_medicion_fallida_sigue_sin_medidas():
    fallida = {"version": 1, "disponible": False, "fuente": "medir_entorno", "frames": 0, "campos": {}, "avisos": [],
               "error": "sin GPU"}
    e = agentes.entorno("fijo", "x", PROYECTO, None, fallida)
    assert "mediciones" not in e
    assert "La medición 3D falló: sin GPU" in agentes.texto_entorno(PROYECTO, fallida)


def _respuesta_agente(fijo: dict, **cambios) -> dict:
    """Lo que devolvería Claude: el entorno del fixture con cambios, confianza como lista y ajustes."""
    r = {k: copy.deepcopy(v) for k, v in fijo.items() if k not in ("version", "videos", "escena_usd", "fondo_reconstruido_usd")}
    r["terreno"].pop("friccion", None)
    for campo, valor in cambios.items():
        if campo == "ajustes":
            continue
        a, b = campo.split("__")
        r[a][b] = valor
    r["confianza"] = [{"campo": k, "valor": 0.6} for k in ("filas.separacion_m", "terreno.suelo", "panel.peso_kg")]
    r["ajustes"] = cambios.get("ajustes", [])
    return r


def test_cambio_sin_razon_se_descarta(monkeypatch, medidas):
    fijo = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(agentes, "pedir_json", lambda **kw: _respuesta_agente(fijo, filas__separacion_m=7.0))
    e = agentes.entorno("claude", "x", PROYECTO, [{"type": "text", "text": "frame"}], medidas, b"png")
    assert e["filas"]["separacion_m"] == 5.2
    assert any("filas.separacion_m" in a and "sin razón" in a for a in e["mediciones"]["avisos"])
    assert e["mediciones"]["ajustes"] == []


def test_cambio_con_razon_se_acepta(monkeypatch, medidas):
    fijo = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    razon = "la vista cenital muestra una cuarta línea sobre el borde del video que no es una fila"
    monkeypatch.setattr(agentes, "pedir_json", lambda **kw: _respuesta_agente(
        fijo, filas__cantidad=3, ajustes=[{"campo": "filas.cantidad", "razon": razon}]))
    e = agentes.entorno("claude", "x", PROYECTO, [{"type": "text", "text": "frame"}], medidas, b"png")
    assert e["filas"]["cantidad"] == 3
    assert e["mediciones"]["ajustes"] == [{"campo": "filas.cantidad", "medido": 4, "final": 3, "razon": razon}]
    assert e["confianza"]["filas.cantidad"] <= agentes.CONFIANZA_MAX_ESTIMADA
    # Lo demás medido sigue mandando.
    assert e["estructura"]["altura_m"] == 1.32


def test_el_agente_recibe_medidas_y_vista(monkeypatch, medidas):
    fijo = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    visto = {}

    def falso(**kw):
        visto.update(kw)
        return _respuesta_agente(fijo)

    monkeypatch.setattr(agentes, "pedir_json", falso)
    agentes.entorno("claude", "x", PROYECTO, [{"type": "text", "text": "frame"}], medidas, b"\x89PNG")
    tipos = [b["type"] for b in visto["contenido"]]
    assert tipos.count("image") == 1 and visto["contenido"][1]["source"]["media_type"] == "image/png"
    assert "medidas_entorno.json" in visto["contenido"][-1]["text"]
    assert "ajustes" in visto["esquema"]["required"]


def test_esquema_del_agente_sirve_para_la_api():
    esq = agentes.esquema_agente_entorno()
    assert "mediciones" not in esq["properties"]
    para_api(esq)   # no debe fallar


def test_runner_simulado_no_mide(tmp_path):
    sys.path.insert(0, str(RAIZ / "worker-gpu"))
    import runner

    ctx = runner.Contexto(api="", token="", modo="simulado", isaac_python="", sesion=None)
    runner.ejecutar("medir_entorno", tmp_path, "simulado", "", ctx)
    m = validar("medidas_entorno", json.loads((tmp_path / "medidas_entorno.json").read_text(encoding="utf-8")))
    assert m["disponible"] is False
