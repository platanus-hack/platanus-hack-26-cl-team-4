"""Sim runner: toma trabajos de la API, los ejecuta y sube los resultados.

    # en el pod (Isaac Lab): los comandos del entorno RL salen de VIAZ_CMD_* (docs/contrato-entorno-rl.md §1)
    VIAZ_API=https://viaz-api.onrender.com WORKER_TOKEN=... ISAAC_PYTHON=/isaac-sim/python.sh \\
        python worker-gpu/runner.py --modo isaac

    # en un Mac, sin GPU: entorno RL simulado (sim/rl_simulado.py) y trayectoria sintética
    python worker-gpu/runner.py --modo simulado

Un trabajo a la vez (Isaac usa casi toda la GPU). Pull: el pod no expone puertos.
Los checkpoints quedan en VIAZ_DIR_POD/<corrida>/entrenamiento (volumen persistente del pod):
evaluar y grabar_clips los leen de ahí, sin subirlos y bajarlos.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SIM = RAIZ / "sim"
sys.path.insert(0, str(SIM))
import plan  # noqa: E402

log = logging.getLogger("viaz.worker")
TIPOS = {".json": "application/json", ".mp4": "video/mp4", ".urdf": "application/xml", ".usd": "application/octet-stream",
         ".py": "text/x-python", ".jsonl": "application/x-ndjson", ".pt": "application/octet-stream"}
COMANDOS = ("entrenar", "evaluar", "grabar_clip", "validar_robot")


@dataclass
class Contexto:
    api: str
    token: str
    modo: str
    isaac_python: str
    sesion: requests.Session
    dir_pod: Path = field(default_factory=lambda: Path(os.getenv("VIAZ_DIR_POD", str(RAIZ / ".datos" / "pod"))))
    trabajo_id: str = ""
    corrida_id: str = ""
    parametros: dict = field(default_factory=dict)

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


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


# ---------- entorno RL: comandos del contrato ----------

def comando(nombre: str, modo: str) -> list[str]:
    """Comando base del entorno RL. Isaac: VIAZ_CMD_<NOMBRE>. Simulado: sim/rl_simulado.py."""
    if modo == "isaac":
        base = os.getenv(f"VIAZ_CMD_{nombre.upper()}", "")
        if not base:
            raise RuntimeError(f"falta VIAZ_CMD_{nombre.upper()} en el pod (docs/contrato-entorno-rl.md §1)")
        return shlex.split(base)
    return [sys.executable, str(SIM / "rl_simulado.py"), nombre]


def _comunes(d: Path) -> list[str]:
    args = ["--entorno", str(d / "entorno.json"), "--tarea", str(d / "tarea.json"), "--robot", str(d / "robot_cfg.py")]
    if (d / "escena.usd").exists():
        args += ["--escena", str(d / "escena.usd")]
    return args


def _correr_rl(nombre: str, ctx: Contexto, d: Path, *extra: str, timeout: float = 3600) -> None:
    cmd = [*comando(nombre, ctx.modo), *_comunes(d), *extra]
    log.info("ejecuto %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{nombre} terminó con código {r.returncode}: {(r.stderr or r.stdout)[-1500:]}")


def _dir_entrenamiento(ctx: Contexto) -> Path:
    return ctx.dir_pod / ctx.corrida_id / "entrenamiento"


def _metricas_locales(dir_ent: Path) -> list[dict]:
    f = dir_ent / "metricas.jsonl"
    if not f.exists():
        return []
    filas = []
    for linea in f.read_text(encoding="utf-8").splitlines():
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue  # línea a medio escribir
    return filas


def _checkpoints(dir_ent: Path) -> list[int]:
    return sorted(int(p.stem.split("_")[-1]) for p in (dir_ent / "checkpoints").glob("model_*.pt"))


def _checkpoint_cercano(dir_ent: Path, iteracion: int | None) -> Path:
    """El checkpoint de esa iteración, o el primero después; sin iteración, el último."""
    disponibles = _checkpoints(dir_ent)
    if not disponibles:
        raise RuntimeError(f"no hay checkpoints en {dir_ent / 'checkpoints'}")
    if iteracion is None:
        it = disponibles[-1]
    else:
        it = next((c for c in disponibles if c >= iteracion), disponibles[-1])
    return dir_ent / "checkpoints" / f"model_{it}.pt"


def _latido(ctx: Contexto, metricas: list[dict]) -> str:
    """Manda métricas nuevas. Devuelve 'seguir' o 'detener'. Si la API no responde, sigue entrenando."""
    try:
        # json.dumps deja pasar NaN; la API lo detecta y pide detener (RF-MON-08)
        r = ctx.sesion.post(f"{ctx.api}/worker/trabajos/{ctx.trabajo_id}/latido",
                            headers={**ctx.auth, "Content-Type": "application/json"},
                            data=json.dumps({"metricas": metricas}), timeout=30)
        r.raise_for_status()
        return r.json().get("accion", "seguir")
    except requests.RequestException as e:
        log.warning("latido falló (sigo entrenando): %s", e)
        return "seguir"


def entrenar(ctx: Contexto, d: Path) -> None:
    """Lanza el entrenamiento, manda latidos con las métricas nuevas y obedece 'detener' (RF-GPU-06)."""
    p = ctx.parametros
    dir_ent = _dir_entrenamiento(ctx)
    dir_ent.mkdir(parents=True, exist_ok=True)
    (dir_ent / "DETENER").unlink(missing_ok=True)
    horas = float(p.get("horas", 4))
    extra = ["--salida", str(dir_ent), "--max-horas", str(horas),
             "--tolerancia-pos-m", str(p.get("tolerancia_pos_m", 0.05)),
             "--tolerancia-ang-grados", str(p.get("tolerancia_ang_grados", 5))]
    previos = _checkpoints(dir_ent)
    if previos:  # el pod se reinició: retomar (RF-GPU-05)
        extra += ["--reanudar", str(dir_ent / "checkpoints" / f"model_{previos[-1]}.pt")]
        log.info("retomo el entrenamiento desde la iteración %s", previos[-1])
    cmd = [*comando("entrenar", ctx.modo), *_comunes(d), *extra]
    log.info("ejecuto %s", " ".join(cmd))
    intervalo = float(p.get("latido_s", 300))
    limite = time.monotonic() + horas * 3600 + 1800
    enviado = len(_metricas_locales(dir_ent))
    with open(dir_ent / "entrenar.log", "a", encoding="utf-8") as registro:
        proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=registro, stderr=subprocess.STDOUT)
        proximo = time.monotonic() + intervalo
        while proc.poll() is None:
            time.sleep(min(1.0, intervalo))
            if time.monotonic() >= limite:
                proc.kill()
                raise RuntimeError(f"el entrenamiento pasó las {horas} h + 30 min de margen")
            if time.monotonic() >= proximo:
                filas = _metricas_locales(dir_ent)
                if _latido(ctx, filas[enviado:]) == "detener" and not (dir_ent / "DETENER").exists():
                    log.info("la API pidió detener: guardo checkpoint y termino")
                    (dir_ent / "DETENER").touch()
                enviado = len(filas)
                proximo = time.monotonic() + intervalo
    filas = _metricas_locales(dir_ent)
    _latido(ctx, filas[enviado:])
    if proc.returncode != 0:
        cola = (dir_ent / "entrenar.log").read_text(encoding="utf-8")[-1500:]
        raise RuntimeError(f"entrenar terminó con código {proc.returncode}: {cola}")
    if not filas:
        raise RuntimeError("el entrenamiento no escribió metricas.jsonl")
    paso = max(1, len(filas) // 300)
    puntos = [{k: f.get(k) for k in ("iteracion", "tiempo_s", "recompensa_media", "tasa_exito")} for f in filas[::paso]]
    if puntos[-1]["iteracion"] != filas[-1]["iteracion"]:
        puntos.append({k: filas[-1].get(k) for k in ("iteracion", "tiempo_s", "recompensa_media", "tasa_exito")})
    _escribir(d, "curva.json", {"version": 1, "puntos": puntos})
    _escribir(d, "checkpoints.json", {"version": 1, "iteraciones": _checkpoints(dir_ent),
                                      "detenido": (dir_ent / "DETENER").exists(),
                                      "ultima_iteracion": filas[-1]["iteracion"], "tiempo_s": filas[-1].get("tiempo_s", 0),
                                      "pasos": filas[-1].get("pasos", 0)})


def evaluar(ctx: Contexto, d: Path) -> None:
    """Evalúa un checkpoint en N episodios y graba la muestra (RF-INT-14, RF-INT-15)."""
    p = ctx.parametros
    dir_ent = _dir_entrenamiento(ctx)
    ckpt = _checkpoint_cercano(dir_ent, p.get("checkpoint"))
    episodios = int(p.get("episodios", 100))
    tolerancias = p.get("tolerancias", "0.05:5,0.02:2")
    _correr_rl("evaluar", ctx, d, "--checkpoint", str(ckpt), "--episodios", str(episodios), "--tolerancias", tolerancias,
               "--salida", str(d), "--video", str(d / "video.mp4"), "--trayectoria", str(d / "trayectoria.json"),
               timeout=7200)
    ev = _leer(d, "evaluacion.json")
    principal = ev["tolerancias"][0]
    filas = _metricas_locales(dir_ent)
    ultima = filas[-1] if filas else {}
    tol_txt = ", ".join(f"{t['tasa_exito']:.0%} a {t['pos_m'] * 100:.0f} cm y {t['ang_grados']:.0f}°" for t in ev["tolerancias"])
    resultado = {
        "version": 1, "metodo": "rl", "fuente": ev.get("fuente", "isaac" if ctx.modo == "isaac" else "simulado"),
        "politica": "politica.pt",
        "metricas": {"paneles_instalados": principal["exitos"], "intentos": ev["episodios"],
                     "tasa_exito": principal["tasa_exito"], "ciclo_promedio_s": ev["ciclo_promedio_s"]},
        "video": "video.mp4" if (d / "video.mp4").exists() else None,
        "notas": f"Política de {ckpt.stem} evaluada en {ev['episodios']} episodios: {tol_txt}.",
        "evaluacion": {"episodios": ev["episodios"], "tolerancias": ev["tolerancias"], "checkpoint": ckpt.name},
        "entrenamiento": {"horas": round(float(ultima.get("tiempo_s", 0)) / 3600, 2),
                          "iteraciones": int(ultima.get("iteracion", 0)) + (1 if filas else 0),
                          "pasos": int(ultima.get("pasos", 0)), "factor_video": None},
    }
    if ev.get("fuente") == "simulado":
        resultado["notas"] += " Entorno RL simulado: no es un resultado de Isaac."
    _escribir(d, "resultado.json", resultado)
    shutil.copyfile(ckpt, d / "politica.pt")


def grabar_clips(ctx: Contexto, d: Path) -> None:
    """Graba un clip por checkpoint, les pone el rótulo y arma entrenamiento_rapido.mp4 (RF-INT-13)."""
    import video
    p = ctx.parametros
    dir_ent = _dir_entrenamiento(ctx)
    filas = _metricas_locales(dir_ent)
    if not filas:
        raise RuntimeError("no hay métricas del entrenamiento para rotular los clips")
    por_it = {f["iteracion"]: f for f in filas}
    curva = [(f["iteracion"], f.get("tasa_exito") or 0.0) for f in filas[:: max(1, len(filas) // 200)]]
    segundos = float(p.get("segundos", 7))
    clips_pedidos = p.get("clips") or [{"iteracion": 0, "etiqueta": "Inicio"}, {"iteracion": None, "etiqueta": "Final"}]
    total_s = float(filas[-1].get("tiempo_s", 0))
    factor = round(total_s / max(1.0, segundos * len(clips_pedidos)))
    hechos = []
    for k, c in enumerate(clips_pedidos):
        ckpt = _checkpoint_cercano(dir_ent, c.get("iteracion"))
        it = int(ckpt.stem.split("_")[-1])
        crudo = d / f"clip_{k}_crudo.mp4"
        extra = ["--checkpoint", str(ckpt), "--segundos", str(segundos), "--salida", str(crudo)]
        if k == 0:
            extra.append("--grilla")
        _correr_rl("grabar_clip", ctx, d, *extra, timeout=1800)
        m = por_it.get(it) or min(filas, key=lambda f: abs(f["iteracion"] - it))
        tasa = m.get("tasa_exito") or 0.0
        capa = video.rotulo(
            c.get("etiqueta", f"Iteración {it}"),
            f"Entrenamiento: {video.texto_tiempo(float(m.get('tiempo_s', 0)))} · iteración {it} · éxito {tasa:.0%} · video ×{factor}",
            curva=video.mini_curva(curva, it))
        hechos.append(video.superponer(crudo, capa, d / f"clip_{k}.mp4"))
        crudo.unlink(missing_ok=True)
    salida = video.unir(hechos, d / "entrenamiento_rapido.mp4")
    duracion = video.duracion_s(salida)
    for h in hechos:
        h.unlink(missing_ok=True)
    _escribir(d, "video_info.json", {"version": 1, "duracion_s": round(duracion, 2),
                                     "horas_representadas": round(total_s / 3600, 2),
                                     "factor_video": round(total_s / duracion) if duracion else None,
                                     "clips": [{"etiqueta": c.get("etiqueta"), "iteracion": c.get("iteracion")} for c in clips_pedidos]})


def validar_robot(ctx: Contexto, d: Path) -> None:
    _correr_rl("validar_robot", ctx, d, "--salida", str(d / "validacion.json"), timeout=1800)


# ---------- despacho ----------

def ejecutar(tipo: str, d: Path, modo: str, isaac_python: str, ctx: Contexto | None = None) -> None:
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
    elif tipo in ("validar_robot", "entrenar", "evaluar", "grabar_clips"):
        if ctx is None:
            raise RuntimeError(f"{tipo} necesita el contexto del trabajo")
        {"validar_robot": validar_robot, "entrenar": entrenar, "evaluar": evaluar, "grabar_clips": grabar_clips}[tipo](ctx, d)
    else:
        raise RuntimeError(f"tipo de trabajo desconocido: {tipo}")


def ciclo(api: str, token: str, modo: str, isaac_python: str, s: requests.Session, dir_pod: Path | None = None) -> bool:
    """Toma y ejecuta un trabajo. Devuelve False si no había."""
    ctx = Contexto(api=api, token=token, modo=modo, isaac_python=isaac_python, sesion=s)
    if dir_pod is not None:
        ctx.dir_pod = dir_pod
    r = s.post(f"{api}/worker/trabajos/tomar", headers=ctx.auth, timeout=30)
    if r.status_code == 204:
        return False
    r.raise_for_status()
    t = r.json()
    ctx.trabajo_id, ctx.corrida_id, ctx.parametros = t["trabajo_id"], t["corrida_id"], t.get("parametros") or {}
    log.info("trabajo %s: %s (corrida %s)", t["trabajo_id"], t["tipo"], t["corrida_id"])
    fin = {"ok": True}
    d = ctx.dir_pod / ctx.corrida_id / f"{t['tipo']}-{t['trabajo_id']}"
    try:
        d.mkdir(parents=True, exist_ok=True)
        for archivo, url in t["entradas"].items():
            b = s.get(url, timeout=300)
            b.raise_for_status()
            (d / archivo).write_bytes(b.content)
        ejecutar(t["tipo"], d, modo, isaac_python, ctx)
        for archivo, url in t["subidas"].items():
            f = d / archivo
            if not f.exists():
                continue  # p. ej. video.mp4 en modo simulado del flujo anterior
            tipo = TIPOS.get(f.suffix, "application/octet-stream")
            s.put(url, data=f.read_bytes(), headers={"Content-Type": tipo}, timeout=600).raise_for_status()
    except Exception as e:
        log.exception("trabajo %s falló", t["trabajo_id"])
        fin = {"ok": False, "error": f"{type(e).__name__}: {e}"[:2000]}
    s.post(f"{api}/worker/trabajos/{t['trabajo_id']}/fin", headers=ctx.auth, json=fin, timeout=30).raise_for_status()
    if fin["ok"] and t["tipo"] not in ("entrenar",):
        shutil.rmtree(d, ignore_errors=True)  # los checkpoints viven en <corrida>/entrenamiento, no aquí
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
    if a.modo == "isaac":
        faltan = [f"VIAZ_CMD_{c.upper()}" for c in COMANDOS if not os.getenv(f"VIAZ_CMD_{c.upper()}")]
        if faltan:
            log.warning("faltan %s: los trabajos del entorno RL van a fallar (docs/contrato-entorno-rl.md)", faltan)
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
