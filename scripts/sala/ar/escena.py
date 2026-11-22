"""Escena esquemática de la sala + robot de servicio animado, descrita una sola vez.

La usan exportar_glb.py (Android / web) y exportar_usdz.py (iPhone, AR Quick Look).
Unidades: metros, Y arriba. El pasillo central va en x ≈ 0,15 y el mural al fondo (z negativo).
Medidas aproximadas (±1 m): salen de la nube de puntos de COLMAP y del video, no de un plano.
El robot está ANIMADO A MANO: no está entrenado ni sale de Isaac.
El humanoide de la fila es la malla del modelo publicado del Unitree H1, de pie y quieto (h1_pose.npz).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

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
    "naranja": {"color": (0.95, 0.45, 0.08), "rugosidad": 0.45, "metal": 0.1},
    "azul": {"color": (0.15, 0.35, 0.75), "rugosidad": 0.4, "metal": 0.1},
    "gris_claro": {"color": (0.62, 0.65, 0.70), "rugosidad": 0.5, "metal": 0.3},
    "metal_mecanizado": {"color": (0.48, 0.51, 0.54), "rugosidad": 0.32, "metal": 0.72},
    "goma": {"color": (0.018, 0.021, 0.024), "rugosidad": 0.86, "metal": 0.0},
    "petroleo": {"color": (0.055, 0.28, 0.31), "rugosidad": 0.36, "metal": 0.22},
    "vidrio": {"color": (0.024, 0.060, 0.081), "rugosidad": 0.16, "metal": 0.40},
    "estado": {"color": (0.12, 0.72, 0.53), "rugosidad": 0.32, "metal": 0.0, "emision": (0.07, 0.43, 0.32)},
    "helice": {"color": (0.45, 0.48, 0.52), "rugosidad": 0.3, "metal": 0.5},
    # escaneo estilo Matrix: textura de números con transparencia, que brilla
    "matrix": {"color": (1.0, 1.0, 1.0), "rugosidad": 1.0, "metal": 0.0, "textura": "matrix.png",
               "transparente": True, "emision_textura": True, "doble_cara": True},
    "grilla": {"color": (1.0, 1.0, 1.0), "rugosidad": 1.0, "metal": 0.0, "textura": "grilla.png",
               "transparente": True, "emision_textura": True, "doble_cara": True},
    "caja_analisis": {"color": (0.3, 1.0, 0.55), "rugosidad": 1.0, "metal": 0.0, "emision": (0.12, 0.45, 0.22),
                      "opacidad": 0.2, "transparente": True, "doble_cara": True},
    "laser": {"color": (0.3, 1.0, 0.55), "rugosidad": 1.0, "metal": 0.0, "emision": (0.3, 1.0, 0.55)},
    "anillo": {"color": (0.3, 1.0, 0.55), "rugosidad": 1.0, "metal": 0.0, "emision": (0.3, 1.0, 0.55)},
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
    pendiente = (radio - ra) / alto
    norma = math.hypot(1, pendiente)
    for k in range(lados + 1):
        a = 2 * math.pi * k / lados
        ca, sa = math.cos(a), math.sin(a)
        p += [(radio * ca, -alto / 2, radio * sa), (ra * ca, alto / 2, ra * sa)]
        n += [(ca / norma, pendiente / norma, sa / norma)] * 2
        uv += [(k / lados, 0), (k / lados, 1)]
    for k in range(lados):
        a, b = 2 * k, 2 * k + 2
        i += [a, a + 1, b, a + 1, b + 1, b]
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
            p.append(tuple(radio * v[k] * escala[k] for k in range(3)))
            normal = np.asarray(v) / escala
            n.append(normal / np.linalg.norm(normal))
            uv.append((b / seg, a / anillos))
    for a in range(anillos):
        for b in range(seg):
            q = a * (seg + 1) + b
            if a > 0:
                i += [q, q + 1, q + seg + 1]
            if a < anillos - 1:
                i += [q + 1, q + seg + 2, q + seg + 1]
    m.agregar(np.array(p) + np.array(centro), n, uv, i)



def carcasa(m: Malla, centro, tam, borde, giro=0.0):
    """Carcasa mecanizada con cantos biselados y esquinas redondeadas."""
    sx, sy, sz = (v / 2 for v in tam)
    borde = min(borde, sx * .8, sy * .8, sz * .8)
    radio = min(2 * borde, sx * .88, sz * .88)
    c, s = math.cos(giro), math.sin(giro)
    rot = np.array(((c, 0, s), (0, 1, 0), (-s, 0, c)))
    centro = np.asarray(centro)

    def perfil(y, recorte):
        puntos = []
        for esquina in range(4):
            a = esquina * math.pi / 2
            x = math.copysign(sx - radio, math.cos(a + math.pi / 4))
            z = math.copysign(sz - radio, math.sin(a + math.pi / 4))
            r = radio - recorte
            for paso in range(4):
                theta = a + paso * math.pi / 6
                puntos.append(centro + rot @ (x + r * math.cos(theta), y, z + r * math.sin(theta)))
        return puntos

    def cara(puntos, direccion):
        normal = np.cross(puntos[1] - puntos[0], puntos[2] - puntos[0])
        if np.dot(normal, direccion) < 0:
            puntos = puntos[::-1]
            normal = -normal
        normal /= np.linalg.norm(normal)
        n = len(puntos)
        indices = [k for i in range(1, n - 1) for k in (0, i, i + 1)]
        m.agregar(puntos, [normal] * n, [(0, 0)] * n, indices)

    anillos = [perfil(-sy, borde), perfil(-sy + borde, 0), perfil(sy - borde, 0), perfil(sy, borde)]
    cara(anillos[0], (0, -1, 0))
    cara(anillos[-1], (0, 1, 0))
    for bajo, alto in zip(anillos, anillos[1:]):
        for i in range(len(bajo)):
            j = (i + 1) % len(bajo)
            cara([bajo[i], bajo[j], alto[j], alto[i]], (bajo[i] + alto[j]) / 2 - centro)


def tramo(m: Malla, desde, hasta, radio, radio_final=None, lados=12):
    """Cilindro o tronco de cono alineado a una articulación."""
    origen, destino = np.asarray(desde), np.asarray(hasta)
    vector = destino - origen
    largo = np.linalg.norm(vector)
    eje = vector / largo
    referencia = (0, 0, 1) if abs(eje[2]) < .9 else (1, 0, 0)
    lateral = np.cross(eje, referencia)
    lateral /= np.linalg.norm(lateral)
    rot = np.column_stack((lateral, eje, np.cross(lateral, eje)))
    segmento = Malla()
    cilindro(segmento, (0, 0, 0), radio, largo, lados=lados, radio_arriba=radio_final)
    p, n, uv, indices = segmento.arrays()
    m.agregar(p @ rot.T + (origen + destino) / 2, n @ rot.T, uv, indices)


def aro(m: Malla, centro, radio, tubo, eje="y", lados=20):
    """Aro cerrado con una sección circular ligera."""
    p, n, uv, indices = [], [], [], []
    centro = np.asarray(centro)
    for i in range(lados):
        a = i * math.tau / lados
        for j in range(6):
            b = j * math.tau / 6
            direccion = (math.cos(a) * math.cos(b), math.sin(b), math.sin(a) * math.cos(b))
            normal = np.asarray(direccion)
            posicion = np.array((radio * math.cos(a), 0, radio * math.sin(a))) + tubo * normal
            if eje == "z":
                posicion = posicion[[0, 2, 1]] * (1, -1, 1)
                normal = normal[[0, 2, 1]] * (1, -1, 1)
            p.append(centro + posicion)
            n.append(normal)
            uv.append((i / lados, j / 6))
            q = i * 6 + j
            sig_i = ((i + 1) % lados) * 6
            sig_j = (j + 1) % 6
            indices += [q, q - j + sig_j, sig_i + j, q - j + sig_j, sig_i + sig_j, sig_i + j]
    m.agregar(p, n, uv, indices)


def plano(m: Malla, centro, ancho, alto, normal_z=1, du=0.0):
    cx, cy, cz = centro
    w, h = ancho / 2, alto / 2
    p = [(cx - w, cy - h, cz), (cx + w, cy - h, cz), (cx + w, cy + h, cz), (cx - w, cy + h, cz)]
    m.agregar(p, [(0, 0, normal_z)] * 4, [(du, 0), (1 + du, 0), (1 + du, 1), (du, 1)], [0, 1, 2, 0, 2, 3])


def plano_piso(m: Malla, centro, ancho, largo):
    """Rectángulo horizontal (normal hacia arriba)."""
    cx, cy, cz = centro
    w, l = ancho / 2, largo / 2
    p = [(cx - w, cy, cz + l), (cx + w, cy, cz + l), (cx + w, cy, cz - l), (cx - w, cy, cz - l)]
    m.agregar(p, [(0, 1, 0)] * 4, [(0, 0), (1, 0), (1, 1), (0, 1)], [0, 1, 2, 0, 2, 3])


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
    for z in np.arange(-7.7, 0.7, 0.9):
        for x in list(np.arange(-3.4, PASILLO_X - 0.6, 0.55)) + list(np.arange(PASILLO_X + 0.75, 4.4, 0.55)):
            caja(g["silla"], (x, 0.45, z), (0.44, 0.04, 0.42))           # asiento
            caja(g["silla"], (x, 0.68, z + 0.2), (0.44, 0.38, 0.03))     # respaldo (detrás, hacia el sur)
            caja(g["silla"], (x, 0.22, z), (0.40, 0.44, 0.36))           # patas, simplificadas como bloque oscuro
    return g


# ---------------- robots ----------------
def robot_cuerpo() -> dict[str, Malla]:
    """Robot de servicio con base autónoma, mástil y pantalla de estado."""
    g = {k: Malla() for k in ("robot_blanco", "robot_gris", "negro", "ojos", "acento", "goma", "vidrio", "estado")}
    cilindro(g["goma"], (0, .075, 0), .272, .15, lados=28)
    cilindro(g["robot_gris"], (0, .154, 0), .282, .035, lados=28)
    cilindro(g["robot_blanco"], (0, .228, 0), .263, .118, lados=28, radio_arriba=.205)
    aro(g["acento"], (0, .169, 0), .265, .006, lados=30)
    for lado in (-1, 1):
        cilindro(g["goma"], (lado * .271, .075, 0), .075, .047, lados=16, eje="x")
        cilindro(g["robot_gris"], (lado * .296, .075, 0), .040, .007, lados=14, eje="x")
    carcasa(g["robot_gris"], (0, .247, .218), (.23, .045, .052), .012)
    for x in (-.068, 0, .068):
        cilindro(g["vidrio"], (x, .247, .246), .012, .008, lados=12, eje="z")
    cilindro(g["robot_gris"], (0, .53, -.025), .096, .49, radio_arriba=.115, lados=18)
    carcasa(g["robot_blanco"], (0, .605, 0), (.325, .46, .30), .055)
    carcasa(g["negro"], (0, .66, .151), (.20, .12, .035), .013)
    carcasa(g["vidrio"], (0, .661, .171), (.172, .093, .018), .008)
    caja(g["estado"], (0, .641, .181), (.100, .008, .002))
    for x in (-.103, 0, .103):
        caja(g["robot_gris"], (x, .465, -.148), (.025, .075, .013))
    cilindro(g["robot_gris"], (0, .894, -.017), .073, .15, lados=16)
    esfera(g["robot_blanco"], (0, 1.07, 0), .157, seg=20, anillos=12, escala=(1.10, .83, .96))
    carcasa(g["negro"], (0, 1.067, .130), (.245, .118, .089), .027)
    carcasa(g["vidrio"], (0, 1.069, .176), (.221, .092, .018), .008)
    for x in (-.054, .054):
        carcasa(g["ojos"], (x, 1.077, .187), (.025, .030, .006), .002)
    return g


BRAZO_PIVOTE = (0.0, 0.78, 0.18)


def robot_brazo() -> dict[str, Malla]:
    """El conjunto móvil conserva el pivote y la posición de la taza."""
    g = {k: Malla() for k in ("robot_gris", "robot_blanco", "metal_mecanizado", "bandeja", "taza", "cafe", "goma")}
    cilindro(g["robot_gris"], (0, 0, .023), .056, .055, lados=16, eje="z")
    tramo(g["metal_mecanizado"], (0, 0, .04), (0, 0, .25), .027, .019)
    carcasa(g["robot_blanco"], (0, .001, .14), (.075, .063, .145), .014)
    cilindro(g["robot_gris"], (0, 0, .294), .047, .031, lados=16)
    cilindro(g["bandeja"], (0, .023, .300), .151, .016, lados=30)
    aro(g["metal_mecanizado"], (0, .034, .30), .143, .006, lados=28)
    cilindro(g["goma"], (0, .033, .300), .077, .004, lados=16)
    cilindro(g["taza"], (0, .065, .300), .028, .065, lados=20, radio_arriba=.039)
    cilindro(g["cafe"], (0, .099, .300), .034, .005, lados=20)
    aro(g["taza"], (0, .102, .30), .037, .004, lados=20)
    aro(g["taza"], (.042, .070, .300), .019, .005, eje="z", lados=14)
    return g


def robot_industrial() -> dict[str, Malla]:
    """Brazo de seis ejes con pinza, montado en una plataforma industrial."""
    g = {k: Malla() for k in ("robot_gris", "naranja", "negro", "acento", "metal_mecanizado", "goma", "estado")}
    carcasa(g["robot_gris"], (0, .166, 0), (.63, .19, .56), .045)
    carcasa(g["negro"], (0, .26, 0), (.58, .053, .49), .018)
    for lado in (-1, 1):
        for z in (-.192, .192):
            cilindro(g["goma"], (lado * .289, .076, z), .076, .083, lados=16, eje="x")
            cilindro(g["metal_mecanizado"], (lado * .333, .076, z), .037, .012, lados=12, eje="x")
        caja(g["acento"], (lado * .307, .193, .236), (.014, .034, .035))
    carcasa(g["negro"], (0, .173, .279), (.27, .051, .035), .015)
    caja(g["estado"], (0, .176, .300), (.19, .010, .004))
    cilindro(g["metal_mecanizado"], (0, .295, -.105), .145, .042, lados=24)
    cilindro(g["robot_gris"], (0, .344, -.105), .129, .059, lados=20)
    hombro, codo, muneca = (0, .455, -.11), (0, .945, -.195), (0, .806, .331)
    carcasa(g["naranja"], (0, .438, -.11), (.252, .185, .225), .040)
    tramo(g["naranja"], hombro, codo, .107, .079, lados=10)
    tramo(g["naranja"], codo, muneca, .091, .056, lados=10)
    for y, z, radio in ((.455, -.11, .112), (.945, -.195, .084), (.806, .331, .062)):
        cilindro(g["robot_gris"], (0, y, z), radio, radio * 2.03, lados=18, eje="x")
        for lado in (-1, 1):
            cilindro(g["metal_mecanizado"], (lado * radio * 1.05, y, z), radio * .57, .016, lados=16, eje="x")
    cable = [(-.092, .47, -.18), (-.107, .73, -.29), (-.083, 1.009, -.24), (-.061, .98, .081), (-.040, .844, .305)]
    for a, b in zip(cable, cable[1:]):
        tramo(g["goma"], a, b, .011, lados=8)
    tramo(g["metal_mecanizado"], muneca, (0, .722, .395), .047, .042)
    carcasa(g["negro"], (0, .695, .406), (.143, .063, .088), .011)
    for x in (-.057, .057):
        carcasa(g["metal_mecanizado"], (x, .628, .42), (.025, .101, .056), .006)
        caja(g["goma"], (x * .81, .588, .425), (.021, .024, .057))
    return g


def robot_cuadrupedo() -> dict[str, Malla]:
    """Cuadrúpedo de inspección con patas articuladas y cámara frontal."""
    g = {k: Malla() for k in ("gris_claro", "robot_gris", "negro", "vidrio", "petroleo", "metal_mecanizado", "ojos", "goma")}
    carcasa(g["robot_gris"], (0, .53, 0), (.42, .15, .70), .037)
    carcasa(g["petroleo"], (0, .625, .015), (.407, .13, .655), .031)
    carcasa(g["gris_claro"], (0, .705, -.054), (.265, .048, .42), .015)
    carcasa(g["negro"], (0, .555, .33), (.32, .114, .151), .022)
    carcasa(g["vidrio"], (0, .563, .409), (.267, .073, .026), .011)
    for x in (-.082, .082):
        cilindro(g["metal_mecanizado"], (x, .567, .425), .027, .014, lados=12, eje="z")
        cilindro(g["ojos"], (x, .567, .435), .012, .008, lados=12, eje="z")
    cilindro(g["negro"], (0, .756, .215), .055, .057, lados=16)
    cilindro(g["vidrio"], (0, .773, .215), .057, .024, lados=16)
    for lado in (-1, 1):
        for signo in (-1, 1):
            z = signo * .245
            cadera = (lado * .209, .512, z)
            rodilla = (lado * .278, .277, z - signo * .123)
            pie = (lado * .286, .064, z + signo * .124)
            cilindro(g["negro"], cadera, .078, .099, lados=16, eje="x")
            cilindro(g["metal_mecanizado"], (lado * .264, .512, z), .055, .015, lados=14, eje="x")
            tramo(g["gris_claro"], cadera, rodilla, .050, .033, lados=10)
            esfera(g["negro"], rodilla, .048, seg=12, anillos=8)
            tramo(g["robot_gris"], rodilla, pie, .031, .021, lados=10)
            carcasa(g["goma"], (pie[0], .036, pie[2]), (.099, .072, .126), .014)
    return g


def robot_dron() -> dict[str, Malla]:
    """Dron de inspección con cuatro rotores, protectores y cámara estabilizada."""
    g = {k: Malla() for k in ("negro", "helice", "ojos", "acento", "robot_gris", "gris_claro", "goma", "vidrio", "estado")}
    carcasa(g["gris_claro"], (0, 1.04, 0), (.282, .134, .405), .034)
    carcasa(g["robot_gris"], (0, .975, -.018), (.250, .059, .352), .021)
    carcasa(g["negro"], (0, 1.116, -.055), (.157, .038, .195), .012)
    caja(g["acento"], (0, 1.137, -.054), (.100, .007, .025))
    for x in (-.307, .307):
        for z in (-.319, .319):
            tramo(g["robot_gris"], (x * .33, 1.018, z * .30), (x, 1.051, z), .037, .023)
            cilindro(g["negro"], (x, 1.064, z), .045, .063, lados=16)
            cilindro(g["gris_claro"], (x, 1.106, z), .028, .023, lados=14)
            aro(g["goma"], (x, 1.107, z), .155, .008, lados=20)
            carcasa(g["helice"], (x, 1.115, z), (.267, .013, .022), .005, giro=.52 * (x / abs(x)))
            esfera(g["estado"] if z > 0 else g["acento"], (x, 1.057, z + .047), .009, seg=10, anillos=6)
    for x in (-.065, .065):
        tramo(g["negro"], (x, .992, .111), (x, .901, .173), .013, lados=10)
    cilindro(g["robot_gris"], (0, .906, .172), .052, .127, lados=16, eje="x")
    carcasa(g["negro"], (0, .902, .180), (.105, .084, .094), .014)
    cilindro(g["vidrio"], (0, .902, .233), .031, .023, lados=16, eje="z")
    cilindro(g["ojos"], (0, .902, .246), .014, .004, lados=12, eje="z")
    return g


def robot_humanoide() -> dict[str, Malla]:
    """Unitree H1 de pie: malla del modelo publicado, de h1_pose.npz (sale de generar_h1_pose.py). Mira a +z."""
    d = np.load(Path(__file__).with_name("h1_pose.npz"))
    m = Malla()
    m.agregar(d["pos"], d["nor"], np.zeros((len(d["pos"]), 2)), d["idx"].tolist())
    return {"robot_gris": m}


def escaneo(ancho: float, alto: float) -> dict[str, Malla]:
    """Muro de números estilo Matrix que recorre el lugar: dos capas con profundidad y un marco de láser."""
    g = {k: Malla() for k in ("matrix", "laser")}
    plano(g["matrix"], (0, alto / 2, 0), ancho, alto)
    plano(g["matrix"], (0, alto / 2, -0.35), ancho, alto, du=0.43)       # segunda capa, desfasada
    grosor = 0.045
    caja(g["laser"], (0, grosor / 2, 0), (ancho, grosor, 0.05))          # línea en el piso
    caja(g["laser"], (0, alto, 0), (ancho, grosor, 0.05))                # línea arriba
    for x in (-ancho / 2, ancho / 2):                                    # bordes verticales
        caja(g["laser"], (x, alto / 2, 0), (grosor, alto, 0.05))
    return g


def franja_grilla(ancho: float, largo: float) -> dict[str, Malla]:
    """Franja de grilla verde en el piso: se enciende cuando el muro pasa por encima (zona ya escaneada)."""
    g = {"grilla": Malla()}
    plano_piso(g["grilla"], (0, 0.006, 0), ancho, largo)
    return g


def caja_analisis(modelo: dict[str, Malla], brazo: dict[str, Malla] | None = None) -> dict[str, Malla]:
    """Ajusta la caja de escaneo a la silueta de cada robot."""
    puntos = np.concatenate([np.asarray(m.pos) for m in modelo.values() if m.pos])
    if brazo is not None:
        puntos_brazo = np.concatenate([np.asarray(m.pos) for m in brazo.values() if m.pos])
        puntos = np.concatenate([puntos, puntos_brazo + BRAZO_PIVOTE])
    minimo = puntos.min(axis=0) - (.065, 0, .07)
    maximo = puntos.max(axis=0) + (.065, .075, .07)
    minimo[1] = 0
    centro = (minimo + maximo) / 2
    alto = maximo[1]

    g = {"caja_analisis": Malla(), "laser": Malla()}
    caja(g["caja_analisis"], centro, maximo - minimo)
    for x in (minimo[0], maximo[0]):
        for z in (minimo[2], maximo[2]):
            caja(g["laser"], (x, centro[1], z), (.012, alto, .012))
    return g


def anillo() -> dict[str, Malla]:
    """Marca bajo el robot elegido."""
    g = {"anillo": Malla()}
    cilindro(g["anillo"], (0, 0.012, 0), 0.42, 0.012, lados=40)
    return g


def _fuente(tam: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", tam)
    except OSError:
        return ImageFont.load_default()


def textura_matrix(destino, ancho=1024, alto=512, semilla=7):
    """PNG con columnas densas de números verdes sobre fondo transparente (estilo Matrix)."""
    import random
    from PIL import Image, ImageDraw
    random.seed(semilla)
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = _fuente(34)
    paso_x, paso_y = 21, 33
    for x in range(2, ancho, paso_x):
        for _ in range(2):                                   # dos estelas por columna: más densidad
            largo = random.randint(8, alto // paso_y + 4)
            inicio = random.randint(-largo // 2, alto // paso_y)
            for k in range(largo):
                y = (inicio + k) * paso_y
                if not 0 <= y < alto:
                    continue
                brillo = (k + 1) / largo
                cabeza = k == largo - 1
                color = (225, 255, 235, 255) if cabeza else (70, 255, 150, int(150 + 105 * brillo))
                d.text((x, y), random.choice("0123456789"), font=fnt, fill=color)
    a = np.array(img).astype("f4")
    filas = np.linspace(0, 1, alto)
    a[:, :, 3] *= np.clip(np.minimum(filas, 1 - filas) * 8, 0, 1)[:, None]
    Image.fromarray(a.astype("u1"), "RGBA").save(destino)


def textura_grilla(destino, celdas=16, alto=128, semilla=11):
    """PNG de una franja de grilla verde (celdas cuadradas, bordes brillantes y algunos números)."""
    import random
    from PIL import Image, ImageDraw
    random.seed(semilla)
    ancho = celdas * alto
    img = Image.new("RGBA", (ancho, alto), (40, 255, 130, 38))
    d = ImageDraw.Draw(img)
    for k in range(celdas + 1):
        d.line([(k * alto, 0), (k * alto, alto)], fill=(80, 255, 160, 255), width=6)
    d.line([(0, 0), (ancho, 0)], fill=(80, 255, 160, 255), width=6)
    d.line([(0, alto - 1), (ancho, alto - 1)], fill=(80, 255, 160, 255), width=6)
    for k in range(celdas):
        d.line([(k * alto + alto // 2, 0), (k * alto + alto // 2, alto)], fill=(80, 255, 160, 110), width=2)
        d.line([(k * alto, alto // 2), (k * alto + alto, alto // 2)], fill=(80, 255, 160, 110), width=2)
        if random.random() < 0.6:
            d.text((k * alto + 12, 10), "".join(random.choice("01") for _ in range(4)), font=_fuente(26),
                   fill=(150, 255, 190, 230))
    img.save(destino)


# ---------------- línea de tiempo ----------------
VEL = 0.7          # m/s, como un robot de servicio real
# El cuadro 0 es la "pose de reposo": los 5 robots visibles y completos. AR Quick Look (iPhone) y Scene Viewer
# (Android) usan ese cuadro para medir el objeto, ponerlo sobre el piso, calcular la sombra y moverlo con los dedos.
# Si algo empieza encogido a cero, el objeto queda "plano" y la AR se comporta mal.
T_ESCANEO = (1.0, 8.0)   # 7 s: el muro recorre el espacio despacio, para que se note
T_ELIGE = 8.6      # aparece el anillo bajo el elegido y se apagan las cajas de análisis
T_DESAPARECEN = (9.3, 10.0)
T_ENTREGA = 10.6   # el elegido parte a repartir el café
REAPARECEN = 1.6   # segundos antes del final: los otros 4 vuelven a aparecer para reiniciar el bucle igual que empezó
MINIMO = 0.001     # escala de "escondido" (0 exacto rompe algunas normales)


def entrega(z_ini: float, z_fin: float, x: float, t0: float):
    """Ida, entrega (sube la bandeja), giro, vuelta, giro. Listas de (t, valor) desde t0."""
    t_ida = abs(z_fin - z_ini) / VEL
    yaw_ida = 0.0 if z_fin > z_ini else math.pi        # el robot mira hacia +z por defecto
    tr, rot, brazo = [], [], []
    t = t0
    tr += [(0.0, (x, 0, z_ini)), (t, (x, 0, z_ini))]; rot += [(0.0, yaw_ida), (t, yaw_ida)]; brazo += [(0.0, 0.0), (t, 0.0)]
    t += t_ida; tr += [(t, (x, 0, z_fin))]; rot += [(t, yaw_ida)]; brazo += [(t, 0.0)]
    t += 0.6; brazo += [(t, -0.35)]
    t += 3.0; brazo += [(t, -0.35)]
    t += 0.6; brazo += [(t, 0.0)]
    tr += [(t, (x, 0, z_fin))]; rot += [(t, yaw_ida)]
    t += 1.0; rot += [(t, yaw_ida + math.pi)]; tr += [(t, (x, 0, z_fin))]
    t += t_ida; tr += [(t, (x, 0, z_ini))]; rot += [(t, yaw_ida + math.pi)]
    t += 1.0; rot += [(t, yaw_ida + 2 * math.pi)]; tr += [(t, (x, 0, z_ini))]
    brazo += [(t, 0.0)]
    return tr, rot, brazo, t


@dataclass
class Nodo:
    nombre: str
    mallas: dict | None = None
    hijos: list = field(default_factory=list)
    t: tuple = (0.0, 0.0, 0.0)            # traslación fija (si no hay pista "t")
    pistas: dict = field(default_factory=dict)   # "t": [(t, xyz)], "ry"/"rx": [(t, rad)], "s": [(t, escala)]


ROBOTS = [robot_industrial, robot_cuadrupedo, None, robot_dron, robot_humanoide]   # None = el de servicio (elegido)
ELEGIDO = 2

# Todo centrado en el punto donde se coloca el objeto: la fila queda adelante (z < 0) y el elegido viene hacia quien mira.
VARIANTES = {
    "maqueta": {"sala": True, "escala": 0.05, "fila_z": -8.7, "fila_x": [-2.6, -1.25, PASILLO_X, 1.55, 2.9],
                "z_fin": 1.2, "escaneo": (X1 - X0 + 0.4, 3.0, (X0 + X1) / 2, Z0 + 0.4, Z1), "franja": 0.9},
    "robot": {"sala": False, "escala": 1.0, "fila_z": -1.0, "fila_x": [-1.9, -0.95, 0.0, 0.95, 1.9],
              "z_fin": 1.3, "escaneo": (6.5, 3.0, 0.0, -4.0, 2.5), "franja": 0.5},   # cubre el espacio real
}
# Diagnóstico (/sala/prueba): la misma escena sin el muro de números, para aislar qué rompe la AR del iPhone.
VARIANTES["prueba_sin_escaneo"] = {**VARIANTES["robot"], "escaneo": None}


def construir(variante: str):
    """Devuelve (raíz, duración total en s)."""
    cfg = VARIANTES[variante]
    hijos = []
    if cfg["sala"]:
        hijos.append(Nodo("sala", sala()))
    tr, rot, br, fin = entrega(cfg["fila_z"], cfg["z_fin"], cfg["fila_x"][ELEGIDO], T_ENTREGA)
    e0, e1 = T_ESCANEO
    if cfg["escaneo"] is not None:
        _, _, _, z_desde, z_hasta = cfg["escaneo"]
        cuando_pasa = lambda z: e0 + (z - z_desde) / (z_hasta - z_desde) * (e1 - e0)  # noqa: E731
        t_paso = cuando_pasa(cfg["fila_z"])
    for k, (fabrica, x) in enumerate(zip(ROBOTS, cfg["fila_x"])):
        modelo = robot_cuerpo() if fabrica is None else fabrica()
        brazo_servicio = robot_brazo() if k == ELEGIDO else None
        extras = []
        if cfg["escaneo"] is not None:   # caja de análisis: se enciende cuando el muro pasa por el robot
            extras.append(Nodo("analisis", caja_analisis(modelo, brazo_servicio), pistas={"s": [
                (0.0, MINIMO), (t_paso - 0.05, MINIMO), (t_paso + 0.25, 1.0), (T_ELIGE, 1.0),
                (T_ELIGE + 0.35, MINIMO), (fin, MINIMO)]}))
        if k == ELEGIDO:
            marca = Nodo("anillo", anillo(), pistas={"s": [(0.0, MINIMO), (T_ELIGE, MINIMO), (T_ELIGE + 0.3, 1.0),
                                                            (T_ENTREGA + 1.0, 1.0), (T_ENTREGA + 1.5, MINIMO), (fin, MINIMO)]})
            brazo = Nodo("brazo", brazo_servicio, t=BRAZO_PIVOTE, pistas={"rx": br})
            hijos.append(Nodo("robot_servicio", modelo, hijos=[brazo, marca, *extras], pistas={"t": tr, "ry": rot}))
        else:
            d0, d1 = T_DESAPARECEN
            r0 = fin - REAPARECEN + 0.2 * (k if k < ELEGIDO else k - 1)
            escala = [(0.0, 1.0), (d0 + 0.08 * k, 1.0), (d1 + 0.08 * k, MINIMO),
                      (r0, MINIMO), (r0 + 0.5, 1.0), (fin, 1.0)]
            hijos.append(Nodo(f"robot_{fabrica.__name__.split('_')[1]}", modelo, hijos=extras,
                              t=(x, 0, cfg["fila_z"]), pistas={"s": escala}))
    if cfg["escaneo"] is None:
        raiz = Nodo("viaz", hijos=hijos, pistas={})
        _tiempos_crecientes(raiz)
        return raiz, fin
    ancho, alto, cx, z_desde, z_hasta = cfg["escaneo"]
    # rastro en el piso: franjas de grilla que se encienden cuando el muro pasa por encima
    paso = cfg["franja"]
    n = int(math.ceil((z_hasta - z_desde) / paso))
    for k in range(n):
        zc = z_desde + (k + 0.5) * paso
        tk = cuando_pasa(zc)
        apaga = T_ELIGE + 0.3 + 0.04 * k
        hijos.append(Nodo(f"rastro_{k:02d}", franja_grilla(ancho, paso * 0.96), t=(cx, 0, zc), pistas={"s": [
            (0.0, MINIMO), (tk - 0.05, MINIMO), (tk + 0.2, 1.0), (apaga, 1.0), (apaga + 0.4, MINIMO), (fin, MINIMO)]}))
    hijos.append(Nodo("escaneo", escaneo(ancho, alto), pistas={
        "t": [(0.0, (cx, 0, z_desde)), (e0, (cx, 0, z_desde)), (e1, (cx, 0, z_hasta)), (fin, (cx, 0, z_hasta))],
        "s": [(0.0, MINIMO), (e0 - 0.01, MINIMO), (e0, 1.0), (e1, 1.0), (e1 + 0.01, MINIMO), (fin, MINIMO)]}))
    raiz = Nodo("viaz", hijos=hijos, pistas={})
    _tiempos_crecientes(raiz)
    return raiz, fin


def pose_inicial(n: Nodo) -> dict:
    """Traslación, rotación (cuaternión x, y, z, w) y escala en el cuadro 0: la pose de reposo del objeto."""
    t = muestrear(n.pistas["t"], 0.0) if "t" in n.pistas else n.t
    if "ry" in n.pistas:
        q = quat_y(muestrear(n.pistas["ry"], 0.0))
    elif "rx" in n.pistas:
        q = quat_x(muestrear(n.pistas["rx"], 0.0))
    else:
        q = (0.0, 0.0, 0.0, 1.0)
    s = muestrear(n.pistas["s"], 0.0) if "s" in n.pistas else 1.0
    return {"t": tuple(t), "q": q, "s": s}


def _tiempos_crecientes(n: Nodo):
    """glTF exige tiempos estrictamente crecientes: corre 1 ms las claves repetidas."""
    for clave, claves in n.pistas.items():
        fijas, previo = [], -1.0
        for t, v in claves:
            t = max(t, previo + 0.001)
            fijas.append((t, v))
            previo = t
        n.pistas[clave] = fijas
    for h in n.hijos:
        _tiempos_crecientes(h)


def quat_y(yaw: float):
    return (0.0, math.sin(yaw / 2), 0.0, math.cos(yaw / 2))   # x, y, z, w


def quat_x(a: float):
    return (math.sin(a / 2), 0.0, 0.0, math.cos(a / 2))


def muestrear(claves, t):
    """Interpolación lineal de una lista (t, valor) en el tiempo t."""
    if t <= claves[0][0]:
        return claves[0][1]
    for (t0, v0), (t1, v1) in zip(claves, claves[1:]):
        if t0 <= t <= t1:
            u = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            if isinstance(v0, tuple):
                return tuple(a + (b - a) * u for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * u
    return claves[-1][1]
