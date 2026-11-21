"""Robot elegido del catálogo, construido con Isaac Lab en archivos aparte del terreno. Solo corre en el pod.

    $ISAACLAB_SH -p sim/robot_isaaclab.py --headless --salida /workspace/vivo/robot [--robot leapting-mmr] [--foto]

Escribe en --salida:
  robot.urdf            clon paramétrico del robot del catálogo (backend/viaz/urdf.py)
  robot.usd             el robot solo, convertido por Isaac Lab. El terreno no va en este archivo
  robot_vitrina.usda    el robot referenciado sobre un piso de arena con cielo y sol, para abrirlo en Isaac Sim
  robot_detallado.usda  robot.usd más el aspecto del robot real (sim/robot_visual.py): mallas, materiales y texturas
  robot_isaaclab.json   lo que Isaac midió del robot: articulaciones, masa y posición de la ventosa
  robot*.png            fotos de la vitrina (con --foto)

No entrena nada: arma el robot, lo deja 2 s en la pose de espera y revisa que la ventosa quede donde
dice la geometría del clon.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "sim"))
import robot_visual  # noqa: E402
from viaz import urdf  # noqa: E402

CATALOGO = REPO / "backend" / "viaz" / "catalogo" / "robots"
PRIM_ROBOT = "/World/Robot"
PRIM_CAMARA = "/World/Camara"

# Pose de espera (rad): el brazo adelante y la ventosa mirando hacia abajo (los tres ejes paralelos suman π).
POSE_ESPERA = {"shoulder_pan": 0.0, "shoulder_lift": 0.5, "elbow": 1.3, "wrist_1": math.pi - 1.8,
               "wrist_2": 0.0, "wrist_3": 0.0}
# Control de posición: cada articulación entrega su torque máximo con este error. Mismo criterio que el entorno RL.
ERROR_TORQUE_MAX_RAD = 0.05
RAZON_AMORTIGUAMIENTO = 8.0
DT_S = 1 / 120
PASOS_QUIETO = 240                      # 2 s en la pose de espera antes de medir
TOLERANCIA_VENTOSA_M = 0.005            # entre la ventosa medida y la geometría del clon con los ángulos medidos
TOLERANCIA_POSE_RAD = 0.02              # cuánto cede el brazo por su peso con el control de posición
FOTO_PX = (1280, 720)
PASOS_FOTO = 40
# Fotos: nombre -> (ojo, punto que mira). La lateral repite el encuadre de la foto del fabricante.
FOTOS = {"robot.png": ((8.6, -7.4, 4.0), (1.6, 0.0, 1.4)), "robot_lateral.png": ((1.4, -11.5, 1.9), (1.4, 0.0, 1.6)),
         "robot_ventosa.png": ((4.4, -2.2, 1.2), (2.6, 0.0, 2.2)), "robot_atras.png": ((-6.0, 4.6, 2.6), (0.6, 0.0, 1.3))}


def leer_robot(robot_id: str) -> dict:
    ruta = CATALOGO / f"{robot_id}.json"
    if not ruta.exists():
        raise SystemExit(f"'{robot_id}' no está en el catálogo; opciones: {sorted(p.stem for p in CATALOGO.glob('[!_]*.json'))}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def ganancias() -> tuple[dict, dict]:
    rigidez = {n: e / ERROR_TORQUE_MAX_RAD for n, e in urdf.ESFUERZO_NM.items()}
    return rigidez, {n: k / RAZON_AMORTIGUAMIENTO for n, k in rigidez.items()}


def ventosa_esperada(robot: dict, q: dict[str, float]) -> tuple[float, float, float]:
    """Origen del eslabón de la ventosa con el brazo en q (giro vertical en 0), según la geometría de urdf.py."""
    g = urdf.geometria(robot["alcance_m"], robot.get("fisica"))
    a = q["shoulder_lift"]
    b = a + q["elbow"]
    c = b + q["wrist_1"]
    x = g["montaje_x_m"] + g["l1_m"] * math.sin(a) + g["l2_m"] * math.sin(b) + (urdf.MUNECA[0] + urdf.MUNECA[1]) * math.sin(c)
    z = g["hombro_z_m"] + g["l1_m"] * math.cos(a) + g["l2_m"] * math.cos(b) + (urdf.MUNECA[0] + urdf.MUNECA[1]) * math.cos(c)
    return (round(x, 4), 0.0, round(z, 4))


def convertir(ruta_urdf: Path, carpeta_usd: Path) -> Path:
    """Convierte robot.urdf a robot.usd con Isaac Lab. Devuelve la ruta de robot.usd."""
    from isaaclab.sim.converters import UrdfConverter, UrdfConverterCfg

    rigidez, amortiguamiento = ganancias()
    return Path(UrdfConverter(UrdfConverterCfg(
        asset_path=str(ruta_urdf), usd_dir=str(carpeta_usd), usd_file_name="robot.usd", force_usd_conversion=True,
        fix_base=True,                    # la base se mueve por código (RF-INT-18), no con tracción
        merge_fixed_joints=True, self_collision=False,
        joint_drive=UrdfConverterCfg.JointDriveCfg(
            target_type="position",
            gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=rigidez, damping=amortiguamiento)),
    )).usd_path)


def articulacion_cfg(ruta_usd: Path, prim: str = PRIM_ROBOT):
    """ArticulationCfg de Isaac Lab para el robot ya convertido (robot.usd o robot_detallado.usda)."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import ArticulationCfg

    rigidez, amortiguamiento = ganancias()
    return ArticulationCfg(
        prim_path=prim,
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(ruta_usd),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(enabled_self_collisions=False)),
        init_state=ArticulationCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0), joint_pos=dict(POSE_ESPERA)),
        actuators={"brazo": ImplicitActuatorCfg(
            joint_names_expr=list(urdf.ARTICULACIONES), stiffness=rigidez, damping=amortiguamiento,
            effort_limit_sim=dict(urdf.ESFUERZO_NM), velocity_limit_sim=urdf.VELOCIDAD_RAD_S)},
    )


