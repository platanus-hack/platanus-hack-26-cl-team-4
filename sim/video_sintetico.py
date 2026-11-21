"""Video de un parque con geometría conocida, para medir el error del agente Entorno (fase 0). Solo corre en el pod.

    /venv/isaac/bin/python sim/video_sintetico.py --dir DIR [--segundos 20] [--fps 10]

DIR trae entorno.json (la verdad) y escena.usd (python sim/generar_escena.py --dir DIR). Escribe DIR/video_sintetico.mp4:
una persona que camina por el pasillo entre la fila 0 y la 1 con el celular a 1,6 m, mirando a los lados, y al final
gira para mirar a través de las filas. La cámara tiembla un poco, como en la mano.

Después: medir_entorno.py sobre ese video y comparar contra entorno.json (sim/comparar_medidas.py).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

ALTURA_OJO_M = 1.6


def recorrido(entorno: dict, n: int) -> list[tuple[tuple, tuple]]:
    """(ojo, mira) de cada cuadro. Coordenadas de generar_escena: filas a lo largo de X, fila i en y = -i · separación."""
    f = entorno["filas"]
    largo, sep = f["largo_m"], f["separacion_m"]
    y_pasillo = -sep / 2 if f["cantidad"] > 1 else 2.5
    poses = []
    caminata = int(n * 0.75)
    for k in range(n):
        if k < caminata:   # camina por el pasillo y mira a los lados
            s = k / max(1, caminata - 1)
            x = -3.0 + s * (largo * 0.75 + 3.0)
            giro = math.radians(35) * math.sin(2 * math.pi * 1.5 * s)
            ojo = (x, y_pasillo + 0.15 * math.sin(7 * s), ALTURA_OJO_M + 0.03 * math.sin(11 * s))
            mira = (x + 6 * math.cos(giro), y_pasillo + 6 * math.sin(giro), 1.0)
        else:              # se detiene y gira para mirar a través de las filas
            s = (k - caminata) / max(1, n - caminata - 1)
            x = largo * 0.75
            giro = math.radians(-20 - 140 * s)
            ojo = (x, y_pasillo, ALTURA_OJO_M)
            mira = (x + 8 * math.cos(giro), y_pasillo + 8 * math.sin(giro), 0.9)
        poses.append((ojo, mira))
    return poses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--segundos", type=float, default=20.0)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--resolucion", default="1280x720")
    a = ap.parse_args()
    ancho, alto = (int(x) for x in a.resolucion.split("x"))
    entorno = json.loads((a.dir / "entorno.json").read_text(encoding="utf-8"))

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": ancho, "height": alto})
    import numpy as np
    import omni.replicator.core as rep
    import omni.usd
    from pxr import Gf, UsdGeom

    omni.usd.get_context().open_stage(str((a.dir / "escena.usd").resolve()))
    for _ in range(30):
        app.update()
    stage = omni.usd.get_context().get_stage()
    camara = UsdGeom.Camera.Define(stage, "/World/CamaraSintetica")
    camara.CreateFocalLengthAttr(18.0)          # ~ gran angular de un celular
    camara.CreateHorizontalApertureAttr(20.955)
    camara.CreateClippingRangeAttr(Gf.Vec2f(0.05, 5000.0))
    xform = UsdGeom.Xformable(camara)
    op = xform.AddTransformOp()
    producto = rep.create.render_product(str(camara.GetPath()), (ancho, alto))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([producto])

    import imageio_ffmpeg
    salida = a.dir / "video_sintetico.mp4"
    ffmpeg = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-s", f"{ancho}x{alto}", "-r", str(a.fps), "-i", "-",
                               "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(salida)], stdin=subprocess.PIPE)
    poses = recorrido(entorno, int(a.segundos * a.fps))
    for k, (ojo, mira) in enumerate(poses):
        vista = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*ojo), Gf.Vec3d(*mira), Gf.Vec3d(0, 0, 1))
        op.Set(vista.GetInverse())
        rep.orchestrator.step(rt_subframes=8 if k else 32, delta_time=0.0)
        img = np.asarray(rgb.get_data())[..., :3]
        ffmpeg.stdin.write(np.ascontiguousarray(img, dtype=np.uint8).tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(json.dumps({"video": str(salida), "cuadros": len(poses), "fps": a.fps,
                      "verdad": {"filas": entorno["filas"], "estructura": entorno["estructura"], "panel": entorno["panel"]}}))
    app.close()


if __name__ == "__main__":
    main()
