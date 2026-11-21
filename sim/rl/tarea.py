"""Geometría de la tarea instalar_panel en una copia de la escena de entrenamiento. Sin Isaac.

Sale de la descripción del terreno (sim/viaz_escena.describir_entrenamiento) y del robot de la corrida.
También define el recorrido de referencia de la ventosa: lo siguen el oráculo (sim/rl/oraculo.py),
los inicios asistidos del entrenamiento y la prueba de alcance de validar_robot.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import viaz_escena  # noqa: E402

from . import base_movil  # noqa: E402
from . import cinematica as cin  # noqa: E402
from .robot import Cadena  # noqa: E402

ESPERA_M = 0.25             # la ventosa espera a esta altura sobre el panel de arriba de la pila
HOLGURA_TRASLADO_M = 0.20   # el panel pasa a esta altura sobre el tubo
RETIRO_M = 0.25             # después de soltar, la ventosa sube esta altura
PAN_REF = -math.pi / 2      # el brazo trabaja del lado de la fila 0: la pila queda en -pi y el tubo en -pi/2
PUNTOS = ("espera", "tomar", "subir", "sobre_meta", "dejar", "retirar")
# Tramos del recorrido de referencia: (desde, hasta, el panel va en la ventosa).
TRAMOS = (("espera", "tomar", False), ("tomar", "subir", True), ("subir", "sobre_meta", True),
          ("sobre_meta", "dejar", True))


@dataclass(frozen=True)
class Tarea:
    panel_tam: tuple[float, float, float]     # ancho (X), largo (Y), espesor
    panel_masa_kg: float
    meta: tuple[float, float, float]          # centro del panel instalado, en la copia. Rumbo 0
    base: tuple[float, float, float]          # pose nominal de la base, en la copia. Rumbo 0
    pila_x: float                             # centro de la pila, en el marco de la base
    en_pila: int                              # paneles en la pila, contando el que se instala
    cubierta_z: float
    tubo_arriba_z: float
    giro_agarre: float = 0.0                  # rumbo de la ventosa respecto del panel al tomarlo: 0 o pi/2
    # Secuencia de paneles (RF-INT-18). `meta` y `base` son las del panel 0. El panel k va `k * paso_slot` más adelante.
    paneles: int = 1                          # paneles seguidos que instala: caben en el tramo y hay en la pila
    paso_slot: float = 0.0                    # de un punto de montaje al siguiente, a lo largo del tubo (X)

    @property
    def dist_inicial_m(self) -> float:
        """Del panel de arriba de la pila a su pose ideal, con la base en su pose nominal. Panel 0."""
        return self.dist_inicial_k(0)

    def dist_inicial_k(self, k: int) -> float:
        """Lo mismo para el panel k: la pila tiene k paneles menos."""
        panel = cin.a_mundo(self.panel_en_pila(self.en_pila - 1 - k), self.base, 0.0)
        return math.dist(panel, self.meta)

    def meta_k(self, k: int) -> tuple[float, float, float]:
        """Pose ideal del panel k (su slot), en la copia."""
        return base_movil.punto_montaje(self.meta, self.paso_slot, k)

    def base_k(self, k: int) -> tuple[float, float, float]:
        """Punto de montaje del panel k: dónde se detiene la base, en la copia."""
        return base_movil.punto_montaje(self.base, self.paso_slot, k)

    def slot_del_cuerpo(self, j: int) -> int:
        """Slot que ocupa el cuerpo j de la pila (0 = el de abajo) cuando ya está instalado.

        Los paneles salen de arriba hacia abajo: el de arriba de la pila después del panel 0 va al slot 0.
        Mientras se instala el panel k, están instalados los cuerpos con slot menor que k.
        """
        return self.en_pila - 2 - j

    def panel_en_pila(self, k: int) -> tuple[float, float, float]:
        """Centro del panel k de la pila (0 = el de abajo), en el marco de la base."""
        return (self.pila_x, 0.0, self.cubierta_z + (k + 0.5) * self.panel_tam[2])

    @property
    def traslado_z(self) -> float:
        """Altura de la cara de la ventosa mientras lleva el panel sobre el tubo."""
        return self.tubo_arriba_z + self.panel_tam[2] + HOLGURA_TRASLADO_M


def giro_agarre(ventosa: tuple[float, float], panel_tam: tuple[float, ...]) -> float:
    """Cómo se pone la placa sobre el panel para que sus 4 esquinas queden dentro: alineada (0) o cruzada (pi/2)."""
    if ventosa[0] <= panel_tam[0] and ventosa[1] <= panel_tam[1]:
        return 0.0
    if ventosa[1] <= panel_tam[0] and ventosa[0] <= panel_tam[1]:
        return math.pi / 2
    raise ValueError(f"la ventosa de {ventosa[0]:g} × {ventosa[1]:g} m no cabe sobre el panel de "
                     f"{panel_tam[0]:g} × {panel_tam[1]:g} m: no puede sellar")


def de_descripcion(desc: dict, clon: dict, cadena: Cadena, margen_lateral_m: float = 0.0, paneles: int = 1,
                   paso_slot: float = 0.0) -> Tarea:
    """desc: lo que devuelve viaz_escena.describir_entrenamiento(..., con_robot=True).

    margen_lateral_m: cuánto más lejos del tubo se detiene la base (base_movil.margen_lateral_m).
    """
    panel, geo = desc["panel"], clon["geometria"]
    pila_x = geo["pila_x_m"]
    tubo = desc["tubo"]
    return Tarea(
        panel_tam=tuple(panel["tam_m"]), panel_masa_kg=float(panel["masa_kg"]), meta=tuple(panel["pos_esperada_m"]),
        base=(panel["pos_inicial_m"][0] - pila_x, panel["pos_inicial_m"][1] + margen_lateral_m, 0.0), pila_x=pila_x,
        en_pila=len(desc["pila"]) + 1, cubierta_z=cadena.cubierta_z,
        tubo_arriba_z=tubo["pos_m"][2] + tubo["tam_m"][2] / 2,
        giro_agarre=giro_agarre(cadena.ventosa, tuple(panel["tam_m"])), paneles=paneles, paso_slot=paso_slot)


def de_corrida(c, en_pila: int | None = None) -> tuple[dict, Tarea]:
    """Descripción de la escena de entrenamiento y tarea de una corrida (sim/rl/corrida.py), con su secuencia de paneles.

    La base se detiene donde dice el controlador programado (sim/rl/base_movil.py): frente al slot de cada panel
    y lo bastante lejos del tubo para que sus piezas altas no toquen los paneles instalados con el ruido de RF-INT-19.
    """
    en_pila = en_pila or c.tarea["pila_paneles"]["cantidad"]
    desc = viaz_escena.describir_entrenamiento(c.entorno, en_pila, clon=c.clon, con_robot=True)
    panel, tubo, ruido = desc["panel"], desc["tubo"], desc["variaciones"]
    margen = base_movil.margen_lateral_m(
        c.robot, base_y=panel["pos_inicial_m"][1], borde_paneles_y=panel["pos_esperada_m"][1] + panel["tam_m"][1] / 2,
        bajo_paneles_z=tubo["pos_m"][2] + tubo["tam_m"][2] / 2, ruido_pos_m=ruido["base_pos_m"],
        ruido_yaw_grados=ruido["base_yaw_grados"])
    paneles = min(en_pila, base_movil.paneles_secuencia(c.entorno, c.tarea, desc["tramo_m"]))
    return desc, de_descripcion(desc, c.clon, c.cadena, margen, max(1, paneles), base_movil.paso_slot_m(c.entorno))


def recorrido(t: Tarea, panel_pos, panel_rumbo, meta_pos, meta_rumbo, desfase=None):
    """Poses de la cara de la ventosa para tomar el panel y dejarlo en la meta. Todo en el marco de la base.

    panel_pos, panel_rumbo: dónde está el panel ahora. meta_pos, meta_rumbo: su pose ideal.
    desfase: (dx, dy, drumbo) de la ventosa respecto del panel, en el marco del panel. Después de sellar,
    el oráculo mide el desfase real y lo descuenta para que el panel, no la ventosa, quede en la meta.
    Sin desfase medido, la ventosa va centrada en el panel con el giro de agarre de la tarea.
    Devuelve {punto: ((x, y, z), rumbo)}. Acepta números sueltos o tensores.
    """
    medio = t.panel_tam[2] / 2
    dx, dy, drumbo = desfase if desfase is not None else (0.0, 0.0, t.giro_agarre)
    tomar_rumbo = panel_rumbo + t.giro_agarre
    # math.cos sirve aquí solo para números; con tensores se usan sus métodos.
    c, s = (meta_rumbo.cos(), meta_rumbo.sin()) if hasattr(meta_rumbo, "cos") else (math.cos(meta_rumbo), math.sin(meta_rumbo))
    mx, my = meta_pos[0] + c * dx - s * dy, meta_pos[1] + s * dx + c * dy
    arriba = panel_pos[2] + medio
    return {
        "espera": ((panel_pos[0], panel_pos[1], arriba + ESPERA_M), tomar_rumbo),
        "tomar": ((panel_pos[0], panel_pos[1], arriba), tomar_rumbo),
        "subir": ((panel_pos[0], panel_pos[1], arriba * 0 + t.traslado_z), tomar_rumbo),
        "sobre_meta": ((mx, my, meta_pos[2] * 0 + t.traslado_z), meta_rumbo + drumbo),
        "dejar": ((mx, my, meta_pos[2] + medio), meta_rumbo + drumbo),
        "retirar": ((mx, my, meta_pos[2] + medio + RETIRO_M), meta_rumbo + drumbo),
    }


def angulos(cadena: Cadena, puntos: dict, xp=math) -> dict:
    """Cinemática inversa de cada punto del recorrido: {punto: (q, alcanzable)}."""
    return {n: cin.inversa(cadena, pos, rumbo, PAN_REF, xp) for n, (pos, rumbo) in puntos.items()}


def nominal(t: Tarea, cadena: Cadena, k: int = 0) -> dict:
    """Recorrido del panel k con la base en su punto de montaje, sin ruido. Para validar_robot y los tests."""
    meta_base = cin.a_base(t.meta, t.base, 0.0)   # la meta y la base del panel k avanzan lo mismo
    return angulos(cadena, recorrido(t, t.panel_en_pila(t.en_pila - 1 - k), 0.0, meta_base, 0.0))


def problemas_alcance(t: Tarea, cadena: Cadena) -> list[str]:
    """Una oración con números por cada punto del recorrido que el brazo no alcanza (RF-CLO-05).

    Revisa la pila completa (panel 0) y la pila más baja de la secuencia (último panel).
    """
    lista = _problemas_alcance(t, cadena, 0)
    if t.paneles > 1:
        lista += [p for p in _problemas_alcance(t, cadena, t.paneles - 1) if p not in lista]
    return lista


def _problemas_alcance(t: Tarea, cadena: Cadena, k: int) -> list[str]:
    meta_base = cin.a_base(t.meta, t.base, 0.0)
    puntos = recorrido(t, t.panel_en_pila(t.en_pila - 1 - k), 0.0, meta_base, 0.0)
    lista = []
    for nombre, (q, alcanzable) in angulos(cadena, puntos).items():
        (x, y, z), _ = puntos[nombre]
        distancia = math.hypot(math.hypot(x - cadena.montaje_x, y), z + cadena.muneca - cadena.hombro_z)
        if not alcanzable:
            lista.append(f"la ventosa no llega al punto '{nombre}' ({x:.2f}, {y:.2f}, {z:.2f}) m: queda a {distancia:.2f} m "
                         f"del hombro y el brazo estira {cadena.l1 + cadena.l2:.2f} m")
            continue
        for nombre_j, v, lo, hi in zip(("shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"),
                                       q, cadena.inferior, cadena.superior):
            if not lo - 1e-6 <= v <= hi + 1e-6:
                lista.append(f"el punto '{nombre}' pide {nombre_j} = {v:.2f} rad, fuera del recorrido [{lo:.2f}, {hi:.2f}]")
    return lista
