"""Modelos comprobados (paso 6 de la selección v3, RF-CLO-10/11): clave, registro y reuso en construir_robot.

Sin GPU: una corrida falsa responde validar_robot según lo que pida cada test.
"""
from __future__ import annotations

import json
import logging

import pytest

from viaz import agentes, catalogo, modelos, orquestador
from viaz import almacen as alm
from viaz import robot_cfg as rc
from viaz.config import Config
from viaz.esquemas import validar

FIX = agentes.FIXTURES


def _fixtures() -> tuple[dict, dict, dict]:
    e = json.loads((FIX / "entorno.json").read_text(encoding="utf-8"))
    t = json.loads((FIX / "tarea.json").read_text(encoding="utf-8"))
    return e, t, agentes.seleccionar("fijo", "x", e, t, catalogo.cargar()).robots_por_puesto[0]


class CorridaFalsa:
    def __init__(self, store: alm.Almacen, cid: str, respuestas: list[bool] | None = None):
        self.store, self.id = store, cid
        self.respuestas = list(respuestas or [])
        self.validaciones: list[dict] = []

    def escribir(self, archivo, contenido):
        texto = json.dumps(contenido, ensure_ascii=False) if isinstance(contenido, dict) else contenido
        self.store.escribir(alm.clave_corrida(self.id, archivo), texto.encode("utf-8"))

    def leer_json(self, archivo):
        return json.loads(self.store.leer(alm.clave_corrida(self.id, archivo)))

    def existe(self, archivo):
        return self.store.existe(alm.clave_corrida(self.id, archivo))

    def trabajo_gpu(self, tipo, entradas, salidas, parametros=None, espera_s=None, al_esperar=None):
        assert tipo == "validar_robot"
        self.validaciones.append(parametros or {})
        ok = self.respuestas.pop(0) if self.respuestas else True
        self.escribir("validacion.json", {"ok": ok, "problemas": [] if ok else ["choca con la fila 2 en esta escena"]})
        return "t"


@pytest.fixture
def store(tmp_path):
    return alm.AlmacenLocal(tmp_path / "archivos", "http://x")


@pytest.fixture
def cfg(tmp_path):
    return Config(dir_local=tmp_path / "archivos", agentes="fijo", intentos_constructor=3)


def _sin_constructor(monkeypatch):
    def prohibido(*a, **k):
        raise AssertionError("no debía llamarse al agente constructor")
    monkeypatch.setattr(agentes, "constructor", prohibido)


def _construir(store, cfg, cid, robot, respuestas=None):
    e, t, _ = _fixtures()
    c = CorridaFalsa(store, cid, respuestas)
    orquestador.construir_robot(c, cfg, robot, e, t)
    return c, c.leer_json("clon.json")


def test_clave_estable_e_ignora_justificacion_y_alternativas():
    _, _, r = _fixtures()
    assets = rc.cargar_assets()
    k = modelos.clave(r, assets)
    assert k.startswith(f"{r['id']}-") and len(k) == len(r["id"]) + 1 + 12
    assert modelos.clave(r, assets) == k
    otro = {**r, "justificacion": "otro texto", "alternativas": [{"id": "x", "por_que_no": "y"}]}
    assert modelos.clave(otro, assets) == k


def test_clave_cambia_con_una_spec_o_un_asset():
    _, _, r = _fixtures()
    assets = rc.cargar_assets()
    k = modelos.clave(r, assets)
    assert modelos.clave({**r, "carga_util_kg": r["carga_util_kg"] + 1}, assets) != k
    brazos = {**assets["brazos"], "ur10": {**assets["brazos"]["ur10"], "alcance_m": 9.9}}
    assert modelos.clave(r, {**assets, "brazos": brazos}) != k


def test_clave_no_modifica_sus_entradas():
    _, _, r = _fixtures()
    antes = json.dumps(r, sort_keys=True)
    modelos.clave(r, rc.cargar_assets())
    assert json.dumps(r, sort_keys=True) == antes


def test_fidelidad_medido_con_fisica_y_generico_sin():
    _, _, r = _fixtures()
    assert r.get("fisica")
    sin = {k: v for k, v in r.items() if k != "fisica"}
    assert modelos.fidelidad(r) == "medido" and modelos.fidelidad(sin) == "generico"
    assets = rc.cargar_assets()
    ens = rc.ensamblaje_por_defecto(r, assets)
    assert validar("clon", rc.clon(ens, r, assets, 1))["fidelidad"] == "medido"
    assert validar("clon", rc.clon(ens, sin, assets, 1))["fidelidad"] == "generico"


def test_fidelidad_en_el_clon_del_planificador():
    _, _, r = _fixtures()
    assert agentes.clon(r)[0]["fidelidad"] == "medido"


