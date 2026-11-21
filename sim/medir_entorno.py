"""Mide un parque solar desde sus videos: MapAnything (nube métrica) + SAM 3 (qué es cada punto) + medir_geometria.

    /venv/medicion/bin/python sim/medir_entorno.py --videos v0.mp4 [v1.mp4 ...] --salida DIR [--frames 32] [--sin-sam]

Escribe en DIR:
  medidas_entorno.json   valor ± error por campo de entorno.json (esquema: backend/viaz/esquemas/medidas_entorno.schema.json)
  medidas_vista.png      vista cenital de la nube con las filas encontradas: el agente Entorno la mira para revisar
  nube.npz               la nube en el marco del suelo, submuestreada (para depurar)

Corre en un entorno aparte del de Isaac (worker-gpu/pod/instalar_medicion.sh): MapAnything y SAM 3 traen su propio torch.
Si SAM 3 no está (modelo con acceso restringido en Hugging Face), mide solo con la nube y lo avisa.
Si algo falla, igual escribe medidas_entorno.json con "disponible": false y el motivo: el agente sigue sin medidas.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import medir_geometria as mg  # noqa: E402

MODELO = "facebook/map-anything-apache"     # pesos Apache-2.0: uso comercial permitido
MAX_DISTANCIA_M = 80.0                       # puntos más lejos de su cámara: cielo, cerros, ruido
MAX_PUNTOS = 1_500_000
PERCENTIL_CONFIANZA = 20                     # descarta el 20 % de puntos con menos confianza de cada vista
# Prompts de SAM 3 por etiqueta. PVIS-10K eligió "individual solar panel" para paneles sueltos.
PROMPTS = {
    mg.PANEL: ["individual solar panel"],
    mg.TUBO: ["horizontal metal pipe"],
    mg.POSTE: ["metal post"],
    mg.EXCLUIR: ["person", "car", "truck"],
}
UMBRAL_SAM = 0.5


def extraer_frames(videos: list[Path], destino: Path, total: int) -> list[Path]:
    """Frames repartidos parejo en todos los videos. Descarta los más borrosos (varianza del laplaciano)."""
    import imageio_ffmpeg
    from PIL import Image

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    candidatos: list[Path] = []
    por_video = max(2, math.ceil(total * 1.25 / max(1, len(videos))))   # 25 % extra para descartar borrosos
    for i, v in enumerate(videos):
        dur = _duracion_s(ffmpeg, v)
        for k in range(por_video):
            t = dur * (k + 0.5) / por_video
            salida = destino / f"v{i}_{k:03d}.jpg"
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(v), "-frames:v", "1",
                            "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", str(salida)], check=True)
            if salida.exists():
                candidatos.append(salida)
    if not candidatos:
        raise RuntimeError("no pude sacar frames de los videos")

    def nitidez(p: Path) -> float:
        g = np.asarray(Image.open(p).convert("L"), float)
        lap = g[1:-1, 2:] + g[1:-1, :-2] + g[2:, 1:-1] + g[:-2, 1:-1] - 4 * g[1:-1, 1:-1]
        return float(lap.var())

    puntaje = {p: nitidez(p) for p in candidatos}
    nitidos = sorted(candidatos, key=lambda p: -puntaje[p])[:total]
    return sorted(nitidos)


def _duracion_s(ffmpeg: str, video: Path) -> float:
    r = subprocess.run([ffmpeg, "-i", str(video)], capture_output=True, text=True)
    for linea in r.stderr.splitlines():
        if "Duration:" in linea:
            h, m, s = linea.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"no pude leer la duración de {video.name}")


def reconstruir(frames: list[Path], percentil_confianza: float = PERCENTIL_CONFIANZA) -> dict:
    """MapAnything sobre los frames: puntos (N, 3), color, cámara de cada punto y la vertical de las cámaras."""
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import load_images

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = MapAnything.from_pretrained(MODELO).to(dispositivo)
    vistas = load_images([str(f) for f in frames])
    with torch.inference_mode():
        pred = modelo.infer(vistas, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16",
                            apply_mask=True, mask_edges=True, apply_confidence_mask=False)
    puntos, colores, vista_de, arribas, por_vista, camaras = [], [], [], [], [], []
    for i, p in enumerate(pred):
        pts = p["pts3d"][0].float().cpu().numpy()                       # (H, W, 3)
        mascara = p["mask"][0, ..., 0].bool().cpu().numpy()
        conf = p["conf"][0].float().cpu().numpy()
        pose = p["camera_poses"][0].float().cpu().numpy()                 # cam2world, OpenCV (+Y abajo)
        img = p["img_no_norm"][0].float().cpu().numpy()
        centro = pose[:3, 3]
        lejos = np.linalg.norm(pts - centro, axis=-1) > MAX_DISTANCIA_M
        buena = mascara & ~lejos & (conf >= np.percentile(conf[mascara], percentil_confianza) if mascara.any() else mascara)
        por_vista.append({"pts": pts, "buena": buena, "forma": pts.shape[:2]})
        puntos.append(pts[buena])
        colores.append(img[buena])
        vista_de.append(np.full(int(buena.sum()), i))
        arribas.append(-pose[:3, 1])                                       # -Y de la cámara = arriba
        camaras.append(centro)
    arriba = np.mean(arribas, axis=0)
    return {"puntos": np.concatenate(puntos), "colores": np.concatenate(colores), "vista": np.concatenate(vista_de),
            "arriba": arriba / np.linalg.norm(arriba), "por_vista": por_vista, "camaras": np.array(camaras)}


def segmentar(frames: list[Path], recon: dict) -> tuple[np.ndarray, list[np.ndarray], str | None]:
    """SAM 3 por frame: una etiqueta por punto y los puntos de cada panel. Devuelve (etiquetas, paneles, aviso)."""
    try:
        import torch
        from PIL import Image
        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_sam3_image_model
    except Exception as e:  # noqa: BLE001
        return None, [], f"SAM 3 no está instalado ({type(e).__name__}): se mide solo con la nube"
    try:
        procesador = Sam3Processor(build_sam3_image_model())
    except Exception as e:  # noqa: BLE001 — sin acceso al modelo restringido en Hugging Face
        return None, [], f"SAM 3 no cargó ({type(e).__name__}: {str(e)[:120]}): se mide solo con la nube"
    etiquetas, paneles = [], []
    with torch.inference_mode():
        for f, v in zip(frames, recon["por_vista"]):
            h, w = v["forma"]
            img = Image.open(f).convert("RGB")
            estado = procesador.set_image(img)
            lbl = np.zeros((h, w), int)
            for etiqueta, prompts in PROMPTS.items():
                for prompt in prompts:
                    out = procesador.set_text_prompt(state=estado, prompt=prompt)
                    for m, s in zip(out["masks"], out["scores"]):
                        if float(s) < UMBRAL_SAM:
                            continue
                        m = np.asarray(m.squeeze().float().cpu().numpy() > 0.5)
                        m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 0
                        lbl[m] = etiqueta
                        if etiqueta == mg.PANEL:
                            dentro = m & v["buena"]
                            if dentro.sum() > 30:
                                paneles.append(v["pts"][dentro])
            etiquetas.append(lbl[v["buena"]])
    return np.concatenate(etiquetas), paneles, None


def vista_cenital(puntos: np.ndarray, arriba: np.ndarray, resultado: dict, salida: Path, lado_px: int = 1024) -> None:
    """Imagen desde arriba: la nube coloreada por altura, con las filas medidas como líneas rojas."""
    from PIL import Image, ImageDraw

    local, _, _ = mg.a_marco_suelo(puntos, arriba)
    d = resultado["diagnostico"]
    t = math.radians(d["direccion_filas_grados"])
    a = local[:, 0] * math.cos(t) + local[:, 1] * math.sin(t)
    c = -local[:, 0] * math.sin(t) + local[:, 1] * math.cos(t)
    z = local[:, 2]
    a0, a1 = np.percentile(a, [1, 99])
    c0, c1 = np.percentile(c, [1, 99])
    escala = (lado_px - 40) / max(a1 - a0, c1 - c0, 1.0)
    img = Image.new("RGB", (lado_px, lado_px), (20, 20, 24))
    px = ((a - a0) * escala + 20).astype(int)
    py = ((c1 - c) * escala + 20).astype(int)
    ok = (px >= 0) & (px < lado_px) & (py >= 0) & (py < lado_px)
    tono = np.clip(z / 3.0, 0, 1)
    rgb = (np.stack([tono, 1 - np.abs(tono - 0.5) * 2, 1 - tono], -1) * 255).astype(np.uint8)
    arr = np.asarray(img).copy()
    arr[py[ok], px[ok]] = rgb[ok]
    img = Image.fromarray(arr)
    dib = ImageDraw.Draw(img)
    for i, centro in enumerate(d["centros_filas_m"]):
        y = int((c1 - centro) * escala + 20)
        dib.line([(0, y), (lado_px, y)], fill=(255, 60, 60), width=2)
        dib.text((8, y - 14), f"fila {i}", fill=(255, 200, 200))
    campos = resultado["campos"]
    texto = [f"{k}: {v['valor']} ± {v['error']}" for k, v in campos.items()]
    for k, linea in enumerate(texto):
        dib.text((10, lado_px - 16 * (len(texto) - k) - 6), linea, fill=(240, 240, 240))
    escala_m = 5
    dib.line([(lado_px - 20 - escala_m * escala, 20), (lado_px - 20, 20)], fill=(255, 255, 255), width=3)
    dib.text((lado_px - 20 - escala_m * escala, 26), f"{escala_m} m", fill=(255, 255, 255))
    img.save(salida)


def medir(a) -> dict:
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        frames = extraer_frames([Path(v) for v in a.videos], Path(tmp), a.frames)
        recon = reconstruir(frames, a.percentil_confianza)
        etiquetas, paneles, aviso_sam = (None, [], "SAM 3 desactivado (--sin-sam)") if a.sin_sam else segmentar(frames, recon)
    puntos, arriba = recon["puntos"], recon["arriba"]
    if len(puntos) > MAX_PUNTOS:
        elegidos = np.random.default_rng(0).choice(len(puntos), MAX_PUNTOS, replace=False)
        puntos = puntos[elegidos]
        etiquetas = etiquetas[elegidos] if etiquetas is not None else None
    # Escala: con el panel real (si el cliente lo sabe) después de medir; si no, con la altura de la cámara antes.
    escala = {"metodo": "la de MapAnything, sin corregir", "factor": 1.0}
    error_escala = mg.ERROR_ESCALA_REL
    if not (a.largo_panel_m or a.escala_panel_m) and a.altura_camara_m > 0:
        factor, medida = mg.escala_por_camara(puntos, arriba, recon["camaras"], a.altura_camara_m)
        puntos = puntos * factor
        paneles = [p * factor for p in paneles]
        escala = {"metodo": f"cámara a {a.altura_camara_m} m del suelo (medida: {medida:.2f} m)", "factor": round(factor, 4)}
        error_escala = mg.ERROR_ESCALA_CAMARA_REL
    resultado = mg.medir(puntos, arriba, etiquetas, paneles, error_escala_rel=error_escala)
    resultado["diagnostico"]["escala"] = escala
    if aviso_sam:
        resultado["avisos"].insert(0, aviso_sam)
    if a.largo_panel_m or a.escala_panel_m:
        _reescalar(resultado, a.largo_panel_m, a.escala_panel_m)
    a.salida.mkdir(parents=True, exist_ok=True)
    vista_cenital(puntos, arriba, resultado, a.salida / "medidas_vista.png")
    sub = np.random.default_rng(1).choice(len(puntos), min(200_000, len(puntos)), replace=False)
    np.savez_compressed(a.salida / "nube.npz", puntos=puntos[sub].astype(np.float32), arriba=arriba)
    return {"version": 1, "disponible": True,
            "fuente": "map-anything-apache" + ("+sam3" if etiquetas is not None else ""),
            "frames": len(frames), "segundos": round(time.monotonic() - t0, 1),
            "campos": resultado["campos"], "avisos": resultado["avisos"], "diagnostico": resultado["diagnostico"]}


def _reescalar(resultado: dict, largo_real_m: float | None, ancho_real_m: float | None) -> None:
    """Corrige la escala con la medida real del panel (si el cliente sabe el modelo). Escala todas las longitudes.
    Prefiere el largo: se mide en todas las filas con paneles; el ancho solo si se ve el período entre paneles."""
    campos = resultado["campos"]
    referencia = next(((n, real) for n, real in (("panel.largo_m", largo_real_m), ("panel.ancho_m", ancho_real_m))
                       if real and n in campos), None)
    if referencia is None:
        resultado["avisos"].append("se dio la medida real del panel, pero el panel no se midió: escala sin corregir")
        return
    nombre, real = referencia
    f = real / campos[nombre]["valor"]
    for campo, v in campos.items():
        if campo.endswith("_m"):
            v["valor"], v["error"] = round(v["valor"] * f, 3), round(v["error"] * f, 3)
            v["metodo"] += f" · escala ×{f:.3f} con {nombre} real"
    mg.poner_confianza(campos)
    resultado["diagnostico"]["escala"] = {"metodo": f"{nombre} real = {real} m", "factor": round(f, 4)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", nargs="+", required=True)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--frames", type=int, default=64)
    ap.add_argument("--sin-sam", action="store_true")
    ap.add_argument("--largo-panel-m", type=float, help="largo real del panel, si se conoce: corrige la escala")
    ap.add_argument("--escala-panel-m", type=float, help="ancho real del panel, si se conoce: corrige la escala")
    ap.add_argument("--altura-camara-m", type=float, default=mg.ALTURA_CAMARA_MANO_M,
                    help="altura de la cámara sobre el suelo (celular en la mano: 1,5). 0: sin corregir la escala")
    ap.add_argument("--percentil-confianza", type=float, default=PERCENTIL_CONFIANZA,
                    help="descarta este porcentaje de puntos con menos confianza en cada vista")
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)
    try:
        informe = medir(a)
    except Exception as e:  # noqa: BLE001 — el agente sigue sin medidas
        traceback.print_exc()
        informe = {"version": 1, "disponible": False, "fuente": "map-anything-apache", "frames": 0,
                   "campos": {}, "avisos": [], "error": f"{type(e).__name__}: {e}"[:500]}
    (a.salida / "medidas_entorno.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("disponible", "fuente", "frames")} | {"campos": len(informe["campos"])}))


if __name__ == "__main__":
    main()
