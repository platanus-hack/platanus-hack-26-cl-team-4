"""Pasos 5 y 7 de la selección v3: una corrida hija por finalista y comparacion.json en la corrida padre.
Sin GPU ni servicios externos: API real, orquestador y sim runner simulado."""
from __future__ import annotations

import json
from datetime import datetime
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text

from viaz import db, monitor, orquestador
from viaz import almacen as alm
from viaz.api import create_app
from viaz.config import Config
from viaz.esquemas import validar

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "worker-gpu"))
import runner  # noqa: E402

FINALISTAS_DEL_CATALOGO = ["leapting-mmr", "relu-bison"]
ARTEFACTOS_DE_HOY = {
    "entorno.json", "escena.usd", "tarea.json", "requisitos.json", "encontrados.json", "seleccion.json", "robot.json",
    "ensamblaje.json", "robot_cfg.py", "clon.json", "robot.urdf", "validacion.json", "construccion.mp4",
    "resultado.json", "evaluacion.json", "entrenamiento_rapido.mp4", "video_info.json", "curva.json", "hitos.json",
    "monitoreo.jsonl", "video.mp4", "trayectoria.json",
}


def _puerto() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def arrancar(tmp_path, monkeypatch):
    monkeypatch.setenv("VIAZ_SIM_ITERACIONES", "120")
    monkeypatch.setenv("VIAZ_SIM_SEGUNDOS", "2")
    monkeypatch.setenv("VIAZ_SIM_SEGUNDOS_CLIP", "0.3")
    paradas: list = []

    def _arrancar(max_finalistas: int):
        puerto = _puerto()
        url = f"http://127.0.0.1:{puerto}"
        cfg = Config(db_url=f"sqlite:///{tmp_path / 'viaz.db'}", dir_local=tmp_path / "archivos", url_publica=url,
                     agentes="fijo", worker_token="t", admin_token="adm", espera_trabajo_s=120, flujo="rl",
                     horas_entrenamiento=1, monitor_s=0.6, episodios_evaluacion=100, max_finalistas=max_finalistas)
        servidor = uvicorn.Server(uvicorn.Config(create_app(cfg), host="127.0.0.1", port=puerto, log_level="warning"))
        threading.Thread(target=servidor.run, daemon=True).start()
        for _ in range(100):
            if servidor.started:
                break
            time.sleep(0.05)
        parar = threading.Event()
        eng, store = db.motor(cfg.db_url), alm.crear(cfg)

        def orq():
            while not parar.is_set():
                if not orquestador.procesar_una(cfg, eng, store):
                    time.sleep(0.1)

        def worker():
            s = requests.Session()
            while not parar.is_set():
                if not runner.ciclo(url, "t", "simulado", "", s, dir_pod=tmp_path / "pod"):
                    time.sleep(0.1)

        for f in (orq, worker):
            threading.Thread(target=f, daemon=True).start()
        paradas.append((parar, servidor))
        return url, eng, store

    yield _arrancar
    for parar, servidor in paradas:
        parar.set()
        servidor.should_exit = True


def _correr(url: str, segundos: float = 300) -> dict:
    pid = requests.post(f"{url}/proyectos", json={"nombre": "Parque de referencia"}, timeout=5).json()["id"]
    cid = requests.post(f"{url}/proyectos/{pid}/corridas", timeout=5).json()["corrida_id"]
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        c = requests.get(f"{url}/corridas/{cid}", timeout=5).json()
        if c["estado"] in ("listo", "error"):
            return c
        time.sleep(0.3)
    raise AssertionError(f"la corrida no terminó: {c}")


def _artefactos(c: dict) -> dict[str, str]:
    return {a: u for e in c["etapas"] for a, u in e["artefactos"].items()}


def _hijas(eng, padre_id: str) -> list[dict]:
    with eng.connect() as cx:
        return [dict(f) for f in cx.execute(select(db.corridas).where(db.corridas.c.padre_id == padre_id)
                                            .order_by(db.corridas.c.creado)).mappings()]


def _leer(store, cid: str, archivo: str):
    return json.loads(store.leer(alm.clave_corrida(cid, archivo)))


def _horas_entrenadas(eng, cid: str) -> list[float]:
    with eng.connect() as cx:
        return [p["horas"] for p in cx.execute(select(db.trabajos.c.parametros).where(
            db.trabajos.c.corrida_id == cid, db.trabajos.c.tipo == "entrenar")).scalars()]


