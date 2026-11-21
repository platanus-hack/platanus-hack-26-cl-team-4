"""Escena esquemática de la sala + robot de servicio animado, descrita una sola vez.

La usan exportar_glb.py (Android / web) y exportar_usdz.py (iPhone, AR Quick Look).
Unidades: metros, Y arriba. El pasillo central va en x ≈ 0,15 y el mural al fondo (z negativo).
Medidas aproximadas (±1 m): salen de la nube de puntos de COLMAP y del video, no de un plano.
El robot está ANIMADO A MANO: no está entrenado ni sale de Isaac.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# ---------------- materiales ----------------
MATERIALES = {
    "piso": {"color": (0.78, 0.62, 0.42), "rugosidad": 0.7, "metal": 0.0},
    "muro": {"color": (0.93, 0.93, 0.92), "rugosidad": 0.9, "metal": 0.0},
    "madera": {"color": (0.80, 0.63, 0.40), "rugosidad": 0.6, "metal": 0.0},
    "silla": {"color": (0.10, 0.10, 0.11), "rugosidad": 0.5, "metal": 0.0},
    "mural": {"color": (1.0, 1.0, 1.0), "rugosidad": 0.9, "metal": 0.0, "textura": "mural.jpg"},
    "robot_blanco": {"color": (0.95, 0.96, 0.97), "rugosidad": 0.35, "metal": 0.0},
    "robot_gris": {"color": (0.16, 0.18, 0.22), "rugosidad": 0.5, "metal": 0.2},
    "negro": {"color": (0.03, 0.03, 0.04), "rugosidad": 0.4, "metal": 0.0},
    "ojos": {"color": (0.5, 0.86, 1.0), "rugosidad": 0.3, "metal": 0.0, "emision": (0.5, 0.86, 1.0)},
    "acento": {"color": (0.88, 0.63, 0.02), "rugosidad": 0.4, "metal": 0.0, "emision": (0.35, 0.25, 0.0)},
    "bandeja": {"color": (0.79, 0.81, 0.84), "rugosidad": 0.25, "metal": 0.8},
    "taza": {"color": (1.0, 1.0, 1.0), "rugosidad": 0.2, "metal": 0.0},
    "cafe": {"color": (0.35, 0.22, 0.12), "rugosidad": 0.3, "metal": 0.0},
}


# ---------------- mallas ----------------
@dataclass
class Malla:
    pos: list = field(default_factory=list)
    nor: list = field(default_factory=list)
    uv: list = field(default_factory=list)
    idx: list = field(default_factory=list)

    def agregar(self, p, n, uv, i):
        base = len(self.pos)
        self.pos += [tuple(map(float, v)) for v in p]
        self.nor += [tuple(map(float, v)) for v in n]
        self.uv += [tuple(map(float, v)) for v in uv]
        self.idx += [base + k for k in i]

    def arrays(self):
        return (np.array(self.pos, "f4"), np.array(self.nor, "f4"), np.array(self.uv, "f4"), np.array(self.idx, "u4"))


def caja(m: Malla, centro, tam):
    cx, cy, cz = centro
    sx, sy, sz = (t / 2 for t in tam)
    caras = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
             ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (0, 0, -1), (1, 0, 0)),
             ((0, 0, 1), (0, 1, 0), (-1, 0, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    for n, u, v in caras:
        n, u, v = np.array(n), np.array(u), np.array(v)
        e = np.array([sx, sy, sz])
        c = np.array(centro) + n * e
        du, dv = u * e, v * e
        p = [c - du - dv, c + du - dv, c + du + dv, c - du + dv]
        # orientación antihoraria vista desde afuera
        if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), n) < 0:
            p = [p[0], p[3], p[2], p[1]]
        m.agregar(p, [n] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 0, 2, 3])


def cilindro(m: Malla, centro, radio, alto, lados=24, radio_arriba=None, eje="y"):
    ra = radio if radio_arriba is None else radio_arriba
    p, n, uv, i = [], [], [], []
    for k in range(lados + 1):
        a = 2 * math.pi * k / lados
        ca, sa = math.cos(a), math.sin(a)
        p += [(radio * ca, -alto / 2, radio * sa), (ra * ca, alto / 2, ra * sa)]
        n += [(ca, 0, sa)] * 2
        uv += [(k / lados, 0), (k / lados, 1)]
    for k in range(lados):
        a, b = 2 * k, 2 * k + 2
        i += [a, b, a + 1, a + 1, b, b + 1]
    for y, r, ny in ((alto / 2, ra, 1), (-alto / 2, radio, -1)):
        c = len(p)
        p.append((0, y, 0)); n.append((0, ny, 0)); uv.append((0.5, 0.5))
        for k in range(lados + 1):
            a = 2 * math.pi * k / lados
            p.append((r * math.cos(a), y, r * math.sin(a))); n.append((0, ny, 0)); uv.append((0.5, 0.5))
        for k in range(lados):
            i += [c, c + 2 + k, c + 1 + k] if ny > 0 else [c, c + 1 + k, c + 2 + k]
    p, n = np.array(p), np.array(n)
    if eje == "z":  # rotar el eje Y al eje Z
        rot = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        p, n = p @ rot.T, n @ rot.T
    elif eje == "x":
        rot = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]])
        p, n = p @ rot.T, n @ rot.T
    m.agregar(p + np.array(centro), n, uv, i)


def esfera(m: Malla, centro, radio, seg=20, anillos=14, escala=(1, 1, 1)):
    p, n, uv, i = [], [], [], []
    for a in range(anillos + 1):
        th = math.pi * a / anillos
        for b in range(seg + 1):
            ph = 2 * math.pi * b / seg
            v = (math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph))
            p.append(tuple(radio * v[k] * escala[k] for k in range(3))); n.append(v); uv.append((b / seg, a / anillos))
    for a in range(anillos):
        for b in range(seg):
            q = a * (seg + 1) + b
            i += [q, q + 1, q + seg + 1, q + 1, q + seg + 2, q + seg + 1]
    m.agregar(np.array(p) + np.array(centro), n, uv, i)


def plano(m: Malla, centro, ancho, alto, normal_z=1):
    cx, cy, cz = centro
    w, h = ancho / 2, alto / 2
    p = [(cx - w, cy - h, cz), (cx + w, cy - h, cz), (cx + w, cy + h, cz), (cx - w, cy + h, cz)]
    m.agregar(p, [(0, 0, normal_z)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 0, 2, 3])


# ---------------- la sala ----------------
X0, X1, Z0, Z1 = -4.0, 6.0, -11.0, 2.0   # piso (m)
ALTO_MURO_BAJO = 1.1                    # muros recortados: la maqueta se ve desde arriba
PASILLO_X = 0.15


def sala() -> dict[str, Malla]:
    g: dict[str, Malla] = {k: Malla() for k in ("piso", "muro", "madera", "silla", "mural")}
    caja(g["piso"], ((X0 + X1) / 2, -0.05, (Z0 + Z1) / 2), (X1 - X0, 0.1, Z1 - Z0))
    # muros bajos laterales y muro del fondo completo con el mural
    caja(g["muro"], (X0 - 0.075, ALTO_MURO_BAJO / 2, (Z0 + Z1) / 2), (0.15, ALTO_MURO_BAJO, Z1 - Z0))
    caja(g["muro"], (X1 + 0.075, ALTO_MURO_BAJO / 2, (Z0 + Z1) / 2), (0.15, ALTO_MURO_BAJO, Z1 - Z0))
    caja(g["muro"], ((X0 + X1) / 2, 1.6, Z0 - 0.075), (X1 - X0 + 0.3, 3.2, 0.15))
    plano(g["mural"], (1.0, 1.75, Z0 + 0.005), 7.0, 2.9)
    # gradas de madera frente al mural: 3 escalones
    for k in range(3):
        alto = 0.4 * (3 - k)
        caja(g["madera"], (1.0, alto / 2, Z0 + 0.3 + 0.6 * k), (7.0, alto, 0.6))
    # sillas: dos bloques a los lados del pasillo, filas cada 0,9 m mirando al mural
    for z in np.arange(-8.6, 0.7, 0.9):
        for x in list(np.arange(-3.4, PASILLO_X - 0.6, 0.55)) + list(np.arange(PASILLO_X + 0.75, 4.4, 0.55)):
            caja(g["silla"], (x, 0.45, z), (0.44, 0.04, 0.42))           # asiento
            caja(g["silla"], (x, 0.68, z + 0.2), (0.44, 0.38, 0.03))     # respaldo (detrás, hacia el sur)
            caja(g["silla"], (x, 0.22, z), (0.40, 0.44, 0.36))           # patas, simplificadas como bloque oscuro
    return g


# ---------------- el robot ----------------
def robot_cuerpo() -> dict[str, Malla]:
    g = {k: Malla() for k in ("robot_blanco", "robot_gris", "negro", "ojos", "acento")}
    cilindro(g["robot_gris"], (0, 0.12, 0), 0.28, 0.2, radio_arriba=0.26)
    for l in (-1, 1):
        cilindro(g["negro"], (0.27 * l, 0.07, 0), 0.07, 0.04, eje="x")
    cilindro(g["robot_blanco"], (0, 0.62, 0), 0.2, 0.55)
    esfera(g["robot_blanco"], (0, 0.345, 0), 0.2)
    esfera(g["robot_blanco"], (0, 0.895, 0), 0.2)
    caja(g["acento"], (0, 0.62, 0.2), (0.16, 0.05, 0.02))
    esfera(g["robot_blanco"], (0, 1.1, 0), 0.17)
    caja(g["negro"], (0, 1.1, 0.1), (0.22, 0.12, 0.08))
    for l in (-1, 1):
        esfera(g["ojos"], (0.05 * l, 1.105, 0.145), 0.018, seg=10, anillos=8)
    return g


BRAZO_PIVOTE = (0.0, 0.78, 0.18)


def robot_brazo() -> dict[str, Malla]:
    """Coordenadas relativas al pivote del hombro."""
    g = {k: Malla() for k in ("robot_gris", "bandeja", "taza", "cafe")}
    cilindro(g["robot_gris"], (0, 0, 0.12), 0.025, 0.26, eje="z")
    cilindro(g["bandeja"], (0, 0.02, 0.3), 0.15, 0.015, lados=32)
    cilindro(g["taza"], (0, 0.065, 0.3), 0.032, 0.075, radio_arriba=0.04)
    cilindro(g["cafe"], (0, 0.101, 0.3), 0.036, 0.004)
    caja(g["taza"], (0.048, 0.065, 0.3), (0.012, 0.04, 0.008))  # asa
    return g


# ---------------- animación ----------------
VEL = 0.7  # m/s, como un robot de servicio real


def animacion(z_ini: float, z_fin: float, x: float = PASILLO_X):
    """Ida por el pasillo, entrega (sube la bandeja), giro, vuelta, giro. Devuelve listas de (t, valor)."""
    d = abs(z_fin - z_ini)
    t_ida = d / VEL
    tr, rot, brazo = [], [], []
    t = 0.0
    yaw_ida = 0.0 if z_fin > z_ini else math.pi        # el robot mira hacia +z por defecto
    yaw_vuelta = yaw_ida + math.pi
    tr += [(t, (x, 0, z_ini))]; rot += [(t, yaw_ida)]; brazo += [(t, 0.0)]
    t += t_ida; tr += [(t, (x, 0, z_fin))]; rot += [(t, yaw_ida)]; brazo += [(t, 0.0)]
    t += 0.6; brazo += [(t, -0.35)]                    # ofrece la bandeja
    t += 3.0; brazo += [(t, -0.35)]                    # espera
    t += 0.6; brazo += [(t, 0.0)]
    tr += [(t, (x, 0, z_fin))]; rot += [(t, yaw_ida)]
    t += 1.0; rot += [(t, yaw_vuelta)]; tr += [(t, (x, 0, z_fin))]
    t += t_ida; tr += [(t, (x, 0, z_ini))]; rot += [(t, yaw_vuelta)]
    t += 1.0; rot += [(t, yaw_ida + 2 * math.pi)]; tr += [(t, (x, 0, z_ini))]
    brazo += [(t, 0.0)]
    return tr, rot, brazo


def quat_y(yaw: float):
    return (0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2))   # x, y, z, w


def quat_x(a: float):
    return (math.sin(a / 2), 0.0, 0.0, math.cos(a / 2))


def muestrear(claves, t):
    """Interpolación lineal de una lista (t, valor) en el tiempo t."""
    for (t0, v0), (t1, v1) in zip(claves, claves[1:]):
        if t0 <= t <= t1:
            u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            if isinstance(v0, tuple):
                return tuple(a + (b - a) * u for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * u
    return claves[-1][1]


# Dos variantes: la maqueta de la sala (robot recorre el pasillo) y el robot solo a tamaño real.
VARIANTES = {
    "maqueta": {"sala": True, "z_ini": -8.8, "z_fin": 1.2, "escala": 0.05},
    "robot": {"sala": False, "z_ini": -3.0, "z_fin": 0.0, "escala": 1.0, "x": 0.0},
}
