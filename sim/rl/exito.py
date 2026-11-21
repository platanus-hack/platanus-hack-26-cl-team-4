"""Criterio de éxito y recompensa de instalar_panel. Sin Isaac.

Las funciones aceptan números sueltos (tests) o tensores de torch con un valor por entorno.

Éxito (RF-INT-11), medido después de soltar: la succión está apagada, el panel descansa quieto sobre el
tubo dentro de la tolerancia y la ventosa ya se alejó. El entorno exige además que eso dure
PASOS_QUIETO pasos de control seguidos y que ningún eslabón del brazo haya chocado.
"""
from __future__ import annotations

import math

VEL_QUIETO_M_S = 0.05        # el panel "descansa" bajo esta velocidad lineal
GIRO_QUIETO_RAD_S = 0.2      # y bajo esta velocidad angular
ALTURA_APOYO_M = 0.02        # y a esta distancia o menos de la altura de reposo sobre el tubo
ALEJADO_M = 0.10             # la ventosa "se alejó" a esta distancia de la cara de arriba del panel
PASOS_QUIETO = 15            # 0,5 s a 30 Hz

# La recompensa densa es la diferencia de un potencial entre dos pasos de control (Ng, Harada y Russell, 1999).
# Quedarse quieto paga 0, con o sin panel: sostener el panel sin llevarlo ya no es un buen negocio.
# Sellar y soltar en el mismo lugar suma 0. Solo el avance hacia la pose ideal paga.
# Pesos del potencial, en puntos. Un episodio perfecto suma cerca de 35 antes del premio de éxito.
POTENCIAL = {
    "alcanzar": 2.0,     # sin panel: la ventosa llega a la cara de arriba del panel
    "sellar": 3.0,       # el panel está sellado en la ventosa
    "llevar": 20.0,      # avance del panel hacia su pose ideal: lineal, de la pila a la meta
    "afinar": 6.0,       # los últimos centímetros y grados
    "colocado": 10.0,    # panel suelto, quieto y en tolerancia. Vale más que "alcanzar" + "sellar": soltar ahí suma
}
ALEJARSE = 0.3           # fracción de "colocado" que se gana al retirar la ventosa después de soltar
# Costos por segundo de episodio. El entorno los multiplica por el paso de control.
COSTOS = {
    "accion": -0.02,     # cambio brusco de la acción
    "velocidad": -0.01,  # velocidad de las articulaciones
}
# Recompensas de fin de episodio.
PREMIO_EXITO = 50.0      # mayor que todo el potencial: terminar la tarea vale más que acercarse
CASTIGO_FALLA = -10.0    # panel caído
# Un choque borra un éxito: cuesta lo mismo que vale terminar la tarea. Con el éxito que además se pierde, un choque
# pesa ~110 puntos frente a ~70 con el castigo anterior de -10. La política se aleja más de lo que puede tocar.
# Es una recompensa de fin de episodio, no parte del potencial: la diferencia de potencial sigue igual.
CASTIGO_CHOQUE = -PREMIO_EXITO


def _tanh(x):
    return x.tanh() if hasattr(x, "tanh") else math.tanh(x)


def _acos(x):
    return x.acos() if hasattr(x, "acos") else math.acos(x)


def _acotar(x, lo, hi):
    return x.clamp(lo, hi) if hasattr(x, "clamp") else min(max(x, lo), hi)


def _mayor(a, b):
    return (a + b + abs(a - b)) / 2


def error_posicion_m(panel_pos, meta_pos):
    return (sum((panel_pos[k] - meta_pos[k]) ** 2 for k in range(3))) ** 0.5


def error_angulo_grados(quat_relativo):
    """Ángulo entre el panel y su pose ideal. quat_relativo = conj(meta) * panel, (w, x, y, z).

    El panel es simétrico: girado 180° sobre su normal es la misma pose. Por eso se toma el menor ángulo
    hacia la pose ideal o hacia la pose ideal girada 180°.
    """
    w, _, _, z = quat_relativo
    return 2 * _acos(_acotar(_mayor(abs(w), abs(z)), 0.0, 1.0)) * (180 / math.pi)


def en_tolerancia(err_pos_m, err_ang_grados, tol_pos_m: float, tol_ang_grados: float):
    return (err_pos_m <= tol_pos_m) & (err_ang_grados <= tol_ang_grados)


def apoyado(err_altura_m, vel_m_s, giro_rad_s):
    """El panel descansa sobre el tubo: a su altura de reposo y quieto."""
    return (abs(err_altura_m) <= ALTURA_APOYO_M) & (vel_m_s <= VEL_QUIETO_M_S) & (giro_rad_s <= GIRO_QUIETO_RAD_S)


def colocado(err_pos_m, err_ang_grados, err_altura_m, vel_m_s, giro_rad_s, sellada, succion, dist_ventosa_m,
             tol_pos_m: float, tol_ang_grados: float):
    """Condición de éxito de un paso: soltado, apoyado, en tolerancia y con la ventosa lejos."""
    # "== False" y no "not": así la misma línea sirve para un bool y para un tensor de bools.
    suelto = (sellada == False) & (succion == False)  # noqa: E712
    return (en_tolerancia(err_pos_m, err_ang_grados, tol_pos_m, tol_ang_grados)
            & apoyado(err_altura_m, vel_m_s, giro_rad_s) & suelto & (dist_ventosa_m >= ALEJADO_M))


def potencial(dist_ventosa_m, err_pos_m, err_ang_grados, sellada, en_meta_suelto, dist_inicial_m: float):
    """Potencial del estado: cuánto de la tarea ya está hecho, en puntos.

    sellada: 1 si la ventosa tiene el panel. en_meta_suelto: 1 si el panel está suelto, quieto y en tolerancia.
    Los dos como números (0.0 o 1.0). dist_inicial_m: de la pila a la pose ideal (sim/rl/tarea.py).
    El avance del panel cuenta con o sin sello: dejar caer el panel lejos de la meta no suma, y alejarlo resta.
    """
    cerca = 1 - _tanh(dist_ventosa_m / 0.5)
    avance = _acotar(1 - err_pos_m / dist_inicial_m, -1.0, 1.0)
    fino = (1 - _tanh(err_pos_m / 0.08)) * (1 - _tanh(err_ang_grados / 20.0))
    alejarse = (1 - ALEJARSE) + ALEJARSE * _tanh(dist_ventosa_m / 0.15)
    return (POTENCIAL["alcanzar"] * cerca * (1 - en_meta_suelto) + POTENCIAL["sellar"] * sellada
            + POTENCIAL["llevar"] * avance + POTENCIAL["afinar"] * fino
            + POTENCIAL["colocado"] * en_meta_suelto * alejarse)


def costo(cambio_accion2, velocidad2):
    """Costo por segundo de mover el brazo: cambio de la acción y velocidad de las articulaciones, al cuadrado."""
    return COSTOS["accion"] * cambio_accion2 + COSTOS["velocidad"] * velocidad2
