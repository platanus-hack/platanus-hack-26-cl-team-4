"""Las 4 vistas fijas de la escena con el robot (docs/calidad-virtualizacion.md): general, detalle a 1 m, robot y
escala con una figura humana de 1,75 m y una puerta de 2,1 m. Solo apariencia: no entrena ni evalúa.

    $ISAACLAB_SH -p sim/animar/vistas.py --entorno E --tarea T --robot R --escena S --salida DIR [--checkpoint C]

Con --checkpoint, el robot se para con la política antes de las fotos; sin él, se ve en su pose inicial.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

FIGURA_M = 1.75
PUERTA_M = 2.1
PASOS_POLITICA = 60


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--checkpoint", type=Path)
    a = ap.parse_args()
    app = comun.lanzar(a, camaras=True)
    comun.ejecutar(app, lambda: vistas(a))


def _figuras(stage, raiz: str, x: float, y: float) -> None:
    """Figura humana (cápsula de 1,75 m) y marco de puerta de 2,1 m al lado del robot. Sin física."""
    from pxr import Gf, UsdGeom

    cuerpo = UsdGeom.Capsule.Define(stage, f"{raiz}/Escala/Figura")
    cuerpo.CreateRadiusAttr(0.18)
    cuerpo.CreateHeightAttr(FIGURA_M - 2 * 0.18)
    cuerpo.CreateAxisAttr("Z")
    UsdGeom.XformCommonAPI(cuerpo).SetTranslate(Gf.Vec3d(x, y + 1.0, FIGURA_M / 2))
    cuerpo.CreateDisplayColorAttr([(0.85, 0.35, 0.2)])
    for k, (dy, alto) in enumerate(((-0.45, PUERTA_M), (0.45, PUERTA_M))):
        poste = UsdGeom.Cube.Define(stage, f"{raiz}/Escala/Puerta_{k}")
        poste.CreateSizeAttr(1.0)
        UsdGeom.XformCommonAPI(poste).SetTranslate(Gf.Vec3d(x, y + 2.2 + dy, alto / 2))
        UsdGeom.XformCommonAPI(poste).SetScale(Gf.Vec3f(0.06, 0.06, alto))
        poste.CreateDisplayColorAttr([(0.2, 0.2, 0.2)])
    dintel = UsdGeom.Cube.Define(stage, f"{raiz}/Escala/Puerta_dintel")
    dintel.CreateSizeAttr(1.0)
    UsdGeom.XformCommonAPI(dintel).SetTranslate(Gf.Vec3d(x, y + 2.2, PUERTA_M))
    UsdGeom.XformCommonAPI(dintel).SetScale(Gf.Vec3f(0.06, 0.96, 0.06))
    dintel.CreateDisplayColorAttr([(0.2, 0.2, 0.2)])


def vistas(a) -> dict:
    import torch
    from PIL import Image

    sys.path.insert(0, str(comun.SIM))
    from rl import grabacion

    c = comun.leer(a)
    env = comun.crear(comun.cfg_sala(c, 1, a.device, render=True), render=True)
    o = env.scene.env_origins[0].tolist()
    if a.checkpoint:
        envuelto, politica = comun.cargar_politica(env, c, a.checkpoint, a.device)
        obs = envuelto.get_observations()
        for _ in range(PASOS_POLITICA):
            env.command_manager.get_term("base_velocity").vel_command_b[:] = 0.0
            with torch.inference_mode():
                obs, _, _, _ = envuelto.step(politica(obs))
    else:
        env.reset()
    pos = env.scene["robot"].data.root_pos_w[0].tolist()
    x, y = pos[0] - o[0], pos[1] - o[1]
    esp = c.entorno["espacio"]
    _figuras(env.sim.stage, "/World/envs/env_0", x + 1.2, y)
    a.salida.mkdir(parents=True, exist_ok=True)
    cam = comun.Camarografo(env, c)
    tomas = {
        "1_general": ((esp["largo_m"] - 0.5, esp["ancho_m"] - 0.5, esp["alto_m"] - 0.3),
                      (esp["largo_m"] * 0.35, esp["ancho_m"] * 0.45, 0.6)),
        "2_detalle": None,      # a 1 m del robot, con la cámara que lo sigue
        "3_robot": None,
        "4_escala": ((x + 1.2 + 4.5, y + 1.2, 1.4), (x + 1.2, y + 1.2, 1.0)),
    }
    archivos = []
    for nombre, toma in tomas.items():
        if nombre == "2_detalle":
            env.sim.set_camera_view([o[0] + x + 1.0 * math.cos(0.6), o[1] + y + 1.0 * math.sin(0.6), o[2] + 1.3],
                                    [o[0] + x, o[1] + y, o[2] + 1.0])
        elif nombre == "3_robot":
            cam.mover(x, y, saltar=True)
        else:
            ojo, mira = toma
            env.sim.set_camera_view([o[k] + ojo[k] for k in range(3)], [o[k] + mira[k] for k in range(3)])
        for _ in range(grabacion.CUADROS_DE_CARGA):
            env.sim.render()
        ruta = a.salida / f"{nombre}.png"
        Image.fromarray(env.render()[..., :3]).save(ruta)
        archivos.append(str(ruta))
    return {"ok": True, "vistas": archivos}


if __name__ == "__main__":
    main()
