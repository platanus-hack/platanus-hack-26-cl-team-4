"""Clon paramétrico: base móvil + brazo de 6 ejes + ventosa, con geometría primitiva (sin mallas).

Las medidas salen del robot real (alcance). Las mismas medidas van a clon.json["geometria"],
y sim/plan.py las usa para planificar la tarea. Si cambias algo aquí, revisa sim/plan.py.
"""
from __future__ import annotations

ARTICULACIONES = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"]

# Base: caja de 1,6 × 1,0 × 0,6 m sobre ruedas de 0,2 m de radio. Origen de base_link en el suelo.
BASE = (1.6, 1.0, 0.6)
RUEDA_R = 0.2
CUBIERTA_Z = RUEDA_R + BASE[2]          # 0,8 m: techo de la base, donde va la pila de paneles
MONTAJE_X = 0.45                        # el brazo va adelante
HOMBRO_ALTO = 0.3                       # columna entre la base y el eje del hombro
MUNECA = (0.15, 0.1, 0.05)              # muñeca 1, muñeca 2, placa de la ventosa
PILA_X = -0.35                          # la pila de paneles va atrás


def geometria(alcance_m: float) -> dict:
    """Reparte el alcance entre brazo y antebrazo (el resto es la muñeca)."""
    util = max(alcance_m - sum(MUNECA), 0.6)
    return {
        "l1_m": round(util * 0.52, 3),
        "l2_m": round(util * 0.48, 3),
        "muneca_m": round(sum(MUNECA), 3),
        "montaje_x_m": MONTAJE_X,
        "hombro_z_m": round(CUBIERTA_Z + HOMBRO_ALTO, 3),
        "cubierta_z_m": CUBIERTA_Z,
        "pila_x_m": PILA_X,
    }


def _link(nombre: str, geom: str, xyz: str, color: str, masa: float = 1.0) -> str:
    return f"""
  <link name="{nombre}">
    <visual><origin xyz="{xyz}"/><geometry>{geom}</geometry><material name="{color}"/></visual>
    <collision><origin xyz="{xyz}"/><geometry>{geom}</geometry></collision>
    <inertial><mass value="{masa}"/><inertia ixx="0.01" iyy="0.01" izz="0.01" ixy="0" ixz="0" iyz="0"/></inertial>
  </link>"""


def _joint(nombre: str, padre: str, hijo: str, xyz: str, eje: str, lim: float = 3.1) -> str:
    return f"""
  <joint name="{nombre}" type="revolute">
    <parent link="{padre}"/><child link="{hijo}"/>
    <origin xyz="{xyz}"/><axis xyz="{eje}"/>
    <limit lower="{-lim}" upper="{lim}" effort="500" velocity="2.0"/>
  </joint>"""


def generar(nombre: str, alcance_m: float) -> str:
    g = geometria(alcance_m)
    l1, l2 = g["l1_m"], g["l2_m"]
    bx, by, bz = BASE
    partes = [f'<?xml version="1.0"?>\n<robot name="{nombre}">',
              '  <material name="cuerpo"><color rgba="0.95 0.75 0.1 1"/></material>',
              '  <material name="brazo"><color rgba="0.85 0.85 0.88 1"/></material>',
              '  <material name="negro"><color rgba="0.1 0.1 0.1 1"/></material>',
              _link("base_link", f'<box size="{bx} {by} {bz}"/>', f"0 0 {RUEDA_R + bz / 2}", "cuerpo", 400)]
    for i, (x, y) in enumerate([(0.55, 0.55), (0.55, -0.55), (-0.55, 0.55), (-0.55, -0.55)]):
        partes.append(_link(f"rueda_{i}", f'<cylinder radius="{RUEDA_R}" length="0.15"/>', "0 0 0", "negro", 10))
        partes.append(f'  <joint name="rueda_{i}_fija" type="fixed"><parent link="base_link"/><child link="rueda_{i}"/>'
                      f'<origin xyz="{x} {y} {RUEDA_R}" rpy="1.5708 0 0"/></joint>')
    m1, m2, placa = MUNECA
    cadena = [
        ("shoulder_pan", "base_link", "hombro", f"{MONTAJE_X} 0 {CUBIERTA_Z}", "0 0 1",
         f'<cylinder radius="0.14" length="{HOMBRO_ALTO}"/>', f"0 0 {HOMBRO_ALTO / 2}"),
        ("shoulder_lift", "hombro", "brazo", f"0 0 {HOMBRO_ALTO}", "0 1 0",
         f'<box size="0.16 0.16 {l1}"/>', f"0 0 {l1 / 2}"),
        ("elbow", "brazo", "antebrazo", f"0 0 {l1}", "0 1 0",
         f'<box size="0.13 0.13 {l2}"/>', f"0 0 {l2 / 2}"),
        ("wrist_1", "antebrazo", "muneca_1", f"0 0 {l2}", "0 1 0",
         f'<cylinder radius="0.07" length="{m1}"/>', f"0 0 {m1 / 2}"),
        ("wrist_2", "muneca_1", "muneca_2", f"0 0 {m1}", "0 0 1",
         f'<cylinder radius="0.06" length="{m2}"/>', f"0 0 {m2 / 2}"),
        ("wrist_3", "muneca_2", "efector", f"0 0 {m2}", "1 0 0",
         f'<box size="0.6 1.0 {placa}"/>', f"0 0 {placa / 2}"),
    ]
    for nombre_j, padre, hijo, xyz, eje, geom, centro in cadena:
        partes.append(_link(hijo, geom, centro, "negro" if hijo == "efector" else "brazo", 8))
        partes.append(_joint(nombre_j, padre, hijo, xyz, eje))
    partes.append("</robot>\n")
    return "\n".join(partes)
