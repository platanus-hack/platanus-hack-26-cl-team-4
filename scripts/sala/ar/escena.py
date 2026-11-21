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
    "naranja": {"color": (0.95, 0.45, 0.08), "rugosidad": 0.45, "metal": 0.1},
    "azul": {"color": (0.15, 0.35, 0.75), "rugosidad": 0.4, "metal": 0.1},
    "gris_claro": {"color": (0.62, 0.65, 0.70), "rugosidad": 0.5, "metal": 0.3},
    "helice": {"color": (0.45, 0.48, 0.52), "rugosidad": 0.3, "metal": 0.5},
    # escaneo estilo Matrix: textura de números con transparencia, que brilla
    "matrix": {"color": (1.0, 1.0, 1.0), "rugosidad": 1.0, "metal": 0.0, "textura": "matrix.png",
               "transparente": True, "emision_textura": True, "doble_cara": True},
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
    for z in np.arange(-7.7, 0.7, 0.9):
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


# ---------------- otros 4 robots (diseños propios, simples) ----------------
def robot_industrial() -> dict[str, Malla]:
    """Brazo industrial sobre una base con ruedas."""
    g = {k: Malla() for k in ("robot_gris", "naranja", "negro", "acento")}
    caja(g["robot_gris"], (0, 0.17, 0), (0.6, 0.22, 0.5))
    for x in (-0.25, 0.25):
        for z in (-0.18, 0.18):
            cilindro(g["negro"], (x + (0.04 if x > 0 else -0.04), 0.07, z), 0.07, 0.05, eje="x")
    cilindro(g["naranja"], (0, 0.55, 0), 0.08, 0.55)
    esfera(g["naranja"], (0, 0.85, 0), 0.11)
    caja(g["naranja"], (0, 0.85, 0.24), (0.1, 0.1, 0.46))
    esfera(g["naranja"], (0, 0.85, 0.47), 0.07)
    caja(g["naranja"], (0, 0.70, 0.47), (0.08, 0.28, 0.08))
    for x in (-0.04, 0.04):
        caja(g["robot_gris"], (x, 0.53, 0.47), (0.02, 0.08, 0.05))
    caja(g["acento"], (0, 0.29, 0.251), (0.3, 0.04, 0.01))
    return g


def robot_cuadrupedo() -> dict[str, Malla]:
    """Robot de cuatro patas."""
    g = {k: Malla() for k in ("gris_claro", "negro", "ojos", "acento")}
    caja(g["gris_claro"], (0, 0.55, 0), (0.34, 0.2, 0.72))
    caja(g["gris_claro"], (0, 0.66, 0.44), (0.24, 0.17, 0.2))
    caja(g["negro"], (0, 0.67, 0.545), (0.18, 0.07, 0.01))
    for l in (-1, 1):
        esfera(g["ojos"], (0.045 * l, 0.67, 0.552), 0.015, seg=10, anillos=8)
    for x in (-0.15, 0.15):
        for z in (-0.26, 0.26):
            cilindro(g["negro"], (x, 0.24, z), 0.04, 0.46)
            esfera(g["negro"], (x, 0.02, z), 0.05)
    caja(g["acento"], (0, 0.651, 0), (0.2, 0.01, 0.3))
    return g


def robot_dron() -> dict[str, Malla]:
    """Dron de inspección, flotando."""
    g = {k: Malla() for k in ("negro", "helice", "ojos", "acento", "robot_gris")}
    caja(g["negro"], (0, 1.0, 0), (0.34, 0.12, 0.34))
    caja(g["robot_gris"], (0, 1.0, 0), (0.95, 0.04, 0.05))
    caja(g["robot_gris"], (0, 1.0, 0), (0.05, 0.04, 0.95))
    for x, z in ((0.47, 0), (-0.47, 0), (0, 0.47), (0, -0.47)):
        cilindro(g["robot_gris"], (x, 1.05, z), 0.03, 0.08)
        cilindro(g["helice"], (x, 1.1, z), 0.19, 0.01, lados=28)
    esfera(g["negro"], (0, 0.9, 0.08), 0.07)
    esfera(g["ojos"], (0, 0.9, 0.145), 0.03, seg=12, anillos=8)
    caja(g["acento"], (0, 1.065, 0), (0.2, 0.01, 0.2))
    return g


def robot_humanoide() -> dict[str, Malla]:
    """Humanoide simple."""
    g = {k: Malla() for k in ("azul", "robot_blanco", "negro", "ojos", "acento")}
    for x in (-0.1, 0.1):
        caja(g["azul"], (x, 0.27, 0), (0.12, 0.5, 0.15))
        caja(g["negro"], (x, 0.03, 0.03), (0.13, 0.06, 0.22))
    caja(g["robot_blanco"], (0, 0.77, 0), (0.4, 0.48, 0.22))
    caja(g["acento"], (0, 0.85, 0.111), (0.14, 0.05, 0.01))
    for x in (-0.26, 0.26):
        caja(g["azul"], (x, 0.74, 0), (0.09, 0.46, 0.1))
        esfera(g["robot_blanco"], (x, 0.5, 0), 0.055)
    esfera(g["robot_blanco"], (0, 1.15, 0), 0.14)
    caja(g["negro"], (0, 1.16, 0.09), (0.2, 0.08, 0.06))
    for l in (-1, 1):
        esfera(g["ojos"], (0.045 * l, 1.16, 0.122), 0.015, seg=10, anillos=8)
    return g