def test_primera_corrida_registra_y_la_segunda_reusa(store, cfg, monkeypatch):
    _, _, r = _fixtures()
    c1, clon1 = _construir(store, cfg, "c1", r)
    assert clon1["construccion"]["metodo"] == "agente"
    k = modelos.clave(r, rc.cargar_assets())
    meta = json.loads(store.leer(modelos.clave_almacen(k, "modelo.json")))
    assert meta["clave"] == k and meta["robot_id"] == r["id"] and meta["corrida_id"] == "c1"
    assert meta["metodo"] == "agente" and meta["fecha"]

    _sin_constructor(monkeypatch)
    c2, clon2 = _construir(store, cfg, "c2", r)
    validar("clon", clon2)
    assert clon2["construccion"]["metodo"] == "comprobado" and clon2["validado_en_escena"] is True
    assert len(c2.validaciones) == 1
    assert c2.leer_json("ensamblaje.json") == c1.leer_json("ensamblaje.json")
    assert json.loads(store.leer(modelos.clave_almacen(k, "modelo.json")))["corrida_id"] == "c1"


def test_modelo_que_falla_en_la_nueva_escena_vuelve_al_agente(store, cfg, monkeypatch):
    _, _, r = _fixtures()
    _construir(store, cfg, "c1", r)
    vistos: list = []
    original = agentes.constructor

    def espia(modo, modelo, robot, entorno, tarea, assets, intento, problemas=None, previo=None):
        vistos.append(list(problemas or []))
        return original(modo, modelo, robot, entorno, tarea, assets, intento, problemas, previo)

    monkeypatch.setattr(agentes, "constructor", espia)
    c2, clon2 = _construir(store, cfg, "c2", r, respuestas=[False, True])
    assert clon2["construccion"]["metodo"] == "agente" and clon2["validado_en_escena"]
    assert len(c2.validaciones) == 2
    assert vistos and any("fila 2" in p for p in vistos[0])


def test_ficha_cambiada_no_reusa(store, cfg, monkeypatch):
    _, _, r = _fixtures()
    _construir(store, cfg, "c1", r)
    llamadas: list = []
    original = agentes.constructor
    monkeypatch.setattr(agentes, "constructor", lambda *a, **k: llamadas.append(1) or original(*a, **k))
    _, clon = _construir(store, cfg, "c2", {**r, "velocidad_base_m_s": (r.get("velocidad_base_m_s") or 1) + 0.1})
    assert llamadas and clon["construccion"]["metodo"] == "agente"


def test_archivo_guardado_invalido_se_ignora(store, cfg, monkeypatch, caplog):
    _, _, r = _fixtures()
    k = modelos.clave(r, rc.cargar_assets())
    store.escribir(modelos.clave_almacen(k, "ensamblaje.json"), b'{"version": 1, "robot_id": "x"}')
    llamadas: list = []
    original = agentes.constructor
    monkeypatch.setattr(agentes, "constructor", lambda *a, **k: llamadas.append(1) or original(*a, **k))
    with caplog.at_level(logging.WARNING, logger="viaz.modelos"):
        _, clon = _construir(store, cfg, "c1", r)
    assert llamadas and clon["construccion"]["metodo"] == "agente"
    assert any("ignoro" in m for m in caplog.messages)


def test_json_roto_guardado_se_ignora(store):
    store.escribir(modelos.clave_almacen("r-000000000000", "ensamblaje.json"), b"{no es json")
    assert modelos.buscar(store, "r-000000000000") is None


def test_respaldo_determinista_no_se_registra(store, cfg, monkeypatch):
    _, _, r = _fixtures()

    def roto(*a, **k):
        raise agentes.ErrorAgente("sin respuesta")

    monkeypatch.setattr(agentes, "constructor", roto)
    _, clon = _construir(store, cfg, "c1", r)
    assert clon["construccion"]["metodo"] == "determinista"
    k = modelos.clave(r, rc.cargar_assets())
    assert not store.existe(modelos.clave_almacen(k, "ensamblaje.json"))
    assert modelos.buscar(store, k) is None


class AlmacenQueFallaEnModelos(alm.AlmacenLocal):
    def escribir(self, clave, datos, tipo="application/octet-stream"):
        if clave.startswith("modelos/"):
            raise OSError("R2 no responde")
        super().escribir(clave, datos, tipo)


def test_error_al_guardar_no_hace_fallar_la_corrida(tmp_path, cfg, caplog):
    _, _, r = _fixtures()
    store = AlmacenQueFallaEnModelos(tmp_path / "archivos", "http://x")
    with caplog.at_level(logging.WARNING, logger="viaz.modelos"):
        _, clon = _construir(store, cfg, "c1", r)
    assert clon["construccion"]["metodo"] == "agente" and clon["validado_en_escena"]
    assert any("R2 no responde" in m for m in caplog.messages)
