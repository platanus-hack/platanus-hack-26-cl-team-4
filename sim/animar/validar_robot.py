"""Comando `validar_robot` de animar_evento: el modelo del robot carga en la sala, cabe y no choca al aparecer.

    $ISAACLAB_SH -p sim/tareas.py validar_robot --entorno E --tarea T --robot R --escena S --salida validacion.json
        [--video crudo.mp4]

Sin política todavía: el robot aparece en el primer punto con las articulaciones en su pose por defecto y se
sostiene con los motores (sin caminar) durante SOSTENER_S. Revisa:
1. Sin Isaac: clon.json trae un modelo con configuración de caminata (comun.LOCOMOCION).
2. En Isaac: el robot carga, su punto más alto cabe bajo el techo y ninguna pieza que no es un pie toca algo
   al aparecer. Que se caiga sin política no es una falla: todavía no aprendió a pararse.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

SOSTENER_S = 2.0
ARRANQUE_S = 0.3              # el choque se revisa al aparecer, antes de que la falta de política lo haga caer


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--video", type=Path)
    a = ap.parse_args()
    try:
        c = comun.leer(a)
        _ = c.modelo
    except SystemExit as e:
        a.salida.write_text(json.dumps({"ok": False, "problemas": [str(e)], "fuente": "isaac"}, ensure_ascii=False),
                            encoding="utf-8")
        print(e, flush=True)
        sys.exit(1)
    app = comun.lanzar(a, camaras=bool(a.video))
    comun.ejecutar(app, lambda: validar(a, c), a.salida)


def validar(a, c) -> dict:
    import torch

    sys.path.insert(0, str(comun.SIM))
    from rl import grabacion

    env = comun.crear(comun.cfg_sala(c, 1, a.device, render=bool(a.video)), render=bool(a.video))
    env.reset()
    robot = env.scene["robot"]
    vig = comun.Vigilante(env, c)
    salida = grabacion.Video(a.video) if a.video else None
    if salida:
        comun.camara_sala(env, c, 0, sigue=tuple(comun.inicio(c)[:2]))
        grabacion.descartar_inicio(env)
    accion = torch.zeros(1, env.action_manager.total_action_dim, device=env.device)
    listo = torch.zeros(1, dtype=torch.bool, device=env.device)
    choque_inicio = False
    alto_max = 0.0
    for k in range(int(SOSTENER_S / env.step_dt)):
        env.step(accion)
        if k * env.step_dt <= ARRANQUE_S:
            pos = robot.data.root_pos_w[:, :2] - env.scene.env_origins[:, :2]
            vig.actualizar(pos, listo)
            choque_inicio = bool(vig.choque[0])
            alto_max = max(alto_max, float((robot.data.body_pos_w[0, :, 2] - env.scene.env_origins[0, 2]).max()))
        if salida:
            salida.cuadro(env.render())
    if salida:
        print(json.dumps(salida.cerrar()), flush=True)
    problemas = []
    esp = c.entorno["espacio"]
    if esp["interior"] and alto_max > esp["alto_m"] - comun.HOLGURA_ALTURA_M:
        problemas.append(f"el robot mide {alto_max:.2f} m y el techo está a {esp['alto_m']} m")
    if choque_inicio:
        problemas.append("una pieza del robot toca un elemento de la sala al aparecer en el primer punto")
    return {"ok": not problemas, "problemas": problemas, "fuente": "isaac", "modelo": c.modelo,
            "articulaciones": len(robot.joint_names), "alto_m": round(alto_max, 3),
            "dist_min_elementos_m": round(float(vig.dist_min[0]), 3)}


if __name__ == "__main__":
    main()