def escaneo(ancho: float, alto: float) -> dict[str, Malla]:
    """Muro de números estilo Matrix que recorre el lugar, con una línea láser en el piso."""
    g = {k: Malla() for k in ("matrix", "laser")}
    plano(g["matrix"], (0, alto / 2, 0), ancho, alto)
    caja(g["laser"], (0, 0.01, 0), (ancho, 0.02, 0.03))
    return g


def anillo() -> dict[str, Malla]:
    """Marca bajo el robot elegido."""
    g = {"anillo": Malla()}
    cilindro(g["anillo"], (0, 0.012, 0), 0.42, 0.012, lados=40)
    return g


def textura_matrix(destino, ancho=1024, alto=512, semilla=7):
    """PNG con columnas de números verdes sobre fondo transparente (estilo Matrix)."""
    import random
    from PIL import Image, ImageDraw, ImageFont
    random.seed(semilla)
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 30)
    except OSError:
        fnt = ImageFont.load_default()
    paso_x, paso_y = 22, 30
    for x in range(4, ancho, paso_x):
        largo = random.randint(6, alto // paso_y)
        inicio = random.randint(-largo // 2, alto // paso_y)
        for k in range(largo):
            y = (inicio + k) * paso_y
            if not 0 <= y < alto:
                continue
            brillo = (k + 1) / largo
            cabeza = k == largo - 1
            color = (210, 255, 225, 255) if cabeza else (60, 255, 140, int(130 + 125 * brillo))
            d.text((x, y), random.choice("0123456789"), font=fnt, fill=color)
    # bordes arriba y abajo que se desvanecen
    a = np.array(img).astype("f4")
    filas = np.linspace(0, 1, alto)
    a[:, :, 3] *= np.clip(np.minimum(filas, 1 - filas) * 6, 0, 1)[:, None]
    Image.fromarray(a.astype("u1"), "RGBA").save(destino)


# ---------------- línea de tiempo ----------------
VEL = 0.7          # m/s, como un robot de servicio real
# El cuadro 0 es la "pose de reposo": los 5 robots visibles y completos. AR Quick Look (iPhone) y Scene Viewer
# (Android) usan ese cuadro para medir el objeto, ponerlo sobre el piso, calcular la sombra y moverlo con los dedos.
# Si algo empieza encogido a cero, el objeto queda "plano" y la AR se comporta mal.
T_ESCANEO = (1.2, 4.7)
T_ELIGE = 4.9      # aparece el anillo bajo el elegido
T_DESAPARECEN = (5.4, 6.1)
T_ENTREGA = 6.6    # el elegido parte a repartir el café
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
                "z_fin": 1.2, "escaneo": (X1 - X0 + 0.4, 3.0, (X0 + X1) / 2, Z0 + 0.4, Z1)},
    "robot": {"sala": False, "escala": 1.0, "fila_z": -1.0, "fila_x": [-1.9, -0.95, 0.0, 0.95, 1.9],
              "z_fin": 1.3, "escaneo": (5.2, 2.2, 0.0, -2.2, 1.9)},
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
    for k, (fabrica, x) in enumerate(zip(ROBOTS, cfg["fila_x"])):
        if k == ELEGIDO:
            marca = Nodo("anillo", anillo(), pistas={"s": [(0.0, MINIMO), (T_ELIGE, MINIMO), (T_ELIGE + 0.3, 1.0),
                                                            (T_ENTREGA + 1.0, 1.0), (T_ENTREGA + 1.5, MINIMO), (fin, MINIMO)]})
            brazo = Nodo("brazo", robot_brazo(), t=BRAZO_PIVOTE, pistas={"rx": br})
            hijos.append(Nodo("robot_servicio", robot_cuerpo(), hijos=[brazo, marca], pistas={"t": tr, "ry": rot}))
        else:
            d0, d1 = T_DESAPARECEN
            r0 = fin - REAPARECEN + 0.2 * (k if k < ELEGIDO else k - 1)
            escala = [(0.0, 1.0), (d0 + 0.08 * k, 1.0), (d1 + 0.08 * k, MINIMO),
                      (r0, MINIMO), (r0 + 0.5, 1.0), (fin, 1.0)]
            hijos.append(Nodo(f"robot_{fabrica.__name__.split('_')[1]}", fabrica(), t=(x, 0, cfg["fila_z"]),
                              pistas={"s": escala}))
    if cfg["escaneo"] is None:
        raiz = Nodo("viaz", hijos=hijos, pistas={})
        _tiempos_crecientes(raiz)
        return raiz, fin
    ancho, alto, cx, z_desde, z_hasta = cfg["escaneo"]
    e0, e1 = T_ESCANEO
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
