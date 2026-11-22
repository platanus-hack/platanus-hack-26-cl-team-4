"""Corrida.etapa: arma una lista nueva de etapas en vez de cambiar la que ya existe."""
from __future__ import annotations

import copy

from sqlalchemy import select

from viaz import almacen as alm
from viaz import db
from viaz.config import Config
from viaz.corrida import Corrida


def _corrida(tmp_path):
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'v.db'}", dir_local=tmp_path / "a")
    eng = db.motor(cfg.db_url)
    etapas = [{"nombre": e, "estado": "pendiente", "artefactos": []} for e in db.ETAPAS]
    with eng.begin() as cx:
        cx.execute(db.corridas.insert().values(id="c1", proyecto_id="p", estado="en_cola", etapas=etapas))
    with eng.connect() as cx:
        fila = dict(cx.execute(select(db.corridas).where(db.corridas.c.id == "c1")).mappings().first())
    return Corrida(cfg, eng, alm.crear(cfg), fila), eng


def test_etapa_no_cambia_la_lista_guardada_antes(tmp_path):
    c, _ = _corrida(tmp_path)
    antes = c.etapas
    copia = copy.deepcopy(antes)
    c.etapa("entorno", "en_curso")
    c.etapa("entorno", "listo", ["entorno.json"])
    assert antes == copia


def test_etapa_guarda_en_la_base_lo_mismo_que_hoy(tmp_path):
    c, eng = _corrida(tmp_path)
    c.etapa("entorno", "en_curso", estado_corrida="analizando_entorno")
    c.etapa("entorno", "listo", ["entorno.json", "escena.usd"])
    c.etapa("tarea", "en_curso")
    with eng.connect() as cx:
        fila = cx.execute(select(db.corridas.c.etapas, db.corridas.c.estado)
                          .where(db.corridas.c.id == "c1")).mappings().first()
    assert fila["estado"] == "analizando_entorno"
    assert fila["etapas"] == [
        {"nombre": "entorno", "estado": "listo", "artefactos": ["entorno.json", "escena.usd"]},
        {"nombre": "tarea", "estado": "en_curso", "artefactos": []},
        {"nombre": "robot", "estado": "pendiente", "artefactos": []},
        {"nombre": "clon", "estado": "pendiente", "artefactos": []},
        {"nombre": "inteligencia", "estado": "pendiente", "artefactos": []},
    ]
    assert c.etapa_actual == "tarea"
    assert c.etapas == fila["etapas"]
