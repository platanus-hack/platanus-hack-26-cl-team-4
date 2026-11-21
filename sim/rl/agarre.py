"""Agarre por succión virtual: cuándo sella la ventosa y con qué fuerza sostiene. Sin Isaac.

El modelo (docs/escena-isaac.md, "Agarre en el entorno RL"):
- La ventosa sella si la succión está encendida y las 4 esquinas de su placa están sobre el panel,
  a menos de DIST_SELLO_M de su cara de arriba. Eso exige posición, rumbo e inclinación a la vez.
- Mientras sella, una fuerza constante empuja el panel contra la placa y otra igual y opuesta carga la
  ventosa. La fuerza neta sobre el par es cero: el brazo siente el peso real del panel.
- PhysX resuelve el contacto placa–panel. La fricción de la goma evita que el panel resbale.
- El sello y la fuerza se calculan una vez por paso de control. La fuerza va en el marco del panel,
  donde casi no cambia mientras el panel está contra la placa.
- El sello se pierde si se apaga la succión o si alguna esquina se aleja más de DIST_ROMPE_M.

Las funciones aceptan números sueltos o tensores de torch (un valor por entorno).
"""
from __future__ import annotations

from . import cinematica as cin

GRAVEDAD = 9.81
# EN 13155 pide que un elevador por vacío sostenga 2 veces su carga nominal. La carga nominal
# es la carga útil del robot real (clon.json, escala.carga_util_kg).
FACTOR_VENTOSA = 2.0
DIST_SELLO_M = 0.02      # separación máxima entre la placa y el panel para que la ventosa selle
DIST_ROMPE_M = 0.05      # separación a la que un panel sellado se suelta solo
HUNDIDO_M = 0.02         # una esquina más abajo que esto está dentro del panel: no cuenta como sello


def fuerza_ventosa_n(carga_util_kg: float) -> float:
    """Fuerza con que la ventosa aprieta el panel contra la placa."""
    return FACTOR_VENTOSA * GRAVEDAD * carga_util_kg


def esquinas_sobre_panel(ventosa_pos, ventosa_quat, panel_pos, panel_quat, ventosa_tam):
    """Las 4 esquinas de la placa de la ventosa, en el marco del panel. Lista de 4 puntos (x, y, z)."""
    inverso = cin.quat_conj(panel_quat)
    puntos = []
    for sx in (-0.5, 0.5):
        for sy in (-0.5, 0.5):
            e = cin.quat_rotar(ventosa_quat, (sx * ventosa_tam[0], sy * ventosa_tam[1], 0.0))
            mundo = tuple(e[k] + ventosa_pos[k] - panel_pos[k] for k in range(3))
            puntos.append(cin.quat_rotar(inverso, mundo))
    return puntos


def _contacto(esquinas, panel_tam, hasta_m: float):
    """True si las 4 esquinas de la placa están sobre el panel y a menos de `hasta_m` de su cara de arriba."""
    ok = None
    for x, y, z in esquinas:
        separacion = z - panel_tam[2] / 2
        esta = ((abs(x) <= panel_tam[0] / 2) & (abs(y) <= panel_tam[1] / 2)
                & (separacion <= hasta_m) & (separacion >= -HUNDIDO_M))
        ok = esta if ok is None else ok & esta
    return ok


def actualizar(sellada, succion, ventosa_pos, ventosa_quat, panel_pos, panel_quat, ventosa_tam, panel_tam):
    """Estado del sello en el paso siguiente. `sellada` y `succion` son booleanos (o tensores booleanos)."""
    esquinas = esquinas_sobre_panel(ventosa_pos, ventosa_quat, panel_pos, panel_quat, ventosa_tam)
    return succion & ((sellada & _contacto(esquinas, panel_tam, DIST_ROMPE_M)) | _contacto(esquinas, panel_tam, DIST_SELLO_M))


def llave(fuerza_n, ventosa_pos, ventosa_quat, panel_pos, panel_quat):
    """Fuerza y torque sobre el panel, en el marco del panel, cuando la ventosa sella.

    La fuerza va por la normal de la placa, hacia la ventosa, aplicada en el centro de la placa.
    La reacción sobre la ventosa es (0, 0, fuerza_n) en su propio marco, sin torque.
    """
    nx, ny, nz = cin.quat_rotar(ventosa_quat, (0.0, 0.0, 1.0))   # normal de la placa, hacia afuera
    f = (-fuerza_n * nx, -fuerza_n * ny, -fuerza_n * nz)
    r = tuple(ventosa_pos[k] - panel_pos[k] for k in range(3))
    t = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    inverso = cin.quat_conj(panel_quat)
    return cin.quat_rotar(inverso, f), cin.quat_rotar(inverso, t)
