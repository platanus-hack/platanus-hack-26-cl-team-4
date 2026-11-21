"""Configuración por variables de entorno. Valores por defecto = desarrollo local sin servicios externos."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _url_db(url: str) -> str:
    # Render entrega postgres://... o postgresql://...; SQLAlchemy con psycopg 3 necesita postgresql+psycopg://
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


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


def cargar() -> Config:
    return Config()
