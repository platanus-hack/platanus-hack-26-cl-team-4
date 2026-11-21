"""Cinemática del brazo del clon: directa e inversa en forma cerrada. Sin Isaac.

Cada función recibe `xp`: el módulo `math` para números sueltos (tests, validación) o `torch` para lotes
(un valor por entorno, en la GPU). El código es el mismo en los dos casos.

Convenciones (las de sim/plan.py y backend/viaz/urdf.py):
- Marco de la base: origen en el suelo bajo el centro de la base, X hacia adelante, Z arriba.
- Cuaterniones (w, x, y, z), como tupla de 4 componentes.
- Hombro y codo en 0 = brazo vertical. Con la suma hombro + codo + muñeca 1 = pi, la ventosa mira hacia abajo.
- Rumbo: ángulo en el plano del suelo del eje X de la ventosa (el lado corto de la placa) o del panel (su ancho).
  El panel es simétrico: un rumbo y el mismo más 180° son la misma pose.
"""
from __future__ import annotations

import math

PI = math.pi
MU2_REF = PI / 4   # la muñeca 2 trabaja entre 0 (pila) y pi/2 (tubo): rama estable para las dos poses
MARGEN_LIMITE_RAD = 0.01   # el giro se queda a esta distancia del tope: PhysX rechaza una pose justo en el límite


def acotar(x, lo, hi):
    return x.clamp(lo, hi) if hasattr(x, "clamp") else min(max(x, lo), hi)


def envolver(ang, periodo: float, xp=math):
    """Lleva un ángulo a [-periodo/2, periodo/2)."""
    return ang - periodo * xp.floor(ang / periodo + 0.5)


def quat_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def quat_conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def quat_rotar(q, v):
    """Rota el vector v por el cuaternión unitario q."""
    w, x, y, z = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + y * tz - z * ty, vy + w * ty + z * tx - x * tz, vz + w * tz + x * ty - y * tx)


def quat_eje(eje: int, ang, xp=math):
    """Cuaternión de un giro `ang` alrededor del eje X (0), Y (1) o Z (2)."""
    c, s = xp.cos(ang / 2), xp.sin(ang / 2)
    cero = s * 0
    return (c, *(s if k == eje else cero for k in range(3)))


def rumbo(q, xp=math):
    """Ángulo en el plano del suelo del eje X local de un cuerpo con orientación q."""
    w, x, y, z = q
    return xp.atan2(2 * (x * y + w * z), 1 - 2 * (y * y + z * z))


def a_base(pos, base_pos, base_rumbo, xp=math):
    """Punto del mundo expresado en el marco de la base."""
    dx, dy = pos[0] - base_pos[0], pos[1] - base_pos[1]
    c, s = xp.cos(base_rumbo), xp.sin(base_rumbo)
    return (c * dx + s * dy, -s * dx + c * dy, pos[2] - base_pos[2])


def a_mundo(pos, base_pos, base_rumbo, xp=math):
    """Punto del marco de la base expresado en el mundo."""
    c, s = xp.cos(base_rumbo), xp.sin(base_rumbo)
    return (base_pos[0] + c * pos[0] - s * pos[1], base_pos[1] + s * pos[0] + c * pos[1], base_pos[2] + pos[2])


def directa(c, q, xp=math):
    """Pose de la cara de la ventosa en el marco de la base: (posición, cuaternión). q: los 6 ángulos."""
    pan, hombro, codo, mu1, mu2, mu3 = q
    a1, a2 = hombro, hombro + codo
    a3 = a2 + mu1
    radio = c.l1 * xp.sin(a1) + c.l2 * xp.sin(a2) + (c.m1 + c.m2) * xp.sin(a3)
    alto = c.l1 * xp.cos(a1) + c.l2 * xp.cos(a2) + (c.m1 + c.m2) * xp.cos(a3)
    giro = quat_mul(quat_mul(quat_eje(2, pan, xp), quat_eje(1, a3, xp)),
                    quat_mul(quat_eje(2, mu2, xp), quat_eje(0, mu3, xp)))
    px, py, pz = quat_rotar(giro, (0.0, 0.0, c.placa))
    return ((c.montaje_x + radio * xp.cos(pan) + px, radio * xp.sin(pan) + py, c.hombro_z + alto + pz), giro)


def inversa(c, pos, rumbo_ventosa, pan_ref, xp=math, mu2_ref: float = MU2_REF):
    """Ángulos para dejar la cara de la ventosa en `pos` (marco de la base), mirando hacia abajo.

    pan_ref: de los giros equivalentes, elige el más cercano a este y lo recorta al recorrido del URDF.
    Devuelve (q, alcanzable). Si el punto queda fuera de alcance, q es la pose más estirada hacia él.
    """
    dx, dy, dz = pos[0] - c.montaje_x, pos[1], pos[2] + c.muneca - c.hombro_z
    pan = acotar(pan_ref + envolver(xp.atan2(dy, dx) - pan_ref, 2 * PI, xp),
                 c.inferior[0] + MARGEN_LIMITE_RAD, c.superior[0] - MARGEN_LIMITE_RAD)
    d = dx * xp.cos(pan) + dy * xp.sin(pan)
    coseno = (d * d + dz * dz - c.l1 ** 2 - c.l2 ** 2) / (2 * c.l1 * c.l2)
    alcanzable = (coseno >= -1) & (coseno <= 1)
    codo = xp.acos(acotar(coseno, -1.0, 1.0))
    hombro = xp.atan2(d, dz) - xp.atan2(c.l2 * xp.sin(codo), c.l1 + c.l2 * xp.cos(codo))
    mu1 = PI - hombro - codo
    mu2 = mu2_ref + envolver(pan + PI - rumbo_ventosa - mu2_ref, PI, xp)
    return (pan, hombro, codo, mu1, mu2, mu2 * 0), alcanzable
