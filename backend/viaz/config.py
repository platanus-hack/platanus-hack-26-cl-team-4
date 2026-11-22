"""Configuración por variables de entorno. Valores por defecto = desarrollo local sin servicios externos."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .esquemas import esquema


def _url_db(url: str) -> str:
    # Render entrega postgres://... o postgresql://...; SQLAlchemy con psycopg 3 necesita postgresql+psycopg://
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


TOPE_FINALISTAS: int = esquema("seleccion")["properties"]["finalistas"]["maxItems"]


def validar_max_finalistas(valor: int | str) -> int:
    """Cuántos finalistas puede devolver la selección: 1 a TOPE_FINALISTAS."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"VIAZ_MAX_FINALISTAS debe ser un entero de 1 a {TOPE_FINALISTAS}; vale {valor!r}") from None
    if not 1 <= n <= TOPE_FINALISTAS:
        raise ValueError(f"VIAZ_MAX_FINALISTAS debe estar entre 1 y {TOPE_FINALISTAS}; vale {n}")
    return n


@dataclass(frozen=True)
class Config:
    db_url: str = field(default_factory=lambda: _url_db(os.getenv("DATABASE_URL", "sqlite:///./.datos/viaz.db")))
    # local: archivos en disco servidos por la API. r2: Cloudflare R2 (S3) con URLs firmadas.
    almacen: str = field(default_factory=lambda: os.getenv("VIAZ_ALMACEN", "local"))
    dir_local: Path = field(default_factory=lambda: Path(os.getenv("VIAZ_DIR_LOCAL", "./.datos/archivos")))
    url_publica: str = field(default_factory=lambda: os.getenv("VIAZ_URL_PUBLICA", "http://localhost:8000").rstrip("/"))
    r2_endpoint: str = field(default_factory=lambda: os.getenv("R2_ENDPOINT", ""))
    r2_bucket: str = field(default_factory=lambda: os.getenv("R2_BUCKET", "viaz"))
    r2_key_id: str = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID", ""))
    r2_secret: str = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY", ""))
    # fijo: los agentes devuelven fixtures (sin gastar API). claude: llaman a la Claude API.
    agentes: str = field(default_factory=lambda: os.getenv("VIAZ_AGENTES", "fijo"))
    modelo: str = field(default_factory=lambda: os.getenv("VIAZ_MODELO", "claude-opus-5-5"))
    worker_token: str = field(default_factory=lambda: os.getenv("WORKER_TOKEN", "dev-token"))
    origenes: list[str] = field(default_factory=lambda: [o.strip() for o in os.getenv("VIAZ_ORIGENES", "http://localhost:3000").split(",") if o.strip()])
    corrida_demo: str = field(default_factory=lambda: os.getenv("VIAZ_CORRIDA_DEMO", ""))
    espera_trabajo_s: int = field(default_factory=lambda: int(os.getenv("VIAZ_ESPERA_TRABAJO_S", "1800")))
    # Flujo del orquestador: rl (demo: entorno a mano, constructor, entrenamiento) o planificador (flujo anterior).
    flujo: str = field(default_factory=lambda: os.getenv("VIAZ_FLUJO", "rl"))
    # Entorno y tarea escritos a mano (RF-MAP-11, RF-TAR-04). Vacío = fixtures de ejemplo.
    entorno_manual: str = field(default_factory=lambda: os.getenv("VIAZ_ENTORNO_MANUAL", ""))
    tarea_manual: str = field(default_factory=lambda: os.getenv("VIAZ_TAREA_MANUAL", ""))
    # Medir el parque en los videos (sim/medir_entorno.py) antes del agente Entorno. En el flujo rl, con medición
    # el entorno lo arma el agente con las medidas en vez de leerlo a mano.
    medir: bool = field(default_factory=lambda: os.getenv("VIAZ_MEDIR", "").lower() in ("1", "true", "si", "sí"))
    # Medida real del panel, si el cliente sabe el modelo: corrige la escala de la reconstrucción. Sin ella, la escala
    # sale de la altura de la cámara (celular en la mano, 1,5 m; un dron: VIAZ_ALTURA_CAMARA_M con su altura de vuelo).
    largo_panel_m: float = field(default_factory=lambda: float(os.getenv("VIAZ_LARGO_PANEL_M", "0") or 0))
    escala_panel_m: float = field(default_factory=lambda: float(os.getenv("VIAZ_ESCALA_PANEL_M", "0") or 0))
    altura_camara_m: float = field(default_factory=lambda: float(os.getenv("VIAZ_ALTURA_CAMARA_M", "1.5") or 0))
    horas_entrenamiento: float = field(default_factory=lambda: float(os.getenv("VIAZ_HORAS_ENTRENAMIENTO", "4")))
    episodios_evaluacion: int = field(default_factory=lambda: int(os.getenv("VIAZ_EPISODIOS_EVALUACION", "100")))
    intentos_constructor: int = field(default_factory=lambda: int(os.getenv("VIAZ_INTENTOS_CONSTRUCTOR", "3")))
    max_finalistas: int = field(default_factory=lambda: validar_max_finalistas(
        os.getenv("VIAZ_MAX_FINALISTAS", str(TOPE_FINALISTAS))))
    # Monitor del entrenamiento (RF-MON): cada cuánto chequea y a dónde avisa.
    monitor_s: float = field(default_factory=lambda: float(os.getenv("VIAZ_MONITOR_S", "600")))
    discord_webhook: str = field(default_factory=lambda: os.getenv("VIAZ_DISCORD_WEBHOOK", ""))
    # Token para acciones del equipo (detener un entrenamiento). Por defecto, el mismo del worker.
    admin_token: str = field(default_factory=lambda: os.getenv("VIAZ_ADMIN_TOKEN", "") or os.getenv("WORKER_TOKEN", "dev-token"))


def cargar() -> Config:
    return Config()
