"""Flujo del demo con RL (entorno RL simulado), latido, monitor y agente constructor. Sin GPU ni servicios externos."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn
from sqlalchemy import select, update

from viaz import agentes, catalogo, db, monitor, orquestador
from viaz import almacen as alm
from viaz import robot_cfg as rc
from viaz.api import create_app
from viaz.config import Config
from viaz.esquemas import validar

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "worker-gpu"))
import runner  # noqa: E402

FIX = agentes.FIXTURES


def _puerto() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def sistema(tmp_path, monkeypatch):
    """API + orquestador (flujo rl) + runner simulado, cada uno en su hilo."""
    monkeypatch.setenv("VIAZ_SIM_ITERACIONES", "120")
    monkeypatch.setenv("VIAZ_SIM_SEGUNDOS", "3")
    monkeypatch.setenv("VIAZ_SIM_SEGUNDOS_CLIP", "0.4")
    puerto = _puerto()
    url = f"http://127.0.0.1:{puerto}"
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'viaz.db'}", dir_local=tmp_path / "archivos", url_publica=url,
                 agentes="fijo", worker_token="t", admin_token="adm", espera_trabajo_s=120, flujo="rl",
                 horas_entrenamiento=1, monitor_s=0.6, episodios_evaluacion=100)
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
    yield url, eng, store
    parar.set()
    servidor.should_exit = True


def _correr(url: str, segundos: float = 150) -> dict:
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


def test_flujo_rl_completo(sistema):
    url, eng, _ = sistema
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    a = _artefactos(c)
    for n in ("entorno", "tarea", "robot", "clon", "resultado", "evaluacion", "ensamblaje", "hitos", "curva"):
        validar(n, requests.get(a[f"{n}.json"], timeout=5).json())
    clon = requests.get(a["clon.json"], timeout=5).json()
    assert clon["validado_en_escena"] and clon["construccion"]["metodo"] == "agente"
    assert "PARAMETROS" in requests.get(a["robot_cfg.py"], timeout=5).text
    r = requests.get(a["resultado.json"], timeout=5).json()
    assert r["metodo"] == "rl" and r["fuente"] == "simulado"
    assert r["evaluacion"]["episodios"] == 100 and len(r["evaluacion"]["tolerancias"]) == 2
    assert r["metricas"]["tasa_exito"] >= 0.9
    assert r["entrenamiento"]["factor_video"] and r["entrenamiento"]["iteraciones"] > 0
    for v in ("entrenamiento_rapido.mp4", "video.mp4"):
        assert requests.get(a[v], timeout=10).content[4:8] == b"ftyp", v  # es un mp4
    chequeos = [json.loads(x) for x in requests.get(a["monitoreo.jsonl"], timeout=5).text.splitlines()]
    assert chequeos and chequeos[-1]["hito"] == "fin"
    for ch in chequeos:
        validar("monitoreo", ch)
    with eng.connect() as cx:
        assert cx.execute(select(db.metricas.c.id)).first() is not None  # llegaron métricas por latido
    m = requests.get(f"{url}/corridas/{c['id']}/metricas", timeout=5).json()["metricas"]
    assert m[0]["iteracion"] == 0


def test_nan_detiene_el_entrenamiento(sistema, monkeypatch):
    monkeypatch.setenv("VIAZ_SIM_NAN_EN", "20")
    monkeypatch.setenv("VIAZ_SIM_SEGUNDOS", "12")
    url, _, store = sistema
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    ck = json.loads(store.leer(alm.clave_corrida(c["id"], "checkpoints.json")))
    assert ck["detenido"] and ck["ultima_iteracion"] < 119


def test_latido_y_trabajos_vencidos(tmp_path):
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'v.db'}", dir_local=tmp_path / "a", worker_token="t", admin_token="adm")
    from fastapi.testclient import TestClient
    cli = TestClient(create_app(cfg))
    eng = db.motor(cfg.db_url)
    auth = {"Authorization": "Bearer t"}
    with eng.begin() as cx:
        cx.execute(db.trabajos.insert().values(id="t1", corrida_id="c1", tipo="entrenar", entradas=[], salidas=[]))
    assert cli.post("/worker/trabajos/t1/latido", headers=auth, json={"metricas": []}).status_code == 409
    assert cli.post("/worker/trabajos/tomar", headers=auth).json()["trabajo_id"] == "t1"
    r = cli.post("/worker/trabajos/t1/latido", headers=auth, json={"metricas": [{"iteracion": 0, "tasa_exito": 0.1}]})
    assert r.json() == {"accion": "seguir", "nan": False}
    # un trabajo tomado hace 2 h pero con latido reciente NO vuelve a la cola
    from datetime import timedelta
    with eng.begin() as cx:
        cx.execute(update(db.trabajos).values(tomado_en=db.ahora() - timedelta(hours=2)))
    assert db.devolver_trabajos_vencidos(eng) == 0
    with eng.begin() as cx:
        cx.execute(update(db.trabajos).values(latido_en=db.ahora() - timedelta(hours=1)))
    assert db.devolver_trabajos_vencidos(eng) == 1
    # detener: solo el equipo
    cli.post("/worker/trabajos/tomar", headers=auth)
    assert cli.post("/corridas/c1/detener", headers=auth).status_code == 401
    assert cli.post("/corridas/c1/detener", headers={"Authorization": "Bearer adm"}).status_code == 200
    assert cli.post("/worker/trabajos/t1/latido", headers=auth, json={"metricas": []}).json()["accion"] == "detener"


def test_latido_con_nan_pide_detener(tmp_path):
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'v.db'}", dir_local=tmp_path / "a", worker_token="t")
    from fastapi.testclient import TestClient
    cli = TestClient(create_app(cfg))
    eng = db.motor(cfg.db_url)
    with eng.begin() as cx:
        cx.execute(db.trabajos.insert().values(id="t1", corrida_id="c1", tipo="entrenar", entradas=[], salidas=[]))
    auth = {"Authorization": "Bearer t", "Content-Type": "application/json"}
    cli.post("/worker/trabajos/tomar", headers=auth)
    r = cli.post("/worker/trabajos/t1/latido", headers=auth,
                 content='{"metricas": [{"iteracion": 3, "recompensa_media": NaN, "tasa_exito": 0.2}]}')
    assert r.json() == {"accion": "detener", "nan": True}
    with eng.connect() as cx:
        datos = cx.execute(select(db.metricas.c.datos)).scalar_one()
    assert datos["recompensa_media"] is None and datos["nan"] is True


def _fixtures():
    e = json.loads((FIX / "entorno.json").read_text(encoding="utf-8"))
    t = json.loads((FIX / "tarea.json").read_text(encoding="utf-8"))
    return e, t, agentes.robot("fijo", "x", e, t, catalogo.cargar())


def test_reglas_del_constructor():
    e, t, r = _fixtures()
    assets = rc.cargar_assets()
    ens = rc.ensamblaje_por_defecto(r, assets)
    validar("ensamblaje", ens)
    assert rc.problemas(ens, r, assets, agentes.alcance_necesario(e)) == []
    trampa = {**ens, "carga_util_kg": 5, "brazo": {**ens["brazo"], "esfuerzo_max_nm": 10}}
    p = rc.problemas(trampa, r, assets, agentes.alcance_necesario(e))
    assert any("carga_util_kg" in x for x in p) and any("esfuerzo" in x for x in p)
    assert any("catálogo" in x for x in rc.problemas({**ens, "brazo": {**ens["brazo"], "asset": "kuka"}}, r, assets, 1))
    ns: dict = {}
    exec(rc.generar(ens, assets), ns)
    assert ns["PARAMETROS"]["alcance_m"] == pytest.approx(r["alcance_m"], rel=0.05)
    validar("clon", rc.clon(ens, r, assets, 1))


def test_monitor_clasifica_curvas():
    def curva(f, n=60):
        return [{"iteracion": i, "pasos": i, "tiempo_s": i * 60.0, "recompensa_media": f(i)[0], "tasa_exito": f(i)[1]} for i in range(n)]
    sube = curva(lambda i: (5 + i * 0.5, min(0.95, i / 80)))
    plana = curva(lambda i: (20.0, 0.3))
    cae = curva(lambda i: (40 - i * 0.6, 0.5))
    assert monitor.chequeo_reglas(sube, sube, [], 4)["estado"] == "mejorando"
    assert monitor.chequeo_reglas(cae, cae, [], 4)["estado"] == "divergiendo"
    previos: list = []
    for _ in range(3):
        previos.append(monitor.chequeo_reglas(plana, plana, previos, 4))
    assert [p["recomendacion"] for p in previos] == ["seguir", "seguir", "ajustar"]
    h = monitor.hitos(sube)
    assert h["primer_exito"] == 4 and h["exito_50"] == 40 and h["umbral_alcanzado"] is None
    av = monitor.Avisador("")
    ch = monitor.chequeo_reglas(cae, cae, [], 4)
    assert av.avisar(ch, 4) and not av.avisar(ch, 4)  # 1 aviso por tipo cada 30 min
    assert av.enviados[0].startswith("🔴")


def test_constructor_reintenta_y_usa_respaldo(sistema, monkeypatch):
    """Intento 1 con carga falsa → el agente recibe los problemas. Si nunca lo logra, se usa el ensamblaje por defecto."""
    url, _, store = sistema
    vistos: list = []
    original = agentes.constructor

    def agente_torpe(modo, modelo, robot, entorno, tarea, assets, intento, problemas=None, previo=None):
        vistos.append(list(problemas or []))
        ens = original(modo, modelo, robot, entorno, tarea, assets, intento, problemas, previo)
        return {**ens, "carga_util_kg": 1}  # siempre miente sobre la carga útil

    monkeypatch.setattr(agentes, "constructor", agente_torpe)
    c = _correr(url)
    assert c["estado"] == "listo", c["error"]
    clon = json.loads(store.leer(alm.clave_corrida(c["id"], "clon.json")))
    assert clon["construccion"]["metodo"] == "determinista"
    assert len(vistos) == 3 and vistos[0] == [] and any("carga_util_kg" in p for p in vistos[1])
