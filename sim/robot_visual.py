"""Aspecto detallado del robot sobre el clon de Isaac Lab: mallas, materiales y texturas. Solo corre en el pod.

construir() escribe robot_detallado.usda = robot.usd (física y articulaciones, sin tocar) + una capa visual.
La capa oculta las cajas y cilindros del clon y dibuja el robot real encima de cada eslabón.
Las colisiones, las masas y las articulaciones son las de backend/viaz/urdf.py, que lee la ficha física
del robot (bloque `fisica` del catálogo). Las mallas usan esas mismas medidas: lo que se ve es lo que choca.

Cada robot del catálogo tiene su tabla de piezas en APARIENCIAS. Un robot sin tabla queda con el clon primitivo.
Fuente del LEAPTING MMR: fotos y ficha de https://www.leapting.com/product/zj (consultado el 2026-11-21).
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from viaz import urdf  # noqa: E402

TEXTURA_PX = 512
SEGMENTOS = 32


# ---------- mallas ----------

@dataclass(frozen=True)
class Malla:
    """Caras con normales y UV por vértice de cara. Las UV van en metros, para que la textura no se estire."""
    puntos: np.ndarray       # (N, 3)
    caras: tuple[int, ...]   # vértices por cara
    indices: np.ndarray      # (M,)
    normales: np.ndarray     # (M, 3)
    uv: np.ndarray           # (M, 2)


def caja(x: float, y: float, z: float) -> Malla:
    """Caja centrada en el origen."""
    h = np.array([x, y, z]) / 2
    puntos, normales, uv = [], [], []
    for eje in range(3):
        u, v = (eje + 1) % 3, (eje + 2) % 3
        for signo in (1.0, -1.0):
            n = np.zeros(3)
            n[eje] = signo
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)) if signo > 0 else ((-1, -1), (-1, 1), (1, 1), (1, -1)):
                p = np.zeros(3)
                p[eje], p[u], p[v] = signo * h[eje], su * h[u], sv * h[v]
                puntos.append(p)
                normales.append(n)
                uv.append((su * h[u], sv * h[v]))
    return Malla(np.array(puntos), (4,) * 6, np.arange(24), np.array(normales), np.array(uv))


def revolucion(perfil: list[tuple[float, float]], n: int = SEGMENTOS) -> Malla:
    """Sólido de revolución alrededor de Z. perfil = [(radio, z), ...] de abajo hacia arriba, con tapas."""
    ang = np.linspace(0, 2 * math.pi, n + 1)
    puntos, caras, indices, normales, uv = [], [], [], [], []
    largo = 0.0
    for (r0, z0), (r1, z1) in zip(perfil, perfil[1:]):
        dr, dz = r1 - r0, z1 - z0
        tramo = math.hypot(dr, dz)
        nr, nz = (dz / tramo, -dr / tramo) if tramo else (1.0, 0.0)
        for k in range(n):
            for a, r, z, v in ((ang[k], r0, z0, largo), (ang[k + 1], r0, z0, largo),
                               (ang[k + 1], r1, z1, largo + tramo), (ang[k], r1, z1, largo + tramo)):
                indices.append(len(puntos))
                puntos.append((r * math.cos(a), r * math.sin(a), z))
                normales.append((nr * math.cos(a), nr * math.sin(a), nz))
                uv.append((a * max(r0, r1), v))
            caras.append(4)
        largo += tramo
    for (r, z), signo in ((perfil[0], -1.0), (perfil[-1], 1.0)):
        if r <= 0:
            continue
        orden = range(n) if signo > 0 else range(n - 1, -1, -1)
        for k in orden:
            indices.append(len(puntos))
            puntos.append((r * math.cos(ang[k]), r * math.sin(ang[k]), z))
            normales.append((0.0, 0.0, signo))
            uv.append((r * math.cos(ang[k]), r * math.sin(ang[k])))
        caras.append(n)
    return Malla(np.array(puntos), tuple(caras), np.array(indices), np.array(normales), np.array(uv))


def caja_biselada(x: float, y: float, z: float, b: float = 0.04) -> Malla:
    """Caja centrada en el origen con las esquinas verticales y el borde de arriba cortados en bisel de b metros."""
    def anillo(hx: float, hy: float, zc: float) -> np.ndarray:
        return np.array([(hx - b, -hy, zc), (hx, -hy + b, zc), (hx, hy - b, zc), (hx - b, hy, zc),
                         (-hx + b, hy, zc), (-hx, hy - b, zc), (-hx, -hy + b, zc), (-hx + b, -hy, zc)])
    niveles = [anillo(x / 2, y / 2, -z / 2), anillo(x / 2, y / 2, z / 2 - b), anillo(x / 2 - b, y / 2 - b, z / 2)]
    puntos, caras, normales, uv = [], [], [], []
    for abajo, arriba in zip(niveles, niveles[1:]):
        for k in range(8):
            cara = np.array([abajo[k], abajo[(k + 1) % 8], arriba[(k + 1) % 8], arriba[k]])
            n = np.cross(cara[1] - cara[0], cara[3] - cara[0])
            n = n / np.linalg.norm(n)
            u = (cara[1] - cara[0]) / np.linalg.norm(cara[1] - cara[0])
            w = np.cross(n, u)
            puntos += list(cara)
            normales += [n] * 4
            uv += [(float(q @ u), float(q @ w)) for q in cara]
            caras.append(4)
    for nivel, signo in ((niveles[-1], 1.0), (niveles[0][::-1], -1.0)):
        puntos += list(nivel)
        normales += [np.array([0.0, 0.0, signo])] * 8
        uv += [(q[0], q[1]) for q in nivel]
        caras.append(8)
    return Malla(np.array(puntos), tuple(caras), np.arange(len(puntos)), np.array(normales), np.array(uv))


def esfera(radio: float, aplastada: float = 1.0) -> Malla:
    """Esfera centrada en el origen; aplastada < 1 la achata en Z."""
    return revolucion([(radio * math.sin(a), -radio * aplastada * math.cos(a)) for a in np.linspace(0.0, math.pi, 9)][1:-1], 20)


def cilindro(radio: float, largo: float) -> Malla:
    """Cilindro con eje Z, centrado en el origen."""
    return revolucion([(radio, -largo / 2), (radio, largo / 2)])


def _rotacion(rpy_grados: tuple[float, float, float]) -> np.ndarray:
    rx, ry, rz = (math.radians(v) for v in rpy_grados)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    return (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))


def mover(m: Malla, pos: tuple[float, float, float], rpy_grados: tuple[float, float, float] = (0, 0, 0)) -> Malla:
    r = _rotacion(rpy_grados)
    return Malla(m.puntos @ r.T + np.array(pos), m.caras, m.indices, m.normales @ r.T, m.uv)


def unir(mallas: list[Malla]) -> Malla:
    base, indices = 0, []
    for m in mallas:
        indices.append(m.indices + base)
        base += len(m.puntos)
    return Malla(np.concatenate([m.puntos for m in mallas]), sum((m.caras for m in mallas), ()),
                 np.concatenate(indices), np.concatenate([m.normales for m in mallas]),
                 np.concatenate([m.uv for m in mallas]))


# ---------- texturas ----------

def _ruido(semilla: int, fino: float, estirado: float = 1.0) -> np.ndarray:
    """Ruido suave en 0..1 que se repite sin costura. fino = tamaño del grano en píxeles."""
    rng = np.random.default_rng(semilla)
    f = np.fft.fftfreq(TEXTURA_PX)
    fx, fy = np.meshgrid(f, f)
    filtro = np.exp(-((fx * fino * estirado) ** 2 + (fy * fino) ** 2) * 20)
    campo = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((TEXTURA_PX, TEXTURA_PX))) * filtro))
    return (campo - campo.min()) / (campo.max() - campo.min())


def _normal(altura: np.ndarray, fuerza: float) -> np.ndarray:
    dx = (np.roll(altura, -1, 1) - np.roll(altura, 1, 1)) * fuerza
    dy = (np.roll(altura, -1, 0) - np.roll(altura, 1, 0)) * fuerza
    n = np.dstack([-dx, -dy, np.ones_like(altura)])
    return n / np.linalg.norm(n, axis=2, keepdims=True) * 0.5 + 0.5


def _guardar(ruta: Path, imagen: np.ndarray) -> None:
    from PIL import Image

    Image.fromarray((np.clip(imagen, 0, 1) * 255).astype(np.uint8)).save(ruta)


POLVO = np.array([0.72, 0.60, 0.44])    # polvo del desierto que se pega a la máquina


def _pintura(color: tuple[float, float, float], semilla: int, polvo_max: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pintura con polvo: color, rugosidad y relieve fino."""
    manchas = np.clip(_ruido(semilla, 60) * 1.6 - 0.5, 0, 1)[..., None] * polvo_max
    grano = _ruido(semilla + 1, 3)
    albedo = np.array(color) * (1 - manchas) + POLVO * manchas
    rugosidad = 0.38 + 0.4 * manchas[..., 0] + 0.08 * grano
    return albedo, np.dstack([rugosidad] * 3), _normal(grano, 0.25)


