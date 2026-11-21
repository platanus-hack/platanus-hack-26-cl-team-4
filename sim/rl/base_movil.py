"""Controlador programado de la base móvil (RF-INT-18). Sin Isaac y sin RL.

La base avanza por el pasillo de la fila 0, en línea recta, de un punto de montaje al siguiente. Frente a
cada punto se detiene y la política del brazo instala un panel. Este módulo decide:
- cuántos paneles seguidos instala en la escena de entrenamiento (los que caben en el tramo de tubo),
- dónde se detiene la base frente al panel k (punto de montaje),
- a qué distancia del tubo va, para que ninguna pieza alta de la base toque los paneles ya instalados, y
- cómo avanza entre dos paradas: velocidad en trapecio, parte y llega detenida.

El entorno usa la misma regla en los dos casos: para poner la base al inicio de un episodio de
entrenamiento y para moverla entre paneles en la evaluación (sim/rl/entorno.py).
Las funciones de movimiento aceptan números sueltos (tests) o tensores de torch con un valor por entorno.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan  # noqa: E402

from .robot import ESLABON_BASE, Robot  # noqa: E402

VEL_BASE_M_S = plan.VEL_BASE     # 0,8 m/s: la velocidad de la base en el plan del demo
ACEL_BASE_M_S2 = 0.8             # llega a su velocidad en 1 s: una base de 2 t con orugas no parte de golpe
HOLGURA_PIEZAS_M = 0.03          # espacio libre que queda entre la base y un panel instalado, en el peor caso


def paneles_secuencia(entorno: dict, tarea: dict, tramo_m: float) -> int:
    """Paneles seguidos que el robot instala en la escena de entrenamiento.

    Son los que pide la tarea y hay en la pila (plan.cantidad), mientras su slot quepa entero en el tramo de tubo.
    """
    medio = entorno["panel"]["ancho_m"] / 2
    return sum(1 for s in plan.slots(entorno, plan.cantidad(entorno, tarea)) if s[0] + medio <= tramo_m + 1e-9)


def paso_slot_m(entorno: dict) -> float:
    """Distancia entre dos puntos de montaje seguidos, a lo largo del tubo."""
    a, b = plan.slots(entorno, 2)
    return round(b[0] - a[0], 4)


def margen_lateral_m(robot: Robot, base_y: float, borde_paneles_y: float, bajo_paneles_z: float,
                     ruido_pos_m: float, ruido_yaw_grados: float) -> float:
    """Cuánto más lejos del tubo tiene que ir la base para no tocar los paneles instalados.

    base_y: distancia nominal del eje de la fila al centro de la base. borde_paneles_y: hasta dónde llegan los
    paneles instalados hacia el pasillo. bajo_paneles_z: altura de su cara de abajo.
    Revisa las piezas fijas de la base que suben más que esa altura (un gabinete, no las orugas), con la base
    detenida en el peor caso del ruido de RF-INT-19: corrida hacia el tubo y girada. Devuelve 0 si ya caben.
    """
    giro = math.radians(ruido_yaw_grados)
    fijas = {u.hijo: u.xyz for u in robot.uniones if u.tipo == "fixed" and u.padre == ESLABON_BASE}
    cerca = math.inf
    for nombre, xyz in {ESLABON_BASE: (0.0, 0.0, 0.0), **fijas}.items():
        pieza = robot.piezas[nombre]
        if pieza.forma != "caja" or xyz[2] + pieza.centro[2] + pieza.dims[2] / 2 <= bajo_paneles_z:
            continue
        for sx in (-0.5, 0.5):
            x = xyz[0] + pieza.centro[0] + sx * pieza.dims[0]
            y = xyz[1] + pieza.centro[1] - pieza.dims[1] / 2      # el lado de la pieza que mira al tubo
            for g in (-giro, giro):
                cerca = min(cerca, base_y - ruido_pos_m + x * math.sin(g) + y * math.cos(g))
    return round(max(0.0, borde_paneles_y + HOLGURA_PIEZAS_M - cerca), 3)


def largo_base_m(robot: Robot) -> tuple[float, float]:
    """Hasta dónde llega la base hacia atrás y hacia adelante de su centro, con todo lo que lleva fijo (x mínimo, x máximo)."""
    fijas = {u.hijo: u.xyz for u in robot.uniones if u.tipo == "fixed" and u.padre == ESLABON_BASE}
    extremos = []
    for nombre, xyz in {ESLABON_BASE: (0.0, 0.0, 0.0), **fijas}.items():
        pieza = robot.piezas[nombre]
        medio = pieza.dims[0] / 2 if pieza.forma == "caja" else pieza.dims[0]   # una rueda ocupa su radio
        extremos += [xyz[0] + pieza.centro[0] - medio, xyz[0] + pieza.centro[0] + medio]
    return min(extremos), max(extremos)


def espaciado_copias_m(robot: Robot, recorrido_m: float, minimo_m: float, libre_m: float = 1.0) -> float:
    """Distancia entre copias de la escena para que la base de una no se meta en la copia de al lado.

    recorrido_m: lo que avanza la base hasta el último panel. El robot de la copia vecina parte `espaciado` más
    adelante: entre su parte de atrás y el frente de este, en su última parada, quedan `libre_m`. Redondea al centímetro, hacia arriba.
    """
    atras, adelante = largo_base_m(robot)
    return max(minimo_m, math.ceil((recorrido_m + adelante - atras + libre_m) * 100) / 100)


def punto_montaje(base_0: tuple[float, float, float], paso_m: float, k: int) -> tuple[float, float, float]:
    """Dónde se detiene la base para instalar el panel k. base_0: la parada del panel 0."""
    return (base_0[0] + k * paso_m, base_0[1], base_0[2])


def _acotar(x, lo, hi):
    return x.clamp(lo, hi) if hasattr(x, "clamp") else min(max(x, lo), hi)


def _menor(a, b):
    return (a + b - abs(a - b)) / 2


def _perfil(distancia_m, v_max: float, a_max: float):
    """Velocidad que alcanza, tiempo de aceleración y tiempo a velocidad constante. Trapecio, o triángulo si es corto."""
    v = _menor(distancia_m * 0 + v_max, (distancia_m * a_max) ** 0.5)
    t_a = v / a_max
    t_c = (distancia_m - v * t_a) / (v + 1e-9)
    return v, t_a, _acotar(t_c, 0.0, math.inf)


def duracion_s(distancia_m, v_max: float = VEL_BASE_M_S, a_max: float = ACEL_BASE_M_S2):
    """Tiempo que tarda la base en recorrer la distancia, de detenida a detenida."""
    _, t_a, t_c = _perfil(distancia_m, v_max, a_max)
    return 2 * t_a + t_c


def avance_m(t_s, distancia_m, v_max: float = VEL_BASE_M_S, a_max: float = ACEL_BASE_M_S2):
    """Distancia recorrida a los t_s segundos de partir. Antes de 0 vale 0 y después de llegar vale la distancia."""
    v, t_a, t_c = _perfil(distancia_m, v_max, a_max)
    t1 = _acotar(t_s, t_a * 0, t_a)
    t2 = _acotar(t_s - t_a, t_c * 0, t_c)
    t3 = _acotar(t_s - t_a - t_c, t_a * 0, t_a)
    return _menor(0.5 * a_max * t1 * t1 + v * t2 + v * t3 - 0.5 * a_max * t3 * t3, distancia_m)


def pose_en_viaje(inicio, fin, t_s, v_max: float = VEL_BASE_M_S, a_max: float = ACEL_BASE_M_S2):
    """Pose (x, y, rumbo) de la base a los t_s segundos de un viaje recto de `inicio` a `fin`.

    El rumbo cambia con la misma fracción del avance: la base corrige su giro mientras avanza.
    """
    dx, dy = fin[0] - inicio[0], fin[1] - inicio[1]
    distancia = (dx * dx + dy * dy) ** 0.5
    fraccion = avance_m(t_s, distancia, v_max, a_max) / (distancia + 1e-9)
    return tuple(inicio[k] + (fin[k] - inicio[k]) * fraccion for k in range(3))
