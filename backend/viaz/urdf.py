"""Clon paramétrico: base móvil + brazo de 6 ejes + ventosa, con geometría primitiva (sin mallas).

Las medidas salen del robot real (alcance). Las mismas medidas van a clon.json["geometria"],
y sim/plan.py las usa para planificar la tarea. Si cambias algo aquí, revisa sim/plan.py.

Física: cada link tiene masa e inercia calculadas de su forma (caja o cilindro sólido).
PhysX se vuelve inestable con inercias inventadas (p. ej. 0,01 para una base de 600 kg).
Las masas son supuestos hasta tener la ficha del robot real: ver MASA_* abajo.
"""
from __future__ import annotations

import math

ARTICULACIONES = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"]

# Base: caja de 1,6 × 1,0 × 0,6 m sobre ruedas de 0,2 m de radio. Origen de base_link en el suelo.
BASE = (1.6, 1.0, 0.6)
RUEDA_R = 0.2
RUEDA_ANCHO = 0.15
CUBIERTA_Z = RUEDA_R + BASE[2]          # 0,8 m: techo de la base, donde va la pila de paneles
MONTAJE_X = 0.45                        # el brazo va adelante
HOMBRO_ALTO = 0.3                       # columna entre la base y el eje del hombro
HOMBRO_R = 0.14
BRAZO_LADO, ANTEBRAZO_LADO = 0.16, 0.13
MUNECA = (0.15, 0.1, 0.05)              # muñeca 1, muñeca 2, placa de la ventosa
VENTOSA = (0.6, 1.0)                    # placa de la ventosa en X e Y
PILA_X = -0.35                          # la pila de paneles va atrás

# Masas supuestas (kg). Cambiarlas cuando tengamos la ficha del robot real.
MASA_BASE_KG = 600.0                    # chasis + baterías de una base que carga paneles
MASA_RUEDA_KG = 15.0
MASA_VENTOSA_KG = 6.0
DENSIDAD_BRAZO_KG_M3 = 2700 * 0.3       # aluminio en perfiles huecos (~30 % lleno)

# Articulaciones: límites y esfuerzo (N·m) suficientes para mover un panel de ~35 kg con el brazo extendido.
LIMITE_RAD = 3.1
ESFUERZO_NM = {"shoulder_pan": 1500, "shoulder_lift": 3000, "elbow": 1500, "wrist_1": 400, "wrist_2": 200, "wrist_3": 200}
VELOCIDAD_RAD_S = 1.5


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


# ---------- inercias ----------

