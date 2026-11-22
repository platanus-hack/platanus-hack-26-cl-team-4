"""Modelos comprobados (paso 6 de la selección v3, RF-CLO-10/11).

Un modelo comprobado es un ensamblaje.json que pasó validar_robot en alguna escena. Se guarda en el almacén con
una clave que cambia si cambia la ficha del robot o el catálogo de assets. "Aprobado" (rúbrica humana y PR en
sim/assets_aprobados/) es otro nivel: este módulo nunca lo afirma.

Claves: modelos/<clave>/ensamblaje.json y modelos/<clave>/modelo.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from .almacen import Almacen
from .esquemas import ErrorEsquema, validar

log = logging.getLogger("viaz.modelos")

CAMPOS_FUERA_DE_CLAVE = ("justificacion", "alternativas")
LARGO_HASH = 12


def clave(robot: dict, assets: dict) -> str:
    """<id del robot>-<12 hex>: SHA-256 de la ficha (sin texto de la selección) y del catálogo de assets."""
    ficha = {k: v for k, v in robot.items() if k not in CAMPOS_FUERA_DE_CLAVE}
    canonico = json.dumps({"ficha": ficha, "assets": assets}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{robot['id']}-{hashlib.sha256(canonico.encode('utf-8')).hexdigest()[:LARGO_HASH]}"


def clave_almacen(clave_modelo: str, archivo: str) -> str:
    return f"modelos/{clave_modelo}/{archivo}"


def fidelidad(robot: dict) -> Literal["generico", "medido"]:
    return "medido" if robot.get("fisica") else "generico"


def buscar(store: Almacen, clave_modelo: str) -> dict | None:
    """ensamblaje.json guardado para la clave, o None. Un archivo que no cumple el esquema se ignora."""
    ruta = clave_almacen(clave_modelo, "ensamblaje.json")
    if not store.existe(ruta):
        return None
    try:
        return validar("ensamblaje", json.loads(store.leer(ruta)))
    except (json.JSONDecodeError, ErrorEsquema) as e:
        log.warning("modelo %s: ignoro el ensamblaje guardado: %s", clave_modelo, e)
        return None


def registrar(store: Almacen, clave_modelo: str, ens: dict, robot_id: str, corrida_id: str) -> bool:
    """Guarda un ensamblaje que pasó validar_robot. Un error del almacén se registra y no corta la corrida."""
    meta = {"clave": clave_modelo, "robot_id": robot_id, "corrida_id": corrida_id,
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "metodo": "agente"}
    try:
        for archivo, datos in (("modelo.json", meta), ("ensamblaje.json", ens)):
            store.escribir(clave_almacen(clave_modelo, archivo),
                           json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
    except Exception as e:
        log.warning("modelo %s: no pude guardarlo, la corrida sigue: %s", clave_modelo, e)
        return False
    log.info("modelo %s: registrado desde la corrida %s", clave_modelo, corrida_id)
    return True
