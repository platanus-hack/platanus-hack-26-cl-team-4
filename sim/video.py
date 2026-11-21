"""Utilidades de video para el demo: rótulos, mini curva, unión de clips. Python puro + ffmpeg (imageio-ffmpeg).

Lo usan:
- worker-gpu/runner.py: agrega el rótulo a cada clip del entrenamiento y arma entrenamiento_rapido.mp4 (RF-INT-13).
- sim/rl_simulado.py: genera videos de prueba sin Isaac.

Formato de salida: 1280 × 720, 30 fps, H.264, yuv420p (se reproduce en cualquier navegador).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ANCHO, ALTO, FPS = 1280, 720, 30


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _correr(args: list[str]) -> None:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {r.stderr[-800:]}")


# Fuentes con tildes y "×". La de Pillow por defecto no las trae. VIAZ_FUENTE permite elegir otra.
_FUENTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # Ubuntu (pod): paquete fonts-dejavu-core
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",              # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def _fuente(tam: int):
    import os
    from PIL import ImageFont
    for ruta in [os.getenv("VIAZ_FUENTE", ""), *_FUENTES]:
        if ruta and Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default(size=tam)  # sin tildes: instalar fonts-dejavu-core en el pod


def duracion_s(video: Path) -> float:
    """Duración de un mp4 en segundos (lee la salida de ffmpeg -i)."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(video)], capture_output=True, text=True)
    for linea in r.stderr.splitlines():
        if "Duration:" in linea:
            h, m, s = linea.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"no pude leer la duración de {video}")


def frames_a_mp4(carpeta: Path, salida: Path, fps: int = FPS) -> Path:
    """Codifica f_0000.png, f_0001.png… en un mp4 H.264."""
    _correr(["-framerate", str(fps), "-i", str(carpeta / "f_%04d.png"),
             "-vf", f"scale={ANCHO}:{ALTO}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(salida)])
    return salida


def mini_curva(puntos: list[tuple[float, float]], hasta_x: float, ancho: int = 260, alto: int = 90):
    """Imagen RGBA con la curva de éxito (x = iteración, y = 0..1) hasta `hasta_x`, y el resto atenuado."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (ancho, alto), (15, 18, 23, 200))
    d = ImageDraw.Draw(img)
    if len(puntos) >= 2:
        x0, x1 = puntos[0][0], max(puntos[-1][0], puntos[0][0] + 1)
        a_px = lambda x, y: (8 + (x - x0) / (x1 - x0) * (ancho - 16), alto - 8 - max(0.0, min(1.0, y)) * (alto - 16))  # noqa: E731
        y90 = a_px(x0, 0.9)[1]  # línea de la meta: 90 %
        d.line([(8, y90), (ancho - 8, y90)], fill=(90, 100, 115, 255), width=1)
        todos = [a_px(x, y) for x, y in puntos]
        d.line(todos, fill=(110, 120, 135, 255), width=2)
        hechos = [a_px(x, y) for x, y in puntos if x <= hasta_x]
        if len(hechos) >= 2:
            d.line(hechos, fill=(224, 161, 6, 255), width=3)
        if hechos:
            cx, cy = hechos[-1]
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(224, 161, 6, 255))
    d.text((8, 4), "éxito", font=_fuente(14), fill=(200, 205, 215, 255))
    return img


def rotulo(texto_grande: str, texto_chico: str, curva=None, aviso: str = "Simulación"):
    """Capa transparente 1280×720 con el rótulo del clip (RF-INT-13, RNF-18)."""
    from PIL import Image, ImageDraw
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    maximo = ANCHO - 24 - 150 - 24 - 32 - 24   # sin tapar la etiqueta "Simulación"
    tam_g, tam_c = 34, 20
    while tam_g > 18 and d.textlength(texto_grande, font=_fuente(tam_g)) > maximo:
        tam_g -= 2
    while tam_c > 12 and d.textlength(texto_chico, font=_fuente(tam_c)) > maximo:
        tam_c -= 1
    ancho = max(d.textlength(texto_grande, font=_fuente(tam_g)), d.textlength(texto_chico, font=_fuente(tam_c)), 300) + 32
    d.rounded_rectangle([24, 24, 24 + ancho, 24 + 92], radius=10, fill=(15, 18, 23, 200))
    d.text((40, 34 + (34 - tam_g) // 2), texto_grande, font=_fuente(tam_g), fill=(255, 255, 255, 255))
    d.text((40, 78), texto_chico, font=_fuente(tam_c), fill=(200, 205, 215, 255))
    d.rounded_rectangle([ANCHO - 24 - 150, 24, ANCHO - 24, 24 + 36], radius=8, fill=(224, 161, 6, 230))
    d.text((ANCHO - 24 - 140, 31), aviso, font=_fuente(20), fill=(26, 19, 0, 255))
    if curva is not None:
        capa.alpha_composite(curva, (ANCHO - 24 - curva.width, ALTO - 24 - curva.height))
    return capa


def superponer(video: Path, capa, salida: Path) -> Path:
    """Pone la capa PNG encima de todo el video y lo normaliza a 1280×720 H.264."""
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "capa.png"
        capa.save(png)
        _correr(["-i", str(video), "-i", str(png), "-filter_complex",
                 f"[0:v]scale={ANCHO}:{ALTO},setsar=1,fps={FPS}[v];[v][1:v]overlay=0:0",
                 "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(salida)])
    return salida


def unir(clips: list[Path], salida: Path) -> Path:
    """Concatena clips ya normalizados en un solo mp4."""
    with tempfile.TemporaryDirectory() as tmp:
        lista = Path(tmp) / "lista.txt"
        lista.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
        _correr(["-f", "concat", "-safe", "0", "-i", str(lista), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(salida)])
    return salida


def texto_tiempo(segundos: float) -> str:
    h, m = int(segundos // 3600), int(segundos % 3600 // 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def tarjeta(titulo: str, lineas: list[str], salida: Path, segundos: float = 3.0, aviso: str = "Simulación") -> Path:
    """Clip de texto fijo (por ejemplo, un intento del agente rechazado por reglas antes de ir al pod)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (ANCHO, ALTO), (24, 28, 36))
    d = ImageDraw.Draw(img)
    d.text((80, 200), titulo, font=_fuente(44), fill=(255, 255, 255))
    for k, linea in enumerate(lineas[:6]):
        d.text((80, 290 + k * 46), linea, font=_fuente(28), fill=(205, 210, 220))
    d.rounded_rectangle([ANCHO - 24 - 150, 24, ANCHO - 24, 24 + 36], radius=8, fill=(224, 161, 6))
    d.text((ANCHO - 24 - 140, 31), aviso, font=_fuente(20), fill=(26, 19, 0))
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "t.png"
        img.save(png)
        _correr(["-loop", "1", "-framerate", str(FPS), "-i", str(png), "-t", str(segundos),
                 "-vf", f"scale={ANCHO}:{ALTO}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(salida)])
    return salida

