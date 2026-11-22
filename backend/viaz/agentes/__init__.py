"""Agentes de etapa. Cada uno recibe archivos del contrato y devuelve el suyo, ya validado.

Modo `fijo` (VIAZ_AGENTES=fijo): devuelven fixtures, para desarrollar el flujo sin gastar API.
Modo `claude`: llaman a la Claude API.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import NamedTuple

from .. import urdf
from ..config import TOPE_FINALISTAS, validar_max_finalistas
from ..esquemas import esquema, sin_campos
from . import perfiles, seleccion
from .base import ErrorAgente, frames_de_videos, pedir_json, validado
from .perfiles import alcance_necesario

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PROMPTS = Path(__file__).resolve().parent / "prompts"


def _prompt(nombre: str) -> str:
    """Instrucciones del agente. Viven en prompts/<nombre>.md (contrato: docs/agentes/)."""
    return (PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def _fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------- 1. Entorno ----------

SISTEMA_ENTORNO = _prompt("entorno")
# Campos de entorno.json que sim/medir_entorno.py puede medir en los videos (medidas_entorno.json).
CAMPOS_MEDIBLES = ("filas.cantidad", "filas.separacion_m", "filas.largo_m", "estructura.tipo", "estructura.altura_m",
                   "estructura.inclinacion_grados", "panel.largo_m", "panel.ancho_m", "terreno.pendiente_grados")
CONFIANZA_MIN_MEDIDA = 0.4      # bajo esto la medida no manda: el agente decide (y lo anota)
CONFIANZA_MAX_ESTIMADA = 0.7    # un dato que nadie midió no pasa de esta confianza

# Perfiles: bloques extra que solo existen para un tipo de espacio. El agente mapea cualquier espacio (sala,
# bodega, taller...); la medición 3D (sim/medir_geometria.py) y las etapas Tarea → Inteligencia todavía solo
# saben trabajar con parque_solar (sim/plan.py, urdf.py, web).
PERFILES = {"parque_solar": ("filas", "estructura", "panel")}
TIPOS_CON_PIPELINE = {"parque_solar"}


def esquema_agente_entorno() -> dict:
    """Lo que devuelve el modelo: entorno.json sin los campos del orquestador, más sus ajustes a las medidas.
    - `confianza` va como lista porque structured outputs no acepta objetos con claves libres.
    - Los bloques de perfil (filas, estructura, panel) van siempre, pero aceptan null.
    - Sin if/then/else: la API no los acepta; la regla de perfiles se valida en local."""
    esq = sin_campos(esquema("entorno"), ["version", "videos", "escena_usd", "fondo_reconstruido_usd", "mediciones"])
    for k in ("if", "then", "else"):
        esq.pop(k, None)
    for campos in PERFILES.values():
        for c in campos:
            esq["properties"][c] = {"anyOf": [esq["properties"][c], {"type": "null"}]}
            esq["required"].append(c)
    # La fricción del suelo no se ve en un video: la escribe el equipo o sale del tipo de suelo (sim/fisica.py).
    esq["properties"]["terreno"]["properties"].pop("friccion", None)
    esq["properties"]["confianza"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["campo", "valor"],
        "properties": {"campo": {"type": "string"}, "valor": {"type": "number"}}}}
    # Cada dato que el agente deja distinto de lo medido lleva su razón. Sin razón, el código vuelve a lo medido.
    esq["properties"]["ajustes"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["campo", "razon"],
        "properties": {"campo": {"enum": list(CAMPOS_MEDIBLES)}, "razon": {"type": "string"}}}}
    esq["required"] = [*esq["required"], "ajustes"]
    return esq


def texto_entorno(proyecto: dict, medidas: dict | None = None) -> str:
    texto = f"Espacio: {proyecto['nombre']}\nDescripción del cliente: {proyecto['descripcion'] or '(sin descripción)'}"
    if medidas and medidas.get("disponible"):
        texto += ("\n\nmedidas_entorno.json (medido en los videos con una reconstrucción 3D métrica; "
                  "la imagen cenital muestra la nube y las filas encontradas):\n" + json.dumps(medidas, ensure_ascii=False))
    elif medidas:
        texto += f"\n\nLa medición 3D falló: {medidas.get('error', 'sin detalle')}. Estima todo desde los frames."
    return texto


def _leer(datos: dict, campo: str):
    a, b = campo.split(".")
    return datos[a][b]


def _poner(datos: dict, campo: str, valor) -> None:
    a, b = campo.split(".")
    datos[a][b] = int(valor) if campo == "filas.cantidad" else valor


def _distinto(campo: str, final, medida: dict) -> bool:
    if isinstance(medida["valor"], str) or campo == "filas.cantidad":
        return final != medida["valor"]
    return abs(float(final) - float(medida["valor"])) > max(float(medida["error"]), 1e-6)


def aplicar_medidas(datos: dict, medidas: dict | None, ajustes: list[dict] | None = None) -> dict:
    """Las medidas mandan sobre lo que estimó el agente, salvo los ajustes con razón. Calcula la confianza.

    datos: entorno.json del agente (o el fixture en modo fijo), con `confianza` como objeto.
    Devuelve datos con `mediciones` (qué se midió y qué se ajustó). Sin medidas, solo limita la confianza.
    """
    confianza = dict(datos.get("confianza") or {})
    # Las medidas 3D son del perfil parque_solar (filas, estructura, panel). En otro tipo no aplican.
    if datos.get("tipo") != "parque_solar":
        medidas = None
    if not medidas or not medidas.get("disponible"):
        datos["confianza"] = {k: min(v, CONFIANZA_MAX_ESTIMADA) for k, v in confianza.items()}
        return datos
    razones = {a["campo"]: a["razon"].strip() for a in (ajustes or []) if a.get("razon", "").strip()}
    medidos, aplicados, avisos = [], [], list(medidas.get("avisos", []))
    for campo, m in medidas["campos"].items():
        if campo not in CAMPOS_MEDIBLES or m.get("confianza", 0) < CONFIANZA_MIN_MEDIDA:
            continue
        final = _leer(datos, campo)
        if _distinto(campo, final, m):
            if campo in razones:
                aplicados.append({"campo": campo, "medido": m["valor"], "final": final, "razon": razones[campo]})
                confianza[campo] = min(confianza.get(campo, 0.5), CONFIANZA_MAX_ESTIMADA)
                continue
            if ajustes is not None:   # el agente lo cambió sin decir por qué
                avisos.append(f"{campo}: el agente propuso {final} sin razón; se usa lo medido ({m['valor']})")
        _poner(datos, campo, m["valor"])
        medidos.append(campo)
        confianza[campo] = m["confianza"]
    for campo, v in confianza.items():
        if campo not in medidos:
            confianza[campo] = min(v, CONFIANZA_MAX_ESTIMADA)
    datos["confianza"] = confianza
    datos["mediciones"] = {"fuente": medidas["fuente"], "medidos": medidos, "ajustes": aplicados, "avisos": avisos}
    return datos


def normalizar_entorno(datos: dict) -> dict:
    """Respuesta del modelo → forma del contrato: confianza como objeto y sin perfiles que no aplican."""
    datos = copy.deepcopy(datos)
    if isinstance(datos.get("confianza"), list):
        datos["confianza"] = {c["campo"]: c["valor"] for c in datos["confianza"]}
    propios = PERFILES.get(datos.get("tipo"), ())
    for campos in PERFILES.values():
        for c in campos:
            if c not in propios or datos.get(c) is None:
                datos.pop(c, None)
    return datos


def entorno(modo: str, modelo: str, proyecto: dict, frames: list[dict] | None,
            medidas: dict | None = None, vista_png: bytes | None = None) -> dict:
    """entorno.json del proyecto. Con medidas (sim/medir_entorno.py), los datos medidos mandan: el agente revisa,
    completa lo que no se pudo medir y solo cambia una medida si da una razón visible en los frames."""
    if modo == "fijo":
        datos = aplicar_medidas(_fixture("entorno"), medidas)
    else:
        if not frames:
            raise ErrorAgente("el agente Entorno necesita al menos un video")
        contenido = list(frames)
        if vista_png:
            contenido.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                          "data": base64.b64encode(vista_png).decode()}})
        contenido.append({"type": "text", "text": texto_entorno(proyecto, medidas)})
        datos = normalizar_entorno(pedir_json(modelo=modelo, sistema=SISTEMA_ENTORNO,
                                              esquema=esquema_agente_entorno(), contenido=contenido))
        ajustes = datos.pop("ajustes", [])
        datos = aplicar_medidas(datos, medidas, ajustes)
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


# ---------- 3. Selección de robot (contrato v3: docs/agentes/seleccion-robot.md) ----------

SISTEMA_ROBOT = _prompt("robot")


class Seleccion(NamedTuple):
    requisitos: dict
    seleccion: dict
    robots_por_puesto: list[dict]


def _candidato_para_el_modelo(ficha: dict, requisitos: dict) -> dict:
    return {**ficha, "alcance_min_m": seleccion.alcance_min(ficha, requisitos),
            "tiene_nucleo_fisica": seleccion.tiene_nucleo(ficha), "specs_estimadas": seleccion.specs_estimadas(ficha)}


def _texto_seleccion(requisitos: dict, tope: int, candidatos: list[dict], titulo: str) -> str:
    return (f"requisitos.json:\n{json.dumps(requisitos, ensure_ascii=False)}\n\n"
            f"Tope de finalistas: {tope}\n\n"
            f"{titulo}:\n{json.dumps([_candidato_para_el_modelo(f, requisitos) for f in candidatos], ensure_ascii=False)}")


def _seleccion_con_modelo(modelo: str, requisitos: dict, fichas: list[dict], tope: int,
                          busqueda: dict | None, encontrados: list[str]) -> dict:
    pasan, descartados = seleccion.particion(fichas, requisitos)
    if not pasan:
        elegido = seleccion.menos_fallas(fichas, requisitos)
        texto = _texto_seleccion(requisitos, tope, [elegido],
                                 "Ningún candidato pasó el descarte. Candidato elegido por el código, "
                                 f"con sus fallas {seleccion.fallas(elegido, requisitos)}")
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=seleccion.ESQUEMA_JUSTIFICACION,
                           contenido=[{"type": "text", "text": texto}])
        return seleccion.armar([{"id": elegido["id"], "puesto": 1, "justificacion": datos["justificacion"]}],
                               [], descartados, busqueda, encontrados)
    orden = seleccion.ordenadas(pasan, requisitos)
    if not any(seleccion.tiene_nucleo(f) for f in orden):
        elegido = orden[0]
        texto = _texto_seleccion(requisitos, tope, [elegido],
                                 "Ningún candidato que pasó el descarte tiene el núcleo de fisica. Candidato "
                                 "elegido por el código, el primero por las preferencias; el clon usa la base genérica")
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=seleccion.ESQUEMA_JUSTIFICACION,
                           contenido=[{"type": "text", "text": texto}])
        return seleccion.armar([{"id": elegido["id"], "puesto": 1, "justificacion": datos["justificacion"]}],
                               seleccion.alternativas_sin_nucleo(orden, elegido), descartados, busqueda,
                               encontrados)
    texto = _texto_seleccion(requisitos, tope, orden, "Candidatos que pasaron el descarte por reglas, "
                                                      "ordenados por las preferencias")
    eleccion = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=seleccion.esquema_eleccion([f["id"] for f in orden]),
                          contenido=[{"type": "text", "text": texto}])
    seleccion.comprobar(eleccion, pasan, tope)
    return seleccion.armar(eleccion["finalistas"], eleccion["alternativas"], descartados, busqueda, encontrados)


def seleccionar(modo: str, modelo: str, entorno_json: dict, tarea_json: dict, catalogo: dict[str, dict],
                max_finalistas: int = TOPE_FINALISTAS, busqueda: dict | None = None,
                encontrados: list[str] | None = None) -> Seleccion:
    """Pasos 1, 3 y 4: requisitos, descarte por reglas y 1 a max_finalistas finalistas, cada uno con su robot.json.

    catalogo: todas las fichas candidatas (repo, compartidas y encontradas). busqueda y encontrados: el resultado
    del paso 2 (busqueda.buscar), que va tal cual a seleccion.json. Sin ellos, la búsqueda queda `omitida`."""
    tope = validar_max_finalistas(max_finalistas)
    fichas = list(catalogo.values())
    ids = list(encontrados or [])
    req = perfiles.requisitos(entorno_json, tarea_json, fichas)
    sel = (seleccion.por_reglas(req, fichas, tope, busqueda, ids) if modo == "fijo"
           else _seleccion_con_modelo(modelo, req, fichas, tope, busqueda, ids))
    return Seleccion(req, sel, seleccion.robots_finalistas(sel, catalogo))


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


__all__ = ["ErrorAgente", "Seleccion", "alcance_necesario", "clon", "constructor", "entorno", "frames_de_videos",
           "seleccionar", "tarea"]
