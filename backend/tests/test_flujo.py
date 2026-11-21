"""Flujo de punta a punta sin servicios externos: API real (uvicorn), orquestador y sim runner simulado."""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn

from viaz import almacen as alm
from viaz import db, orquestador
from viaz.api import create_app
from viaz.config import Config
from viaz.esquemas import validar

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "worker-gpu"))
import runner  # noqa: E402


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def entorno_local(tmp_path):
    puerto = _puerto_libre()
    url = f"http://127.0.0.1:{puerto}"
    cfg = Config(db_url=f"sqlite:///{tmp_path / 'viaz.db'}", dir_local=tmp_path / "archivos", url_publica=url,
                 agentes="fijo", worker_token="t", espera_trabajo_s=60, flujo="planificador")
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
    yield url, store
    parar.set()
    servidor.should_exit = True


def _esperar(url: str, cid: str, segundos: float = 60) -> dict:
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        c = requests.get(f"{url}/corridas/{cid}", timeout=5).json()
        if c["estado"] in ("listo", "error"):
            return c
        time.sleep(0.2)
    raise AssertionError(f"la corrida no terminó: {c}")


def test_flujo_completo(entorno_local):
    url, _ = entorno_local
    p = requests.post(f"{url}/proyectos", json={"nombre": "Parque de prueba", "videos": ["planta 1.mp4"]}, timeout=5)
    assert p.status_code == 201, p.text
    proyecto = p.json()
    assert proyecto["subida"][0]["archivo"] == "planta-1.mp4"
    assert requests.put(proyecto["subida"][0]["url_firmada"], data=b"no-es-un-video", timeout=5).status_code == 204

    cid = requests.post(f"{url}/proyectos/{proyecto['id']}/corridas", timeout=5).json()["corrida_id"]
    c = _esperar(url, cid)
    assert c["estado"] == "listo", c["error"]
    assert [e["estado"] for e in c["etapas"]] == ["listo"] * 5

    artefactos = {a: u for e in c["etapas"] for a, u in e["artefactos"].items()}
    for nombre in ("entorno", "tarea", "robot", "clon", "resultado", "trayectoria"):
        validar(nombre, requests.get(artefactos[f"{nombre}.json"], timeout=5).json())
    assert requests.get(artefactos["escena.usd"], timeout=5).text.startswith("#usda 1.0")
    assert "<robot" in requests.get(artefactos["robot.urdf"], timeout=5).text

    clon = requests.get(artefactos["clon.json"], timeout=5).json()
    assert clon["validado_en_escena"] is True
    resultado = requests.get(artefactos["resultado.json"], timeout=5).json()
    assert resultado["fuente"] == "simulado"
    assert resultado["metricas"]["paneles_instalados"] == 5
    tray = requests.get(artefactos["trayectoria.json"], timeout=5).json()
    assert tray["frames"][-1]["instalados"] == [0, 1, 2, 3, 4]


def test_worker_rechaza_token_malo(entorno_local):
    url, _ = entorno_local
    r = requests.post(f"{url}/worker/trabajos/tomar", headers={"Authorization": "Bearer otro"}, timeout=5)
    assert r.status_code == 401


def test_corrida_falla_si_el_robot_no_alcanza(entorno_local, monkeypatch):
    """Un clon que no llega a la estructura deja la corrida en error con el motivo."""
    import viaz.urdf as urdf
    original = urdf.geometria
    monkeypatch.setattr(urdf, "geometria", lambda alcance, fisica=None: {**original(alcance, fisica), "l1_m": 0.3, "l2_m": 0.3})
    url, _ = entorno_local
    pid = requests.post(f"{url}/proyectos", json={"nombre": "x"}, timeout=5).json()["id"]
    cid = requests.post(f"{url}/proyectos/{pid}/corridas", timeout=5).json()["corrida_id"]
    c = _esperar(url, cid)
    assert c["estado"] == "error"
    assert "fuera de alcance" in c["error"]
    assert {e["nombre"]: e["estado"] for e in c["etapas"]}["clon"] == "error"


def test_corrida_inexistente(entorno_local):
    url, _ = entorno_local
    assert requests.get(f"{url}/corridas/nada", timeout=5).status_code == 404
    assert requests.get(f"{url}/corridas/demo", timeout=5).status_code == 404


def test_almacen_local_no_sale_de_su_carpeta(tmp_path):
    store = alm.AlmacenLocal(tmp_path, "http://x")
    with pytest.raises(ValueError):
        store.escribir("../fuera.txt", b"x")
