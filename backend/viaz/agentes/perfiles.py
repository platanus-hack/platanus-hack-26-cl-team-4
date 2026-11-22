"""Paso 1 de la selección v3: perfiles de dominio. Traducen entorno.json y tarea.json a requisitos.json.

Un perfil es una función pura (entorno, tarea, fichas) -> requisitos. La selección solo lee requisitos.json:
el vocabulario del dominio (panel, tubo, parque) vive aquí y en ningún otro paso.
"""
from __future__ import annotations

import math
from typing import Callable

from .. import urdf
from .base import ErrorAgente, validado
from .seleccion import preferencias

Perfil = Callable[[dict, dict, list[dict]], dict]


# ---------- Perfil solar ----------

PENDIENTE_MAX_BASE_MOVIL_GRADOS = 10
ORDEN_PREFERENCIAS_SOLAR = ("real_sobre_ficticio", "menos_specs_estimadas", "mayor_margen_carga_alcance",
                            "mayor_velocidad_base")


def alcance_necesario(entorno_json: dict, robot_json: dict | None = None) -> float:
    """Alcance mínimo (m) para dejar un panel sobre el tubo de la fila 0 desde el pasillo.
    Misma geometría que urdf.py y sim/plan.py: hombro sobre la base, muñeca de largo fijo.
    Depende del robot: un vehículo más ancho queda más lejos del tubo y uno más alto sube el hombro."""
    v = urdf.vehiculo((robot_json or {}).get("fisica"))
    hombro_z = v.cubierta_z + urdf.HOMBRO_ALTO
    muneca = sum(urdf.MUNECA)
    d = entorno_json["panel"]["largo_m"] / 2 + v.ancho / 2 + 0.06   # sim/plan.py: distancia_pasillo
    dz = entorno_json["estructura"]["altura_m"] + 0.05 + 0.04 + muneca - hombro_z  # tubo + panel + muñeca
    return round(math.ceil((math.hypot(d, dz) + muneca) * 100) / 100 + 0.05, 2)  # +5 cm de margen: justo en el límite, la IK falla


def _tipos_solares(pendiente_grados: float) -> list[str]:
    if pendiente_grados > PENDIENTE_MAX_BASE_MOVIL_GRADOS:
        return ["vehiculo_con_brazo"]
    return ["base_movil_brazo", "vehiculo_con_brazo"]   # explícito: un humanoide no sirve en el perfil solar


def _numero(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def advertencias_de_confianza(confianza: dict[str, float]) -> list[str]:
    return [f"{campo} tiene confianza {_numero(valor)}: es un valor supuesto, no medido"
            for campo, valor in confianza.items() if valor < 1]


def perfil_solar(entorno_json: dict, tarea_json: dict, fichas: list[dict]) -> dict:
    panel = entorno_json["panel"]
    pendiente = entorno_json["terreno"]["pendiente_grados"]
    return {
        "version": 1,
        "dominio": "solar",
        "tarea": tarea_json["tarea"],
        "objeto": {"nombre": "panel", "largo_m": panel["largo_m"], "ancho_m": panel["ancho_m"],
                   "peso_kg": panel["peso_kg"]},
        "carga_min_kg": panel["peso_kg"],
        "efectores_aceptados": ["ventosa"],
        "tipos_aceptados": _tipos_solares(pendiente),
        "movilidad": "movil",
        "pendiente_grados": pendiente,
        "por_robot": [{"id": f["id"], "alcance_min_m": alcance_necesario(entorno_json, f)} for f in fichas],
        "preferencias": preferencias(ORDEN_PREFERENCIAS_SOLAR),
        "advertencias": advertencias_de_confianza(entorno_json.get("confianza") or {}),
    }


# ---------- Registro ----------

PERFILES: dict[str, Perfil] = {"solar": perfil_solar}
DOMINIO_POR_TIPO_DE_ENTORNO = {"parque_solar": "solar"}


def requisitos(entorno_json: dict, tarea_json: dict, fichas: list[dict]) -> dict:
    """requisitos.json validado, con el perfil que corresponde a entorno.tipo."""
    tipo = str(entorno_json.get("tipo"))
    dominio = DOMINIO_POR_TIPO_DE_ENTORNO.get(tipo)
    if dominio is None:
        raise ErrorAgente(f"no hay perfil de dominio para entornos tipo '{tipo}'. "
                          f"Tipos con perfil: {', '.join(sorted(DOMINIO_POR_TIPO_DE_ENTORNO))}")
    return validado("requisitos", PERFILES[dominio](entorno_json, tarea_json, fichas))
