"""Valida el clon en la escena con Isaac Sim (headless). SIN PROBAR EN ISAAC: verificar en el pod.

    $ISAAC_PYTHON sim/validar_clon.py --dir <carpeta>

Entradas: entorno.json, tarea.json (opcional), clon.json, robot.urdf, escena.usd. Salida: validacion.json.
Revisa: la importación, que estén las 6 articulaciones del contrato y el alcance del plan (sim/plan.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402

ARTICULACIONES = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"]
TAREA_MINIMA = {"objetivo": {"cantidad": 1}, "pila_paneles": {"cantidad": 1}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    a = ap.parse_args()
    leer = lambda n: json.loads((a.dir / n).read_text(encoding="utf-8"))  # noqa: E731
    entorno, clon = leer("entorno.json"), leer("clon.json")
    tarea = leer("tarea.json") if (a.dir / "tarea.json").exists() else TAREA_MINIMA

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    problemas: list[str] = []
    try:
        import isaac_comun
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleArticulation

        isaac_comun.abrir_escena(a.dir / "escena.usd")
        world = World(stage_units_in_meters=1.0)
        ruta = isaac_comun.importar_urdf(a.dir / "robot.urdf")
        robot = world.scene.add(SingleArticulation(prim_path=ruta, name="robot"))
        world.reset()
        faltan = [j for j in ARTICULACIONES if j not in robot.dof_names]
        if faltan:
            problemas.append(f"faltan articulaciones en el clon importado: {faltan}")
        for _ in range(30):
            world.step(render=False)
    except Exception as e:  # el error de Isaac va a validacion.json para que el orquestador lo muestre
        problemas.append(f"Isaac: {type(e).__name__}: {e}")
    finally:
        app.close()

    plano = plan.validar(entorno, tarea, clon)
    problemas += plano["problemas"]
    salida = {"ok": not problemas, "problemas": problemas, "fuente": "isaac",
              "paneles_planificados": plano["paneles_planificados"]}
    (a.dir / "validacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False))


if __name__ == "__main__":
    main()
