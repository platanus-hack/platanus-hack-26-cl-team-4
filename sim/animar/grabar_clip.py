"""Comando `grabar_clip` de animar_evento: un clip de la política de un checkpoint, en la sala.

    $ISAACLAB_SH -p sim/tareas.py grabar_clip --entorno E --tarea T --robot R --escena S --checkpoint C
        --segundos 7 --salida clip.mp4 [--grilla]

Un robot hace el recorrido y la coreografía con la cámara que lo sigue. Con un checkpoint temprano se cae: eso es
lo que muestra el video acelerado. Con --grilla abre con 1,5 s de la vista alta de 16 copias de entrenamiento.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

GRILLA_S = 1.5
COPIAS_GRILLA = 16


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--segundos", type=float, default=7.0)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--grilla", action="store_true")
    a = ap.parse_args()
    app = comun.lanzar(a, camaras=True)
    comun.ejecutar(app, lambda: grabar(a))


def grabar(a) -> dict:
    import torch

    sys.path.insert(0, str(comun.SIM))
    from rl import grabacion

    c = comun.leer(a)
    env = comun.crear(comun.cfg_sala(c, 1, a.device, render=True), render=True)
    envuelto, politica = comun.cargar_politica(env, c, a.checkpoint, a.device)
    obs = envuelto.get_observations()
    coreo = comun.Coreografo(env, c)
    salida = grabacion.Video(a.salida)
    cam = comun.Camarografo(env, c)
    cam.mover(*comun.inicio(c)[:2], saltar=True)
    grabacion.descartar_inicio(env)
    if a.grilla:   # vista general de la sala antes de seguir al robot
        for _ in range(int(GRILLA_S * 30)):
            salida.cuadro(env.render())
    reloj = comun.Reloj(env.step_dt)
    for _ in range(int(a.segundos / env.step_dt)):
        coreo.actualizar()
        with torch.inference_mode():
            obs, _, _, _ = envuelto.step(politica(obs))
        pos, _ = coreo.posicion()
        x, y = pos[0].tolist()
        cam.mover(x, y)
        if reloj.toca():
            salida.cuadro(env.render())
    info = salida.cerrar()
    print(json.dumps(info), flush=True)
    return {"ok": True, **info}


if __name__ == "__main__":
    main()
