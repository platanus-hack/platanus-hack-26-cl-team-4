"""Agentes de etapa. Cada uno recibe archivos del contrato y devuelve el suyo, ya validado.

Modo `fijo` (VIAZ_AGENTES=fijo): devuelven fixtures, para desarrollar el flujo sin gastar API.
Modo `claude`: llaman a la Claude API.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from .. import urdf
from ..esquemas import esquema, sin_campos
from .base import ErrorAgente, frames_de_videos, pedir_json, validado

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PROMPTS = Path(__file__).resolve().parent / "prompts"


def _prompt(nombre: str) -> str:
    """Instrucciones del agente. Viven en prompts/<nombre>.md (contrato: docs/agentes/)."""
    return (PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def _fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------- 1. Entorno ----------

SISTEMA_ENTORNO = _prompt("entorno")


def esquema_agente_entorno() -> dict:
    """Lo que devuelve el modelo: entorno.json sin los campos del orquestador.
    `confianza` va como lista porque structured outputs no acepta objetos con claves libres."""
    esq = sin_campos(esquema("entorno"), ["version", "videos", "escena_usd", "fondo_reconstruido_usd"])
    esq["properties"]["confianza"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["campo", "valor"],
        "properties": {"campo": {"type": "string"}, "valor": {"type": "number"}}}}
    return esq


def texto_entorno(proyecto: dict) -> str:
    return f"Planta: {proyecto['nombre']}\nDescripción del cliente: {proyecto['descripcion'] or '(sin descripción)'}"


def entorno(modo: str, modelo: str, proyecto: dict, frames: list[dict] | None) -> dict:
    if modo == "fijo":
        datos = _fixture("entorno")
    else:
        if not frames:
            raise ErrorAgente("el agente Entorno necesita al menos un video")
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_ENTORNO, esquema=esquema_agente_entorno(),
                           contenido=[*frames, {"type": "text", "text": texto_entorno(proyecto)}])
        datos["confianza"] = {c["campo"]: c["valor"] for c in datos["confianza"]}
    datos.update(version=1, videos=[v.rsplit("/", 1)[1] for v in proyecto["videos"]],
                 escena_usd="escena.usd", fondo_reconstruido_usd=None)
    return validado("entorno", datos)


# ---------- 2. Tarea ----------

SISTEMA_TAREA = _prompt("tarea")


def tarea(modo: str, modelo: str, proyecto: dict, entorno_json: dict, frames: list[dict] | None) -> dict:
    if modo == "fijo":
        datos = _fixture("tarea")
    else:
        esq = sin_campos(esquema("tarea"), ["version"])
        texto = (f"Descripción del cliente: {proyecto['descripcion'] or '(sin descripción)'}\n"
                 f"entorno.json:\n{json.dumps(entorno_json, ensure_ascii=False)}")
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_TAREA, esquema=esq,
                           contenido=[*(frames or []), {"type": "text", "text": texto}])
    datos["version"] = 1
    return validado("tarea", datos)


# ---------- 3. Robot ----------

SISTEMA_ROBOT = _prompt("robot")


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


def _specs_estimadas(r: dict) -> list[str]:
    """Specs de selección que el fabricante no publica. Las medidas `fisica.*` son del clon, no de la selección."""
    return [k for k in r.get("estimados", {}) if not k.startswith("fisica.")]


def _fallas(r: dict, entorno_json: dict) -> list[str]:
    """Criterios obligatorios del prompt de selección (prompts/robot.md)."""
    f = []
    necesario = alcance_necesario(entorno_json, r)
    if r["carga_util_kg"] < entorno_json["panel"]["peso_kg"]:
        f.append(f"carga útil de {r['carga_util_kg']} kg menor que el panel ({entorno_json['panel']['peso_kg']} kg)")
    if r["efector"] != "ventosa":
        f.append("no usa ventosa")
    if r["alcance_m"] < necesario:
        f.append(f"alcance de {r['alcance_m']} m menor que el necesario ({necesario} m)")
    if r["tipo"] == "brazo_fijo":
        f.append("brazo fijo: no se desplaza por el parque")
    if entorno_json["terreno"]["pendiente_grados"] > 10 and r["tipo"] != "vehiculo_con_brazo":
        f.append("la pendiente pide un vehículo con brazo")
    return f


def eleccion_por_reglas(entorno_json: dict, catalogo: dict[str, dict]) -> dict:
    """Modo fijo (sin LLM): mismos criterios del prompt, en el mismo orden. Determinista."""
    def clave(r):
        return (len(_fallas(r, entorno_json)), r["ficticio"], len(_specs_estimadas(r)),
                -min(r["carga_util_kg"] / entorno_json["panel"]["peso_kg"], 3), -r["alcance_m"])
    orden = sorted(catalogo.values(), key=clave)
    r = orden[0]
    fallas, necesario = _fallas(r, entorno_json), alcance_necesario(entorno_json, r)
    partes = [f"{r['nombre']} carga {r['carga_util_kg']} kg y el panel pesa {entorno_json['panel']['peso_kg']} kg",
              f"su alcance de {r['alcance_m']} m cubre los {necesario} m necesarios para dejar el panel sobre el tubo"
              if r["alcance_m"] >= necesario else f"su alcance de {r['alcance_m']} m no cubre los {necesario} m necesarios"]
    texto = ("No hay un robot que cumpla todo: " + "; ".join(fallas) + ". " if fallas else "") + \
        ("Lo elegimos porque " + " y ".join(partes) + ".")
    if _specs_estimadas(r):
        texto += f" Ojo: el fabricante no publica {', '.join(_specs_estimadas(r))}; esos valores son estimaciones."
    if r["ficticio"]:
        texto += " Es un robot de referencia ficticio."
    alternativas = []
    for o in orden[1:]:
        f = _fallas(o, entorno_json)
        motivo = ("; ".join(f) if f else "ficticio" if o["ficticio"] else
                  f"specs estimadas ({', '.join(_specs_estimadas(o))})" if _specs_estimadas(o) else "menor margen de carga y alcance")
        alternativas.append({"id": o["id"], "por_que_no": motivo})
    return {"id": r["id"], "justificacion": texto + " (Elección por reglas, sin LLM.)", "alternativas": alternativas}


def robot(modo: str, modelo: str, entorno_json: dict, tarea_json: dict, catalogo: dict[str, dict]) -> dict:
    ids = list(catalogo)
    if modo == "fijo":
        eleccion = eleccion_por_reglas(entorno_json, catalogo)
    else:
        esq = {
            "type": "object", "additionalProperties": False, "required": ["id", "justificacion", "alternativas"],
            "properties": {
                "id": {"enum": ids},
                "justificacion": {"type": "string"},
                "alternativas": esquema("robot")["properties"]["alternativas"],
            },
        }
        texto = (f"entorno.json:\n{json.dumps(entorno_json, ensure_ascii=False)}\n\n"
                 f"tarea.json:\n{json.dumps(tarea_json, ensure_ascii=False)}\n\n"
                 f"Catálogo:\n{json.dumps([{**r, 'alcance_necesario_m': alcance_necesario(entorno_json, r)} for r in catalogo.values()], ensure_ascii=False)}")
        eleccion = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=esq,
                              contenido=[{"type": "text", "text": texto}])
    if eleccion["id"] not in catalogo:
        raise ErrorAgente(f"el agente eligió un robot fuera del catálogo: {eleccion['id']}")
    # Las specs salen siempre del catálogo, nunca del modelo.
    datos = {**copy.deepcopy(catalogo[eleccion["id"]]),
             "justificacion": eleccion["justificacion"], "alternativas": eleccion["alternativas"]}
    return validado("robot", datos)


# ---------- 4. Clon ----------

def clon(robot_json: dict) -> tuple[dict, str]:
    """Determinista: arma el clon paramétrico desde las specs del robot. Devuelve (clon.json, robot.urdf)."""
    if robot_json["tipo"] != "base_movil_brazo":
        raise ErrorAgente(f"todavía no hay clon para robots tipo {robot_json['tipo']}")
    diferencias = ["geometría primitiva (cajas y cilindros), sin mallas del fabricante",
                   "vehículo con las medidas y la masa del fabricante; las orugas no giran y se mueve sin simular tracción"
                   if robot_json.get("fisica") else "base con 4 ruedas fijas; se mueve sin simular tracción",
                   "brazo genérico de 6 ejes escalado al alcance del robot real"]
    if robot_json["ficticio"]:
        diferencias.insert(0, "el robot de referencia es ficticio")
    datos = {
        "version": 1, "robot_id": robot_json["id"], "usd": None, "urdf": "robot.urdf",
        "piezas": {"base": "caja_4_ruedas", "brazo": "brazo_6_ejes", "efector": robot_json["efector"]},
        "escala": {"alcance_m": robot_json["alcance_m"], "carga_util_kg": robot_json["carga_util_kg"]},
        "geometria": urdf.geometria(robot_json["alcance_m"], robot_json.get("fisica")),
        "diferencias_con_real": diferencias,
        "validado_en_escena": False,
    }
    return validado("clon", datos), urdf.generar(robot_json["id"], robot_json["alcance_m"], robot_json.get("fisica"))


# ---------- 4b. Constructor del robot en Isaac Lab ----------

SISTEMA_CONSTRUCTOR = _prompt("constructor")


def esquema_agente_constructor(assets: dict) -> dict:
    """ensamblaje.json sin los campos que llena el código, con los assets del catálogo como enum."""
    esq = sin_campos(esquema("ensamblaje"), ["version", "robot_id"])
    esq = copy.deepcopy(esq)
    esq["properties"]["base"]["properties"]["asset"] = {"enum": sorted(assets["bases"])}
    esq["properties"]["brazo"]["properties"]["asset"] = {"enum": sorted(assets["brazos"])}
    esq["properties"]["efector"]["properties"]["asset"] = {"enum": sorted(assets["efectores"])}
    return esq


def constructor(modo: str, modelo: str, robot_json: dict, entorno_json: dict, tarea_json: dict, assets: dict,
                intento: int, problemas_previos: list[str] | None = None, previo: dict | None = None) -> dict:
    """Devuelve ensamblaje.json validado contra su esquema. Las reglas del robot real las revisa robot_cfg.problemas()."""
    from .. import robot_cfg as rc
    if modo == "fijo":
        datos = rc.ensamblaje_por_defecto(robot_json, assets)
    else:
        texto = (f"robot.json:\n{json.dumps(robot_json, ensure_ascii=False)}\n\n"
                 f"entorno.json:\n{json.dumps(entorno_json, ensure_ascii=False)}\n\n"
                 f"tarea.json:\n{json.dumps(tarea_json, ensure_ascii=False)}\n\n"
                 f"alcance_necesario_m: {alcance_necesario(entorno_json)}\n"
                 f"Reglas: alcance resultante = alcance del brazo × escala_alcance + largo del efector, "
                 f"±5 % del real; esfuerzo_max_nm ≥ (carga + masa del efector) × 9,81 × alcance × {rc.FACTOR_ESFUERZO}.\n\n"
                 f"Catálogo de assets:\n{json.dumps(assets, ensure_ascii=False)}\n\n"
                 f"Intento {intento} de 3.")
        if previo is not None:
            texto += (f"\n\nEnsamblaje del intento anterior:\n{json.dumps(previo, ensure_ascii=False)}"
                      f"\nProblemas:\n- " + "\n- ".join(problemas_previos or []))
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_CONSTRUCTOR, esquema=esquema_agente_constructor(assets),
                           contenido=[{"type": "text", "text": texto}])
    datos.update(version=1, robot_id=robot_json["id"])
    return validado("ensamblaje", datos)


__all__ = ["ErrorAgente", "entorno", "tarea", "robot", "clon", "constructor", "frames_de_videos"]
