"""Paso 7 de la selección v3: comparacion.json (contrato: docs/agentes/seleccion-robot.md §3).

El código ordena a los finalistas con una regla fija sobre el resultado de cada corrida hija. El LLM solo escribe
`explicacion` y nunca cambia el ranking.
"""
from __future__ import annotations

import json
import logging
from typing import NamedTuple, Sequence

from .agentes.base import ErrorAgente, pedir_json
from .agentes import PROMPTS
from .esquemas import validar

log = logging.getLogger("viaz.comparacion")

SISTEMA_COMPARACION = (PROMPTS / "comparacion.md").read_text(encoding="utf-8")

QUE_COMPARA = ("alcance", "tamaño", "masa", "carga útil", "velocidad de la base")
QUE_NO_COMPARA = (
    "motores y control del robot real: todos los clones usan un brazo de Isaac Lab escalado (ur10 o franka_panda)",
)
ESQUEMA_EXPLICACION = {"type": "object", "additionalProperties": False, "required": ["explicacion"],
                       "properties": {"explicacion": {"type": "string"}}}


class Hija(NamedTuple):
    robot: dict
    corrida_id: str
    resultado: dict | None
    clon: dict | None
    error: str | None


def fidelidad(hija: Hija) -> str:
    del_clon = (hija.clon or {}).get("fidelidad")
    if del_clon:
        return del_clon
    return "medido" if hija.robot.get("fisica") else "generico"


FIDELIDAD_EN_TEXTO = {"generico": "genérica", "medido": "medida", "verificado": "verificada"}


def _fila(hija: Hija, resultado: dict) -> dict:
    m = resultado["metricas"]
    nombre = {"nombre": hija.robot["nombre"]} if hija.robot.get("nombre") else {}
    return {"id": hija.robot["id"], **nombre, "corrida_id": hija.corrida_id, "tasa_exito": m["tasa_exito"],
            "ciclo_s": m["ciclo_promedio_s"] if m["tasa_exito"] > 0 else None, "fidelidad": fidelidad(hija)}


def _nombre(fila_o_robot: dict) -> str:
    return fila_o_robot.get("nombre") or fila_o_robot["id"]


def _orden(fila: dict) -> tuple:
    return (-fila["tasa_exito"], fila["ciclo_s"] is None, fila["ciclo_s"] or 0.0, fila["id"])


def ranking(hijas: Sequence[Hija]) -> list[dict]:
    filas = sorted((_fila(h, h.resultado) for h in hijas if h.error is None and h.resultado), key=_orden)
    return [{**f, "puesto": i} for i, f in enumerate(filas, start=1)]


def regla(condiciones: dict) -> str:
    return (f"Gana el robot con mayor porcentaje de éxito, con un error de hasta "
            f"{condiciones['tolerancia_pos_m'] * 100:g} cm y {condiciones['tolerancia_ang_grados']:g}°. "
            "Si empatan, gana el de menor tiempo de ciclo. Si siguen empatados, se ordenan por su código, "
            "en orden alfabético.")


def advertencias(hijas: Sequence[Hija], filas: list[dict], condiciones: dict) -> list[str]:
    avisos = [f"La corrida hija {h.corrida_id} de {_nombre(h.robot)} falló y quedó fuera del ranking: {h.error[:300]}"
              for h in hijas if h.error is not None]
    niveles = sorted({FIDELIDAD_EN_TEXTO[f["fidelidad"]] for f in filas})
    if len(niveles) > 1:
        avisos.append(f"Los clones tienen fidelidad distinta ({' y '.join(niveles)}): "
                      "la diferencia puede venir del clon.")
    if condiciones["semillas"] is None:
        avisos.append("El entrenamiento no fija semillas: parte de la diferencia entre finalistas puede venir del azar.")
    if any(h.resultado and h.resultado.get("fuente") == "simulado" for h in hijas):
        avisos.append("Métricas del entorno simulado, no de Isaac: no sirven para elegir un robot.")
    return avisos


def explicacion_fija(filas: list[dict], texto_regla: str) -> str:
    primero = filas[0]
    ciclo = f" y un ciclo de {primero['ciclo_s']:g} s" if primero["ciclo_s"] is not None else ""
    return (f"{_nombre(primero)} queda en el puesto 1 de {len(filas)} con {primero['tasa_exito']:.0%} de éxito{ciclo}. "
            f"Regla: {texto_regla}")


def comparar(hijas: Sequence[Hija], condiciones: dict) -> dict:
    filas = ranking(hijas)
    if not filas:
        raise ErrorAgente("fallaron las corridas de todos los finalistas: "
                          + "; ".join(f"{h.robot['id']}: {h.error}" for h in hijas)[:1500])
    texto_regla = regla(condiciones)
    return validar("comparacion", {
        "version": 1, "ganador": filas[0]["id"], "regla": texto_regla, "condiciones": dict(condiciones),
        "ranking": filas, "advertencias": advertencias(hijas, filas, condiciones),
        "que_compara": list(QUE_COMPARA), "que_no_compara": list(QUE_NO_COMPARA),
        "explicacion": explicacion_fija(filas, texto_regla),
    })


def explicar(modo: str, modelo: str, comp: dict) -> dict:
    """La explicación para el cliente. Dice si la escribió Claude o es la plantilla (problema 6)."""
    plantilla = {**comp, "fuente_explicacion": "plantilla"}
    if modo == "fijo":
        return plantilla
    sin_explicacion = {k: v for k, v in comp.items() if k not in ("explicacion", "fuente_explicacion")}
    try:
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_COMPARACION, esquema=ESQUEMA_EXPLICACION, effort="medium",
                           contenido=[{"type": "text", "text": json.dumps(sin_explicacion, ensure_ascii=False)}],
                           max_tokens=8000, etiqueta="comparacion")
        return validar("comparacion", {**comp, "explicacion": datos["explicacion"], "fuente_explicacion": "claude"})
    except Exception as e:
        log.warning("la explicación de la comparación falló, queda la plantilla: %s", e)
        return plantilla
