"""Lee la carpeta de una corrida: lo que el runner le pasa a los 4 comandos (docs/contrato-entorno-rl.md §2).

Python puro. Nada del parque ni del robot va fijo en el código del entorno: todo sale de aquí.
- entorno.json y tarea.json llegan por argumento.
- robot_cfg.py llega por argumento. De él se lee PARAMETROS.
- clon.json y robot.urdf se buscan al lado de robot_cfg.py. Si falta robot.urdf, se genera con
  backend/viaz/urdf.py desde clon.json, igual que lo hace el orquestador.
"""
from __future__ import annotations

import importlib.util
import json
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path

from . import robot as robot_mod

RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Corrida:
    carpeta: Path
    entorno: dict
    tarea: dict
    parametros: dict
    clon: dict
    urdf: str
    robot: robot_mod.Robot
    cadena: robot_mod.Cadena

    @property
    def carga_util_kg(self) -> float:
        return float(self.clon["escala"]["carga_util_kg"])


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _generar_urdf(clon: dict) -> str:
    """El mismo URDF que escribe el orquestador (backend/viaz/orquestador.py, construir_robot)."""
    ruta = RAIZ / "backend" / "viaz" / "urdf.py"
    spec = importlib.util.spec_from_file_location("viaz_urdf", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo   # las dataclasses de urdf.py buscan su módulo ahí
    spec.loader.exec_module(modulo)
    ficha = RAIZ / "backend" / "viaz" / "catalogo" / "robots" / f"{clon['robot_id']}.json"
    fisica = _json(ficha).get("fisica") if ficha.exists() else None
    return modulo.generar(clon["robot_id"], clon["escala"]["alcance_m"], fisica)


def leer(entorno: str | Path, tarea: str | Path, robot_cfg: str | Path) -> Corrida:
    robot_cfg = Path(robot_cfg).resolve()
    carpeta = robot_cfg.parent
    ruta_clon = carpeta / "clon.json"
    if not ruta_clon.exists():
        raise FileNotFoundError(f"falta clon.json al lado de {robot_cfg}: el entorno saca de él la carga útil del robot")
    clon = _json(ruta_clon)
    ruta_urdf = carpeta / clon.get("urdf", "robot.urdf")
    urdf = ruta_urdf.read_text(encoding="utf-8") if ruta_urdf.exists() else _generar_urdf(clon)
    robot = robot_mod.leer_urdf(urdf)
    cadena = robot_mod.cadena(robot)
    geo = clon["geometria"]
    if abs(cadena.montaje_x - geo["montaje_x_m"]) > 1e-3 or abs(cadena.cubierta_z - geo["cubierta_z_m"]) > 1e-3:
        raise ValueError(f"robot.urdf no calza con clon.json: el brazo va en x = {cadena.montaje_x} m sobre una cubierta de "
                         f"{cadena.cubierta_z} m, y clon.json dice {geo['montaje_x_m']} m y {geo['cubierta_z_m']} m")
    return Corrida(carpeta=carpeta, entorno=_json(Path(entorno)), tarea=_json(Path(tarea)),
                   parametros=runpy.run_path(str(robot_cfg))["PARAMETROS"], clon=clon, urdf=urdf,
                   robot=robot, cadena=cadena)


def de_carpeta(carpeta: str | Path) -> Corrida:
    carpeta = Path(carpeta)
    return leer(carpeta / "entorno.json", carpeta / "tarea.json", carpeta / "robot_cfg.py")