def _vitrina(sim_utils, texturas: Path | None) -> None:
    """Piso de arena, cielo y sol. Nada del parque solar."""
    piso = sim_utils.CuboidCfg(size=(60.0, 60.0, 0.1), collision_props=sim_utils.CollisionPropertiesCfg(),
                               visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.55, 0.44, 0.31), roughness=0.95))
    piso.func("/World/Piso", piso, translation=(0.0, 0.0, -0.052))
    cielo = sim_utils.DomeLightCfg(intensity=1100.0, texture_file=str(texturas / "cielo.png")) if texturas else \
        sim_utils.DomeLightCfg(intensity=800.0, color=(0.72, 0.84, 1.0))
    cielo.func("/World/LuzCielo", cielo)
    sol = sim_utils.DistantLightCfg(intensity=3200.0, color=(1.0, 0.95, 0.86), angle=0.8)
    sol.func("/World/LuzSol", sol, orientation=(0.86, 0.25, -0.35, 0.27))


def _fijar_pose_en_usd(stage) -> None:
    """Deja la pose de espera escrita en la vitrina: al dar Play en Isaac Sim el brazo parte ahí y se queda."""
    from pxr import PhysxSchema, Usd, UsdPhysics

    for prim in Usd.PrimRange(stage.GetPrimAtPath(PRIM_ROBOT)):
        if prim.IsA(UsdPhysics.RevoluteJoint) and prim.GetName() in POSE_ESPERA:
            grados = math.degrees(POSE_ESPERA[prim.GetName()])
            UsdPhysics.DriveAPI.Apply(prim, "angular").CreateTargetPositionAttr().Set(grados)
            PhysxSchema.JointStateAPI.Apply(prim, "angular").CreatePositionAttr().Set(grados)


