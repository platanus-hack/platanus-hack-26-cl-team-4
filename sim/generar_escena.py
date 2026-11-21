"""Genera escena.usd (texto USDA) desde entorno.json: la parte ESTÁTICA de la planta. Python puro.

    python sim/generar_escena.py --dir <carpeta con entorno.json>

Qué lleva: suelo, tubos de torsión y postes, todo con colisión y material de fricción.
Qué NO lleva: paneles ni robot (son dinámicos; los agrega sim/viaz_escena.py en Isaac Lab),
ni PhysicsScene (la crea Isaac Lab con los parámetros de sim/fisica.py).
Los objetos estáticos no llevan masa: un colisionador sin RigidBodyAPI es fijo e inamovible.

Reglas (iguales a web/lib/escena.ts): Z arriba, metros. Fila i: tubo en y = -i * separacion,
a altura_m, de x = 0 a x = largo_m, con postes cada 7 m.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fisica  # noqa: E402

POSTE_CADA_M = 7.0
TUBO_LADO_M = 0.1


def _material(nombre: str) -> str:
    m = fisica.material(nombre)
    return f'''
        def Material "{nombre.capitalize()}" (
            prepend apiSchemas = ["PhysicsMaterialAPI"]
        )
        {{
            float physics:staticFriction = {m["estatica"]}
            float physics:dynamicFriction = {m["dinamica"]}
            float physics:restitution = {m["restitucion"]}
        }}'''


def _cubo(nombre: str, centro, escala, color, material: str) -> str:
    c = ", ".join(f"{v:.4f}" for v in centro)
    s = ", ".join(f"{v:.4f}" for v in escala)
    col = ", ".join(f"{v:.3f}" for v in color)
    return f'''
    def Cube "{nombre}" (
        prepend apiSchemas = ["PhysicsCollisionAPI", "MaterialBindingAPI"]
    )
    {{
        double size = 1
        double3 xformOp:translate = ({c})
        float3 xformOp:scale = ({s})
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        color3f[] primvars:displayColor = [({col})]
        rel material:binding:physics = </World/Materiales/{material.capitalize()}>
    }}'''


def escena_usda(entorno: dict) -> str:
    f, e = entorno["filas"], entorno["estructura"]
    largo, sep, alto = f["largo_m"], f["separacion_m"], e["altura_m"]
    # Suelo plano en z = 0. La pendiente de entorno.json todavía NO se modela: la base del robot
    # se mueve a z = 0 y el plan supone suelo plano. [Por hacer] suelo inclinado + base que siga el terreno.
    partes = [_cubo("Suelo", (largo / 2, -sep * (f["cantidad"] - 1) / 2, -0.05),
                    (largo + 20, sep * f["cantidad"] + 20, 0.1), (0.62, 0.52, 0.40), "suelo")]
    for i in range(f["cantidad"]):
        y = -i * sep
        partes.append(_cubo(f"Fila{i}_Tubo", (largo / 2, y, alto), (largo, TUBO_LADO_M, TUBO_LADO_M),
                            (0.55, 0.57, 0.6), "acero"))
        for j in range(int(largo // POSTE_CADA_M) + 1):
            x = min(j * POSTE_CADA_M, largo)
            partes.append(_cubo(f"Fila{i}_Poste{j}", (x, y, (alto - TUBO_LADO_M / 2) / 2),
                                (0.15, 0.15, alto - TUBO_LADO_M / 2), (0.45, 0.47, 0.5), "acero"))
    materiales = "".join(_material(n) for n in ("suelo", "acero"))
    cuerpo = "".join(partes)
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    kilogramsPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Scope "Materiales"
    {{{materiales}
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
