"""Agente constructor: catálogo de assets, reglas y plantilla de robot_cfg.py (docs/agentes/constructor-robot.md).

El agente devuelve ensamblaje.json (piezas + parámetros). Este módulo:
1. valida el ensamblaje contra las specs del robot real (el agente no puede cambiarlas),
2. genera robot_cfg.py: el diccionario PARAMETROS (interfaz estable con el entorno RL) y una
   función crear_articulacion_cfg() para Isaac Lab, SIN PROBAR EN ISAAC,
3. arma clon.json con la misma geometría que urdf.py y sim/plan.py.
"""
from __future__ import annotations

import json
import math
import pprint
from pathlib import Path

from . import urdf

ASSETS = Path(__file__).resolve().parent / "catalogo" / "assets_isaaclab.json"
TOLERANCIA_ALCANCE = 0.05   # ±5 % respecto del robot real
FACTOR_ESFUERZO = 1.2       # margen sobre el torque de sostener la carga con el brazo estirado
DIFERENCIAS_FIJAS = [
    "la navegación de la base es programada; el aprendizaje por refuerzo controla el brazo",
    "geometría aproximada con piezas de Isaac Lab, sin las mallas del fabricante",
]


def cargar_assets(ruta: Path = ASSETS) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def alcance_resultante(ens: dict, assets: dict) -> float:
    brazo = assets["brazos"][ens["brazo"]["asset"]]
    efector = assets["efectores"][ens["efector"]["asset"]]
    return round(brazo["alcance_m"] * ens["brazo"]["escala_alcance"] + efector["largo_m"], 3)


def esfuerzo_minimo(carga_kg: float, efector_kg: float, alcance_m: float) -> float:
    """Torque (N·m) para sostener la carga y el efector con el brazo estirado, con margen."""
    return round((carga_kg + efector_kg) * 9.81 * alcance_m * FACTOR_ESFUERZO, 1)


def problemas(ens: dict, robot: dict, assets: dict, alcance_necesario_m: float) -> list[str]:
    """Reglas del contrato (§4). Cada problema es una oración con números: el agente la lee para corregir."""
    p: list[str] = []
    for tipo, clave in (("bases", "base"), ("brazos", "brazo"), ("efectores", "efector")):
        if ens[clave]["asset"] not in assets[tipo]:
            p.append(f"{clave} '{ens[clave]['asset']}' no está en el catálogo de assets; opciones: {sorted(assets[tipo])}")
    if p:
        return p
    efector = assets["efectores"][ens["efector"]["asset"]]
    if assets["bases"][ens["base"]["asset"]]["tipo"] != "movil":
        p.append("la base debe ser móvil (decisión del equipo)")
    if ens["brazo"]["asset"] not in efector["para"]:
        p.append(f"el efector '{ens['efector']['asset']}' no calza con el brazo '{ens['brazo']['asset']}'")
    if robot.get("efector") == "ventosa" and efector["tipo"] != "ventosa":
        p.append("el robot real usa ventosa; elige un efector tipo ventosa")
    alc = alcance_resultante(ens, assets)
    if abs(alc - robot["alcance_m"]) > TOLERANCIA_ALCANCE * robot["alcance_m"]:
        p.append(f"alcance resultante {alc} m difiere más de 5 % del robot real ({robot['alcance_m']} m); ajusta escala_alcance")
    if alc < alcance_necesario_m:
        p.append(f"alcance resultante {alc} m menor que el necesario ({alcance_necesario_m} m)")
    if ens["carga_util_kg"] != robot["carga_util_kg"]:
        p.append(f"carga_util_kg debe ser la del robot real ({robot['carga_util_kg']} kg), no {ens['carga_util_kg']}")
    minimo = esfuerzo_minimo(robot["carga_util_kg"], efector["masa_kg"], alc)
    if ens["brazo"]["esfuerzo_max_nm"] < minimo:
        p.append(f"esfuerzo_max_nm {ens['brazo']['esfuerzo_max_nm']} no sostiene la carga útil; mínimo {minimo} N·m")
    return p