def escribir_texturas(carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, color, semilla, polvo in (("blanco", (0.90, 0.89, 0.83), 10, 0.16), ("verde", (0.16, 0.50, 0.13), 20, 0.30),
                                          ("azul", (0.03, 0.20, 0.55), 30, 0.10), ("gris", (0.22, 0.23, 0.24), 40, 0.25)):
        for sufijo, imagen in zip(("color", "rugosidad", "normal"), _pintura(color, semilla, polvo)):
            _guardar(carpeta / f"{nombre}_{sufijo}.png", imagen)
    # Funda del brazo: tela con arrugas a lo ancho del eslabón.
    arrugas = 0.6 * _ruido(50, 70, 0.35) + 0.3 * _ruido(51, 28, 0.3) + 0.1 * _ruido(53, 10, 0.5)
    trama = _ruido(52, 1.5)
    sombra = (0.70 + 0.30 * arrugas)[..., None]
    _guardar(carpeta / "tela_color.png", np.array([0.95, 0.33, 0.05]) * sombra * (0.94 + 0.06 * trama[..., None]))
    _guardar(carpeta / "tela_rugosidad.png", np.dstack([0.78 + 0.12 * trama] * 3))
    _guardar(carpeta / "tela_normal.png", _normal(arrugas + 0.02 * trama, 11.0))
    # Goma de las orugas y de las ventosas.
    grano = _ruido(60, 2.5)
    polvo = np.clip(_ruido(61, 40) * 1.5 - 0.4, 0, 1)[..., None] * 0.45
    _guardar(carpeta / "goma_color.png", np.array([0.035, 0.035, 0.035]) * (1 - polvo) + POLVO * polvo * 0.6)
    _guardar(carpeta / "goma_rugosidad.png", np.dstack([0.85 + 0.1 * grano] * 3))
    _guardar(carpeta / "goma_normal.png", _normal(grano, 4.0))
    # Arena del suelo de la vitrina, con ondas y grano.
    ondas, piedras = _ruido(80, 55), _ruido(81, 2.0)
    _guardar(carpeta / "arena_color.png", np.array([0.62, 0.49, 0.35]) * (0.93 + 0.09 * ondas[..., None]) * (0.94 + 0.08 * piedras[..., None]))
    _guardar(carpeta / "arena_rugosidad.png", np.dstack([0.9 + 0.08 * piedras] * 3))
    _guardar(carpeta / "arena_normal.png", _normal(ondas * 2 + 0.3 * piedras, 2.5))
    # Cielo para la luz de ambiente: azul arriba, claro en el horizonte y suelo cálido abajo.
    alto = np.linspace(1.0, -1.0, TEXTURA_PX // 2)[:, None, None]
    arriba = np.array([0.24, 0.47, 0.86]) * np.clip(alto, 0, 1) ** 0.45 + np.array([0.78, 0.86, 0.95]) * (1 - np.clip(alto, 0, 1) ** 0.45)
    cielo = np.where(alto >= 0, arriba, np.array([0.55, 0.45, 0.33]) * np.ones_like(arriba))
    _guardar(carpeta / "cielo.png", np.broadcast_to(cielo, (TEXTURA_PX // 2, TEXTURA_PX, 3)).copy())
    # Aluminio cepillado del marco de ventosas.
    cepillado = _ruido(70, 2.0, 30.0)
    _guardar(carpeta / "aluminio_color.png", np.dstack([0.78 + 0.08 * cepillado] * 3))
    _guardar(carpeta / "aluminio_rugosidad.png", np.dstack([0.28 + 0.2 * cepillado] * 3))
    _guardar(carpeta / "aluminio_normal.png", _normal(cepillado, 1.0))


# material: (textura, metálico, metros por repetición, emisión)
MATERIALES = {
    "blanco": ("blanco", 0.0, 1.2, None), "verde": ("verde", 0.0, 1.2, None), "azul": ("azul", 0.0, 1.2, None),
    "gris": ("gris", 0.6, 1.2, None), "tela": ("tela", 0.0, 0.9, None), "goma": ("goma", 0.0, 0.4, None),
    "aluminio": ("aluminio", 0.55, 0.5, None), "arena": ("arena", 0.0, 3.0, None),
    "amarillo": (None, 0.0, 1.0, None), "negro": (None, 0.0, 1.0, None),
    "baliza": (None, 0.0, 1.0, (1.0, 0.45, 0.0)), "foco": (None, 0.0, 1.0, (1.0, 0.97, 0.9)),
    "rojo": (None, 0.0, 1.0, None),
}
COLOR_PLANO = {"baliza": (1.0, 0.45, 0.0), "foco": (0.95, 0.95, 0.9), "rojo": (0.75, 0.02, 0.02),
               "amarillo": (0.90, 0.62, 0.03), "negro": (0.02, 0.02, 0.022)}


# ---------- LEAPTING MMR ----------
# Forma y colores tomados de las fotos de la ficha y de los videos de obra del fabricante
# (canal de YouTube de LEAPTING: Arabia Saudita, Perú, Australia; consultados el 2026-11-21).

TACO_ALTO = 0.03
ORUGA_VISIBLE = 0.7       # la banda de goma ocupa esta parte del alto de la oruga física; arriba va el bastidor verde

DIFERENCIAS_LEAPTING = [
    "sin el logotipo del fabricante: hay una franja azul en su lugar",
    "el remolque es una plataforma plana pegada a la base: no articula en el enganche ni voltea la pila",
    "la pila se apoya a la altura de la cubierta; en el remolque real queda más abajo",
    "las orugas y las ruedas del remolque no giran: la base se mueve por código",
    "el brazo pesa lo que el clon genérico, menos que un brazo industrial de 100 kg de carga útil",
]


def _oruga(v, lado: float) -> dict[str, list[Malla]]:
    alto_fisico, largo, ancho = urdf.medidas_oruga(v)
    alto = ORUGA_VISIBLE * alto_fisico
    y = lado * (v.ancho - ancho) / 2
    r = alto / 2
    cx = v.largo * urdf.ORUGA_CENTRO
    x0, x1 = cx - largo / 2 + r, cx + largo / 2 - r
    ri = r - TACO_ALTO / 2                  # la banda va por dentro; los tacos llegan justo al suelo
    banda = [mover(caja(x1 - x0, ancho, 2 * ri), (cx, y, r))]
    banda += [mover(cilindro(ri, ancho), (x, y, r), (90, 0, 0)) for x in (x0, x1)]
    taco = caja(0.045, ancho, TACO_ALTO)
    paso = 0.09
    for k in range(int((x1 - x0) / paso) + 1):
        for z, giro in ((r + ri, 0), (r - ri, 180)):
            banda.append(mover(taco, (x0 + k * paso, y, z), (0, giro, 0)))
    for x, base in ((x1, 0.0), (x0, 180.0)):
        for k in range(1, 8):
            a = math.radians(base + k * 22.5)
            banda.append(mover(taco, (x + ri * math.sin(a), y, r + ri * math.cos(a)), (0, math.degrees(a), 0)))
    cara = y + lado * (ancho / 2 + 0.008)
    ruedas = [mover(cilindro(0.2 * alto, 0.03), (x0 + 0.1 + k * (x1 - x0 - 0.2) / 6, cara, 0.24 * alto), (90, 0, 0)) for k in range(7)]
    ruedas += [mover(cilindro(0.36 * alto, 0.03), (x, cara, r), (90, 0, 0)) for x in (x0, x1)]
    ruedas += [mover(cilindro(0.1 * alto, 0.045), (x, cara, r), (90, 0, 0)) for x in (x0, x1)]
    # Bastidor verde sobre la banda, con su guardabarros inclinado.
    bastidor = [mover(caja_biselada(largo - 0.06, ancho + 0.02, alto_fisico - alto + 0.02, 0.03), (cx, y, (alto_fisico + alto) / 2 + 0.01)),
                mover(caja(x1 - x0 - 0.25, 0.014, 0.3 * alto), (cx, cara, 0.62 * alto))]
    return {"goma": banda, "verde": bastidor, "negro": ruedas}


def _rueda_remolque() -> dict[str, list[Malla]]:
    """Rueda con eje Y: neumático con hombros redondos y llanta amarilla, como en los videos."""
    r, w = urdf.REMOLQUE_RUEDA_R, urdf.REMOLQUE_RUEDA_ANCHO
    neumatico = revolucion([(0.62 * r, -w / 2), (0.93 * r, -w / 2), (r, -0.3 * w), (r, 0.3 * w), (0.93 * r, w / 2), (0.62 * r, w / 2)])
    llanta = revolucion([(0.62 * r, -w / 2 - 0.006), (0.62 * r, w / 2 + 0.006)])
    return {"goma": [mover(neumatico, (0, 0, 0), (90, 0, 0))], "amarillo": [mover(llanta, (0, 0, 0), (90, 0, 0))],
            "negro": [mover(cilindro(0.16 * r, w + 0.03), (0, 0, 0), (90, 0, 0))]}


def _remolque(g: dict, v) -> dict[str, list[Malla]]:
    largo, _ = v.remolque
    x, alto, top = g["pila_x_m"], urdf.REMOLQUE_ALTO_M, v.cubierta_z
    p: dict[str, list[Malla]] = {m: [] for m in MATERIALES}
    p["blanco"].append(mover(caja_biselada(largo, v.ancho, alto, 0.03), (x, 0, top - alto / 2)))
    for lado in (1.0, -1.0):                # largueros y parachoques del bastidor
        p["gris"].append(mover(caja(largo - 0.3, 0.08, 0.14), (x, lado * (v.ancho / 2 - 0.45), top - alto - 0.07)))
        p["goma"].append(mover(caja(largo - 0.1, 0.012, 0.04), (x, lado * (v.ancho / 2 + 0.004), top - alto + 0.03)))
    radio = urdf.REMOLQUE_RUEDA_R
    for dx in (-0.45, 0.45):                # dos ejes con sus soportes
        p["gris"].append(mover(cilindro(0.045, v.ancho - 0.3), (x + dx, 0, radio), (90, 0, 0)))
        for lado in (1.0, -1.0):
            y = lado * (v.ancho - urdf.REMOLQUE_RUEDA_ANCHO) / 2
            p["gris"].append(mover(caja(0.1, 0.06, top - alto - radio), (x + dx, lado * (v.ancho / 2 - 0.45), (top - alto + radio) / 2)))
            for material, mallas in _rueda_remolque().items():
                p[material] += [mover(m, (x + dx, y, radio)) for m in mallas]
    # Lanza de enganche hasta el frente del vehículo.
    frente, borde = v.largo / 2, x - largo / 2
    p["gris"].append(mover(caja(borde - frente + 0.2, 0.1, 0.08), ((frente + borde) / 2, 0, top - alto - 0.05)))
    p["aluminio"].append(mover(cilindro(0.03, 0.14), (frente + 0.08, 0, top - alto - 0.03)))
    return p


def _base(g: dict, v) -> dict[str, list[Malla]]:
    atras, adelante = -v.largo / 2, v.largo / 2
    cubierta = v.cubierta_z
    oruga_alto, oruga_largo, oruga_ancho = urdf.medidas_oruga(v)
    faldon = oruga_alto + 0.02              # borde inferior de la carrocería blanca
    gab_largo, gab_alto = v.gabinete
    gab_x1 = atras + gab_largo
    gab_cx, gab_ancho, gab_top = (atras + gab_x1) / 2, v.ancho - 0.2, cubierta + gab_alto
    p: dict[str, list[Malla]] = {m: [] for m in MATERIALES}
    for lado in (1.0, -1.0):
        for material, mallas in _oruga(v, lado).items():
            p[material] += mallas
    # Chasis verde entre las orugas.
    p["verde"].append(mover(caja(oruga_largo - 0.1, v.ancho - 2 * oruga_ancho, 0.6 * oruga_alto),
                            (v.largo * urdf.ORUGA_CENTRO, 0, 0.7 * oruga_alto)))
    # Carrocería blanco crema con los bordes en bisel: cubierta baja adelante y gabinete eléctrico atrás.
    p["blanco"].append(mover(caja_biselada(adelante - gab_x1 + 0.06, v.ancho, cubierta - faldon, 0.05), ((gab_x1 + adelante) / 2 - 0.03, 0, (cubierta + faldon) / 2)))
    p["blanco"].append(mover(caja_biselada(gab_largo, gab_ancho, gab_top - faldon, 0.06), (gab_cx, 0, (gab_top + faldon) / 2)))
    # Parachoques de goma en el borde inferior y juntas entre paneles.
    tramo = (adelante - gab_x1) / 3
    for lado in (1.0, -1.0):
        costado = lado * (v.ancho / 2 + 0.002)
        p["goma"].append(mover(caja(adelante - gab_x1 - 0.1, 0.012, 0.045), ((gab_x1 + adelante) / 2, costado, faldon + 0.03)))
        for k in range(1, 3):
            p["gris"].append(mover(caja(0.008, 0.006, cubierta - faldon - 0.14), (gab_x1 + k * tramo, costado, (cubierta + faldon) / 2)))
        for k in range(3):                  # tapas de registro con sus cierres
            cx = gab_x1 + (k + 0.5) * tramo
            p["negro"].append(mover(caja(0.05, 0.008, 0.02), (cx + 0.2, costado, cubierta - 0.3)))
        p["azul"].append(mover(caja(0.34, 0.006, 0.075), (gab_x1 + 0.5 * tramo - 0.05, costado, cubierta - 0.17)))   # franja donde va la marca
        # Puerta del gabinete: marco, dos manillas, bisagras y franja.
        yg = lado * (gab_ancho / 2 + 0.002)
        puerta_z, puerta_alto, puerta_largo = (cubierta + gab_top) / 2 - 0.12, gab_alto + 0.2, gab_largo - 0.26
        for dx, dz, cx, cz in ((puerta_largo, 0.008, 0, puerta_alto / 2), (puerta_largo, 0.008, 0, -puerta_alto / 2),
                               (0.008, puerta_alto, -puerta_largo / 2, 0), (0.008, puerta_alto, puerta_largo / 2, 0),
                               (0.006, puerta_alto, 0, 0)):
            p["gris"].append(mover(caja(dx, 0.006, dz), (gab_cx + cx, yg, puerta_z + cz)))
        for dx in (-0.06, 0.06):
            p["negro"].append(mover(caja(0.025, 0.03, 0.13), (gab_cx + dx, yg + lado * 0.012, puerta_z)))
        for dz in (-0.3, 0.3):
            p["aluminio"].append(mover(cilindro(0.012, 0.07), (gab_cx - puerta_largo / 2 + 0.01, yg + lado * 0.008, puerta_z + dz)))
        p["azul"].append(mover(caja(0.30, 0.006, 0.065), (gab_cx - 0.16, yg, gab_top - 0.2)))
        p["rojo"].append(mover(cilindro(0.04, 0.035), (gab_x1 + 0.14, lado * (v.ancho / 2 + 0.018), cubierta - 0.1), (90, 0, 0)))   # parada de emergencia
        p["amarillo"].append(mover(caja(0.11, 0.008, 0.11), (gab_x1 + 0.14, costado, cubierta - 0.1)))
        # Sensores de navegación en las esquinas.
        for x in (atras + 0.07, adelante - 0.1):
            p["negro"].append(mover(caja_biselada(0.1, 0.09, 0.07, 0.015), (x, lado * (v.ancho / 2 - (0.14 if x < 0 else 0.04)), (gab_top if x < 0 else cubierta) + 0.035)))
    # Rejilla de ventilación en la cara trasera.
    for k in range(9):
        p["gris"].append(mover(caja(0.012, 0.7, 0.016), (atras - 0.004, 0, cubierta + 0.1 + k * 0.045), (0, 25, 0)))
    # Sobre el techo: baliza, lidar de navegación y antena.
    p["negro"].append(mover(cilindro(0.045, 0.03), (gab_cx - 0.3, 0.5, gab_top + 0.015)))
    p["baliza"].append(mover(revolucion([(0.04, 0.0), (0.04, 0.06), (0.025, 0.085), (0.0, 0.09)]), (gab_cx - 0.3, 0.5, gab_top + 0.03)))
    p["aluminio"].append(mover(cilindro(0.02, 0.2), (gab_x1 - 0.14, 0, gab_top + 0.1)))
    p["negro"].append(mover(cilindro(0.055, 0.075), (gab_x1 - 0.14, 0, gab_top + 0.24)))
    p["negro"].append(mover(esfera(0.09, 0.55), (gab_cx, -0.45, gab_top + 0.02)))
    p["blanco"].append(mover(revolucion([(0.07, 0.0), (0.07, 0.02), (0.045, 0.055), (0.0, 0.065)]), (gab_cx - 0.3, -0.5, gab_top)))
    # Pedestal del brazo con sus pernos.
    mx, lado_pedestal = g["montaje_x_m"], 2 * v.hombro_r + 0.16
    p["gris"].append(mover(caja_biselada(lado_pedestal, lado_pedestal, 0.04, 0.02), (mx, 0, cubierta - 0.012)))
    p["aluminio"] += [mover(cilindro(0.016, 0.014), (mx + (v.hombro_r + 0.045) * math.cos(a), (v.hombro_r + 0.045) * math.sin(a), cubierta + 0.012))
                      for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    for lado in (1.0, -1.0):
        p["foco"].append(mover(caja(0.012, 0.16, 0.05), (adelante + 0.004, lado * 0.7, cubierta - 0.12)))
    for material, mallas in _remolque(g, v).items():
        p[material] += mallas
    return p


def _funda(radios: list[tuple[float, float]], semilla: int) -> Malla:
    """Funda de tela holgada: el perfil se llena de pliegues de distinto tamaño."""
    rng = np.random.default_rng(semilla)
    alturas = [z for _, z in radios]
    z = np.linspace(alturas[0], alturas[-1], max(8, int((alturas[-1] - alturas[0]) / 0.04)))
    base = np.interp(z, alturas, [r for r, _ in radios])
    pliegues = 0.009 * np.sin(z * 2 * math.pi / 0.37 + rng.uniform(0, 6)) + 0.005 * np.sin(z * 2 * math.pi / 0.13 + rng.uniform(0, 6))
    pliegues += rng.normal(0, 0.003, len(z))
    pliegues[[0, -1]] = 0.0
    return revolucion(list(zip((base + pliegues).tolist(), z.tolist())), 28)


def _eje(radio: float, largo: float, z: float, tapa: float) -> dict[str, list[Malla]]:
    """Carcasa de una articulación de eje Y: la funda cubre el motor y termina en dos domos."""
    m = largo / 2
    domo = [(tapa, -m - 0.06), (radio * 0.75, -m - 0.035), (radio * 1.02, -m), (radio * 0.97, 0), (radio * 1.02, m), (radio * 0.75, m + 0.035), (tapa, m + 0.06)]
    return {"tela": [mover(revolucion(domo), (0, 0, z), (90, 0, 0))]}


def _eslabon(perfil: list[tuple[float, float]], semilla: int, eje: dict | None) -> dict[str, list[Malla]]:
    p: dict[str, list[Malla]] = {"tela": [_funda(perfil, semilla)], "goma": [], "negro": []}
    for material, mallas in (eje or {}).items():
        p[material] += mallas
    return p


def _ventosa(v) -> dict[str, list[Malla]]:
    """Marco de 8 ventosas como en los videos: viga larga, cuatro travesaños, ventosas de fuelle y caja de visión.
    La cara que toca el panel queda en z = 0,05 m (placa del clon); la caja de visión va del otro lado."""
    largo, ancho = v.ventosa
    p: dict[str, list[Malla]] = {"aluminio": [], "goma": [], "azul": [], "gris": [], "negro": []}
    p["gris"].append(mover(caja_biselada(0.3, 0.3, 0.016, 0.006), (0, 0, 0.008)))                 # brida
    p["aluminio"].append(mover(caja_biselada(largo, 0.2, 0.03, 0.008), (0, 0, 0.019)))            # viga
    fuelle = revolucion([(0.018, 0.0), (0.045, 0.004), (0.03, 0.008), (0.052, 0.014)])
    for x in (-0.44 * largo, -0.15 * largo, 0.15 * largo, 0.44 * largo):
        p["aluminio"].append(mover(caja(0.05, ancho, 0.022), (x, 0, 0.02)))                       # travesaño
        for y in (-ancho / 2 + 0.06, ancho / 2 - 0.06):
            p["gris"].append(mover(cilindro(0.012, 0.012), (x, y, 0.034)))
            p["goma"].append(mover(fuelle, (x, y, 0.036)))
    p["azul"].append(mover(caja(0.14, 0.09, 0.02), (0.3, 0.0, 0.03)))                             # bloque de válvulas de vacío
    p["goma"].append(mover(cilindro(0.012, 0.5 * largo), (0.2 * largo, 0.07, -0.005), (0, 90, 0)))   # manguera de vacío
    # Caja de visión sobre un poste, del lado de la muñeca.
    p["aluminio"].append(mover(caja(0.04, 0.04, 0.2), (-0.3, 0, -0.09)))
    p["gris"].append(mover(caja_biselada(0.2, 0.14, 0.11, 0.015), (-0.3, 0, -0.24)))
    p["negro"].append(mover(cilindro(0.03, 0.02), (-0.3, 0, -0.17)))
    return p


def piezas_leapting(g: dict, v) -> dict[str, dict[str, list[Malla]]]:
    """Mallas por eslabón y material, en el marco de cada eslabón (Z a lo largo del eslabón).
    Las medidas salen de la ficha física del robot (v), las mismas que usa la colisión."""
    l1, l2 = g["l1_m"], g["l2_m"]
    hombro_alto = g["hombro_z_m"] - g["cubierta_z_m"]
    h, b, a = v.hombro_r, v.brazo_lado / 2, v.antebrazo_lado / 2
    antebrazo = _eslabon([(a + 0.04, 0.0), (a + 0.03, 0.3), (a - 0.02, l2 - 0.2), (a - 0.03, l2)], 3, _eje(a - 0.02, 2 * a - 0.02, l2, 0.07))
    antebrazo["tela"].append(mover(esfera(a + 0.05, 0.8), (-0.1, 0, 0.05)))                       # motor del codo bajo la funda
    antebrazo["goma"].append(mover(cilindro(0.024, 0.75 * l2), (0, a + 0.03, 0.5 * l2)))         # manguera a la ventosa
    antebrazo["goma"] += [mover(cilindro(0.03, 0.03), (0, a + 0.03, z)) for z in (0.14 * l2, 0.5 * l2, 0.86 * l2)]
    return {
        "base_link": _base(g, v),
        "hombro": _eslabon([(h, 0.0), (h, 0.05), (0.92 * h, 0.16), (0.85 * h, hombro_alto)], 1, _eje(0.85 * h, 2 * h - 0.04, hombro_alto, 0.16)),
        "brazo": _eslabon([(b + 0.02, 0.0), (b + 0.01, 0.3), (b - 0.03, l1 - 0.3), (b - 0.01, l1)], 2, _eje(b, 2 * b + 0.06, l1, 0.13)),
        "antebrazo": antebrazo,
        "muneca_1": _eslabon([(0.12, 0.0), (0.10, 0.15)], 4, None),
        "muneca_2": {"aluminio": [revolucion([(0.08, 0.0), (0.08, 0.06), (0.11, 0.06), (0.11, 0.10)])]},
        "efector": _ventosa(v),
    }


APARIENCIAS = {"leapting-mmr": (piezas_leapting, DIFERENCIAS_LEAPTING)}


# ---------- USD ----------

def _material(stage, ruta: str, nombre: str, texturas: str = "./texturas"):
    from pxr import Sdf, UsdShade

    textura, metalico, metros, emision = MATERIALES[nombre]
    mat = UsdShade.Material.Define(stage, f"{ruta}/{nombre}")
    sup = UsdShade.Shader.Define(stage, f"{ruta}/{nombre}/superficie")
    sup.CreateIdAttr("UsdPreviewSurface")
    sup.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metalico)
    if textura is None:
        sup.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(COLOR_PLANO[nombre])
        sup.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
        if emision:
            sup.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(emision)
    else:
        st = UsdShade.Shader.Define(stage, f"{ruta}/{nombre}/st")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        escala = UsdShade.Shader.Define(stage, f"{ruta}/{nombre}/escala")
        escala.CreateIdAttr("UsdTransform2d")
        escala.CreateInput("in", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        escala.CreateInput("scale", Sdf.ValueTypeNames.Float2).Set((1 / metros, 1 / metros))
        # Solo el color va en sRGB. Rugosidad y normal son datos: con sRGB Isaac los lee mal.
        for entrada, sufijo, espacio, salida, tipo in (
                ("diffuseColor", "color", "sRGB", "rgb", Sdf.ValueTypeNames.Color3f),
                ("roughness", "rugosidad", "raw", "r", Sdf.ValueTypeNames.Float),
                ("normal", "normal", "raw", "rgb", Sdf.ValueTypeNames.Normal3f)):
            tex = UsdShade.Shader.Define(stage, f"{ruta}/{nombre}/{sufijo}")
            tex.CreateIdAttr("UsdUVTexture")
            tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(f"{texturas}/{textura}_{sufijo}.png")
            tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(espacio)
            tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
            tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
            tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(escala.ConnectableAPI(), "result")
            if sufijo == "normal":
                tex.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set((2, 2, 2, 1))
                tex.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set((-1, -1, -1, 0))
            sup.CreateInput(entrada, tipo).ConnectToSource(tex.ConnectableAPI(), salida)
    mat.CreateSurfaceOutput().ConnectToSource(sup.ConnectableAPI(), "surface")
    return mat


def _malla_usd(stage, ruta: str, m: Malla, material) -> None:
    from pxr import Sdf, UsdGeom, UsdShade, Vt

    malla = UsdGeom.Mesh.Define(stage, ruta)
    malla.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(m.puntos.astype(np.float32)))
    malla.CreateFaceVertexCountsAttr(list(m.caras))
    malla.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(m.indices.astype(np.int32)))
    malla.CreateSubdivisionSchemeAttr("none")
    malla.CreateDoubleSidedAttr(True)
    malla.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(m.normales.astype(np.float32)))
    malla.SetNormalsInterpolation("faceVarying")
    UsdGeom.PrimvarsAPI(malla).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, "faceVarying").Set(
        Vt.Vec2fArray.FromNumpy(m.uv.astype(np.float32)))
    UsdShade.MaterialBindingAPI.Apply(malla.GetPrim()).Bind(material)


def construir(robot_usd: Path, robot: dict) -> tuple[Path, dict]:
    """Escribe robot_detallado.usda junto a robot.usd. Devuelve su ruta y un resumen de lo dibujado."""
    from pxr import Usd, UsdGeom, UsdPhysics

    robot_id = robot["id"]
    if robot_id not in APARIENCIAS or "fisica" not in robot:
        return robot_usd, {"detalle": False, "motivo": f"'{robot_id}' no tiene tabla de piezas en robot_visual.py o ficha física"}
    piezas_de, diferencias = APARIENCIAS[robot_id]
    carpeta = robot_usd.parent
    escribir_texturas(carpeta / "texturas")
    ruta = carpeta / "robot_detallado.usda"
    if ruta.exists():
        ruta.unlink()
    stage = Usd.Stage.CreateNew(str(ruta))
    stage.GetRootLayer().subLayerPaths.append(f"./{robot_usd.name}")
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    raiz = Usd.Stage.Open(str(robot_usd)).GetDefaultPrim().GetPath()
    stage.SetDefaultPrim(stage.GetPrimAtPath(raiz))
    eslabones = {p.GetName(): p for p in Usd.PrimRange(stage.GetPrimAtPath(raiz)) if p.HasAPI(UsdPhysics.RigidBodyAPI)}
    piezas = piezas_de(urdf.geometria(robot["alcance_m"], robot["fisica"]), urdf.vehiculo(robot["fisica"]))
    faltan = sorted(set(piezas) - set(eslabones))
    if faltan:
        raise ValueError(f"robot.usd no trae los eslabones {faltan}; trae {sorted(eslabones)}")
    materiales = {n: _material(stage, f"{raiz}/AparienciaReal", n) for n in MATERIALES}
    caras = 0
    for nombre, por_material in piezas.items():
        prim = eslabones[nombre]
        ocultos = [h for h in prim.GetChildren() if h.GetName() == "visuals"]
        if not ocultos:
            raise ValueError(f"el eslabón '{nombre}' no tiene 'visuals'; trae {[h.GetName() for h in prim.GetChildren()]}")
        UsdGeom.Imageable(ocultos[0]).MakeInvisible()
        for material, mallas in por_material.items():
            if mallas:
                unida = unir(mallas)
                caras += len(unida.caras)
                _malla_usd(stage, f"{prim.GetPath()}/detalle/{material}", unida, materiales[material])
    stage.GetRootLayer().Save()
    return ruta, {"detalle": True, "caras": caras, "eslabones": sorted(piezas), "diferencias_con_real": diferencias}


def suelo_de_arena(stage, ruta: str, lado: float, texturas: Path) -> None:
    """Plano de arena con textura para la vitrina. Solo se ve: la colisión del piso la pone quien lo llama."""
    h = lado / 2
    plano = Malla(np.array([(-h, -h, 0.0), (h, -h, 0.0), (h, h, 0.0), (-h, h, 0.0)]), (4,), np.arange(4),
                  np.tile((0.0, 0.0, 1.0), (4, 1)), np.array([(-h, -h), (h, -h), (h, h), (-h, h)]))
    _malla_usd(stage, f"{ruta}/malla", plano, _material(stage, ruta, "arena", str(texturas)))
