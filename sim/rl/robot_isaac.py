"""Robot de la corrida como articulación de Isaac Lab. Solo corre en el pod.

El robot sale de robot.urdf: geometría, masas, recorrido, torque y velocidad máximos (RF-INT-23).
Lo único que agrega el entorno son las ganancias del control de posición, que se derivan del torque
máximo de cada articulación para que sirvan con cualquier robot del catálogo.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fisica  # noqa: E402

from .corrida import Corrida  # noqa: E402
from .robot import ARTICULACIONES  # noqa: E402

# Cada articulación entrega su torque máximo con este error de posición. Menos error = brazo más rígido.
ERROR_TORQUE_MAX_RAD = 0.05
# Amortiguamiento = rigidez / 8: cerca del crítico para un brazo que carga el panel a 2 m.
RAZON_AMORTIGUAMIENTO = 8.0
# Eslabones que nunca deben tocar nada. La base carga la pila y la ventosa toca el panel.
ESLABONES_SIN_CONTACTO = ("hombro", "brazo", "antebrazo", "muneca_1", "muneca_2")


def ganancias(c: Corrida) -> tuple[dict, dict]:
    rigidez = {u.nombre: u.esfuerzo / ERROR_TORQUE_MAX_RAD for u in c.robot.articulaciones}
    return rigidez, {n: k / RAZON_AMORTIGUAMIENTO for n, k in rigidez.items()}


def ruta_urdf(c: Corrida) -> Path:
    """robot.urdf de la carpeta. Si la corrida no lo trae, lo escribe en una carpeta temporal."""
    ruta = c.carpeta / c.clon.get("urdf", "robot.urdf")
    if ruta.exists():
        return ruta
    ruta = Path(tempfile.mkdtemp(prefix="viaz_urdf_")) / "robot.urdf"
    ruta.write_text(c.urdf, encoding="utf-8")
    return ruta


def articulacion_cfg(c: Corrida, pos: tuple[float, float, float], q_inicial: tuple[float, ...],
                     prim: str = "{ENV_REGEX_NS}/Robot"):
    """ArticulationCfg con la base fija. La base se mueve por código (RF-INT-18), no con tracción."""
    import isaaclab.sim as sim_utils
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.assets import ArticulationCfg
    from isaaclab.sim.converters import UrdfConverterCfg

    rigidez, amortiguamiento = ganancias(c)
    arts = c.robot.articulaciones
    return ArticulationCfg(
        prim_path=prim,
        spawn=sim_utils.UrdfFileCfg(
            asset_path=str(ruta_urdf(c)),
            fix_base=True,
            merge_fixed_joints=True,
            self_collision=False,
            joint_drive=UrdfConverterCfg.JointDriveCfg(
                gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=0.0)),
            activate_contact_sensors=True,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(max_depenetration_velocity=fisica.DESPENETRACION_MAX_M_S),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=False,
                solver_position_iteration_count=fisica.ITER_POSICION,
                solver_velocity_iteration_count=fisica.ITER_VELOCIDAD),
        ),
        init_state=ArticulationCfg.InitialStateCfg(pos=pos, joint_pos=dict(zip(ARTICULACIONES, q_inicial))),
        actuators={"brazo": ImplicitActuatorCfg(
            joint_names_expr=list(ARTICULACIONES), stiffness=rigidez, damping=amortiguamiento,
            effort_limit_sim={u.nombre: u.esfuerzo for u in arts},
            velocity_limit_sim={u.nombre: u.velocidad for u in arts})},
    )
