"""Ejecuta la tarea en Isaac Sim con física y la graba. SIN PROBAR EN ISAAC: verificar en el pod.

    $ISAAC_PYTHON sim/ejecutar_tarea.py --dir <carpeta> [--sin-video]

Entradas: entorno.json, tarea.json, clon.json, robot.urdf, escena.usd.
Salidas: trayectoria.json (poses medidas en Isaac), resultado.json y video.mp4.

Versión 0 (checkpoint 1): reproduce el plan de sim/plan.py.
- El brazo sigue el plan con objetivos de posición; la base se mueve de forma cinemática.
- El panel agarrado sigue a la ventosa. Al soltarlo, la física decide dónde queda.
- Un panel cuenta como instalado si queda a menos de 5 cm y 5° de su slot.
Siguiente versión: cambiar el plan fijo por un planificador (cuRobo / RMPflow) y RL para alinear el panel.
Video: necesita `imageio-ffmpeg` en el Python de Isaac (./python.sh -m pip install imageio-ffmpeg).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402

TOL_POS_M = 0.05
TOL_ANG_GRADOS = 5.0
VIDEO = (1280, 720)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--sin-video", action="store_true")
    a = ap.parse_args()
    leer = lambda n: json.loads((a.dir / n).read_text(encoding="utf-8"))  # noqa: E731
    entorno, tarea, clon = leer("entorno.json"), leer("tarea.json"), leer("clon.json")
    plano = plan.generar(entorno, tarea, clon)
    p = entorno["panel"]

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": VIDEO[0], "height": VIDEO[1]})
    try:
        import numpy as np
        import isaac_comun
        from isaacsim.core.api import World
        from isaacsim.core.api.objects import DynamicCuboid
        from isaacsim.core.prims import SingleArticulation, SingleXFormPrim

        isaac_comun.abrir_escena(a.dir / "escena.usd")
        world = World(stage_units_in_meters=1.0, physics_dt=1 / 120, rendering_dt=1 / plano["fps"])
        ruta = isaac_comun.importar_urdf(a.dir / "robot.urdf")
        robot = world.scene.add(SingleArticulation(prim_path=ruta, name="robot"))
        efector = SingleXFormPrim(f"{ruta}/efector")
        paneles = [world.scene.add(DynamicCuboid(
            prim_path=f"/World/Panel{k}", name=f"panel{k}", mass=p["peso_kg"],
            scale=np.array([p["ancho_m"], p["largo_m"], plan.PANEL_ESPESOR]),
            position=np.array([0.0, 0.0, -10.0 - k]), color=np.array([0.05, 0.1, 0.35])))
            for k in range(len(plano["paneles"]))]
        world.reset()
        indices = [robot.get_dof_index(n) for n in plano["articulaciones"]]

        grabar = not a.sin_video
        if grabar:
            import imageio_ffmpeg
            import omni.replicator.core as rep
            xs = [s["pos_m"][0] for s in plano["paneles"]] or [0.0]
            centro = (min(xs) + max(xs)) / 2
            cam = rep.create.camera(position=(centro - 4, 9, 5), look_at=(centro, 0, 1))
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            rgb.attach([rep.create.render_product(cam, VIDEO)])
            ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo",
                                   "-pix_fmt", "rgba", "-s", f"{VIDEO[0]}x{VIDEO[1]}", "-r", str(plano["fps"]),
                                   "-i", "-", "-pix_fmt", "yuv420p", "-vcodec", "libx264", str(a.dir / "video.mp4")],
                                  stdin=subprocess.PIPE)

        frames_medidos = []
        soltados: set[int] = set()
        for fr in plano["frames"]:
            x, y, _ = fr["base"]["pos_m"]
            robot.set_world_pose(position=np.array([x, y, 0.0]), orientation=np.array([1.0, 0, 0, 0]))
            robot.set_linear_velocity(np.zeros(3))
            robot.set_angular_velocity(np.zeros(3))
            robot.apply_action(_accion(fr["q"], indices))
            # Paneles: en la pila (cinemáticos), agarrados (siguen a la ventosa) o soltados (física).
            restantes = [k for k in range(len(paneles)) if k not in soltados and k != fr["agarre"]]
            for nivel, k in enumerate(sorted(restantes, reverse=True)):
                px, py, pz = plano["pila"]["pos_m"]
                _fijar(paneles[k], [x + px, y + py, pz + (nivel + 0.5) * plano["pila"]["paso_m"]])
            if fr["agarre"] is not None:
                pos, _ = efector.get_world_pose()
                _fijar(paneles[fr["agarre"]], [pos[0], pos[1], pos[2] - plan.PANEL_ESPESOR])
            for k in fr["instalados"]:
                if k not in soltados:
                    soltados.add(k)  # desde aquí manda la física
            world.step(render=grabar)
            if grabar:
                datos = rgb.get_data()
                if datos is not None and getattr(datos, "size", 0):
                    ff.stdin.write(np.ascontiguousarray(datos).tobytes())
            q_med = robot.get_joint_positions()
            frames_medidos.append({**fr, "q": [round(float(q_med[i]), 4) for i in indices]})

        for _ in range(plano["fps"]):  # 1 s para que los paneles se asienten
            world.step(render=False)
        instalados, poses_finales = [], []
        for k, slot in enumerate(plano["paneles"]):
            pos, quat = paneles[k].get_world_pose()
            err = math.dist([float(v) for v in pos], slot["pos_m"])
            ang = math.degrees(2 * math.acos(min(1.0, abs(float(quat[0])))))
            poses_finales.append({"id": k, "pos_m": [round(float(v), 4) for v in pos],
                                  "quat": [round(float(v), 4) for v in quat]})
            if err <= TOL_POS_M and ang <= TOL_ANG_GRADOS:
                instalados.append(k)
        if grabar:
            ff.stdin.close()
            ff.wait()
    finally:
        app.close()

    n = len(plano["paneles"])
    total = plano["frames"][-1]["t_s"] if plano["frames"] else 0.0
    trayectoria = {**plano, "paneles": poses_finales, "frames": frames_medidos}
    resultado = {
        "version": 1, "metodo": "planificador", "fuente": "isaac", "politica": None,
        "metricas": {"paneles_instalados": len(instalados), "intentos": n,
                     "tasa_exito": round(len(instalados) / n, 3) if n else 0.0,
                     "ciclo_promedio_s": round(total / n, 2) if n else 0.0},
        "video": "video.mp4" if (a.dir / "video.mp4").exists() else None,
        "notas": f"Plan fijo v0 reproducido con física. Instalados: {instalados}.",
    }
    (a.dir / "trayectoria.json").write_text(json.dumps(trayectoria), encoding="utf-8")
    (a.dir / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado["metricas"]))


def _accion(q, indices):
    import numpy as np
    from isaacsim.core.utils.types import ArticulationAction
    return ArticulationAction(joint_positions=np.array(q), joint_indices=np.array(indices))


def _fijar(cuerpo, pos):
    import numpy as np
    cuerpo.set_world_pose(position=np.array(pos), orientation=np.array([1.0, 0, 0, 0]))
    cuerpo.set_linear_velocity(np.zeros(3))
    cuerpo.set_angular_velocity(np.zeros(3))


if __name__ == "__main__":
    main()
