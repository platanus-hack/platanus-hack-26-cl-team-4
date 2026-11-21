"""Entorno RL SIMULADO: imita los 4 comandos del contrato (docs/contrato-entorno-rl.md) sin Isaac.

    python sim/rl_simulado.py entrenar --entorno E --tarea T --robot R --escena S --salida DIR --max-horas 4 ...
    python sim/rl_simulado.py evaluar  ... --checkpoint C --episodios 100 --tolerancias 0.05:5,0.02:2 --salida DIR
    python sim/rl_simulado.py grabar_clip ... --checkpoint C --segundos 7 --salida clip.mp4 [--grilla]
    python sim/rl_simulado.py validar_robot ... --salida validacion.json

Sirve para probar el sistema completo en un Mac y en CI. NO es un resultado de Isaac:
las métricas son una curva sintética y los videos son dibujos 2D rotulados "simulado".

Perillas (variables de entorno, no son parte del contrato):
- VIAZ_SIM_ITERACIONES (300), VIAZ_SIM_SEGUNDOS (6): largo y duración real del entrenamiento simulado.
- VIAZ_SIM_SEGUNDOS_CLIP: tope de segundos por clip (para tests rápidos).
- VIAZ_SIM_NAN_EN: iteración en la que la recompensa sale NaN (para probar la detención).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import runpy
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402
import video  # noqa: E402

ARTICULACIONES = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"]


def _leer(p: str | Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _tasa(i: int, n: int) -> float:
    """Curva logística determinista que llega a ~0,94: la forma típica de un PPO que aprende."""
    return round(0.94 / (1 + math.exp(-(i - 0.42 * n) / (0.07 * n))), 4)


def _iteracion(checkpoint: str) -> int:
    return int(Path(checkpoint).stem.split("_")[-1])


def _metricas_de(checkpoint: str) -> list[dict]:
    f = Path(checkpoint).parent.parent / "metricas.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


# ---------- entrenar ----------

def entrenar(a) -> None:
    n = int(os.getenv("VIAZ_SIM_ITERACIONES", "300"))
    pausa = float(os.getenv("VIAZ_SIM_SEGUNDOS", "6")) / n
    nan_en = int(os.getenv("VIAZ_SIM_NAN_EN", "-1"))
    salida = Path(a.salida)
    (salida / "checkpoints").mkdir(parents=True, exist_ok=True)
    inicio = _iteracion(a.reanudar) + 1 if a.reanudar else 0
    seg_por_it = a.max_horas * 3600 * 0.8 / n  # tiempo "real" que representaría cada iteración en el pod
    rnd = random.Random(7)
    with open(salida / "metricas.jsonl", "a", encoding="utf-8") as f:
        for i in range(inicio, n):
            tasa = max(0.0, min(1.0, _tasa(i, n) + rnd.uniform(-0.02, 0.02)))
            fila = {"iteracion": i, "pasos": i * 24 * 4096, "tiempo_s": round(i * seg_por_it, 1),
                    "recompensa_media": float("nan") if i == nan_en else round(5 + 40 * tasa + rnd.uniform(-1, 1), 3),
                    "tasa_exito": round(tasa, 4), "largo_episodio": round(300 - 120 * tasa, 1),
                    "perdida_valor": round(0.8 - 0.5 * tasa, 4), "perdida_politica": -0.01, "entropia": round(2.2 - 0.9 * tasa, 3)}
            f.write(json.dumps(fila) + "\n")
            f.flush()
            if i % 50 == 0 or i == n - 1:
                (salida / "checkpoints" / f"model_{i}.pt").write_bytes(b"checkpoint simulado")
            if (salida / "DETENER").exists():
                (salida / "checkpoints" / f"model_{i}.pt").write_bytes(b"checkpoint simulado")
                return
            time.sleep(pausa)


# ---------- dibujo 2D (solo para los videos simulados) ----------

def _cuadro(t: float, precision: float, titulo: str, grilla: bool = False):
    """Vista lateral: base que avanza, brazo de 2 tramos y un panel que baja al tubo."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (video.ANCHO, video.ALTO), (24, 28, 36))
    d = ImageDraw.Draw(img)
    if grilla:
        for fx in range(16):
            for fy in range(9):
                x, y = 40 + fx * 76, 40 + fy * 72
                d.rectangle([x, y, x + 60, y + 50], outline=(70, 80, 95))
                d.rectangle([x + 10 + (t * 40 + fx * 3) % 30, y + 30, x + 26 + (t * 40 + fx * 3) % 30, y + 42], fill=(224, 161, 6))
        d.text((40, video.ALTO - 60), "4096 entornos en paralelo (simulado)", font=video._fuente(26), fill=(220, 225, 235))
        return img
    suelo = 600
    d.rectangle([0, suelo, video.ANCHO, video.ALTO], fill=(58, 52, 44))
    tubo_y = suelo - 220
    for px in range(200, 1280, 260):
        d.rectangle([px, tubo_y, px + 10, suelo], fill=(140, 145, 155))
    d.rectangle([150, tubo_y - 8, 1280, tubo_y + 8], fill=(170, 175, 185))
    fase = (t % 4) / 4
    base_x = 260 + int(t // 4) * 240
    d.rectangle([base_x - 90, suelo - 110, base_x + 90, suelo - 30], fill=(224, 161, 6))
    for rx in (base_x - 60, base_x + 60):
        d.ellipse([rx - 28, suelo - 56, rx + 28, suelo], fill=(20, 20, 20))
    hombro = (base_x + 40, suelo - 150)
    destino = (base_x + 120 + (1 - precision) * 90, tubo_y - 14 - (1 - precision) * 50)
    pila = (base_x - 40, suelo - 120)
    s = fase * 2 if fase < 0.5 else 2 - fase * 2
    ef = (pila[0] + (destino[0] - pila[0]) * s, pila[1] + (destino[1] - pila[1]) * s)
    codo = ((hombro[0] + ef[0]) / 2 - 20, min(hombro[1], ef[1]) - 90)
    d.line([hombro, codo, ef], fill=(210, 212, 218), width=14)
    d.ellipse([hombro[0] - 14, hombro[1] - 14, hombro[0] + 14, hombro[1] + 14], fill=(90, 95, 105))
    angulo = (1 - precision) * 18 * (1 if fase < 0.5 else 1)
    w, h = 150, 10
    cx, cy = ef[0], ef[1] + 12
    rad = math.radians(angulo)
    esquinas = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    d.polygon([(cx + x * math.cos(rad) - y * math.sin(rad), cy + x * math.sin(rad) + y * math.cos(rad)) for x, y in esquinas],
              fill=(40, 70, 140), outline=(120, 150, 220))
    d.text((40, video.ALTO - 60), titulo, font=video._fuente(24), fill=(220, 225, 235))
    return img


def _render(salida: Path, segundos: float, precision: float, titulo: str, grilla_s: float = 0.0) -> None:
    tope = os.getenv("VIAZ_SIM_SEGUNDOS_CLIP")
    if tope:
        segundos, grilla_s = min(segundos, float(tope)), min(grilla_s, float(tope) / 2)
    fps = 15 if tope else video.FPS
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(max(1, int(segundos * fps))):
            t = k / fps
            _cuadro(t, precision, titulo, grilla=t < grilla_s).save(Path(tmp) / f"f_{k:04d}.png")
        video.frames_a_mp4(Path(tmp), salida, fps=fps)


# ---------- evaluar, grabar_clip, validar_robot ----------

def evaluar(a) -> None:
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    it = _iteracion(a.checkpoint)
    filas = _metricas_de(a.checkpoint)
    tasa = next((m["tasa_exito"] for m in filas if m["iteracion"] == it), 0.9) or 0.0
    tolerancias = []
    for k, par in enumerate(a.tolerancias.split(",")):
        pos, ang = (float(x) for x in par.split(":"))
        t = tasa if k == 0 else tasa * 0.66  # tolerancia más estricta: menos éxitos
        exitos = round(t * a.episodios)
        tolerancias.append({"pos_m": pos, "ang_grados": ang, "exitos": exitos, "tasa_exito": round(exitos / a.episodios, 4)})
    ev = {"version": 1, "checkpoint": Path(a.checkpoint).name, "episodios": a.episodios, "tolerancias": tolerancias,
          "ciclo_promedio_s": 38.0, "colisiones": round((1 - tasa) * a.episodios * 0.2), "fuente": "simulado"}
    (salida / "evaluacion.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.video:
        _render(Path(a.video), 24, tasa, "Muestra del robot entrenado · simulación")
    clon = Path(a.robot).parent / "clon.json"
    if a.trayectoria and clon.exists():
        tray = plan.generar(_leer(a.entorno), _leer(a.tarea), _leer(clon))
        Path(a.trayectoria).write_text(json.dumps(tray), encoding="utf-8")


def grabar_clip(a) -> None:
    filas = _metricas_de(a.checkpoint)
    it = _iteracion(a.checkpoint)
    tasa = next((m["tasa_exito"] for m in filas if m["iteracion"] == it), 0.0) or 0.0
    _render(Path(a.salida), a.segundos, tasa, f"Checkpoint {it}", grilla_s=1.5 if a.grilla else 0.0)


def validar_robot(a) -> None:
    params = runpy.run_path(a.robot)["PARAMETROS"]
    clon = _leer(Path(a.robot).parent / "clon.json")
    v = plan.validar(_leer(a.entorno), _leer(a.tarea), clon, carga_util_kg=params["carga_util_kg"])
    faltan = [j for j in ARTICULACIONES if j not in params.get("articulaciones", [])]
    if faltan:
        v["problemas"].append(f"faltan articulaciones: {faltan}")
    salida = {"ok": not v["problemas"], "problemas": v["problemas"], "fuente": "simulado",
              "paneles_planificados": v.get("paneles_planificados", 0)}
    Path(a.salida).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("comando", choices=["entrenar", "evaluar", "grabar_clip", "validar_robot"])
    for n in ("--entorno", "--tarea", "--robot", "--escena", "--salida"):
        ap.add_argument(n, required=n != "--escena")
    ap.add_argument("--max-horas", type=float, default=4)
    ap.add_argument("--tolerancia-pos-m", type=float, default=0.05)
    ap.add_argument("--tolerancia-ang-grados", type=float, default=5)
    ap.add_argument("--reanudar")
    ap.add_argument("--checkpoint")
    ap.add_argument("--episodios", type=int, default=100)
    ap.add_argument("--tolerancias", default="0.05:5,0.02:2")
    ap.add_argument("--video")
    ap.add_argument("--trayectoria")
    ap.add_argument("--segundos", type=float, default=7)
    ap.add_argument("--grilla", action="store_true")
    a = ap.parse_args()
    {"entrenar": entrenar, "evaluar": evaluar, "grabar_clip": grabar_clip, "validar_robot": validar_robot}[a.comando](a)


if __name__ == "__main__":
    main()
