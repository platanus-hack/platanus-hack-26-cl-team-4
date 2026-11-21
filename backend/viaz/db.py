"""Tablas y cola de trabajos. Postgres en Render; SQLite en desarrollo y tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text, create_engine, select, update
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

# estado: en_cola | analizando_entorno | eligiendo_robot | clonando | simulando | listo | error
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

# tipo: generar_escena | validar_clon | ejecutar_tarea | entrenar_subtarea
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
    Column("creado", DateTime(timezone=True), nullable=False, default=ahora),
)

ETAPAS = ["entorno", "tarea", "robot", "clon", "inteligencia"]


def motor(url: str) -> Engine:
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    else:
        eng = create_engine(url, pool_pre_ping=True)
    meta.create_all(eng)
    return eng


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
    """Un trabajo tomado sin `fin` en `minutos` vuelve a la cola (el pod pudo caerse)."""
    limite = ahora() - timedelta(minutes=minutos)
    with eng.begin() as cx:
        r = cx.execute(update(trabajos)
                       .where(trabajos.c.estado == "tomado", trabajos.c.tomado_en < limite)
                       .values(estado="pendiente", tomado_en=None))
        return r.rowcount or 0
