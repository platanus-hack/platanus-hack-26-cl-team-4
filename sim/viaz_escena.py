"""Escena de VIAZ para Isaac Lab: planta estática + paneles con masa + robot clonado.

Dos partes:
- describir(): Python puro. Calcula qué va en la escena (posiciones, tamaños, masas, materiales).
  Se prueba sin Isaac (backend/tests/test_escena.py).
- construir_cfg(): arma el InteractiveSceneCfg de Isaac Lab. Importa isaaclab: solo corre en el pod.
  SIN PROBAR EN ISAAC LAB: los nombres de la API son de Isaac Lab 2.x y hay que verificarlos en el pod.

Capas (docs/escena-isaac.md):
- Estática: escena.usd de generar_escena.py (suelo, tubos, postes; colisión + fricción, sin masa).
- Dinámica: un RigidObject por panel (masa de entorno.json, fricción, sin rebote).
- Robot: robot.urdf como Articulation (masas e inercias del URDF) con actuadores de posición.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fisica  # noqa: E402
import plan  # noqa: E402

COLOR_PANEL = (0.05, 0.1, 0.35)

# Ganancias de los actuadores del brazo (PD implícito de PhysX). Rígidas para seguir el plan
# con un panel de ~35 kg; calibrar en el pod si el brazo oscila o no llega.
RIGIDEZ = {"shoulder_pan": 8000.0, "shoulder_lift": 12000.0, "elbow": 8000.0,
           "wrist_1": 2000.0, "wrist_2": 1000.0, "wrist_3": 1000.0}
AMORTIGUAMIENTO = {k: v / 10 for k, v in RIGIDEZ.items()}


def altura_reposo_panel(entorno: dict) -> float:
    """Z del centro de un panel apoyado sobre el tubo (cara de arriba del tubo + medio espesor)."""
    return round(entorno["estructura"]["altura_m"] + plan.TUBO_R + fisica.PANEL_ESPESOR_M / 2, 4)


def describir(entorno: dict, n_paneles: int, caida_m: float = 0.0, con_robot: bool = False,
              clon: dict | None = None) -> dict:
    """Qué va en la escena.

    caida_m > 0: los paneles parten caida_m sobre su slot (prueba de física: se sueltan y se asientan).
    con_robot: agrega el robot en el pasillo de la fila 0, frente al primer slot.
    """
    p = entorno["panel"]
    slots = plan.slots(entorno, n_paneles)
    paneles = [{
        "nombre": f"panel_{k}",
        "tam_m": (p["ancho_m"], p["largo_m"], fisica.PANEL_ESPESOR_M),
        "masa_kg": p["peso_kg"],
        "pos_inicial_m": (s[0], s[1], round(s[2] + caida_m, 4)),
        "pos_esperada_m": (s[0], s[1], altura_reposo_panel(entorno)),
        "material": fisica.material("panel"),
    } for k, s in enumerate(slots)]
    desc = {
        "dt_s": fisica.DT_S,
        "render_cada": fisica.RENDER_CADA,
        "estatica": {"usd": "escena.usd"},
        "paneles": paneles,
        "robot": None,
    }
    if con_robot:
        if clon is None:
            raise ValueError("con_robot necesita clon.json")
        x0 = (slots[0][0] if slots else plan.INICIO_X) - clon["geometria"]["montaje_x_m"]
        desc["robot"] = {
            "urdf": "robot.urdf",
            "pos_inicial_m": (round(x0, 4), plan.distancia_pasillo(entorno), 0.0),
            "q_inicial": dict(zip(["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"],
                                  plan.poses(entorno, clon["geometria"])["casa"])),
            "rigidez": RIGIDEZ, "amortiguamiento": AMORTIGUAMIENTO,
        }
    return desc


def sim_cfg():
    """SimulationCfg con los parámetros de sim/fisica.py."""
    import isaaclab.sim as sim_utils

    return sim_utils.SimulationCfg(
        dt=fisica.DT_S,
        render_interval=fisica.RENDER_CADA,
        gravity=(0.0, 0.0, -fisica.GRAVEDAD),
        physx=sim_utils.PhysxCfg(enable_ccd=True),  # CCD: los paneles delgados no atraviesan el tubo
    )


def construir_cfg(desc: dict, carpeta: Path):
    """InteractiveSceneCfg de Isaac Lab a partir de describir(). Llamar después de crear la app."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.utils import configclass

    @configclass
    class EscenaViazCfg(InteractiveSceneCfg):
        luz = AssetBaseCfg(prim_path="/World/Luz", spawn=sim_utils.DomeLightCfg(intensity=2500.0))
        planta = AssetBaseCfg(prim_path="/World/Planta",
                              spawn=sim_utils.UsdFileCfg(usd_path=str(carpeta / desc["estatica"]["usd"])))

    cfg = EscenaViazCfg(num_envs=1, env_spacing=0.0, replicate_physics=False)

    for p in desc["paneles"]:
        m = p["material"]
        setattr(cfg, p["nombre"], RigidObjectCfg(
            prim_path=f"/World/Paneles/{p['nombre']}",
            spawn=sim_utils.CuboidCfg(
                size=p["tam_m"],
                rigid_props=sim_utils.RigidBodyPropertiesCfg(
                    solver_position_iteration_count=fisica.ITER_POSICION,
                    solver_velocity_iteration_count=fisica.ITER_VELOCIDAD,
                    max_depenetration_velocity=fisica.DESPENETRACION_MAX_M_S,
                ),
                mass_props=sim_utils.MassPropertiesCfg(mass=p["masa_kg"]),
                collision_props=sim_utils.CollisionPropertiesCfg(
                    contact_offset=fisica.CONTACTO_OFFSET_M, rest_offset=0.0),
                physics_material=sim_utils.RigidBodyMaterialCfg(
                    static_friction=m["estatica"], dynamic_friction=m["dinamica"], restitution=m["restitucion"]),
                visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=COLOR_PANEL, metallic=0.4, roughness=0.35),
            ),
            init_state=RigidObjectCfg.InitialStateCfg(pos=p["pos_inicial_m"]),
        ))

    r = desc["robot"]
    if r:
        from isaaclab.actuators import ImplicitActuatorCfg
        from isaaclab.assets import ArticulationCfg
        from isaaclab.sim.converters import UrdfConverterCfg

        cfg.robot = ArticulationCfg(
            prim_path="/World/Robot",
            spawn=sim_utils.UrdfFileCfg(
                asset_path=str(carpeta / r["urdf"]),
                fix_base=False,
                merge_fixed_joints=False,
                joint_drive=UrdfConverterCfg.JointDriveCfg(
                    gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=0.0)),
                activate_contact_sensors=False,
            ),
            init_state=ArticulationCfg.InitialStateCfg(pos=r["pos_inicial_m"], joint_pos=r["q_inicial"]),
            actuators={"brazo": ImplicitActuatorCfg(
                joint_names_expr=list(r["rigidez"]), stiffness=r["rigidez"], damping=r["amortiguamiento"])},
        )
    return cfg
