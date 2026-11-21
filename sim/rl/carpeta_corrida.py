"""Arma la carpeta de una corrida para un robot del catálogo, sin API ni LLM (ensamblaje por defecto).

    python sim/rl/carpeta_corrida.py --robot leapting-mmr --dir /tmp/corrida

Escribe lo mismo que el orquestador le entrega al pod: entorno.json, tarea.json, ensamblaje.json,
robot_cfg.py, clon.json, robot.urdf y escena.usd. Sirve para probar el entorno RL con cualquier robot.
Corre con el Python del backend (necesita jsonschema), no con el de Isaac.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
sys.path.insert(0, str(RAIZ / "sim"))


def escribir(robot_id: str, carpeta: Path, entorno: Path | None = None, tarea: Path | None = None) -> Path:
    import generar_escena
    from viaz import catalogo, robot_cfg, urdf

    fixtures = RAIZ / "backend" / "viaz" / "fixtures"
    entorno_json = json.loads((entorno or fixtures / "entorno.json").read_text(encoding="utf-8"))
    tarea_json = json.loads((tarea or fixtures / "tarea.json").read_text(encoding="utf-8"))
    robot = catalogo.cargar()[robot_id]
    assets = robot_cfg.cargar_assets()
    ens = robot_cfg.ensamblaje_por_defecto(robot, assets)
    clon = robot_cfg.clon(ens, robot, assets, intentos=1)
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, datos in (("entorno.json", entorno_json), ("tarea.json", tarea_json), ("ensamblaje.json", ens), ("clon.json", clon)):
        (carpeta / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "robot_cfg.py").write_text(robot_cfg.generar(ens, assets), encoding="utf-8")
    (carpeta / "robot.urdf").write_text(urdf.generar(robot["id"], clon["escala"]["alcance_m"], robot.get("fisica")), encoding="utf-8")
    (carpeta / "escena.usd").write_text(generar_escena.escena_usda(entorno_json), encoding="utf-8")
    return carpeta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot", required=True, help="id del catálogo, p. ej. leapting-mmr")
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--entorno", type=Path)
    ap.add_argument("--tarea", type=Path)
    a = ap.parse_args()
    print(escribir(a.robot, a.dir, a.entorno, a.tarea))


if __name__ == "__main__":
    main()
