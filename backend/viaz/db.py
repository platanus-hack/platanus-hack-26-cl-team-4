"""Tablas y cola de trabajos. Postgres en Render; SQLite en desarrollo y tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import (JSON, Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, func,
                        inspect, select, text, update)
from sqlalchemy.engine import Engine

meta = MetaData()


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return uuid.uuid4().hex[:12]


proyectos = Table(
    "proyectos", meta,
    Column("id", String(32), primary_key=True),
    Column("nombre", String(200), nullable=False),
    Column("descripcion", Text, nullable=False, default=""),
    Column("videos", JSON, nullable=False, default=list),  # claves en el almacén
    Column("creado", DateTime(timezone=True), nullable=False, default=ahora),
)

# estado: en_cola | analizando_entorno | eligiendo_robot | clonando | simulando | entrenando | evaluando | listo | error
corridas = Table(
    "corridas", meta,
    Column("id", String(32), primary_key=True),
    Column("proyecto_id", String(32), nullable=False),
    Column("estado", String(32), nullable=False, default="en_cola"),
    Column("etapas", JSON, nullable=False, default=list),  # [{nombre, estado, artefactos: [archivo]}]
    Column("error", Text),
    Column("creado", DateTime(timezone=True), nullable=False, default=ahora),
    Column("actualizado", DateTime(timezone=True), nullable=False, default=ahora),
)

# tipo: generar_escena | validar_clon | validar_robot | ejecutar_tarea | entrenar | evaluar | grabar_clips
# estado: pendiente | tomado | ok | error
trabajos = Table(
    "trabajos", meta,
    Column("id", String(32), primary_key=True),
    Column("corrida_id", String(32), nullable=False),
    Column("tipo", String(32), nullable=False),
    Column("estado", String(16), nullable=False, default="pendiente"),
    Column("entradas", JSON, nullable=False, default=list),  # archivos de la corrida que lee
    Column("salidas", JSON, nullable=False, default=list),   # archivos de la corrida que escribe
    Column("error", Text),
    Column("tomado_en", DateTime(timezone=True)),
    Column("latido_en", DateTime(timezone=True)),             # último latido de un trabajo largo (RF-API-06)
    Column("detener", Boolean, nullable=False, default=False),  # el próximo latido responde "detener"
    Column("parametros", JSON, nullable=False, default=dict),   # argumentos del trabajo (horas, checkpoint, episodios…)
    Column("creado", DateTime(timezone=True), nullable=False, default=ahora),
)

# Métricas del entrenamiento: una fila por iteración, llegan con cada latido (RF-GPU-06).
metricas = Table(
    "metricas", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trabajo_id", String(32), nullable=False, index=True),
    Column("corrida_id", String(32), nullable=False, index=True),
    Column("iteracion", Integer, nullable=False),
    Column("datos", JSON, nullable=False),
    Column("creado", DateTime(timezone=True), nullable=False, default=ahora),
)

# Columnas agregadas después de la primera versión: create_all no las agrega a tablas que ya existen.
_COLUMNAS_NUEVAS = {
    "trabajos": {"latido_en": "TIMESTAMP", "detener": "BOOLEAN NOT NULL DEFAULT FALSE", "parametros": "JSON"},
}

ETAPAS = ["entorno", "tarea", "robot", "clon", "inteligencia"]


def motor(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    else:
        eng = create_engine(url, pool_pre_ping=True)
    meta.create_all(eng)
    _migrar(eng)
    return eng


def _migrar(eng: Engine) -> None:
    """Agrega columnas nuevas a bases existentes (SQLite local o Postgres de Render)."""
    insp = inspect(eng)
    for tabla, columnas in _COLUMNAS_NUEVAS.items():
        existentes = {c["name"] for c in insp.get_columns(tabla)}
        with eng.begin() as cx:
            for nombre, tipo in columnas.items():
                if nombre not in existentes:
                    if eng.dialect.name == "sqlite":
                        tipo = tipo.replace("FALSE", "0")
                    cx.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}"))
            if "parametros" in columnas and "parametros" not in existentes:
                cx.execute(text(f"UPDATE {tabla} SET parametros = '{{}}' WHERE parametros IS NULL"))


def tomar_con_lock(eng: Engine, tabla: Table, condicion, cambios: dict):
    """Toma una fila que cumpla `condicion` y la actualiza en la misma transacción.
    En Postgres usa FOR UPDATE SKIP LOCKED; en SQLite la escritura ya es exclusiva."""
    with eng.begin() as cx:
        q = select(tabla).where(condicion).order_by(tabla.c.creado).limit(1)
        if eng.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        fila = cx.execute(q).mappings().first()
        if fila is None:
            return None
        cx.execute(update(tabla).where(tabla.c.id == fila["id"]).values(**cambios))
        return {**fila, **cambios}


def devolver_trabajos_vencidos(eng: Engine, minutos: int = 30) -> int:
    """Un trabajo tomado sin `fin` ni latido en `minutos` vuelve a la cola (el pod pudo caerse).
    Un entrenamiento de horas sigue tomado mientras mande latidos (RF-API-05, RF-API-06)."""
    limite = ahora() - timedelta(minutes=minutos)
    ultimo = func.coalesce(trabajos.c.latido_en, trabajos.c.tomado_en)
    with eng.begin() as cx:
        r = cx.execute(update(trabajos)
                       .where(trabajos.c.estado == "tomado", ultimo < limite)
                       .values(estado="pendiente", tomado_en=None, latido_en=None))
        return r.rowcount or 0
