"""Genera escena.usd (texto USDA) desde entorno.json. Python puro: corre con o sin Isaac.

    python sim/generar_escena.py --dir <carpeta con entorno.json>

Reglas (iguales a web/lib/escena.ts): Z arriba, metros. Fila i: tubo de torsión en y = -i * separacion,
a altura_m, de x = 0 a x = largo_m, con postes cada 7 m. Todo con colisión.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

POSTE_CADA_M = 7.0


def _cubo(nombre: str, centro, escala, color) -> str:
    c = ", ".join(f"{v:.4f}" for v in centro)
    s = ", ".join(f"{v:.4f}" for v in escala)
    col = ", ".join(f"{v:.3f}" for v in color)
    return f'''
    def Cube "{nombre}" (
        prepend apiSchemas = ["PhysicsCollisionAPI"]
    )
    {{
        double size = 1
        double3 xformOp:translate = ({c})
        float3 xformOp:scale = ({s})
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        color3f[] primvars:displayColor = [({col})]
    }}'''


def escena_usda(entorno: dict) -> str:
    f, e = entorno["filas"], entorno["estructura"]
    largo, sep, alto = f["largo_m"], f["separacion_m"], e["altura_m"]
    partes = [_cubo("Suelo", (largo / 2, -sep * (f["cantidad"] - 1) / 2, -0.05),
                    (largo + 20, sep * f["cantidad"] + 20, 0.1), (0.62, 0.52, 0.40))]
    for i in range(f["cantidad"]):
        y = -i * sep
        partes.append(_cubo(f"Fila{i}_Tubo", (largo / 2, y, alto), (largo, 0.1, 0.1), (0.55, 0.57, 0.6)))
        n_postes = int(largo // POSTE_CADA_M) + 1
        for j in range(n_postes):
            x = min(j * POSTE_CADA_M, largo)
            partes.append(_cubo(f"Fila{i}_Poste{j}", (x, y, alto / 2), (0.15, 0.15, alto), (0.45, 0.47, 0.5)))
    cuerpo = "".join(partes)
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def PhysicsScene "physicsScene"
    {{
        vector3f physics:gravityDirection = (0, 0, -1)
        float physics:gravityMagnitude = 9.81
    }}

    def Xform "Planta"
    {{{cuerpo}
    }}
}}
'''


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    a = ap.parse_args()
    entorno = json.loads((a.dir / "entorno.json").read_text(encoding="utf-8"))
    (a.dir / "escena.usd").write_text(escena_usda(entorno), encoding="utf-8")
    print(f"escena.usd: {entorno['filas']['cantidad']} filas de {entorno['filas']['largo_m']} m")


if __name__ == "__main__":
    main()
