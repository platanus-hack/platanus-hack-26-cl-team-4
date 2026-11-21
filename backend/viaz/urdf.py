"""Clon paramétrico: base móvil + brazo de 6 ejes + ventosa, con geometría primitiva (sin mallas).

Las medidas salen del robot real (alcance). Las mismas medidas van a clon.json["geometria"],
y sim/plan.py las usa para planificar la tarea. Si cambias algo aquí, revisa sim/plan.py.

Física: cada link tiene masa e inercia calculadas de su forma (caja o cilindro sólido).
PhysX se vuelve inestable con inercias inventadas (p. ej. 0,01 para una base de 600 kg).
Las masas son supuestos hasta tener la ficha del robot real: ver MASA_* abajo.

Un robot con bloque `fisica` en su ficha del catálogo usa sus propias medidas. El núcleo (largo, ancho, masa,
altura de la cubierta y tracción) siempre está. Lo opcional (posición y grosor del brazo, marco de ventosas,
gabinete, remolque, posición de la pila) usa el valor genérico si falta, o la pieza no se dibuja.
Sin ese bloque, el clon es el de siempre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

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

# Robots con ficha física (bloque `fisica` del catálogo): cómo se reparten sus medidas. Son supuestos del clon.
ORUGA_ALTO, ORUGA_LARGO, ORUGA_ANCHO = 0.44, 0.70, 0.20   # fracción de la altura de cubierta, del largo y del ancho
ORUGA_CENTRO = 0.13                     # las orugas van corridas hacia adelante: fracción del largo
MASA_ORUGA, MASA_GABINETE = 0.12, 0.08  # fracción de la masa de la máquina, por oruga y para el gabinete
ENGANCHE_M = 0.30                       # barra entre el frente del vehículo y el remolque
REMOLQUE_ALTO_M = 0.18                  # espesor de la plataforma del remolque; su cara de arriba queda a la altura de cubierta
REMOLQUE_RUEDA_R, REMOLQUE_RUEDA_ANCHO, MASA_RUEDA_REMOLQUE = 0.36, 0.26, 0.04   # masa: fracción de la del remolque

# Articulaciones: límites y esfuerzo (N·m) suficientes para mover un panel de ~35 kg con el brazo extendido.
LIMITE_RAD = 3.1
ESFUERZO_NM = {"shoulder_pan": 1500, "shoulder_lift": 3000, "elbow": 1500, "wrist_1": 400, "wrist_2": 200, "wrist_3": 200}
VELOCIDAD_RAD_S = 1.5


@dataclass(frozen=True)
class Vehiculo:
    """Medidas del vehículo y del brazo que cambian con el robot. Sin ficha física, son las del clon de siempre."""
    largo: float = BASE[0]
    ancho: float = BASE[1]
    cubierta_z: float = CUBIERTA_Z
    montaje_x: float = MONTAJE_X
    pila_x: float = PILA_X
    hombro_r: float = HOMBRO_R
    brazo_lado: float = BRAZO_LADO
    antebrazo_lado: float = ANTEBRAZO_LADO
    traccion: str = "ruedas"
    masa_kg: float | None = None            # masa de la máquina completa; None = suma de las masas supuestas
    gabinete: tuple[float, float] | None = None   # largo y alto del gabinete trasero, sobre la cubierta
    ventosa: tuple[float, float] = VENTOSA  # marco de ventosas en X e Y
    remolque: tuple[float, float] | None = None   # largo y masa del remolque de paneles
    rueda_xy: tuple[float, float] = (0.55, 0.55)  # centro de las ruedas desde el centro de la base (solo `ruedas`)


def vehiculo(fisica: dict | None) -> Vehiculo:
    """Lee el bloque `fisica` de la ficha del catálogo (robot.schema.json). None = clon de siempre."""
    if not fisica:
        return Vehiculo()
    largo, ancho = fisica["largo_m"], fisica["ancho_m"]
    montaje_x = fisica.get("brazo_x_m", round(largo * MONTAJE_X / BASE[0], 3))   # sin dato: misma fracción del largo
    grosor = fisica.get("brazo_grosor_m")
    gabinete = _par(fisica, "gabinete_largo_m", "gabinete_alto_m")
    remolque = _par(fisica, "remolque_largo_m", "remolque_masa_kg")
    return Vehiculo(
        largo=largo, ancho=ancho, cubierta_z=fisica["altura_cubierta_m"],
        montaje_x=montaje_x, pila_x=_pila_x(fisica, montaje_x, gabinete, remolque),
        hombro_r=round(grosor * 0.75, 3) if grosor else HOMBRO_R,
        brazo_lado=grosor or BRAZO_LADO, antebrazo_lado=fisica.get("antebrazo_grosor_m", ANTEBRAZO_LADO),
        traccion=fisica["traccion"], masa_kg=fisica["masa_kg"],
        gabinete=gabinete, ventosa=_par(fisica, "ventosa_largo_m", "ventosa_ancho_m") or VENTOSA, remolque=remolque,
        rueda_xy=(round(largo / 2 - RUEDA_R, 4), round(ancho / 2 - RUEDA_ANCHO / 2, 4)))   # dentro de la base


def _par(fisica: dict, a: str, b: str) -> tuple[float, float] | None:
    """Campos que van juntos (robot.schema.json, dependentRequired): los dos o ninguno."""
    return (fisica[a], fisica[b]) if a in fisica else None


def _pila_x(fisica: dict, montaje_x: float, gabinete: tuple | None, remolque: tuple | None) -> float:
    largo = fisica["largo_m"]
    if remolque:
        # El robot real no lleva la pila encima: la toma de un remolque que arrastra por el lado del brazo.
        return round(largo / 2 + ENGANCHE_M + remolque[0] / 2, 4)
    if "pila_x_m" in fisica:
        return fisica["pila_x_m"]
    # Sin remolque, la pila va sobre la cubierta, entre el brazo y el extremo libre. El gabinete va atrás: con
    # gabinete, el extremo libre es el de adelante; sin gabinete, el más lejano al brazo.
    extremo = largo / 2 if gabinete or montaje_x < 0 else -largo / 2
    return round((montaje_x + extremo) / 2, 4)


def geometria(alcance_m: float, fisica: dict | None = None) -> dict:
    """Reparte el alcance entre brazo y antebrazo (el resto es la muñeca)."""
    v = vehiculo(fisica)
    util = max(alcance_m - sum(MUNECA), 0.6)
    g = {
        "l1_m": round(util * 0.52, 3),
        "l2_m": round(util * 0.48, 3),
        "muneca_m": round(sum(MUNECA), 3),
        "montaje_x_m": v.montaje_x,
        "hombro_z_m": round(v.cubierta_z + HOMBRO_ALTO, 3),
        "cubierta_z_m": v.cubierta_z,
        "pila_x_m": v.pila_x,
    }
    return {**g, "medio_ancho_m": round(v.ancho / 2, 3)} if fisica else g


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


def _fijas(v: Vehiculo) -> list[dict]:
    """Piezas rígidas pegadas a base_link, con su unión (posición y giro del origen). Aquí se decide qué piezas hay."""
    return [*(_ruedas(v) if v.traccion == "ruedas" else _orugas(v)),
            *(_gabinete(v) if v.gabinete else []),
            *(_remolque(v) if v.remolque else [])]


def _ruedas(v: Vehiculo) -> list[dict]:
    rx, ry = v.rueda_xy
    return [{"link": f"rueda_{i}", "forma": "cilindro", "dims": (RUEDA_R, RUEDA_ANCHO), "centro": (0, 0, 0),
             "masa": MASA_RUEDA_KG, "color": "negro", "union": (f"{x} {y} {RUEDA_R}", "1.5708 0 0")}
            for i, (x, y) in enumerate([(rx, ry), (rx, -ry), (-rx, ry), (-rx, -ry)])]


def _orugas(v: Vehiculo) -> list[dict]:
    alto, largo, ancho = medidas_oruga(v)
    x = round(v.largo * ORUGA_CENTRO, 4)
    return [{"link": f"oruga_{i}", "forma": "caja", "dims": (largo, ancho, alto), "centro": (0, 0, alto / 2),
             "masa": round(v.masa_kg * MASA_ORUGA, 1), "color": "negro",
             "union": (f"{x} {round(lado * (v.ancho - ancho) / 2, 4)} 0", "0 0 0")} for i, lado in enumerate((1, -1))]


def _gabinete(v: Vehiculo) -> list[dict]:
    gl, ga = v.gabinete
    return [{"link": "gabinete", "forma": "caja", "dims": (gl, round(v.ancho - 0.2, 4), ga), "centro": (0, 0, ga / 2),
             "masa": round(v.masa_kg * MASA_GABINETE, 1), "color": "cuerpo",
             "union": (f"{round(-v.largo / 2 + gl / 2, 4)} 0 {v.cubierta_z}", "0 0 0")}]


def _remolque(v: Vehiculo) -> list[dict]:
    rl, rm = v.remolque
    rx = v.pila_x                           # la pila va centrada sobre el remolque
    ruedas = [(dx, lado) for dx in (-0.45, 0.45) for lado in (1, -1)]
    lista = [{"link": "remolque", "forma": "caja", "dims": (rl, v.ancho, REMOLQUE_ALTO_M), "centro": (0, 0, REMOLQUE_ALTO_M / 2),
              "masa": round(rm * (1 - MASA_RUEDA_REMOLQUE * len(ruedas)), 1), "color": "cuerpo",
              "union": (f"{rx} 0 {round(v.cubierta_z - REMOLQUE_ALTO_M, 4)}", "0 0 0")}]
    for i, (dx, lado) in enumerate(ruedas):
        y = round(lado * (v.ancho - REMOLQUE_RUEDA_ANCHO) / 2, 4)
        lista.append({"link": f"rueda_remolque_{i}", "forma": "cilindro", "dims": (REMOLQUE_RUEDA_R, REMOLQUE_RUEDA_ANCHO),
                      "centro": (0, 0, 0), "masa": round(rm * MASA_RUEDA_REMOLQUE, 1), "color": "negro",
                      "union": (f"{round(rx + dx, 4)} {y} {REMOLQUE_RUEDA_R}", "1.5708 0 0")})
    return lista


def medidas_oruga(v: Vehiculo) -> tuple[float, float, float]:
    """Alto, largo y ancho de cada oruga."""
    return round(v.cubierta_z * ORUGA_ALTO, 3), round(v.largo * ORUGA_LARGO, 3), round(v.ancho * ORUGA_ANCHO, 3)


def piezas(alcance_m: float, fisica: dict | None = None) -> list[dict]:
    """Links del clon con forma, medidas, centro y masa. generar() y los tests usan esta lista."""
    v = vehiculo(fisica)
    g = geometria(alcance_m, fisica)
    l1, l2 = g["l1_m"], g["l2_m"]
    m1, m2, placa = MUNECA
    # (link, forma, medidas de la colisión, medidas con las que se calcula la masa, color)
    brazo = [
        ("hombro", "cilindro", (v.hombro_r, HOMBRO_ALTO), (HOMBRO_R, HOMBRO_ALTO), "brazo"),
        ("brazo", "caja", (v.brazo_lado, v.brazo_lado, l1), (BRAZO_LADO, BRAZO_LADO, l1), "brazo"),
        ("antebrazo", "caja", (v.antebrazo_lado, v.antebrazo_lado, l2), (ANTEBRAZO_LADO, ANTEBRAZO_LADO, l2), "brazo"),
        ("muneca_1", "cilindro", (0.07, m1), (0.07, m1), "brazo"),
        ("muneca_2", "cilindro", (0.06, m2), (0.06, m2), "brazo"),
        ("efector", "caja", (v.ventosa[0], v.ventosa[1], placa), None, "negro"),
    ]
    cadena = []
    for link, forma, dims, estructura, color in brazo:
        alto = dims[-1] if forma == "caja" else dims[1]
        if estructura is None:
            masa = MASA_VENTOSA_KG
        elif forma == "caja":
            masa = _masa_caja(*estructura)
        else:
            masa = _masa_cilindro(*estructura)
        cadena.append({"link": link, "forma": forma, "dims": dims, "centro": (0, 0, alto / 2),
                       "masa": round(masa, 3), "color": color})
    fijas = _fijas(v)
    suelo = RUEDA_R if v.traccion == "ruedas" else medidas_oruga(v)[0]
    if v.masa_kg is None:
        masa_base = MASA_BASE_KG
    else:
        propias = [p for p in cadena + fijas if "remolque" not in p["link"]]
        masa_base = round(v.masa_kg - sum(p["masa"] for p in propias), 1)   # el resto de la máquina es chasis
        if masa_base <= 0:
            raise ValueError(f"fisica.masa_kg ({v.masa_kg} kg) no alcanza para las piezas del clon")
    alto_base = round(v.cubierta_z - suelo, 4)
    base = {"link": "base_link", "forma": "caja", "dims": (v.largo, v.ancho, alto_base),
            "centro": (0, 0, round(suelo + alto_base / 2, 4)), "masa": masa_base, "color": "cuerpo"}
    return [base, *fijas, *cadena]


def masa_total(alcance_m: float, fisica: dict | None = None) -> float:
    return round(sum(p["masa"] for p in piezas(alcance_m, fisica)), 1)


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


def generar(nombre: str, alcance_m: float, fisica: dict | None = None) -> str:
    v = vehiculo(fisica)
    g = geometria(alcance_m, fisica)
    l1, l2 = g["l1_m"], g["l2_m"]
    m1, m2, _ = MUNECA
    lista = {p["link"]: p for p in piezas(alcance_m, fisica)}
    partes = [f'<?xml version="1.0"?>\n<robot name="{nombre}">',
              '  <material name="cuerpo"><color rgba="0.95 0.75 0.1 1"/></material>',
              '  <material name="brazo"><color rgba="0.85 0.85 0.88 1"/></material>',
              '  <material name="negro"><color rgba="0.1 0.1 0.1 1"/></material>',
              _link(lista["base_link"])]
    for p in lista.values():
        if "union" in p:
            xyz, rpy = p["union"]
            partes.append(_link(p))
            partes.append(f'  <joint name="{p["link"]}_fija" type="fixed"><parent link="base_link"/><child link="{p["link"]}"/>'
                          f'<origin xyz="{xyz}" rpy="{rpy}"/></joint>')
    cadena = [
        ("shoulder_pan", "base_link", "hombro", f"{v.montaje_x} 0 {v.cubierta_z}", "0 0 1"),
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
