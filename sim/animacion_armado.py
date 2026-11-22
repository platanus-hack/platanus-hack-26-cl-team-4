"""Animación de armado del robot detallado: las piezas llegan una por una y al final el brazo se pliega. Solo en el pod.

    /venv/isaac/bin/python sim/animacion_armado.py --salida armado.mp4 [--fps 30] [--resolucion 1920x1080]

Usa la escena vitrina del robot (piso de arena, cielo y sol: robot_vitrina.usda) y el robot detallado limpio
(exportado/leapting_mmr_detallado.usda: 22 piezas visibles, sin formas simples ni colisiones).

Guion:
1. Escena vacía (0,6 s).
2. Cada pieza baja desde arriba y se asienta en su lugar, en orden de armado: base, cabina, remolque, luces,
   y después el brazo de abajo hacia arriba hasta la ventosa. Una pieza nueva cada 0,33 s.
3. Con el robot completo, el brazo se pliega de la pose cero (vertical) a su pose de espera (robot_isaaclab.json),
   con la cinemática del URDF.
4. El robot terminado queda en pantalla. La cámara gira despacio alrededor durante todo el video.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

DIR = Path("/workspace/vivo/robot")
VITRINA = DIR / "leapting-mmr" / "robot_vitrina.usda"
ROBOT = DIR / "exportado" / "leapting_mmr_detallado.usda"
URDF = DIR / "leapting-mmr" / "robot.urdf"
POSE = DIR / "leapting-mmr" / "robot_isaaclab.json"

# (eslabón, malla, desde dónde llega: desplazamiento en metros respecto de su lugar)
PIEZAS = [
    ("base_link", "goma", (0.0, 0.0, 3.0)),        # orugas
    ("base_link", "negro", (0.0, 0.0, 3.2)),
    ("base_link", "verde", (-1.5, 0.0, 3.0)),
    ("base_link", "gris", (1.8, 0.0, 3.0)),        # remolque
    ("base_link", "amarillo", (1.8, 1.2, 2.5)),    # ruedas del remolque
    ("base_link", "aluminio", (1.5, -1.2, 3.0)),
    ("base_link", "blanco", (-1.5, 0.0, 3.5)),     # cabina y cubierta
    ("base_link", "azul", (0.0, 1.5, 3.0)),
    ("base_link", "rojo", (0.0, -1.5, 2.5)),
    ("base_link", "foco", (0.0, 0.0, 2.5)),
    ("base_link", "baliza", (0.0, 0.0, 2.5)),
    ("hombro", "tela", (0.0, 0.0, 2.5)),
    ("brazo", "tela", (0.0, 0.0, 2.5)),
    ("antebrazo", "tela", (0.0, 0.0, 2.5)),
    ("antebrazo", "goma", (0.0, 0.0, 2.0)),
    ("muneca_1", "tela", (0.0, 0.0, 2.0)),
    ("muneca_2", "aluminio", (0.0, 0.0, 2.0)),
    ("efector", "aluminio", (0.0, 0.0, 2.0)),
    ("efector", "gris", (0.0, 0.0, 2.0)),
    ("efector", "negro", (0.0, 0.0, 2.0)),
    ("efector", "goma", (0.0, 0.0, 1.8)),
    ("efector", "azul", (0.0, 0.0, 1.8)),
]
INICIO_S, CADA_S, BAJADA_S = 0.6, 0.33, 0.75
PAUSA_S, PLIEGUE_S, FINAL_S = 0.4, 1.8, 2.5
CENTRO = (1.3, 0.0, 1.6)            # a dónde mira la cámara
RADIO_M, ALTO_M = 13.0, 4.8
GIRO_GRADOS = (-62.0, -12.0)        # la cámara recorre este arco durante el video


def _suave(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3                       # sale rápido y se asienta despacio


def _suave_doble(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 3 * x * x - 2 * x * x * x


def cadena_urdf() -> list[dict]:
    """Articulaciones del brazo en orden: padre, hijo, origen y eje (el URDF no rota los orígenes)."""
    r = ET.parse(URDF).getroot()
    cadena = []
    for j in r.findall("joint"):
        if j.get("type") != "revolute":
            continue
        cadena.append({"nombre": j.get("name"), "padre": j.find("parent").get("link"), "hijo": j.find("child").get("link"),
                       "origen": [float(v) for v in j.find("origin").get("xyz").split()],
                       "eje": [float(v) for v in j.find("axis").get("xyz").split()]})
    return cadena


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--resolucion", default="1920x1080")
    a = ap.parse_args()
    ancho, alto = (int(x) for x in a.resolucion.split("x"))

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": ancho, "height": alto})
    import imageio_ffmpeg
    import numpy as np
    import omni.replicator.core as rep
    import omni.usd
    from pxr import Gf, UsdGeom

    omni.usd.get_context().open_stage(str(VITRINA))
    for _ in range(20):
        app.update()
    st = omni.usd.get_context().get_stage()
    for ruta in ("/World/Robot", "/physicsScene"):        # el robot de la vitrina y la física no van
        p = st.GetPrimAtPath(ruta)
        if p.IsValid():
            p.SetActive(False)
    raiz = "/World/Armado"
    st.DefinePrim(raiz, "Xform").GetReferences().AddReference(str(ROBOT), "/leapting_mmr")
    for _ in range(10):
        app.update()

    # Eslabones: transformaciones en la pose cero, leídas del USD, y la cinemática para plegar el brazo.
    cadena = cadena_urdf()
    q_espera = json.loads(POSE.read_text())["pose_espera_rad"]
    eslabones = {}
    for nombre in ["base_link"] + [j["hijo"] for j in cadena]:
        x = UsdGeom.Xformable(st.GetPrimAtPath(f"{raiz}/{nombre}"))
        ops = {o.GetOpName(): o for o in x.GetOrderedXformOps()}
        eslabones[nombre] = (ops["xformOp:translate"], ops["xformOp:orient"])

    def poner_pose(fraccion: float) -> None:
        mundo = {"base_link": Gf.Matrix4d(1.0)}
        for j in cadena:
            ang = math.degrees(q_espera.get(j["nombre"], 0.0) * fraccion)
            rot = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(*j["eje"]), ang))
            tras = Gf.Matrix4d().SetTranslate(Gf.Vec3d(*j["origen"]))
            mundo[j["hijo"]] = rot * tras * mundo[j["padre"]]     # USD: vector fila, el local va primero
            t, o = eslabones[j["hijo"]]
            t.Set(mundo[j["hijo"]].ExtractTranslation())
            o.Set(Gf.Quatd(mundo[j["hijo"]].ExtractRotationQuat()))

    piezas = []
    for eslabon, malla, desde in PIEZAS:
        prim = st.GetPrimAtPath(f"{raiz}/{eslabon}/detalle/{malla}")
        if not prim.IsValid():
            print(f"aviso: falta la pieza {eslabon}/{malla}", flush=True)
            continue
        op = UsdGeom.Xformable(prim).AddTranslateOp(opSuffix="armado")
        piezas.append((prim, op, Gf.Vec3d(*desde)))

    camara = UsdGeom.Camera.Define(st, "/World/CamaraArmado")
    camara.CreateFocalLengthAttr(22.0)
    camara.CreateHorizontalApertureAttr(20.955)
    camara.CreateClippingRangeAttr(Gf.Vec2f(0.05, 5000.0))
    op_camara = UsdGeom.Xformable(camara).AddTransformOp()
    producto = rep.create.render_product(str(camara.GetPath()), (ancho, alto))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([producto])

    fin_armado = INICIO_S + (len(piezas) - 1) * CADA_S + BAJADA_S
    inicio_pliegue = fin_armado + PAUSA_S
    total = inicio_pliegue + PLIEGUE_S + FINAL_S
    cuadros = int(total * a.fps)
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-s", f"{ancho}x{alto}", "-r", str(a.fps), "-i", "-",
                               "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                               "-movflags", "+faststart", str(a.salida)], stdin=subprocess.PIPE)
    centro = Gf.Vec3d(*CENTRO)
    for k in range(cuadros):
        t = k / a.fps
        for i, (prim, op, desde) in enumerate(piezas):
            avance = (t - (INICIO_S + i * CADA_S)) / BAJADA_S
            imagen = UsdGeom.Imageable(prim)
            if avance < 0:
                imagen.MakeInvisible()
                continue
            imagen.MakeVisible()
            op.Set(desde * (1 - _suave(avance)))
        poner_pose(_suave_doble((t - inicio_pliegue) / PLIEGUE_S))
        ang = math.radians(GIRO_GRADOS[0] + (GIRO_GRADOS[1] - GIRO_GRADOS[0]) * _suave_doble(t / total))
        ojo = Gf.Vec3d(CENTRO[0] + RADIO_M * math.cos(ang), CENTRO[1] + RADIO_M * math.sin(ang), ALTO_M)
        op_camara.Set(Gf.Matrix4d().SetLookAt(ojo, centro, Gf.Vec3d(0, 0, 1)).GetInverse())
        rep.orchestrator.step(rt_subframes=32 if k == 0 else 8, delta_time=0.0)
        img = np.asarray(rgb.get_data())[..., :3]
        ffmpeg.stdin.write(np.ascontiguousarray(img, dtype=np.uint8).tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(json.dumps({"video": str(a.salida), "segundos": round(total, 2), "cuadros": cuadros, "piezas": len(piezas)}), flush=True)
    app.close()


if __name__ == "__main__":
    main()