def ensamblaje_por_defecto(robot: dict, assets: dict) -> dict:
    """Respuesta determinista (modo fijo): UR10 con ventosa larga sobre la base móvil simple, escalado al real."""
    brazo, efector = assets["brazos"]["ur10"], assets["efectores"]["ventosa_larga"]
    escala = round((robot["alcance_m"] - efector["largo_m"]) / brazo["alcance_m"], 3)
    alc = round(brazo["alcance_m"] * escala + efector["largo_m"], 3)
    return {
        "version": 1, "robot_id": robot["id"],
        "base": {"asset": "base_movil_simple", "altura_cubierta_m": assets["bases"]["base_movil_simple"]["altura_cubierta_m"]},
        "brazo": {"asset": "ur10", "escala_alcance": escala,
                  "esfuerzo_max_nm": math.ceil(esfuerzo_minimo(robot["carga_util_kg"], efector["masa_kg"], alc))},
        "efector": {"asset": "ventosa_larga"},
        "carga_util_kg": robot["carga_util_kg"], "velocidad_max_rad_s": 2.0,
        "diferencias_con_real": [f"brazo UR10 escalado ×{escala} para igualar el alcance de {robot['alcance_m']} m",
                                 f"límites de esfuerzo subidos a {math.ceil(esfuerzo_minimo(robot['carga_util_kg'], efector['masa_kg'], alc))} N·m para la carga útil de {robot['carga_util_kg']} kg"],
        "razonamiento": "Modo fijo: UR10 con ventosa larga, la combinación con tareas de ejemplo en Isaac Lab, escalada al robot real.",
    }


def parametros(ens: dict, assets: dict) -> dict:
    return {
        "robot_id": ens["robot_id"], "base": ens["base"], "brazo": ens["brazo"], "efector": ens["efector"],
        "alcance_m": alcance_resultante(ens, assets), "carga_util_kg": float(ens["carga_util_kg"]),
        "velocidad_max_rad_s": ens["velocidad_max_rad_s"],
        "articulaciones": list(urdf.ARTICULACIONES),
        "articulaciones_asset": assets["brazos"][ens["brazo"]["asset"]]["articulaciones"],
        "isaaclab_cfg": assets["brazos"][ens["brazo"]["asset"]].get("isaaclab_cfg"),
    }


def generar(ens: dict, assets: dict) -> str:
    """Texto de robot_cfg.py. PARAMETROS es la interfaz estable (docs/contrato-entorno-rl.md §7)."""
    params = pprint.pformat(parametros(ens, assets), sort_dicts=False, width=110)
    return f'''"""robot_cfg.py generado por VIAZ desde ensamblaje.json. No editar a mano.

PARAMETROS: interfaz estable con el entorno RL (docs/contrato-entorno-rl.md §7).
crear_articulacion_cfg(): SIN PROBAR EN ISAAC. Si no calza con su entorno, usen solo PARAMETROS.
"""

PARAMETROS = {params}


def crear_articulacion_cfg():
    """ArticulationCfg de Isaac Lab desde el asset del brazo, escalado y con límites de esfuerzo nuevos."""
    import importlib

    ref = PARAMETROS["isaaclab_cfg"]
    base_cfg = getattr(importlib.import_module(ref["modulo"]), ref["nombre"])
    cfg = base_cfg.copy()
    s = PARAMETROS["brazo"]["escala_alcance"]
    cfg.spawn.scale = (s, s, s)
    for actuador in cfg.actuators.values():
        for nombre in ("effort_limit", "effort_limit_sim"):
            if hasattr(actuador, nombre):
                setattr(actuador, nombre, PARAMETROS["brazo"]["esfuerzo_max_nm"])
        for nombre in ("velocity_limit", "velocity_limit_sim"):
            if hasattr(actuador, nombre):
                setattr(actuador, nombre, PARAMETROS["velocidad_max_rad_s"])
    return cfg
'''


def clon(ens: dict, robot: dict, assets: dict, intentos: int) -> dict:
    """clon.json del robot construido. La geometría es la de urdf.py para que plan.py y el visor calcen."""
    alc = alcance_resultante(ens, assets)
    return {
        "version": 1, "robot_id": robot["id"], "usd": None, "urdf": "robot.urdf",
        "piezas": {"base": ens["base"]["asset"], "brazo": ens["brazo"]["asset"], "efector": ens["efector"]["asset"]},
        "escala": {"alcance_m": alc, "carga_util_kg": float(ens["carga_util_kg"])},
        "geometria": urdf.geometria(alc, robot.get("fisica")),
        "diferencias_con_real": [*(["el robot de referencia es ficticio"] if robot.get("ficticio") else []),
                                 *ens["diferencias_con_real"], *DIFERENCIAS_FIJAS],
        "validado_en_escena": False,
        "construccion": {"metodo": "agente", "intentos": intentos, "ensamblaje": "ensamblaje.json", "robot_cfg": "robot_cfg.py"},
    }
