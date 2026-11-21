"""Agentes de etapa. Cada uno recibe archivos del contrato y devuelve el suyo, ya validado.

Modo `fijo` (VIAZ_AGENTES=fijo): devuelven fixtures, para desarrollar el flujo sin gastar API.
Modo `claude`: llaman a la Claude API.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .. import urdf
from ..esquemas import esquema, sin_campos
from .base import ErrorAgente, frames_de_videos, pedir_json, validado

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------- 1. Entorno ----------

SISTEMA_ENTORNO = """Eres el agente Entorno de VIAZ. Analizas frames de video de una planta industrial
(por ahora, parques solares) y estimas los parámetros que hacen falta para generar su escena 3D.
Mide con referencias visibles: personas (~1,7 m), vehículos, paneles estándar (~2,3 × 1,1 m).
Si un dato no se ve, usa un valor típico de parques solares y bájale la confianza.
`confianza` lleva una entrada por dato estimado, con clave tipo "filas.separacion_m" y valor de 0 a 1."""


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

SISTEMA_TAREA = """Eres el agente Tarea de VIAZ. Con los frames de la planta, la descripción del cliente
y los parámetros del entorno, defines qué trabajo hará el robot y cómo se mide.
Por ahora la única tarea es "instalar_panel": el robot lleva una pila de paneles y los deja sobre la estructura.
El objetivo debe ser alcanzable en una demo corta (3 a 10 paneles)."""


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

SISTEMA_ROBOT = """Eres el agente Robot de VIAZ. Eliges, de un catálogo cerrado de robots reales,
el que mejor hace la tarea en esa planta. Compara carga útil contra el peso del panel, alcance contra
la altura y separación de la estructura, y el tipo de robot contra el terreno.
Solo puedes elegir ids del catálogo. Justifica con números del entorno y del robot.
En `alternativas` pon los otros robots del catálogo y por qué no los elegiste.
Si un robot es ficticio, dilo en la justificación."""


def robot(modo: str, modelo: str, entorno_json: dict, tarea_json: dict, catalogo: dict[str, dict]) -> dict:
    ids = list(catalogo)
    if modo == "fijo":
        eleccion = {"id": ids[0], "justificacion": "Modo fijo: primer robot del catálogo, sin análisis.",
                    "alternativas": [{"id": i, "por_que_no": "modo fijo"} for i in ids[1:]]}
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
                 f"Catálogo:\n{json.dumps(list(catalogo.values()), ensure_ascii=False)}")
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
                   "base con 4 ruedas fijas; se mueve sin simular tracción",
                   "brazo genérico de 6 ejes escalado al alcance del robot real"]
    if robot_json["ficticio"]:
        diferencias.insert(0, "el robot de referencia es ficticio")
    datos = {
        "version": 1, "robot_id": robot_json["id"], "usd": None, "urdf": "robot.urdf",
        "piezas": {"base": "caja_4_ruedas", "brazo": "brazo_6_ejes", "efector": robot_json["efector"]},
        "escala": {"alcance_m": robot_json["alcance_m"], "carga_util_kg": robot_json["carga_util_kg"]},
        "geometria": urdf.geometria(robot_json["alcance_m"]),
        "diferencias_con_real": diferencias,
        "validado_en_escena": False,
    }
    return validado("clon", datos), urdf.generar(robot_json["id"], robot_json["alcance_m"])


__all__ = ["ErrorAgente", "entorno", "tarea", "robot", "clon", "frames_de_videos"]
