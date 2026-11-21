"""Texturas del parque, hechas a mano con numpy y PIL. Sin descargas y sin azar suelto: cada textura tiene su semilla.

    python sim/texturas.py --dir <carpeta destino> [nombre ...]

Las usa generar_escena.py (escribe escena.usd y las deja al lado, en texturas/). Cada una se repite sin costura.
Los tamaños de repetición (en metros) los usa generar_escena.py para el tiling.

Reglas de color: los albedos van en sRGB 8 bits, los mapas de normales en OpenGL (Y arriba),
la rugosidad y el metal en escala de grises.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PANEL_PX = (1024, 2160)  # ancho x largo: calza con el módulo de 1,13 x 2,38 m (relación 0,475)


# ---------- bloques comunes ----------

def _ruido(rng: np.random.Generator, n: int, beta: float, largo_min_px: float = 0.0, largo_max_px: float = 0.0,
           anisotropia: float = 1.0) -> np.ndarray:
    """Ruido periódico de media 0 y desviación 1. Espectro 1/f^beta (beta 2 = nubes, 0 = ruido blanco).

    largo_min_px / largo_max_px recortan las longitudes de onda (0 = sin límite). anisotropia > 1 alarga las
    manchas a lo largo de x.
    """
    fx = np.fft.fftfreq(n)[None, :] / anisotropia
    fy = np.fft.fftfreq(n)[:, None]
    f = np.hypot(fx, fy)
    f[0, 0] = 1.0
    filtro = f ** (-beta / 2.0)
    filtro[0, 0] = 0.0
    if largo_min_px:
        filtro[f > 1.0 / largo_min_px] = 0.0
    if largo_max_px:
        filtro[f < 1.0 / largo_max_px] = 0.0
    r = np.fft.ifft2(np.fft.fft2(rng.standard_normal((n, n))) * filtro).real
    return (r - r.mean()) / r.std()


def _desenfoque(a: np.ndarray, sigma_px: float) -> np.ndarray:
    n = a.shape[0]
    f2 = np.hypot(np.fft.fftfreq(n)[None, :], np.fft.fftfreq(n)[:, None]) ** 2
    return np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (math.pi * sigma_px) ** 2 * f2)).real


def _piedras(rng: np.random.Generator, n: int, cantidad: int, radio_px: tuple[float, float],
             paleta: list[tuple[float, float, float]], pesos: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Piedras ovaladas con borde que se enrolla. Devuelve (altura en px, color 0-1, cobertura 0-1)."""
    altura = np.zeros((n, n))
    color = np.zeros((n, n, 3))
    cobertura = np.zeros((n, n))
    pesos_n = np.asarray(pesos) / np.sum(pesos)
    for _ in range(cantidad):
        r = radio_px[0] * (radio_px[1] / radio_px[0]) ** (rng.random() ** 1.6)
        a, b = r * rng.uniform(0.75, 1.3), r * rng.uniform(0.6, 1.0)
        ang, fase = rng.uniform(0, math.pi), rng.uniform(0, 6.28)
        cx, cy = rng.integers(0, n, 2)
        m = int(max(a, b) * 1.35) + 2
        ys, xs = np.mgrid[-m:m + 1, -m:m + 1]
        u = (xs * math.cos(ang) + ys * math.sin(ang)) / a
        v = (-xs * math.sin(ang) + ys * math.cos(ang)) / b
        rr = np.hypot(u, v) * (1 + 0.14 * np.sin(3 * np.arctan2(v, u) + fase))
        domo = np.sqrt(np.clip(1 - rr ** 2, 0, None)) * r * 0.7
        iy, ix = (ys + cy) % n, (xs + cx) % n
        encima = domo > altura[iy, ix]
        base = np.asarray(paleta[rng.choice(len(paleta), p=pesos_n)])
        tono = base * rng.uniform(0.82, 1.15) * (0.85 + 0.3 * domo / (domo.max() + 1e-6))[..., None]
        altura[iy, ix] = np.where(encima, domo, altura[iy, ix])
        color[iy, ix] = np.where(encima[..., None], tono, color[iy, ix])
        cobertura[iy, ix] = np.maximum(cobertura[iy, ix], np.clip(domo * 3, 0, 1) * (domo > 0))
    return altura, color, cobertura


