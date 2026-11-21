"""Catálogo de robots reales: un JSON por robot en robots/ (los que empiezan con _ no se cargan)."""
from __future__ import annotations

import json
from pathlib import Path

from ..esquemas import esquema, sin_campos
from jsonschema import Draft202012Validator

DIR = Path(__file__).parent / "robots"


def cargar() -> dict[str, dict]:
    validador = Draft202012Validator(sin_campos(esquema("robot"), ["justificacion", "alternativas"]))
    robots = {}
    for f in sorted(DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        errores = list(validador.iter_errors(r))
        if errores:
            raise ValueError(f"catálogo: {f.name} no cumple robot.schema.json: {errores[0].message}")
        if r["id"] != f.stem:
            raise ValueError(f"catálogo: el id de {f.name} debe ser '{f.stem}'")
        robots[r["id"]] = r
    if not robots:
        raise ValueError("catálogo vacío")
    return robots
