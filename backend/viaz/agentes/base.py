"""Llamada a Claude que devuelve JSON validado contra el contrato.

- Usa structured outputs (output_config.format). En Opus 5.5 el tool_choice forzado da 400.
- fallbacks="default": si el modelo rechaza la consulta, la API la reintenta en un modelo de respaldo.
- Todo error de la API o del JSON sale como ErrorAgente (docs/pendientes-corrida-real.md, problema 5). Los errores
  pasajeros (429, 529, 5xx, red) se reintentan con espera, salvo que la llamada tenga tiempo tope.
- Con streaming: max_tokens alto sin el límite de 10 min de una respuesta sin streaming (problema 8).
- Dos proveedores (problemas 2 y 3), con VIAZ_CLAUDE:
  - `api` (por defecto): clave de API (ANTHROPIC_API_KEY). Sirve en Render y en local.
  - `suscripcion`: el Agent SDK con el token de `claude setup-token` (CLAUDE_CODE_OAUTH_TOKEN). Solo uso personal
    en la máquina de quien compró el plan: el código lo rechaza en Render y si también hay una clave de API.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from ..esquemas import ErrorEsquema, para_api, validar

log = logging.getLogger("viaz.claude")

PROVEEDORES = ("api", "suscripcion")
MAX_TOKENS = 32000                       # tope por defecto; cada agente puede pedir otro (VIAZ_MAX_TOKENS lo cambia)
ESPERAS_S = (5.0, 20.0, 60.0)            # espera antes de cada reintento de un error pasajero
ESTADOS_PASAJEROS = (408, 429, 500, 502, 503, 504, 529)
USO_ALTO = 0.8                           # avisa si la salida usa más que esto del tope (problema 8)


class ErrorAgente(RuntimeError):
    pass


def proveedor() -> str:
    p = os.getenv("VIAZ_CLAUDE", "api")
    if p not in PROVEEDORES:
        raise ErrorAgente(f"VIAZ_CLAUDE='{p}' no existe; valores: {', '.join(PROVEEDORES)}")
    return p


def max_tokens_por_defecto() -> int:
    return int(os.getenv("VIAZ_MAX_TOKENS", str(MAX_TOKENS)))


def problemas_credenciales() -> list[str]:
    """Lo que falta o sobra para llamar a Claude con el proveedor elegido. Vacío si se puede intentar."""
    if proveedor() == "api":
        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
            return ["falta ANTHROPIC_API_KEY (VIAZ_CLAUDE=api)"]
        return []
    problemas = []
    if os.getenv("RENDER"):
        problemas.append("VIAZ_CLAUDE=suscripcion no se permite en Render: los términos del plan Pro/Max cubren el uso "
                         "personal de Claude Code, no un servicio. En Render usa una clave de API")
    if os.getenv("ANTHROPIC_API_KEY"):
        problemas.append("con VIAZ_CLAUDE=suscripcion no puede haber ANTHROPIC_API_KEY: gana sobre el token de la "
                         "suscripción y la corrida se cobraría a la API sin avisar")
    if not os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        problemas.append("falta CLAUDE_CODE_OAUTH_TOKEN (sale de `claude setup-token`)")
    return problemas


def pedir_json(*, modelo: str, sistema: str, contenido: list[dict], esquema: dict, effort: str = "high",
               tiempo_s: float | None = None, max_tokens: int | None = None, etiqueta: str = "") -> dict:
    """JSON de Claude que cumple `esquema`. Lanza ErrorAgente ante cualquier falla."""
    problemas = problemas_credenciales()
    if problemas:
        raise ErrorAgente("; ".join(problemas))
    tope = max_tokens or max_tokens_por_defecto()
    if proveedor() == "suscripcion":
        return _pedir_suscripcion(modelo=modelo, sistema=sistema, contenido=contenido, esquema=esquema, effort=effort,
                                  tiempo_s=tiempo_s, etiqueta=etiqueta)
    return _pedir_api(modelo=modelo, sistema=sistema, contenido=contenido, esquema=esquema, effort=effort,
                      tiempo_s=tiempo_s, max_tokens=tope, etiqueta=etiqueta)


def _pasajero(e: Exception) -> bool:
    import anthropic

    if isinstance(e, anthropic.APIConnectionError):     # incluye APITimeoutError
        return True
    return isinstance(e, anthropic.APIStatusError) and e.status_code in ESTADOS_PASAJEROS


def _pedir_api(*, modelo: str, sistema: str, contenido: list[dict], esquema: dict, effort: str,
               tiempo_s: float | None, max_tokens: int, etiqueta: str, dormir=time.sleep) -> dict:
    import anthropic

    # Con un tiempo tope, sin reintentos: cada reintento volvería a esperar el tope completo.
    cliente = anthropic.Anthropic(max_retries=0)  # lee ANTHROPIC_API_KEY; los reintentos los maneja este código
    extra = {"timeout": tiempo_s} if tiempo_s is not None else {}
    esperas = () if tiempo_s is not None else ESPERAS_S
    inicio = time.monotonic()
    for intento in range(len(esperas) + 1):
        try:
            with cliente.beta.messages.stream(
                **extra,
                model=modelo,
                max_tokens=max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=sistema,
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": para_api(esquema)}},
            ) as flujo:
                resp = flujo.get_final_message()
            break
        except anthropic.APIError as e:
            estado = getattr(e, "status_code", None)
            if _pasajero(e) and intento < len(esperas):
                log.warning("claude %s: error pasajero %s (%s); reintento en %.0f s", etiqueta or "-", estado,
                            type(e).__name__, esperas[intento])
                dormir(esperas[intento])
                continue
            raise ErrorAgente(f"la API de Claude falló ({type(e).__name__}"
                              f"{f', {estado}' if estado else ''}): {str(e)[:300]}") from e
    _registrar_uso(etiqueta, resp, max_tokens, time.monotonic() - inicio)
    if resp.stop_reason == "refusal":
        raise ErrorAgente(f"el modelo rechazó la consulta: {getattr(resp.stop_details, 'explanation', '')}")
    if resp.stop_reason == "max_tokens":
        raise ErrorAgente(f"la respuesta se cortó por max_tokens ({max_tokens}); sube el tope de este agente")
    texto = next((b.text for b in resp.content if b.type == "text"), None)
    if texto is None:
        raise ErrorAgente(f"respuesta sin texto (stop_reason={resp.stop_reason})")
    return _json(texto)


def _json(texto: str) -> dict:
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErrorAgente(f"la respuesta no es JSON válido: {e}") from e


def _registrar_uso(etiqueta: str, resp, max_tokens: int, segundos: float) -> None:
    """RF-ORQ-06: tokens y duración de cada llamada. Avisa si la salida se acerca al tope (problema 8)."""
    uso = getattr(resp, "usage", None)
    salida = getattr(uso, "output_tokens", None)
    log.info("claude %s: %s tokens de entrada, %s de salida (tope %s), %.1f s", etiqueta or "-",
             getattr(uso, "input_tokens", None), salida, max_tokens, segundos)
    if isinstance(salida, int) and salida > USO_ALTO * max_tokens:
        log.warning("claude %s: la salida usó %d de %d tokens (> %.0f %%): sube su max_tokens",
                    etiqueta or "-", salida, max_tokens, USO_ALTO * 100)


# ---------- Proveedor suscripción: Agent SDK, solo local ----------

def _mensaje_sdk(sistema: str, contenido: list[dict]):
    """El contenido como un mensaje de usuario en streaming (así el SDK acepta imágenes)."""
    async def mensajes():
        yield {"type": "user", "message": {"role": "user", "content": contenido}}
    return mensajes()


def _pedir_suscripcion(*, modelo: str, sistema: str, contenido: list[dict], esquema: dict, effort: str,
                       tiempo_s: float | None, etiqueta: str) -> dict:
    """Una consulta con el Agent SDK de Python: sin herramientas, sin CLAUDE.md ni hooks (carpeta vacía y
    setting_sources vacío), con salida estructurada. Con tiempo tope, la consulta se cancela al cumplirse."""
    import asyncio

    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError as e:
        raise ErrorAgente("VIAZ_CLAUDE=suscripcion necesita el Agent SDK: pip install claude-agent-sdk") from e

    async def correr() -> dict:
        with tempfile.TemporaryDirectory() as vacia:
            opciones = ClaudeAgentOptions(
                # tools=[]: sin herramientas. max_turns=3: la salida estructurada usa un turno propio del SDK.
                model=modelo, system_prompt=sistema, cwd=vacia, setting_sources=[], tools=[], allowed_tools=[], max_turns=3,
                effort=effort, output_format={"type": "json_schema", "schema": para_api(esquema)},
                env={"CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_CODE_OAUTH_TOKEN"]})
            final = None
            async for m in query(prompt=_mensaje_sdk(sistema, contenido), options=opciones):
                if isinstance(m, ResultMessage):
                    final = m
            if final is None:
                raise ErrorAgente("el Agent SDK terminó sin resultado")
            if getattr(final, "is_error", False):
                raise ErrorAgente(f"el Agent SDK devolvió un error: {getattr(final, 'result', '')}"[:300])
            datos = getattr(final, "structured_output", None)
            if datos is None:
                raise ErrorAgente("el Agent SDK no devolvió structured_output")
            log.info("claude %s (suscripción): %s", etiqueta or "-", getattr(final, "usage", None))
            return datos if isinstance(datos, dict) else _json(str(datos))

    inicio = time.monotonic()
    try:
        tarea = correr()
        resultado = asyncio.run(asyncio.wait_for(tarea, tiempo_s) if tiempo_s else tarea)
    except ErrorAgente:
        raise
    except asyncio.TimeoutError as e:
        raise ErrorAgente(f"la consulta con suscripción pasó el tope de {tiempo_s} s") from e
    except Exception as e:  # noqa: BLE001  (el SDK lanza sus propias excepciones de proceso y de red)
        raise ErrorAgente(f"el Agent SDK falló ({type(e).__name__}): {str(e)[:300]}") from e
    log.info("claude %s (suscripción): %.1f s", etiqueta or "-", time.monotonic() - inicio)
    return resultado


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