def test_dos_finalistas_corren_en_hijas_y_el_padre_muestra_al_ganador(arrancar):
    url, eng, store = arrancar(3)
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    hijas = _hijas(eng, c["id"])
    assert len(hijas) == 2 and all(h["estado"] == "listo" for h in hijas)
    assert [_leer(store, h["id"], "robot.json")["id"] for h in hijas] == FINALISTAS_DEL_CATALOGO
    escena_padre = store.leer(alm.clave_corrida(c["id"], "escena.usd"))
    for h in hijas:
        assert store.leer(alm.clave_corrida(h["id"], "escena.usd")) == escena_padre
        assert _leer(store, h["id"], "tarea.json") == _leer(store, c["id"], "tarea.json")
        assert _horas_entrenadas(eng, h["id"]) == [1]
    with eng.connect() as cx:
        tipos_padre = set(cx.execute(select(db.trabajos.c.tipo).where(db.trabajos.c.corrida_id == c["id"])).scalars())
    assert tipos_padre == {"generar_escena"}

    a = _artefactos(c)
    comp = validar("comparacion", requests.get(a["comparacion.json"], timeout=5).json())
    assert {f["corrida_id"] for f in comp["ranking"]} == {h["id"] for h in hijas}
    ganadora = next(h for h in hijas if h["id"] == comp["ranking"][0]["corrida_id"])
    assert requests.get(a["robot.json"], timeout=5).json()["id"] == comp["ganador"]
    assert requests.get(a["resultado.json"], timeout=5).json() == _leer(store, ganadora["id"], "resultado.json")
    assert requests.get(a["clon.json"], timeout=5).json()["robot_id"] == comp["ganador"]
    assert ARTEFACTOS_DE_HOY <= set(a)
    assert any("semillas" in x for x in comp["advertencias"])

    api = requests.get(f"{url}/corridas/{c['id']}", timeout=5).json()
    assert api["padre_id"] is None
    assert [(h["robot_id"], h["estado"]) for h in api["hijas"]] == [(r, "listo") for r in FINALISTAS_DEL_CATALOGO]
    hija = requests.get(f"{url}/corridas/{hijas[0]['id']}", timeout=5).json()
    assert hija["padre_id"] == c["id"] and hija["hijas"] == []


def test_una_hija_que_falla_no_hace_fallar_al_padre(arrancar, monkeypatch):
    original = orquestador.construir_robot

    def falla_relu(c, cfg, robot, entorno, tarea):
        if robot["id"] == "relu-bison":
            raise orquestador.agentes.ErrorAgente("no se pudo construir un robot válido: prueba")
        return original(c, cfg, robot, entorno, tarea)

    monkeypatch.setattr(orquestador, "construir_robot", falla_relu)
    url, eng, store = arrancar(3)
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    hijas = {_leer(store, h["id"], "robot.json")["id"]: h for h in _hijas(eng, c["id"])}
    assert hijas["relu-bison"]["estado"] == "error" and "prueba" in hijas["relu-bison"]["error"]
    comp = _leer(store, c["id"], "comparacion.json")
    assert [f["id"] for f in comp["ranking"]] == ["leapting-mmr"]
    assert any("Bison" in x and hijas["relu-bison"]["id"] in x for x in comp["advertencias"])
    assert comp["ranking"][0]["nombre"].startswith("LEAPTING MMR")


def test_si_todas_las_hijas_fallan_el_padre_queda_en_error(arrancar, monkeypatch):
    def siempre_falla(c, cfg, robot, entorno, tarea):
        raise orquestador.agentes.ErrorAgente("no se pudo construir un robot válido: prueba")

    monkeypatch.setattr(orquestador, "construir_robot", siempre_falla)
    url, eng, _ = arrancar(3)
    c = _correr(url)
    assert c["estado"] == "error"
    assert "finalistas" in c["error"]
    assert all(h["estado"] == "error" for h in _hijas(eng, c["id"]))


def test_un_finalista_sigue_igual_que_hoy(arrancar):
    url, eng, _ = arrancar(1)
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    assert _hijas(eng, c["id"]) == []
    assert set(_artefactos(c)) == ARTEFACTOS_DE_HOY
    assert requests.get(f"{url}/corridas/{c['id']}", timeout=5).json()["hijas"] == []


def _cfg(tmp_path) -> Config:
    return Config(db_url=f"sqlite:///{tmp_path / 'v.db'}", dir_local=tmp_path / "a", worker_token="t",
                  admin_token="adm", flujo="rl", agentes="fijo")


def _insertar_corrida(eng, cid: str, estado: str, padre_id: str | None = None) -> None:
    with eng.begin() as cx:
        cx.execute(db.corridas.insert().values(id=cid, proyecto_id="p", estado=estado, etapas=[], padre_id=padre_id))


def test_procesar_una_nunca_toma_una_hija(tmp_path):
    cfg = _cfg(tmp_path)
    eng, store = db.motor(cfg.db_url), alm.crear(cfg)
    _insertar_corrida(eng, "padre", "entrenando")
    _insertar_corrida(eng, "hija", "en_cola", padre_id="padre")
    assert orquestador.procesar_una(cfg, eng, store) is False


