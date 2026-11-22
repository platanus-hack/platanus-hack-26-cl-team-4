"""Despachador de los comandos del entorno RL por tarea (RF-GEN-03). Sin Isaac hasta que corre el script.

    $ISAACLAB_SH -p sim/tareas.py <comando> --entorno E --tarea T --robot R [...]

Lee `tarea.json → tarea` y corre sim/<carpeta>/<comando>.py con los mismos argumentos. Cada carpeta cumple el
mismo contrato de archivos (docs/contrato-entorno-rl.md): el runner y el orquestador no saben qué tarea es.
Una tarea nueva agrega su carpeta aquí y su perfil en backend/viaz/agentes/perfiles.py (PerfilTarea.sim).
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parent
COMANDOS = ("entrenar", "evaluar", "grabar_clip", "validar_robot")
# Debe calzar con PerfilTarea.sim de backend/viaz/agentes/perfiles.py (lo revisa backend/tests/test_tareas_sim.py).
CARPETAS = {"instalar_panel": "rl", "animar_evento": "animar"}


def tarea_de(argv: list[str]) -> str:
    if "--tarea" not in argv:
        raise SystemExit("falta --tarea con la ruta de tarea.json")
    ruta = Path(argv[argv.index("--tarea") + 1])
    return json.loads(ruta.read_text(encoding="utf-8"))["tarea"]


def script(comando: str, tarea: str) -> Path:
    if comando not in COMANDOS:
        raise SystemExit(f"comando '{comando}' desconocido; comandos: {', '.join(COMANDOS)}")
    if tarea not in CARPETAS:
        raise SystemExit(f"la tarea '{tarea}' no tiene simulación; tareas con simulación: {', '.join(sorted(CARPETAS))}")
    return SIM / CARPETAS[tarea] / f"{comando}.py"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    comando, resto = sys.argv[1], sys.argv[2:]
    ruta = script(comando, tarea_de(resto))
    print(f"[tareas] {comando} → {ruta.relative_to(SIM)}", flush=True)
    sys.argv = [str(ruta), *resto]
    sys.path.insert(0, str(ruta.parent))
    runpy.run_path(str(ruta), run_name="__main__")


if __name__ == "__main__":
    main()