def _normal(altura: np.ndarray, fuerza: float) -> np.ndarray:
    gx = (np.roll(altura, -1, 1) - np.roll(altura, 1, 1)) / 2
    gy = (np.roll(altura, -1, 0) - np.roll(altura, 1, 0)) / 2     # fila 0 arriba: +y de la imagen es abajo
    nz = np.ones_like(altura)
    n = np.stack([-gx * fuerza, gy * fuerza, nz], -1)             # OpenGL: Y arriba
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def _a_png(a: np.ndarray, ruta: Path) -> None:
    """Guarda un arreglo 0-1 (gris o RGB) como PNG de 8 bits."""
    img = (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(img).save(ruta, optimize=True)


def _srgb(r: int, g: int, b: int) -> np.ndarray:
    return np.array([r, g, b]) / 255.0


# ---------- suelo del parque ----------

def _suelo(n: int = 2048) -> dict[str, np.ndarray]:
    """Arena ocre del Atacama con grava fina, piedras sueltas y manchas de tono cada pocos metros."""
    rng = np.random.default_rng(101)
    base = _srgb(190, 160, 130)
    macro = _ruido(rng, n, 2.6, largo_min_px=n / 2)
    manchas = _ruido(rng, n, 2.0, largo_min_px=n / 16, largo_max_px=n / 2)
    grano = _ruido(rng, n, 0.6, largo_min_px=6)
    luz = 1 + 0.045 * macro + 0.04 * manchas + 0.04 * grano
    tinte = np.stack([1 + 0.02 * manchas, np.ones_like(macro), 1 - 0.03 * macro - 0.02 * manchas], -1)
    albedo = base * luz[..., None] * tinte

    paleta = [_srgb(112, 98, 86), _srgb(150, 112, 88), _srgb(188, 170, 146), _srgb(84, 76, 70), _srgb(132, 108, 90)]
    pesos = [2, 3, 3, 1, 4]
    alturas, colores, cob = np.zeros((n, n)), np.zeros((n, n, 3)), np.zeros((n, n))
    for cantidad, radios in ((26000, (0.8, 2.0)), (3600, (2.0, 4.5)), (220, (4.5, 8.0)), (14, (8.0, 13.0))):
        h, c, k = _piedras(rng, n, cantidad, radios, paleta, pesos)
        mejor = h > alturas
        alturas = np.where(mejor, h, alturas)
        colores = np.where(mejor[..., None], c, colores)
        cob = np.maximum(cob, k)
    albedo = albedo * (1 - cob[..., None]) + colores * cob[..., None]
    oclusion = np.clip((_desenfoque(alturas, 5) - alturas) / 4, 0, 1)
    albedo *= (1 - 0.35 * oclusion)[..., None]
    sal = rng.random((n, n)) > 0.9985
    albedo = np.where(sal[..., None], albedo * 0.6 + _srgb(226, 214, 198) * 0.4, albedo)

    relieve = alturas * 0.8 + 0.7 * _ruido(rng, n, 1.4, largo_min_px=3, largo_max_px=24)   # sin ondas largas: inclinarían la luz a trozos
    rugosidad = np.clip(0.9 + 0.05 * grano - 0.12 * cob, 0.6, 1.0)
    return {"suelo_albedo": albedo, "suelo_normal": _normal(relieve, 0.4), "suelo_rugosidad": rugosidad}


def _cerro(ancho: int = 4096, alto: int = 256) -> dict[str, np.ndarray]:
    """Piel de cerro lejano. u da la vuelta al anillo de cerros, v va del pie (abajo) a la cresta (arriba).

    Pardo rojizo con quebradas verticales. Hacia el pie se mezcla con el velo azul grisáceo de la distancia.
    El pie y los bordes de u se enrollan sin costura.
    """
    rng = np.random.default_rng(303)
    n = ancho
    ruido = lambda beta, **k: _ruido(rng, n, beta, **k)[:alto, :]   # noqa: E731
    quebradas = ruido(2.0, largo_min_px=40, anisotropia=0.05)   
    manchas = ruido(2.4, largo_min_px=n / 6)
    grano = ruido(1.0, largo_min_px=3)
    luz = 1 + 0.12 * manchas + 0.10 * quebradas + 0.04 * grano
    cuerpo = _srgb(142, 112, 92)[None, None, :] * luz[..., None]
    cuerpo = cuerpo * (1 + np.stack([0.04 * manchas, 0.0 * manchas, -0.08 * manchas], -1))
    v = np.linspace(1.0, 0.0, alto)[:, None, None]                 # fila 0 = v 1 = cresta
    velo = np.clip(1.0 - v, 0, 1) ** 1.4                           # 0 en la cresta, 1 en el pie
    haze = _srgb(150, 162, 182)[None, None, :]
    return {"cerro_albedo": cuerpo * (1 - 0.5 * velo) + haze * 0.5 * velo}


# ---------- roca ----------

def _roca(n: int = 512) -> dict[str, np.ndarray]:
    """Piedra del desierto: pardo grisáceo con granos y vetas. Sin patrón visible: se pega a una esfera con UV."""
    rng = np.random.default_rng(808)
    nube = _ruido(rng, n, 2.4, largo_min_px=n / 2)
    grano = _ruido(rng, n, 0.9, largo_min_px=2)
    veta = _ruido(rng, n, 1.8, largo_min_px=n / 30, anisotropia=0.2)
    luz = 1 + 0.14 * nube + 0.09 * grano + 0.08 * veta
    return {"roca_albedo": _srgb(128, 110, 96) * luz[..., None]}


# ---------- acero galvanizado ----------

def _acero(n: int = 1024) -> dict[str, np.ndarray]:
    """Galvanizado en caliente: gris zinc con 'flores' (cristales) de brillo distinto y rayas de manejo."""
    rng = np.random.default_rng(404)
    sitios = rng.random((420, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n]
    mejor = np.full((n, n), 1e12)
    ident = np.zeros((n, n), dtype=np.int32)
    for i, (sx, sy) in enumerate(sitios):
        dx = np.minimum(np.abs(xx - sx), n - np.abs(xx - sx))
        dy = np.minimum(np.abs(yy - sy), n - np.abs(yy - sy))
        d = dx * dx + dy * dy
        sel = d < mejor
        mejor = np.where(sel, d, mejor)
        ident = np.where(sel, i, ident)
    brillo = rng.uniform(0.9, 1.08, len(sitios))[ident]
    borde = np.clip(np.sqrt(mejor) / 14, 0, 1)
    rayas = _ruido(rng, n, 1.2, largo_min_px=2, anisotropia=0.08)
    nube = _ruido(rng, n, 2.4, largo_min_px=n / 2)
    luz = brillo * (0.97 + 0.03 * borde) * (1 + 0.02 * rayas + 0.05 * nube)
    albedo = _srgb(168, 172, 176) * luz[..., None]
    rug = np.clip(0.42 + 0.06 * rayas - 0.03 * nube, 0.25, 0.7)
    return {"acero_albedo": albedo, "acero_rugosidad": rug}


# ---------- panel fotovoltaico monocristalino ----------

def _panel() -> dict[str, np.ndarray]:
    """Módulo de 6 x 24 medias celdas: vidrio negro azulado, barras de plata, marco de aluminio anodizado.

    Se dibuja al doble y se reduce, para que las líneas finas salgan suaves. u es el ancho (1,13 m), v el largo (2,38 m).
    """
    rng = np.random.default_rng(505)
    s = 2
    w, h = PANEL_PX[0] * s, PANEL_PX[1] * s
    px_m = PANEL_PX[0] / 1.13
    marco = int(0.036 * px_m) * s
    borde = int(0.010 * px_m) * s
    columnas, filas, hueco, hueco_medio = 6, 24, 3 * s, 9 * s

    def lienzo(fondo):
        return Image.new("RGB" if isinstance(fondo, tuple) else "L", (w, h), fondo)

    albedo, rug, metal = lienzo((176, 179, 186)), lienzo(int(0.38 * 255)), lienzo(int(0.9 * 255))
    da, dr, dm = ImageDraw.Draw(albedo), ImageDraw.Draw(rug), ImageDraw.Draw(metal)
    interior = (marco, marco, w - marco - 1, h - marco - 1)
    da.rectangle((interior[0] - 5 * s, interior[1] - 5 * s, interior[2] + 5 * s, interior[3] + 5 * s), fill=(92, 94, 100))
    da.rectangle(interior, fill=(226, 229, 233))                  # lámina blanca: se ve en las rendijas
    dr.rectangle(interior, fill=int(0.16 * 255))
    dm.rectangle(interior, fill=0)
    ancho_util = w - 2 * (marco + borde)
    largo_util = h - 2 * (marco + borde) - hueco_medio
    cw = (ancho_util - (columnas - 1) * hueco) / columnas
    ch = (largo_util - (filas - 2) * hueco) / filas
    chaflan = 6 * s
    for j in range(filas):
        y0 = marco + borde + j * (ch + hueco) + (hueco_medio - hueco if j >= filas // 2 else 0)
        for i in range(columnas):
            x0 = marco + borde + i * (cw + hueco)
            x1, y1 = x0 + cw, y0 + ch
            tono = rng.uniform(0.86, 1.12)
            azul = rng.uniform(0.9, 1.1)
            c = (int(9 * tono), int(14 * tono), int(34 * tono * azul))
            da.polygon([(x0 + chaflan, y0), (x1 - chaflan, y0), (x1, y0 + chaflan), (x1, y1 - chaflan),
                        (x1 - chaflan, y1), (x0 + chaflan, y1), (x0, y1 - chaflan), (x0, y0 + chaflan)], fill=c)
            dr.rectangle((x0, y0, x1, y1), fill=int(0.07 * 255))
            for k in range(1, 6):                                  # 5 barras de plata a lo largo del módulo
                bx = x0 + cw * k / 6
                da.line([(bx, y0), (bx, y1)], fill=(138, 146, 168), width=max(1, s))
    mascara_marco = Image.new("L", (w, h), 255)
    ImageDraw.Draw(mascara_marco).rectangle(interior, fill=0)
    chico = (PANEL_PX[0], PANEL_PX[1])
    out = {"panel_albedo": np.asarray(albedo.resize(chico, Image.LANCZOS)) / 255.0,
           "panel_rugosidad": np.asarray(rug.resize(chico, Image.LANCZOS)) / 255.0,
           "panel_metal": np.asarray(metal.resize(chico, Image.LANCZOS)) / 255.0}
    ruido = _ruido(rng, 1024, 1.0, largo_min_px=2)
    ruido = np.asarray(Image.fromarray(((ruido * 20) + 128).clip(0, 255).astype(np.uint8)).resize(chico, Image.BILINEAR)) / 255.0 - 0.5
    out["panel_albedo"] = np.clip(out["panel_albedo"] + 0.02 * ruido[..., None], 0, 1)
    return out


# ---------- madera de pallet ----------

def _madera(n: int = 1024) -> dict[str, np.ndarray]:
    """Tablas de pino gastado: vetas a lo largo de x, tonos distintos por tabla, rendijas oscuras."""
    rng = np.random.default_rng(606)
    tablas = 8
    alto = n // tablas
    veta = _ruido(rng, n, 1.6, largo_min_px=2, anisotropia=0.06)
    nudos = _ruido(rng, n, 2.4, largo_min_px=n / 8)
    id_tabla = (np.arange(n) // alto)[:, None] * np.ones((1, n), dtype=int)
    tono_tabla = rng.uniform(0.85, 1.12, tablas)[id_tabla]
    dentro = (np.arange(n) % alto)[:, None] * np.ones((1, n))
    rendija = np.clip(np.minimum(dentro, alto - dentro) / 3.0, 0, 1)
    luz = tono_tabla * (1 + 0.10 * veta + 0.06 * nudos) * (0.35 + 0.65 * rendija)
    albedo = _srgb(176, 134, 92) * luz[..., None]
    rug = np.clip(0.78 + 0.05 * veta, 0.5, 1.0)
    return {"madera_albedo": albedo, "madera_rugosidad": rug}


# ---------- cielo ----------

def _cielo(ancho: int = 2048, alto: int = 1024) -> dict[str, np.ndarray]:
    """Cielo despejado de gran altura, en proyección equirrectangular (u = acimut, v = elevación).

    Colores en sRGB. Azul profundo arriba, velo de polvo tostado en el horizonte, resplandor cálido hacia el sol y suelo pardo abajo.
    El sol está en el acimut y la elevación de SOL_ACIMUT_GRADOS y SOL_ELEVACION_GRADOS.
    """
    rng = np.random.default_rng(707)
    az = (np.arange(ancho) + 0.5) / ancho * 2 * math.pi - math.pi
    el = math.pi / 2 - (np.arange(alto) + 0.5) / alto * math.pi
    az_g, el_g = np.meshgrid(az, el)
    dz = np.sin(el_g)
    dx, dy = np.cos(el_g) * np.cos(az_g), np.cos(el_g) * np.sin(az_g)
    sa, se = math.radians(SOL_ACIMUT_GRADOS), math.radians(SOL_ELEVACION_GRADOS)
    sol = np.array([math.cos(se) * math.cos(sa), math.cos(se) * math.sin(sa), math.sin(se)])
    angulo_sol = np.arccos(np.clip(dx * sol[0] + dy * sol[1] + dz * sol[2], -1, 1))

    cenit, horizonte = np.array([0.03, 0.11, 0.42]), np.array([0.40, 0.52, 0.72])
    t = np.clip(dz, 0, 1) ** 0.42
    cielo = horizonte * (1 - t[..., None]) + cenit * t[..., None]
    polvo = np.exp(-np.clip(dz, 0, 1) / 0.055)[..., None] * np.array([0.82, 0.70, 0.55]) * 0.55
    cielo = cielo * (1 - 0.55 * np.exp(-np.clip(dz, 0, 1) / 0.055)[..., None]) + polvo
    cielo += np.exp(-angulo_sol / 0.16)[..., None] * np.array([0.55, 0.42, 0.22])      # halo del sol
    cielo += np.exp(-angulo_sol / 0.9)[..., None] * np.array([0.10, 0.08, 0.04])
    suelo = np.array([0.55, 0.42, 0.30]) * (0.6 + 0.4 * np.exp(dz / 0.4))[..., None]
    sobre = (dz >= 0)[..., None]
    suavizado = np.clip((dz + 0.02) / 0.04, 0, 1)[..., None]
    mezcla = np.where(sobre, 1.0, suavizado)
    img = cielo * mezcla + suelo * (1 - mezcla)
    img = np.clip(img, 0, 1) + (rng.random(img.shape) - 0.5) / 255.0    # tramado: evita las bandas
    return {"cielo": img}


SOL_ACIMUT_GRADOS = 0.0       # el sol está del lado +X. Igual que SOL de generar_escena.py (rotación Y de 45°)
SOL_ELEVACION_GRADOS = 45.0

# nombre -> (función que lo genera, archivos que escribe). generar_escena.py pide por función.
GENERADORES = {
    "suelo": _suelo,
    "cerro": _cerro,
    "acero": _acero,
    "roca": _roca,
    "panel": _panel,
    "madera": _madera,
    "cielo": _cielo,
}


def generar(destino: Path, grupos: list[str] | None = None) -> list[Path]:
    """Escribe los PNG de cada grupo (todos si no se indica) en destino. Devuelve las rutas."""
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for grupo in grupos or list(GENERADORES):
        for nombre, datos in GENERADORES[grupo]().items():
            ruta = destino / f"{nombre}.png"
            _a_png(datos, ruta)
            rutas.append(ruta)
    return rutas


def raiz_cache() -> Path:
    """Dónde guarda asegurar() las carpetas: VIAZ_TEXTURAS, si no VIAZ_DIR_POD/texturas, si no .datos/texturas del repo."""
    if os.getenv("VIAZ_TEXTURAS"):
        return Path(os.environ["VIAZ_TEXTURAS"])
    if os.getenv("VIAZ_DIR_POD"):
        return Path(os.environ["VIAZ_DIR_POD"]) / "texturas"
    return Path(__file__).resolve().parents[1] / ".datos" / "texturas"


def asegurar(grupos: list[str], raiz: Path | None = None) -> Path:
    """Carpeta con los PNG de estos grupos, hecha una sola vez y compartida por todos los trabajos del pod.

    Cada trabajo del runner corre en su propia carpeta, y se borra al terminar. Por eso las texturas del entrenamiento no
    viajan con escena.usd: viven aparte, en <raiz>/texturas-<huella>. La huella cambia con los grupos y con este archivo,
    así que una textura nueva no pisa una que otro Isaac tenga abierta. Las semillas son fijas: mismo código, mismos PNG.
    La carpeta se arma en una temporal y se renombra de una vez: nunca queda a medias, y si dos procesos la arman a la
    vez gana el primero.
    """
    raiz = raiz or raiz_cache()
    huella = hashlib.sha256(Path(__file__).read_bytes() + ",".join(sorted(grupos)).encode()).hexdigest()[:10]
    destino = raiz / f"texturas-{huella}"
    if destino.is_dir():
        return destino
    raiz.mkdir(parents=True, exist_ok=True)
    temporal = Path(tempfile.mkdtemp(prefix=f".{destino.name}-", dir=raiz))
    try:
        generar(temporal, grupos)
        try:
            temporal.rename(destino)
        except OSError:
            if not destino.is_dir():
                raise
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    return destino


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("grupos", nargs="*", choices=list(GENERADORES))
    a = ap.parse_args()
    for ruta in generar(a.dir, a.grupos or None):
        print(ruta)


if __name__ == "__main__":
    main()
