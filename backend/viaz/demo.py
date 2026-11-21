"""Genera la corrida del demo que la web muestra sin backend (RF-WEB-08).

    cd backend && python -m viaz.demo --salida ../web/public/demo

Corre el flujo completo sin servicios externos: agentes en modo fijo, clon paramétrico y el plan de
sim/plan.py (trayectoria sintética, sin física). Escribe en --salida los archivos del contrato.

Cuando el pod entregue resultados reales de Isaac Lab, se copian en web/public/demo/ encima de estos:
resultado.json (con `evaluacion` y `entrenamiento`), trayectoria.json, video.mp4 y entrenamiento_rapido.mp4.
La web los muestra apenas existan.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import agentes, catalogo
from .esquemas import validar

RAIZ = Path(__file__).resolve().parents[2]


def generar(salida: Path) -> dict:
    sys.path.insert(0, str(RAIZ / "sim"))
    import plan  # noqa: E402  (sim/plan.py, Python puro)

    proyecto = {"nombre": "Parque solar de demostración",
                "descripcion": "Instalación de paneles en trackers de un eje", "videos": []}
    entorno = agentes.entorno("fijo", "", proyecto, None)
    tarea = agentes.tarea("fijo", "", proyecto, entorno, None)
    robots = catalogo.cargar()
    robot = agentes.robot("fijo", "", entorno, tarea, robots)
    # En modo fijo el agente no justifica. Para el demo, la justificación sale solo de los datos.
    p = entorno["panel"]
    otros = len(robots) - 1
    es = lambda x: f"{x:g}".replace(".", ",")  # noqa: E731  coma decimal
    robot["justificacion"] = (
        f"Su carga útil de {es(robot['carga_util_kg'])} kg supera los {es(p['peso_kg'])} kg de cada panel, y su "
        f"alcance de {es(robot['alcance_m'])} m llega al tubo desde el pasillo. "
        + ("Es el único robot del catálogo por ahora." if otros == 0 else f"Se comparó con {otros} robots más del catálogo.")
    )
    clon, urdf_txt = agentes.clon(robot)
    validacion = plan.validar(entorno, tarea, clon)
    if not validacion["ok"]:
        raise SystemExit(f"el clon no pasa la validación: {validacion['problemas']}")
    clon["validado_en_escena"] = True
    trayectoria = plan.generar(entorno, tarea, clon)
    resultado = plan.resultado_simulado(trayectoria)

    archivos = {"entorno.json": entorno, "tarea.json": tarea, "robot.json": robot, "clon.json": clon,
                "trayectoria.json": trayectoria, "resultado.json": resultado}
    for nombre, datos in archivos.items():
        validar(nombre.removesuffix(".json"), datos)

    # LF siempre (newline="\n"): el demo va versionado y así es idéntico en Windows, Mac y CI.
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, datos in archivos.items():
        sangria = None if nombre == "trayectoria.json" else 2
        (salida / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=sangria),
                                     encoding="utf-8", newline="\n")
    (salida / "robot.urdf").write_text(urdf_txt, encoding="utf-8", newline="\n")
    meta = {"generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "origen": "python -m viaz.demo (agentes fijos + plan sintético)",
            "archivos": sorted([*archivos, "robot.urdf"])}
    (salida / "corrida.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8", newline="\n")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, default=RAIZ / "web" / "public" / "demo")
    a = ap.parse_args()
    meta = generar(a.salida)
    print(f"demo en {a.salida}: {', '.join(meta['archivos'])}")


if __name__ == "__main__":
    main()
