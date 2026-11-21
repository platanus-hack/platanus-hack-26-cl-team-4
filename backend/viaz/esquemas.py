"""Esquemas JSON del contrato (docs/contrato-datos.md): carga, validación y versión para la API de Claude."""
from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

DIR = Path(__file__).parent / "esquemas"
NOMBRES = ("entorno", "tarea", "robot", "clon", "resultado", "trayectoria",
           "metricas", "evaluacion", "ensamblaje", "monitoreo", "hitos", "curva", "medidas_entorno")

# Restricciones que los structured outputs de la API no aceptan. Se validan igual en local.
_NO_SOPORTADAS = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems",
                  "minLength", "maxLength", "pattern", "format", "$schema", "title", "description"}


class ErrorEsquema(ValueError):
    pass


@cache
def esquema(nombre: str) -> dict:
    return json.loads((DIR / f"{nombre}.schema.json").read_text(encoding="utf-8"))


def validar(nombre: str, datos: dict) -> dict:
    errores = sorted(Draft202012Validator(esquema(nombre)).iter_errors(datos), key=lambda e: list(e.path))
    if errores:
        detalle = "; ".join(f"{'/'.join(map(str, e.path)) or '(raíz)'}: {e.message}" for e in errores[:5])
        raise ErrorEsquema(f"{nombre}.json no cumple el contrato: {detalle}")
    return datos


def sin_campos(schema: dict, campos: list[str]) -> dict:
    """Copia del esquema sin algunos campos de primer nivel (los que llena el orquestador)."""
    s = copy.deepcopy(schema)
    for c in campos:
        s["properties"].pop(c, None)
        if c in s.get("required", []):
            s["required"].remove(c)
    return s


def para_api(schema: dict) -> dict:
    """Quita restricciones no soportadas por output_config.format. `const` pasa a `enum`."""
    def limpiar(n):
        if isinstance(n, dict):
            out = {k: limpiar(v) for k, v in n.items() if k not in _NO_SOPORTADAS}
            if "const" in out:
                out["enum"] = [out.pop("const")]
            return out
        if isinstance(n, list):
            return [limpiar(x) for x in n]
        return n
    return limpiar(schema)
