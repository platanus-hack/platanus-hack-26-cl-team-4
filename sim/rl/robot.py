"""Lee robot.urdf y entrega lo que el entorno RL necesita del robot. Python puro (sin Isaac).

El entorno no trae ningún robot fijo en el código: la geometría, las masas y los límites de torque y
velocidad (RF-INT-23) salen del URDF de la corrida. La familia cinemática que el entorno sabe mover es la
del clon de backend/viaz/urdf.py: base fija, giro vertical, tres ejes paralelos y una muñeca de dos ejes.
cadena() revisa que el URDF sea de esa familia y falla con un mensaje claro si no lo es.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

ARTICULACIONES = ("shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3")
EJES = ((0, 0, 1), (0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))
ESLABON_VENTOSA = "efector"
ESLABON_BASE = "base_link"


@dataclass(frozen=True)
class Pieza:
    nombre: str
    forma: str                          # "caja" o "cilindro" (eje Z)
    dims: tuple[float, ...]             # caja: x, y, z. cilindro: radio, largo
    centro: tuple[float, float, float]
    masa: float
    inercia: tuple[float, float, float]
    color: tuple[float, float, float]


@dataclass(frozen=True)
class Union:
    nombre: str
    tipo: str                           # "revolute" o "fixed"
    padre: str
    hijo: str
    xyz: tuple[float, float, float]
    rpy: tuple[float, float, float]
    eje: tuple[float, float, float]
    inferior: float
    superior: float
    esfuerzo: float
    velocidad: float
    amortiguamiento: float


@dataclass(frozen=True)
class Robot:
    nombre: str
    piezas: dict[str, Pieza]
    uniones: tuple[Union, ...]

    @property
    def articulaciones(self) -> tuple[Union, ...]:
        return tuple(u for u in self.uniones if u.tipo == "revolute")

    @property
    def masa_kg(self) -> float:
        return sum(p.masa for p in self.piezas.values())


@dataclass(frozen=True)
class Cadena:
    """Medidas de la cadena del brazo, en el marco de la base (origen en el suelo, bajo el centro de la base)."""
    montaje_x: float     # eje del giro vertical
    hombro_z: float      # altura del eje del hombro
    l1: float            # hombro a codo
    l2: float            # codo a muñeca 1
    m1: float            # muñeca 1 a muñeca 2
    m2: float            # muñeca 2 a muñeca 3
    placa: float         # muñeca 3 a la cara de la ventosa
    ventosa: tuple[float, float]   # lados de la placa (x, y)
    cubierta_z: float    # techo de la base, donde descansa la pila
    inferior: tuple[float, ...]
    superior: tuple[float, ...]
    esfuerzo: tuple[float, ...]
    velocidad: tuple[float, ...]

    @property
    def muneca(self) -> float:
        """De la muñeca 1 a la cara de la ventosa, con la ventosa mirando hacia abajo."""
        return self.m1 + self.m2 + self.placa

    @property
    def alcance(self) -> float:
        return self.l1 + self.l2 + self.muneca


def _nums(texto: str | None, n: int, defecto: float = 0.0) -> tuple[float, ...]:
    return tuple(float(v) for v in texto.split()) if texto else (defecto,) * n


def leer_urdf(texto: str) -> Robot:
    raiz = ET.fromstring(texto)
    colores = {m.get("name"): _nums(m.find("color").get("rgba"), 4)[:3]
               for m in raiz.findall("material") if m.find("color") is not None}
    piezas = {}
    for link in raiz.findall("link"):
        col, ine = link.find("collision"), link.find("inertial")
        if col is None or ine is None:
            raise ValueError(f"robot.urdf: el link '{link.get('name')}' no tiene colisión o inercia")
        geo = col.find("geometry")
        if geo.find("box") is not None:
            forma, dims = "caja", _nums(geo.find("box").get("size"), 3)
        elif geo.find("cylinder") is not None:
            c = geo.find("cylinder")
            forma, dims = "cilindro", (float(c.get("radius")), float(c.get("length")))
        else:
            raise ValueError(f"robot.urdf: el link '{link.get('name')}' no es caja ni cilindro")
        origen = col.find("origin")
        i = ine.find("inertia")
        material = link.find("visual/material")
        piezas[link.get("name")] = Pieza(
            nombre=link.get("name"), forma=forma, dims=dims,
            centro=_nums(origen.get("xyz") if origen is not None else None, 3),
            masa=float(ine.find("mass").get("value")),
            inercia=(float(i.get("ixx")), float(i.get("iyy")), float(i.get("izz"))),
            color=colores.get(material.get("name") if material is not None else None, (0.7, 0.7, 0.7)))
    uniones = []
    for j in raiz.findall("joint"):
        origen, eje, lim, din = j.find("origin"), j.find("axis"), j.find("limit"), j.find("dynamics")
        uniones.append(Union(
            nombre=j.get("name"), tipo=j.get("type"), padre=j.find("parent").get("link"), hijo=j.find("child").get("link"),
            xyz=_nums(origen.get("xyz") if origen is not None else None, 3),
            rpy=_nums(origen.get("rpy") if origen is not None else None, 3),
            eje=_nums(eje.get("xyz") if eje is not None else None, 3),
            inferior=float(lim.get("lower")) if lim is not None else 0.0,
            superior=float(lim.get("upper")) if lim is not None else 0.0,
            esfuerzo=float(lim.get("effort")) if lim is not None else 0.0,
            velocidad=float(lim.get("velocity")) if lim is not None else 0.0,
            amortiguamiento=float(din.get("damping")) if din is not None else 0.0))
    return Robot(nombre=raiz.get("name"), piezas=piezas, uniones=tuple(uniones))


def cadena(robot: Robot) -> Cadena:
    """Medidas del brazo. Falla si el URDF no es de la familia cinemática del clon."""
    arts = robot.articulaciones
    nombres = tuple(u.nombre for u in arts)
    if nombres != ARTICULACIONES:
        raise ValueError(f"robot.urdf: se esperaban las articulaciones {list(ARTICULACIONES)} y vienen {list(nombres)}")
    for u, eje in zip(arts, EJES):
        if tuple(round(v) for v in u.eje) != eje or any(abs(v) > 1e-9 for v in u.rpy):
            raise ValueError(f"robot.urdf: la articulación '{u.nombre}' no tiene el eje {eje} sin rotación de origen")
        if u.esfuerzo <= 0 or u.velocidad <= 0 or u.superior <= u.inferior:
            raise ValueError(f"robot.urdf: la articulación '{u.nombre}' no trae límites de torque, velocidad y recorrido")
    pan, hombro, codo, mu1, mu2, mu3 = arts
    for u in (hombro, codo, mu1, mu2, mu3):
        if abs(u.xyz[0]) > 1e-9 or abs(u.xyz[1]) > 1e-9:
            raise ValueError(f"robot.urdf: la articulación '{u.nombre}' está desplazada fuera del eje del eslabón")
    if pan.padre != ESLABON_BASE or mu3.hijo != ESLABON_VENTOSA or abs(pan.xyz[1]) > 1e-9:
        raise ValueError(f"robot.urdf: el brazo debe ir de '{ESLABON_BASE}' a '{ESLABON_VENTOSA}', centrado en Y")
    placa = robot.piezas[ESLABON_VENTOSA]
    if placa.forma != "caja":
        raise ValueError("robot.urdf: la ventosa debe ser una caja")
    return Cadena(
        montaje_x=pan.xyz[0], hombro_z=pan.xyz[2] + hombro.xyz[2], l1=codo.xyz[2], l2=mu1.xyz[2],
        m1=mu2.xyz[2], m2=mu3.xyz[2], placa=placa.dims[2], ventosa=(placa.dims[0], placa.dims[1]),
        cubierta_z=pan.xyz[2],
        inferior=tuple(u.inferior for u in arts), superior=tuple(u.superior for u in arts),
        esfuerzo=tuple(u.esfuerzo for u in arts), velocidad=tuple(u.velocidad for u in arts))