def test_detener_el_padre_llega_al_entrenamiento_de_la_hija(tmp_path):
    cfg = _cfg(tmp_path)
    cli = TestClient(create_app(cfg))
    eng = db.motor(cfg.db_url)
    _insertar_corrida(eng, "padre", "entrenando")
    _insertar_corrida(eng, "hija", "entrenando", padre_id="padre")
    with eng.begin() as cx:
        cx.execute(db.trabajos.insert().values(id="t1", corrida_id="hija", tipo="entrenar", entradas=[], salidas=[]))
    assert cli.post("/corridas/padre/detener", headers={"Authorization": "Bearer adm"}).status_code == 200
    with eng.connect() as cx:
        assert cx.execute(select(db.trabajos.c.detener).where(db.trabajos.c.id == "t1")).scalar_one() is True


def test_la_migracion_agrega_padre_id_a_una_base_existente(tmp_path):
    url = f"sqlite:///{tmp_path / 'vieja.db'}"
    vieja = create_engine(url)
    with vieja.begin() as cx:
        cx.execute(text("CREATE TABLE corridas (id VARCHAR(32) PRIMARY KEY, proyecto_id VARCHAR(32) NOT NULL, "
                        "estado VARCHAR(32) NOT NULL, etapas JSON NOT NULL, error TEXT, creado TIMESTAMP NOT NULL, "
                        "actualizado TIMESTAMP NOT NULL)"))
        cx.execute(text("INSERT INTO corridas VALUES ('c1', 'p', 'listo', '[]', NULL, '2026-11-21', '2026-11-21')"))
    vieja.dispose()
    eng = db.motor(url)
    assert "padre_id" in {c["name"] for c in inspect(eng).get_columns("corridas")}
    with eng.connect() as cx:
        assert cx.execute(select(db.corridas.c.padre_id).where(db.corridas.c.id == "c1")).scalar_one() is None


def test_el_aviso_nombra_al_finalista():
    curva = [{"iteracion": i, "pasos": i, "tiempo_s": i * 60.0, "recompensa_media": 40 - i * 0.6, "tasa_exito": 0.5}
             for i in range(60)]
    ch = monitor.chequeo_reglas(curva, curva, [], 4)
    av = monitor.Avisador("", etiqueta="finalista 2 de 3: relu-bison")
    assert av.avisar(ch, 4)
    assert "finalista 2 de 3: relu-bison" in av.enviados[0].splitlines()[0]


def _padre_con_hijas(tmp_path, estados: dict[str, str]):
    cfg = _cfg(tmp_path)
    cli, eng, store = TestClient(create_app(cfg)), db.motor(cfg.db_url), alm.crear(cfg)
    _insertar_corrida(eng, "padre", "entrenando")
    for n, (robot_id, estado) in enumerate(estados.items()):
        with eng.begin() as cx:
            cx.execute(db.corridas.insert().values(id=f"h-{robot_id}", proyecto_id="p", estado=estado, etapas=[],
                                                   padre_id="padre", creado=datetime(2026, 11, 21, 12, n)))
            cx.execute(db.metricas.insert().values(trabajo_id="t", corrida_id=f"h-{robot_id}", iteracion=0,
                                                   datos={"iteracion": 0, "de": robot_id}))
        store.escribir(alm.clave_corrida(f"h-{robot_id}", "robot.json"), json.dumps({"id": robot_id}).encode())
    return cli, store


def _metricas(cli, cid: str = "padre") -> dict:
    r = cli.get(f"/corridas/{cid}/metricas")
    assert r.status_code == 200
    return r.json()


def test_las_metricas_del_padre_son_las_de_la_hija_que_entrena(tmp_path):
    cli, _ = _padre_con_hijas(tmp_path, {"a": "listo", "b": "entrenando", "c": "clonando"})
    assert _metricas(cli) == {"corrida_id": "padre", "hija_id": "h-b", "metricas": [{"iteracion": 0, "de": "b"}]}


def test_al_terminar_las_metricas_del_padre_son_las_de_la_ganadora(tmp_path):
    cli, store = _padre_con_hijas(tmp_path, {"a": "listo", "b": "listo"})
    store.escribir(alm.clave_corrida("padre", "robot.json"), json.dumps({"id": "b"}).encode())
    assert _metricas(cli)["hija_id"] == "h-b"


def test_sin_robot_json_en_el_padre_gana_la_primera_de_la_comparacion(tmp_path):
    cli, store = _padre_con_hijas(tmp_path, {"a": "listo", "b": "error"})
    store.escribir(alm.clave_corrida("padre", "comparacion.json"),
                   json.dumps({"ranking": [{"id": "a", "corrida_id": "h-a"}]}).encode())
    m = _metricas(cli)
    assert m["hija_id"] == "h-a" and m["metricas"] == [{"iteracion": 0, "de": "a"}]


def test_una_corrida_sin_hijas_da_sus_propias_metricas(tmp_path):
    cli, _ = _padre_con_hijas(tmp_path, {"a": "entrenando"})
    assert _metricas(cli, "h-a") == {"corrida_id": "h-a", "hija_id": None, "metricas": [{"iteracion": 0, "de": "a"}]}
