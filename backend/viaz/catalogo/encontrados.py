"""Catálogo compartido: fichas que trajo la búsqueda web, en el almacén (catalogo/encontrados/<id>.json).

Un objeto por ficha y sin índice: dos corridas nunca reescriben el mismo archivo para agregar una ficha.
Una persona pasa una ficha de aquí a robots/ con un PR (README.md). El catálogo del repo gana un choque de id.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from jsonschema import Draft202012Validator

from ..esquemas import esquema, sin_campos

PREFIJO = "catalogo/encontrados/"
log = logging.getLogger("viaz.catalogo.encontrados")


class Almacen(Protocol):
    def leer(self, clave: str) -> bytes: ...
    def escribir(self, clave: str, datos: bytes, tipo: str = ...) -> None: ...
    def listar(self, prefijo: str) -> list[str]: ...


def clave(robot_id: str) -> str:
    return f"{PREFIJO}{robot_id}.json"


def validar_ficha(ficha: dict) -> dict:
    """Misma regla que catalogo.cargar() más `origen: busqueda`. Un error es un ValueError con el motivo."""
    errores = list(Draft202012Validator(sin_campos(esquema("robot"), ["justificacion", "alternativas"])).iter_errors(ficha))
    if errores:
        raise ValueError(f"no cumple robot.schema.json: {errores[0].message}")
    if ficha.get("origen") != "busqueda":
        raise ValueError("una ficha del catálogo compartido debe tener origen: busqueda")
    return ficha


def cargar(store: Almacen) -> dict[str, dict]:
    """Fichas válidas del catálogo compartido. Un archivo inválido se salta y queda en el log."""
    fichas: dict[str, dict] = {}
    for k in store.listar(PREFIJO):
        if not k.endswith(".json"):
            continue
        try:
            ficha = validar_ficha(json.loads(store.leer(k)))
            if clave(ficha["id"]) != k:
                raise ValueError(f"el id {ficha['id']!r} no coincide con el nombre del archivo")
        except (ValueError, TypeError) as e:
            log.warning("catálogo compartido: salto %s: %s", k, e)
            continue
        fichas[ficha["id"]] = ficha
    return fichas


def guardar(store: Almacen, ficha: dict) -> None:
    validar_ficha(ficha)
    store.escribir(clave(ficha["id"]), json.dumps(ficha, ensure_ascii=False, indent=2).encode("utf-8"),
                   "application/json")


def unir(repo: dict[str, dict], compartidas: dict[str, dict]) -> dict[str, dict]:
    """Fichas conocidas: catálogo del repo + compartido. En un choque de id gana el repo."""
    for i in sorted(set(repo) & set(compartidas)):
        log.warning("catálogo compartido: %s también está en el repo; uso la ficha del repo", i)
    return {**compartidas, **repo}
