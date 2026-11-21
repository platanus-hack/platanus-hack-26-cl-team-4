"""Sim runner: toma trabajos de la API, los ejecuta y sube los resultados.

    # en el pod con la 5090
    VIAZ_API=https://viaz-api.onrender.com WORKER_TOKEN=... ISAAC_PYTHON=/isaac-sim/python.sh \
        python worker-gpu/runner.py --modo isaac

    # en un Mac, sin GPU: trayectoria sintética
    python worker-gpu/runner.py --modo simulado

Un trabajo a la vez (Isaac usa casi toda la GPU). Pull: el pod no expone puertos.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SIM = RAIZ / "sim"
sys.path.insert(0, str(SIM))
import plan  # noqa: E402

log = logging.getLogger("viaz.worker")
TIPOS = {".json": "application/json", ".mp4": "video/mp4", ".urdf": "application/xml", ".usd": "application/octet-stream"}


def _leer(d: Path, n: str) -> dict:
    return json.loads((d / n).read_text(encoding="utf-8"))


def _escribir(d: Path, n: str, datos: dict) -> None:
    (d / n).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def _correr(python: str, script: str, d: Path, *extra: str) -> None:
    cmd = [*python.split(), str(SIM / script), "--dir", str(d), *extra]
    log.info("ejecuto %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=SIM, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        cola = (r.stderr or r.stdout)[-1500:]
        raise RuntimeError(f"{script} terminó con código {r.returncode}: {cola}")


def ejecutar(tipo: str, d: Path, modo: str, isaac_python: str) -> None:
    if tipo == "generar_escena":
        _correr(sys.executable, "generar_escena.py", d)
    elif tipo == "validar_clon":
        if modo == "isaac":
            _correr(isaac_python, "validar_clon.py", d)
        else:
            tarea = _leer(d, "tarea.json") if (d / "tarea.json").exists() else {"objetivo": {"paneles": 1}, "pila_paneles": {"cantidad": 1}}
            v = plan.validar(_leer(d, "entorno.json"), tarea, _leer(d, "clon.json"))
            _escribir(d, "validacion.json", {**v, "fuente": "simulado"})
    elif tipo == "ejecutar_tarea":
        if modo == "isaac":
            _correr(isaac_python, "ejecutar_tarea.py", d)
        else:
            tray = plan.generar(_leer(d, "entorno.json"), _leer(d, "tarea.json"), _leer(d, "clon.json"))
            _escribir(d, "trayectoria.json", tray)
            _escribir(d, "resultado.json", plan.resultado_simulado(tray))
    else:
        raise RuntimeError(f"tipo de trabajo desconocido: {tipo}")


def ciclo(api: str, token: str, modo: str, isaac_python: str, s: requests.Session) -> bool:
    """Toma y ejecuta un trabajo. Devuelve False si no había."""
    auth = {"Authorization": f"Bearer {token}"}
    r = s.post(f"{api}/worker/trabajos/tomar", headers=auth, timeout=30)
    if r.status_code == 204:
        return False
    r.raise_for_status()
    t = r.json()
    log.info("trabajo %s: %s (corrida %s)", t["trabajo_id"], t["tipo"], t["corrida_id"])
    fin = {"ok": True}
    try:
        with tempfile.TemporaryDirectory(prefix="viaz-") as tmp:
            d = Path(tmp)
            for archivo, url in t["entradas"].items():
                b = s.get(url, timeout=120)
                b.raise_for_status()
                (d / archivo).write_bytes(b.content)
            ejecutar(t["tipo"], d, modo, isaac_python)
            for archivo, url in t["subidas"].items():
                f = d / archivo
                if not f.exists():
                    continue  # p. ej. video.mp4 en modo simulado
                tipo = TIPOS.get(f.suffix, "application/octet-stream")
                s.put(url, data=f.read_bytes(), headers={"Content-Type": tipo}, timeout=300).raise_for_status()
    except Exception as e:
        log.exception("trabajo %s falló", t["trabajo_id"])
        fin = {"ok": False, "error": f"{type(e).__name__}: {e}"[:2000]}
    s.post(f"{api}/worker/trabajos/{t['trabajo_id']}/fin", headers=auth, json=fin, timeout=30).raise_for_status()
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.getenv("VIAZ_API", "http://localhost:8000"))
    ap.add_argument("--modo", choices=["simulado", "isaac"], default=os.getenv("VIAZ_MODO_SIM", "simulado"))
    ap.add_argument("--isaac-python", default=os.getenv("ISAAC_PYTHON", "/isaac-sim/python.sh"))
    ap.add_argument("--una-vez", action="store_true", help="procesa como máximo un trabajo y sale")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    token = os.getenv("WORKER_TOKEN", "dev-token")
    api = a.api.rstrip("/")
    log.info("worker listo: api=%s modo=%s", api, a.modo)
    s = requests.Session()
    while True:
        try:
            hubo = ciclo(api, token, a.modo, a.isaac_python, s)
        except requests.RequestException as e:
            log.warning("API no disponible: %s", e)
            hubo = False
        if a.una_vez:
            return
        if not hubo:
            time.sleep(3)


if __name__ == "__main__":
    main()
