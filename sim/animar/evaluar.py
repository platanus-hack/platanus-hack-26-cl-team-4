"""Comando `evaluar` de animar_evento: la política entrenada hace el recorrido y la coreografía en la sala.

    $ISAACLAB_SH -p sim/tareas.py evaluar --entorno E --tarea T --robot R --escena S --checkpoint C
        --episodios N --tolerancias "0.5:30,0.25:30" --salida DIR [--video DIR/video.mp4] [--trayectoria ...]

N copias de la sala corren a la vez; cada una hace un episodio (el recorrido completo). Un episodio es un éxito si
el robot llega a cada punto dentro de la tolerancia de posición, no se cae, no choca y termina antes de
criterios_exito.tiempo_max_s. La tolerancia angular no aplica a esta tarea: se informa tal cual.

Escribe DIR/evaluacion.json (esquema del contrato) y DIR/evaluacion_detalle.json (caídas, choques, despeje,
error por punto). --video graba la copia 0 con una cámara que sigue al robot.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

COPIAS_MAX = 32               # copias de la sala a la vez; más episodios se reparten en tandas
EXTRA_S = 2.0                 # segundos que sigue grabando después de terminar el recorrido


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--episodios", type=int, default=32)
    ap.add_argument("--tolerancias", default="0.5:30")
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--trayectoria", type=Path)
    a = ap.parse_args()
    app = comun.lanzar(a, camaras=bool(a.video))
    comun.ejecutar(app, lambda: evaluar(a))


def _tolerancias(texto: str) -> list[tuple[float, float]]:
    return [tuple(float(x) for x in t.split(":")) for t in texto.split(",") if t]


def tanda(c, a, n: int, video: Path | None) -> list[dict]:
    """n episodios en paralelo. Devuelve una fila por copia."""
    import torch

    sys.path.insert(0, str(comun.SIM))
    from rl import grabacion

    env = comun.crear(comun.cfg_sala(c, n, a.device, render=bool(video)), render=bool(video))
    envuelto, politica = comun.cargar_politica(env, c, a.checkpoint, a.device)
    obs = envuelto.get_observations()
    coreo = comun.Coreografo(env, c)
    vig = comun.Vigilante(env, c)
    listo = torch.zeros(n, dtype=torch.bool, device=env.device)
    grab = grabacion.Video(video) if video else None
    if grab:
        cam = comun.Camarografo(env, c)
        cam.mover(*comun.inicio(c)[:2], saltar=True)
        grabacion.descartar_inicio(env)
    reloj = comun.Reloj(env.step_dt)
    pasos_max = int(env.max_episode_length) + 5
    extra = int(EXTRA_S / env.step_dt)
    restantes = None
    for _ in range(pasos_max + extra):
        coreo.actualizar()
        with torch.inference_mode():
            obs, _, terminado, _ = envuelto.step(politica(obs))
        pos, _ = coreo.posicion()
        vig.actualizar(pos, listo)
        caida = terminado.bool() & ~listo & ~coreo.terminado & (env.episode_length_buf < env.max_episode_length - 1)
        vig.caida |= caida
        listo |= terminado.bool() | coreo.terminado
        if grab:
            x, y = pos[0].tolist()
            cam.mover(x, y)
            if reloj.toca():
                grab.cuadro(env.render())
        if bool(listo.all()):
            restantes = extra if restantes is None else restantes - 1
            if restantes <= 0 or not grab:
                break
    if grab:
        print(json.dumps(grab.cerrar()), flush=True)
    filas = []
    for i in range(n):
        filas.append({"llego": bool(coreo.terminado[i]), "t_fin_s": float(coreo.t_fin[i]),
                      "err_puntos_m": [round(float(e), 3) for e in coreo.err_llegada[i]],
                      "caida": bool(vig.caida[i]), "choque": bool(vig.choque[i]),
                      "dist_min_m": round(float(vig.dist_min[i]), 3) if math.isfinite(float(vig.dist_min[i])) else None})
    return filas


def evaluar(a) -> dict:
    c = comun.leer(a)
    tols = _tolerancias(a.tolerancias)
    n = min(a.episodios, COPIAS_MAX)
    filas = tanda(c, a, n, a.video)
    tmax = c.tarea["criterios_exito"]["tiempo_max_s"] or float("inf")

    def exito(f, pos):
        return (f["llego"] and not f["caida"] and not f["choque"] and f["t_fin_s"] <= tmax
                and max(f["err_puntos_m"] or [0]) <= pos)

    tolerancias = []
    for pos, ang in tols:
        k = sum(exito(f, pos) for f in filas)
        tolerancias.append({"pos_m": pos, "ang_grados": ang, "exitos": k, "tasa_exito": round(k / len(filas), 4)})
    buenos = [f["t_fin_s"] for f in filas if exito(f, tols[0][0])]
    evaluacion = {"version": 1, "checkpoint": a.checkpoint.name, "episodios": len(filas), "tolerancias": tolerancias,
                  "ciclo_promedio_s": round(sum(buenos) / len(buenos), 2) if buenos else 0.0,
                  "colisiones": sum(f["choque"] for f in filas), "fuente": "isaac"}
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "evaluacion.json").write_text(json.dumps(evaluacion, ensure_ascii=False, indent=2), encoding="utf-8")
    detalle = {"version": 1, "tarea": "animar_evento", "checkpoint": a.checkpoint.name, "episodios": len(filas),
               "pedidos": a.episodios, "caidas": sum(f["caida"] for f in filas),
               "choques": sum(f["choque"] for f in filas), "sin_terminar": sum(not f["llego"] for f in filas),
               "nota": "La tolerancia angular no aplica a animar_evento: el éxito mide llegada, caídas, choques y tiempo.",
               "puntos": [p["nombre"] for p in c.animacion["puntos"]], "por_episodio": filas}
    (a.salida / "evaluacion_detalle.json").write_text(json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evaluacion, ensure_ascii=False), flush=True)
    return {"ok": True, **evaluacion}


if __name__ == "__main__":
    main()
