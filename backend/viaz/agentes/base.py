"""Llamada a Claude que devuelve JSON validado contra el contrato.

- Usa structured outputs (output_config.format). En Opus 5.5 el tool_choice forzado da 400.
- fallbacks="default": si el modelo rechaza la consulta, la API la reintenta en un modelo de respaldo.
"""
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path

from ..esquemas import ErrorEsquema, para_api, validar


class ErrorAgente(RuntimeError):
    pass


def pedir_json(*, modelo: str, sistema: str, contenido: list[dict], esquema: dict, effort: str = "high") -> dict:
    import anthropic

    cliente = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY
    resp = cliente.beta.messages.create(
        model=modelo,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=sistema,
        messages=[{"role": "user", "content": contenido}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": para_api(esquema)}},
    )
    if resp.stop_reason == "refusal":
        raise ErrorAgente(f"el modelo rechazó la consulta: {getattr(resp.stop_details, 'explanation', '')}")
    if resp.stop_reason == "max_tokens":
        raise ErrorAgente("la respuesta se cortó por max_tokens")
    texto = next((b.text for b in resp.content if b.type == "text"), None)
    if texto is None:
        raise ErrorAgente(f"respuesta sin texto (stop_reason={resp.stop_reason})")
    return json.loads(texto)


def validado(nombre: str, datos: dict) -> dict:
    try:
        return validar(nombre, datos)
    except ErrorEsquema as e:
        raise ErrorAgente(str(e)) from e


def frames_de_videos(videos: list[bytes], max_frames: int = 8) -> list[dict]:
    """Saca hasta max_frames JPG (1 cada 3 s, 1024 px de ancho) y los devuelve como bloques de imagen."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    bloques: list[dict] = []
    por_video = max(1, max_frames // max(len(videos), 1))
    with tempfile.TemporaryDirectory() as tmp:
        for i, datos in enumerate(videos):
            entrada = Path(tmp) / f"v{i}.mp4"
            entrada.write_bytes(datos)
            patron = str(Path(tmp) / f"v{i}_%02d.jpg")
            subprocess.run([ffmpeg, "-loglevel", "error", "-i", str(entrada), "-vf", "fps=1/3,scale=1024:-2",
                            "-frames:v", str(por_video), patron], check=True)
            for jpg in sorted(Path(tmp).glob(f"v{i}_*.jpg")):
                bloques.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                            "data": base64.b64encode(jpg.read_bytes()).decode()}})
    if not bloques:
        raise ErrorAgente("no pude sacar frames de los videos")
    return bloques[:max_frames]