def main() -> None:
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", default="leapting-mmr", help="id del catálogo (backend/viaz/catalogo/robots)")
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--foto", action="store_true", help="guarda robot.png")
    AppLauncher.add_app_launcher_args(ap)
    a = ap.parse_args()
    a.enable_cameras = a.enable_cameras or a.foto
    AppLauncher(a)

    import isaaclab.sim as sim_utils
    import omni.usd
    import torch
    from isaaclab.assets import Articulation

    datos = leer_robot(a.robot)
    a.salida.mkdir(parents=True, exist_ok=True)
    ruta_urdf = a.salida / "robot.urdf"
    ruta_urdf.write_text(urdf.generar(datos["id"].replace("-", "_"), datos["alcance_m"], datos.get("fisica")), encoding="utf-8")

    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=DT_S, device=a.device))
    ruta_usd, apariencia = robot_visual.construir(convertir(ruta_urdf, a.salida), datos)
    texturas = a.salida / "texturas" if apariencia["detalle"] else None
    _vitrina(sim_utils, texturas)
    robot = Articulation(articulacion_cfg(ruta_usd))
    camara = None
    if a.foto:
        from isaaclab.sensors import Camera, CameraCfg

        camara = Camera(CameraCfg(prim_path=PRIM_CAMARA, width=FOTO_PX[0], height=FOTO_PX[1], data_types=["rgb"],
                                  spawn=sim_utils.PinholeCameraCfg(focal_length=22.0, clipping_range=(0.1, 100.0))))
    stage = omni.usd.get_context().get_stage()
    if texturas:
        robot_visual.suelo_de_arena(stage, "/World/Arena", 60.0, texturas)
    _fijar_pose_en_usd(stage)
    stage.GetRootLayer().Export(str(a.salida / "robot_vitrina.usda"))

    sim.reset()
    q = robot.data.default_joint_pos.clone()
    robot.write_joint_state_to_sim(q, torch.zeros_like(q))
    robot.set_joint_position_target(q)
    for _ in range(PASOS_QUIETO):
        robot.write_data_to_sim()
        sim.step()
        robot.update(DT_S)

    q_medido = dict(zip(robot.joint_names, robot.data.joint_pos[0].tolist()))
    esperada = ventosa_esperada(datos, q_medido)
    medida = robot.data.body_pos_w[0, robot.body_names.index("efector")].tolist()
    error = math.dist(esperada, medida)
    informe = {
        "robot_id": datos["id"], "alcance_m": datos["alcance_m"], "carga_util_kg": datos["carga_util_kg"],
        "articulaciones": robot.joint_names, "eslabones": robot.body_names,
        "masa_kg": round(float(robot.root_physx_view.get_masses().sum()), 1),
        "masa_urdf_kg": urdf.masa_total(datos["alcance_m"], datos.get("fisica")),
        "pose_espera_rad": {n: round(v, 4) for n, v in q_medido.items()},
        "error_articulacion_max_rad": round(float((robot.data.joint_pos - q).abs().max()), 5),
        "ventosa_esperada_m": esperada, "ventosa_medida_m": [round(v, 4) for v in medida],
        "error_ventosa_m": round(error, 4), "usd": ruta_usd.name, "apariencia": apariencia,
    }
    informe["ok"] = error <= TOLERANCIA_VENTOSA_M and informe["error_articulacion_max_rad"] <= TOLERANCIA_POSE_RAD
    if camara:
        from PIL import Image

        for nombre, (ojo, mira) in FOTOS.items():
            camara.set_world_poses_from_view(torch.tensor([ojo], device=sim.device), torch.tensor([mira], device=sim.device))
            for _ in range(PASOS_FOTO):      # el render necesita varios cuadros para asentar luz y sombras
                sim.render()
                camara.update(DT_S)
            Image.fromarray(camara.data.output["rgb"][0, ..., :3].cpu().numpy()).save(a.salida / nombre)
        informe["fotos"] = list(FOTOS)
    (a.salida / "robot_isaaclab.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False), flush=True)
    # app.close() no vuelve en el pod con las cámaras activas (medido: 9 min colgado), por eso se sale directo.
    os._exit(0 if informe["ok"] else 1)


if __name__ == "__main__":
    main()