def _inercia_caja(m: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    return (m * (y * y + z * z) / 12, m * (x * x + z * z) / 12, m * (x * x + y * y) / 12)


def _inercia_cilindro(m: float, r: float, h: float) -> tuple[float, float, float]:
    """Cilindro sólido con eje Z (convención URDF)."""
    lado = m * (3 * r * r + h * h) / 12
    return (lado, lado, m * r * r / 2)


def _masa_caja(x, y, z):
    return DENSIDAD_BRAZO_KG_M3 * x * y * z


def _masa_cilindro(r, h):
    return DENSIDAD_BRAZO_KG_M3 * math.pi * r * r * h


def piezas(alcance_m: float) -> list[dict]:
    """Links del clon con forma, medidas, centro y masa. generar() y los tests usan esta lista."""
    g = geometria(alcance_m)
    l1, l2 = g["l1_m"], g["l2_m"]
    m1, m2, placa = MUNECA
    bx, by, bz = BASE
    lista = [{"link": "base_link", "forma": "caja", "dims": (bx, by, bz), "centro": (0, 0, RUEDA_R + bz / 2),
              "masa": MASA_BASE_KG, "color": "cuerpo"}]
    for i in range(4):
        lista.append({"link": f"rueda_{i}", "forma": "cilindro", "dims": (RUEDA_R, RUEDA_ANCHO), "centro": (0, 0, 0),
                      "masa": MASA_RUEDA_KG, "color": "negro"})
    brazo = [
        ("hombro", "cilindro", (HOMBRO_R, HOMBRO_ALTO), "brazo"),
        ("brazo", "caja", (BRAZO_LADO, BRAZO_LADO, l1), "brazo"),
        ("antebrazo", "caja", (ANTEBRAZO_LADO, ANTEBRAZO_LADO, l2), "brazo"),
        ("muneca_1", "cilindro", (0.07, m1), "brazo"),
        ("muneca_2", "cilindro", (0.06, m2), "brazo"),
        ("efector", "caja", (VENTOSA[0], VENTOSA[1], placa), "negro"),
    ]
    for link, forma, dims, color in brazo:
        alto = dims[-1] if forma == "caja" else dims[1]
        if link == "efector":
            masa = MASA_VENTOSA_KG
        elif forma == "caja":
            masa = _masa_caja(*dims)
        else:
            masa = _masa_cilindro(*dims)
        lista.append({"link": link, "forma": forma, "dims": dims, "centro": (0, 0, alto / 2),
                      "masa": round(masa, 3), "color": color})
    return lista


def masa_total(alcance_m: float) -> float:
    return round(sum(p["masa"] for p in piezas(alcance_m)), 1)


# ---------- URDF ----------

def _geom(p: dict) -> str:
    if p["forma"] == "caja":
        return '<box size="{} {} {}"/>'.format(*p["dims"])
    return '<cylinder radius="{}" length="{}"/>'.format(*p["dims"])


def _link(p: dict) -> str:
    ixx, iyy, izz = (_inercia_caja(p["masa"], *p["dims"]) if p["forma"] == "caja"
                     else _inercia_cilindro(p["masa"], *p["dims"]))
    xyz = "{} {} {}".format(*p["centro"])
    g = _geom(p)
    return f"""
  <link name="{p['link']}">
    <visual><origin xyz="{xyz}"/><geometry>{g}</geometry><material name="{p['color']}"/></visual>
    <collision><origin xyz="{xyz}"/><geometry>{g}</geometry></collision>
    <inertial>
      <origin xyz="{xyz}"/><mass value="{p['masa']}"/>
      <inertia ixx="{ixx:.5f}" iyy="{iyy:.5f}" izz="{izz:.5f}" ixy="0" ixz="0" iyz="0"/>
    </inertial>
  </link>"""


def _joint(nombre: str, padre: str, hijo: str, xyz: str, eje: str) -> str:
    return f"""
  <joint name="{nombre}" type="revolute">
    <parent link="{padre}"/><child link="{hijo}"/>
    <origin xyz="{xyz}"/><axis xyz="{eje}"/>
    <limit lower="{-LIMITE_RAD}" upper="{LIMITE_RAD}" effort="{ESFUERZO_NM[nombre]}" velocity="{VELOCIDAD_RAD_S}"/>
    <dynamics damping="5.0" friction="0.0"/>
  </joint>"""


def generar(nombre: str, alcance_m: float) -> str:
    g = geometria(alcance_m)
    l1, l2 = g["l1_m"], g["l2_m"]
    m1, m2, _ = MUNECA
    lista = {p["link"]: p for p in piezas(alcance_m)}
    partes = [f'<?xml version="1.0"?>\n<robot name="{nombre}">',
              '  <material name="cuerpo"><color rgba="0.95 0.75 0.1 1"/></material>',
              '  <material name="brazo"><color rgba="0.85 0.85 0.88 1"/></material>',
              '  <material name="negro"><color rgba="0.1 0.1 0.1 1"/></material>',
              _link(lista["base_link"])]
    for i, (x, y) in enumerate([(0.55, 0.55), (0.55, -0.55), (-0.55, 0.55), (-0.55, -0.55)]):
        partes.append(_link(lista[f"rueda_{i}"]))
        partes.append(f'  <joint name="rueda_{i}_fija" type="fixed"><parent link="base_link"/><child link="rueda_{i}"/>'
                      f'<origin xyz="{x} {y} {RUEDA_R}" rpy="1.5708 0 0"/></joint>')
    cadena = [
        ("shoulder_pan", "base_link", "hombro", f"{MONTAJE_X} 0 {CUBIERTA_Z}", "0 0 1"),
        ("shoulder_lift", "hombro", "brazo", f"0 0 {HOMBRO_ALTO}", "0 1 0"),
        ("elbow", "brazo", "antebrazo", f"0 0 {l1}", "0 1 0"),
        ("wrist_1", "antebrazo", "muneca_1", f"0 0 {l2}", "0 1 0"),
        ("wrist_2", "muneca_1", "muneca_2", f"0 0 {m1}", "0 0 1"),
        ("wrist_3", "muneca_2", "efector", f"0 0 {m2}", "1 0 0"),
    ]
    for nombre_j, padre, hijo, xyz, eje in cadena:
        partes.append(_link(lista[hijo]))
        partes.append(_joint(nombre_j, padre, hijo, xyz, eje))
    partes.append("</robot>\n")
    return "\n".join(partes)
