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

from .. import geometria, urdf
from ..modelos import fidelidad
from ..config import TOPE_FINALISTAS, validar_max_finalistas
from ..esquemas import esquema, sin_campos
from . import perfiles, seleccion
from .base import ErrorAgente, frames_de_videos, pedir_json, validado
from .perfiles import PERFILES_ENTORNO, PERFILES_TAREA, alcance_necesario, perfil_de, perfil_de_tarea

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PROMPTS = Path(__file__).resolve().parent / "prompts"


# Tope de tokens de salida por agente (pendientes, problema 8). El pensamiento adaptativo de Opus 5.5 cuenta dentro.
# Entorno es el más largo: hasta 8 imágenes y un esquema grande. base.py avisa en el log si una salida pasa el 80 %.
MAX_TOKENS_AGENTE = {"entorno": 48000, "tarea": 24000, "seleccion": 24000, "constructor": 24000, "fichar": 24000}


def _prompt(nombre: str) -> str:
    """Instrucciones del agente. Viven en prompts/<nombre>.md (contrato: docs/agentes/)."""
    return (PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def _fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------- 1. Entorno ----------

SISTEMA_ENTORNO = _prompt("entorno")
CONFIANZA_MIN_MEDIDA = 0.4      # bajo esto la medida no manda: el agente decide (y lo anota)
CONFIANZA_MAX_ESTIMADA = 0.7    # un dato que nadie midió no pasa de esta confianza


def esquema_agente_entorno() -> dict:
    """Lo que devuelve el modelo: entorno.json sin los campos del orquestador, más sus ajustes a las medidas.
    - `confianza` va como lista porque structured outputs no acepta objetos con claves libres.
    - Los bloques de perfil (filas, estructura, panel) van siempre, pero aceptan null.
    - Sin if/then/else: la API no los acepta; la regla de perfiles se valida en local."""
    esq = sin_campos(esquema("entorno"), ["version", "videos", "escena_usd", "fondo_reconstruido_usd", "mediciones"])
    for k in ("if", "then", "else"):
        esq.pop(k, None)
    for perfil in PERFILES_ENTORNO.values():
        for c in perfil.bloques_propios:
            esq["properties"][c] = {"anyOf": [esq["properties"][c], {"type": "null"}]}
            esq["required"].append(c)
    # La fricción del suelo no se ve en un video: la escribe el equipo o sale del tipo de suelo (sim/fisica.py).
    esq["properties"]["terreno"]["properties"].pop("friccion", None)
    # `detalle` es opcional en el contrato; para structured outputs va siempre y acepta null (normalizar_entorno lo quita).
    el = esq["properties"]["elementos"]["items"]
    el["properties"]["detalle"] = {"anyOf": [el["properties"]["detalle"], {"type": "null"}]}
    el["required"] = [*el["required"], "detalle"]
    esq["properties"]["confianza"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["campo", "valor"],
        "properties": {"campo": {"type": "string"}, "valor": {"type": "number"}}}}
    # Cada dato que el agente deja distinto de lo medido lleva su razón. Sin razón, el código vuelve a lo medido.
    medibles = [c for p in PERFILES_ENTORNO.values() for c in p.campos_medibles]
    esq["properties"]["ajustes"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["campo", "razon"],
        "properties": {"campo": {"enum": medibles}, "razon": {"type": "string"}}}}
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
    medibles = perfil_de(datos.get("tipo")).campos_medibles
    if not medibles:
        medidas = None
    if not medidas or not medidas.get("disponible"):
        datos["confianza"] = {k: min(v, CONFIANZA_MAX_ESTIMADA) for k, v in confianza.items()}
        return datos
    razones = {a["campo"]: a["razon"].strip() for a in (ajustes or []) if a.get("razon", "").strip()}
    medidos, aplicados, avisos = [], [], list(medidas.get("avisos", []))
    for campo, m in medidas["campos"].items():
        if campo not in medibles or m.get("confianza", 0) < CONFIANZA_MIN_MEDIDA:
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
    propios = perfil_de(datos.get("tipo")).bloques_propios
    for perfil in PERFILES_ENTORNO.values():
        for c in perfil.bloques_propios:
            if c not in propios or datos.get(c) is None:
                datos.pop(c, None)
    for el in datos.get("elementos") or []:
        if el.get("detalle", 0) is None:
            el.pop("detalle")
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
                                              esquema=esquema_agente_entorno(), contenido=contenido,
                                              max_tokens=MAX_TOKENS_AGENTE["entorno"], etiqueta="entorno"))
        ajustes = datos.pop("ajustes", [])
        datos = aplicar_medidas(datos, medidas, ajustes)
    datos.update(version=1, videos=[v.rsplit("/", 1)[1] for v in proyecto["videos"]],
                 escena_usd="escena.usd", fondo_reconstruido_usd=None)
    return validado("entorno", datos)


# ---------- 2. Tarea ----------

SISTEMA_TAREA = _prompt("tarea")

TAREAS_MANIPULACION = {"instalar_panel", "tomar_y_dejar", "transportar", "ordenar"}
RESTRICCIONES_CON_VALOR = {"velocidad_max_m_s", "distancia_personas_m", "fuerza_max_n"}
INTENTOS_TAREA = 2   # si la respuesta no calza con entorno.json, el agente recibe los problemas y reintenta una vez
CAMPOS_DEL_CODIGO = ("geometria", "advertencias")   # los llena completar_tarea(), nunca el modelo


def esquema_agente_tarea() -> dict:
    """Lo que devuelve el modelo: tarea.json sin `version`. Los perfiles van siempre, pero aceptan null.
    Sin if/then/else: la API no los acepta; la regla de perfiles se valida en local."""
    esq = sin_campos(esquema("tarea"), ["version", *CAMPOS_DEL_CODIGO])
    for k in ("if", "then", "else", "allOf", "$defs"):
        esq.pop(k, None)
    for perfil in PERFILES_TAREA.values():
        for c in perfil.bloques_propios:
            esq["properties"][c] = {"anyOf": [esq["properties"][c], {"type": "null"}]}
            esq["required"].append(c)
    return esq


def normalizar_tarea(datos: dict) -> dict:
    """Respuesta del modelo → forma del contrato: sin perfiles que no aplican."""
    datos = copy.deepcopy(datos)
    propios = perfil_de_tarea(datos.get("tarea")).bloques_propios
    for perfil in PERFILES_TAREA.values():
        for c in perfil.bloques_propios:
            if c not in propios or datos.get(c) is None:
                datos.pop(c, None)
    return datos


def problemas_pedido(t: dict, descripcion_cliente: str | None) -> list[str]:
    """La tarea dice de dónde sale. Si el agente la infirió, deja preguntas para confirmarla con el cliente.
    descripcion_cliente None: no se revisa (tarea.json escrito a mano por el equipo)."""
    problemas = []
    p = t["pedido"]
    if p["origen"] == "inferido" and not p["preguntas"]:
        problemas.append("pedido.origen es inferido pero pedido.preguntas está vacío: escribe 1 a 3 preguntas para el cliente")
    if descripcion_cliente is not None and not descripcion_cliente.strip() and p["origen"] == "cliente":
        problemas.append("pedido.origen es cliente, pero el cliente no escribió una descripción: la tarea es inferida")
    if not t["proposito"].strip():
        problemas.append("proposito está vacío: di para qué le sirve la tarea al cliente")
    return problemas


def completar_tarea(t: dict, entorno_json: dict, descripcion_cliente: str | None = None) -> tuple[dict, list[str]]:
    """Revisa la tarea contra entorno.json y agrega lo que calcula el código (geometria, advertencias).
    Devuelve (tarea completa, problemas). Sin problemas, la tarea pasó la fase 1 del embudo de factibilidad."""
    t = {k: v for k, v in copy.deepcopy(t).items() if k not in CAMPOS_DEL_CODIGO}
    problemas = problemas_tarea(t, entorno_json) + problemas_pedido(t, descripcion_cliente)
    advertencias: list[str] = []
    if not any("no existe en entorno.json" in p for p in problemas):
        prob_geo, advertencias, t["geometria"] = geometria.revisar(t, entorno_json)
        problemas += prob_geo
    if t["pedido"]["origen"] == "inferido":
        advertencias.insert(0, "la tarea es inferida: confirmar con el cliente (pedido.preguntas)")
    t["advertencias"] = advertencias
    if "geometria" not in t:
        t["geometria"] = {"origen_pose": None, "destino_pose": None, "distancia_m": None, "altura_max_m": None}
    return t, problemas


def problemas_tarea(t: dict, entorno_json: dict) -> list[str]:
    """Reglas que el esquema no puede expresar: la tarea tiene que calzar con entorno.json (referencias y lógica).
    La geometría (soporte, encaje, despeje, techo) la revisa viaz/geometria.py desde completar_tarea()."""
    problemas = []
    tipo = t["tarea"]
    requerido = perfil_de_tarea(tipo).entorno_requerido
    if requerido is not None and entorno_json["tipo"] != requerido:
        problemas.append(f"la tarea {tipo} necesita un entorno {requerido}, y el entorno es {entorno_json['tipo']}")
    elementos = {e["nombre"]: e for e in entorno_json.get("elementos", [])}
    for parte in ("objeto", "origen", "destino"):
        nombre = t[parte]["elemento"]
        if nombre is not None and nombre not in elementos:
            disponibles = ", ".join(sorted(elementos)) or "(entorno.json no tiene elementos)"
            problemas.append(f"{parte}.elemento '{nombre}' no existe en entorno.json; elementos: {disponibles}")
    if tipo in TAREAS_MANIPULACION:
        obj = elementos.get(t["objeto"]["elemento"])
        if obj is not None and obj["fijo"]:
            problemas.append(f"objeto '{obj['nombre']}' está marcado fijo en entorno.json: el robot no puede moverlo")
        o, d = t["origen"]["elemento"], t["destino"]["elemento"]
        if o is not None and o == d:
            problemas.append(f"origen y destino son el mismo elemento ('{o}')")
    if "pila_paneles" in t and t["objetivo"]["cantidad"] > t["pila_paneles"]["cantidad"]:
        problemas.append(f"objetivo.cantidad ({t['objetivo']['cantidad']}) es mayor que la pila "
                         f"({t['pila_paneles']['cantidad']})")
    propias = perfil_de_tarea(tipo).problemas
    if propias is not None:
        problemas += propias(t, entorno_json)
    tmax = t["criterios_exito"]["tiempo_max_s"]
    if tmax is not None and tmax < t["objetivo"]["ciclo_s"]:
        problemas.append(f"criterios_exito.tiempo_max_s ({tmax}) es menor que objetivo.ciclo_s ({t['objetivo']['ciclo_s']})")
    for r in t["restricciones"]:
        if r["tipo"] in RESTRICCIONES_CON_VALOR and r["valor"] is None:
            problemas.append(f"la restricción {r['tipo']} necesita un valor")
    return problemas + problemas_calidad(t, entorno_json)


# Calidad (docs/agentes/tarea.md §9): reglas del prompt que el esquema no expresa.
DURACION_MAX_S = 600     # la tarea cabe en una demo corta: cantidad × ciclo_s
# Misma geometría que sim/plan.py (INICIO_X, HOLGURA_SLOT). Una prueba revisa que no se separen.
INICIO_FILA_M = 2.0      # el primer panel va a 2 m del inicio de la fila
HOLGURA_PANEL_M = 0.02   # separación entre paneles instalados


def paneles_que_caben(entorno_json: dict) -> int:
    """Paneles que caben en una fila del perfil parque_solar. Igual que sim/plan.py → caben()."""
    p = entorno_json["panel"]
    return int((entorno_json["filas"]["largo_m"] - INICIO_FILA_M) // (p["ancho_m"] + HOLGURA_PANEL_M))


def problemas_calidad(t: dict, entorno_json: dict) -> list[str]:
    """Duración, restricciones y perfil instalar_panel. El prompt las pide en "Antes de responder"; el código las repite."""
    problemas = []
    n, ciclo = t["objetivo"]["cantidad"], t["objetivo"]["ciclo_s"]
    if n * ciclo > DURACION_MAX_S:
        problemas.append(f"objetivo.cantidad × objetivo.ciclo_s = {n} × {ciclo:g} s = {n * ciclo:g} s, "
                         f"más que {DURACION_MAX_S} s: la tarea no cabe en una demo corta")
    rs = t["restricciones"]
    tipos = [r["tipo"] for r in rs]
    if "no_chocar" not in tipos:
        problemas.append("falta la restricción no_chocar: va siempre")
    if not 1 <= len(rs) <= 5:
        problemas.append(f"hay {len(rs)} restricciones; deben ser de 1 a 5")
    claves = [(r["tipo"], r["valor"], " ".join(r["detalle"].lower().split()).rstrip(".")) for r in rs]
    if len(set(claves)) < len(claves):
        problemas.append("hay restricciones repetidas")
    if "pila_paneles" in t:   # perfil instalar_panel
        pila = t["pila_paneles"]["cantidad"]
        if not 3 <= pila <= 10:
            problemas.append(f"pila_paneles.cantidad es {pila}; en instalar_panel debe estar entre 3 y 10")
        if not 30 <= ciclo <= 120:
            problemas.append(f"objetivo.ciclo_s es {ciclo:g} s; en instalar_panel debe estar entre 30 y 120")
        if "orientacion_fija" not in tipos:
            problemas.append("falta la restricción orientacion_fija (panel horizontal durante el traslado)")
        if "filas" in entorno_json and "panel" in entorno_json and n > (caben := paneles_que_caben(entorno_json)):
            problemas.append(f"objetivo.cantidad es {n}, pero en una fila caben {caben} paneles")
    return problemas


def validar_tarea(t: dict, entorno_json: dict, descripcion_cliente: str | None = None) -> dict:
    """tarea.json completo: esquema + reglas + geometría contra entorno.json. Sirve también para la tarea a mano."""
    t, problemas = completar_tarea(validado("tarea", t), entorno_json, descripcion_cliente)
    if problemas:
        raise ErrorAgente("tarea.json no calza con entorno.json: " + "; ".join(problemas))
    return validado("tarea", t)


def texto_tarea(proyecto: dict, entorno_json: dict, problemas: list[str] | None = None) -> str:
    lineas = []
    for e in entorno_json.get("elementos", []):
        masa = f", {e['masa_kg']} kg" if e["masa_kg"] else ""
        d = e["dimensiones_m"]
        tam = f"{d['largo_m']:g} × {d['ancho_m']:g} × {d['alto_m']:g} m"
        lineas.append(f"- {e['nombre']} ({e['categoria']}, {'fijo' if e['fijo'] else 'movible'}{masa}, {tam}, "
                      f"base a {e['posicion_m']['z_m']:g} m, tope a {geometria.tope(e):g} m)")
    elementos = "\n".join(lineas) or "(ninguno)"
    texto = (f"Descripción del cliente: {proyecto['descripcion'] or '(sin descripción)'}\n"
             f"Tipo de espacio: {entorno_json['tipo']}\n"
             f"Elementos de entorno.json (usa estos nombres en objeto/origen/destino):\n{elementos}\n\n"
             f"entorno.json:\n{json.dumps(entorno_json, ensure_ascii=False)}")
    if problemas:
        texto += ("\n\nTu respuesta anterior no calzó con entorno.json. Corrige estos problemas:\n"
                  + "\n".join(f"- {p}" for p in problemas))
    return texto


def tarea(modo: str, modelo: str, proyecto: dict, entorno_json: dict, frames: list[dict] | None) -> dict:
    """tarea.json para el espacio de entorno.json. El código revisa que calce con el entorno; si no calza,
    el agente recibe los problemas y reintenta (hasta INTENTOS_TAREA)."""
    if modo == "fijo":
        datos = _fixture(perfil_de(entorno_json["tipo"]).fixture_tarea)
        return validar_tarea(datos, entorno_json)
    problemas: list[str] = []
    descripcion = proyecto["descripcion"] or ""
    for _ in range(INTENTOS_TAREA):
        datos = normalizar_tarea(pedir_json(
            modelo=modelo, sistema=SISTEMA_TAREA, esquema=esquema_agente_tarea(),
            contenido=[*(frames or []), {"type": "text", "text": texto_tarea(proyecto, entorno_json, problemas)}],
            max_tokens=MAX_TOKENS_AGENTE["tarea"], etiqueta="tarea"))
        datos["version"] = 1
        datos, problemas = completar_tarea(validado("tarea", datos), entorno_json, descripcion)
        if not problemas:
            return validado("tarea", datos)
    raise ErrorAgente("tarea.json no calza con entorno.json: " + "; ".join(problemas))


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
                           contenido=[{"type": "text", "text": texto}], max_tokens=MAX_TOKENS_AGENTE["seleccion"],
                           etiqueta="seleccion")
        return seleccion.armar(fichas, [{"id": elegido["id"], "puesto": 1, "justificacion": datos["justificacion"]}],
                               [], descartados, busqueda, encontrados)
    orden = seleccion.ordenadas(pasan, requisitos)
    if not any(seleccion.tiene_nucleo(f) for f in orden):
        elegido = orden[0]
        texto = _texto_seleccion(requisitos, tope, [elegido],
                                 "Ningún candidato que pasó el descarte tiene el núcleo de fisica. Candidato "
                                 "elegido por el código, el primero por las preferencias; el clon usa la base genérica")
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=seleccion.ESQUEMA_JUSTIFICACION,
                           contenido=[{"type": "text", "text": texto}], max_tokens=MAX_TOKENS_AGENTE["seleccion"],
                           etiqueta="seleccion")
        return seleccion.armar(fichas, [{"id": elegido["id"], "puesto": 1, "justificacion": datos["justificacion"]}],
                               seleccion.alternativas_sin_nucleo(orden, elegido), descartados, busqueda,
                               encontrados)
    texto = _texto_seleccion(requisitos, tope, orden, "Candidatos que pasaron el descarte por reglas, "
                                                      "ordenados por las preferencias")
    eleccion = pedir_json(modelo=modelo, sistema=SISTEMA_ROBOT, esquema=seleccion.esquema_eleccion([f["id"] for f in orden]),
                          contenido=[{"type": "text", "text": texto}], max_tokens=MAX_TOKENS_AGENTE["seleccion"],
                          etiqueta="seleccion")
    seleccion.comprobar(eleccion, pasan, tope)
    return seleccion.armar(fichas, eleccion["finalistas"], eleccion["alternativas"], descartados, busqueda, encontrados)


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
        "fidelidad": fidelidad(robot_json),
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
                intento: int, problemas_previos: list[str] | None = None, previo: dict | None = None,
                total_intentos: int = 3) -> dict:
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
                 f"Intento {intento} de {total_intentos}.")
        if previo is not None:
            texto += (f"\n\nEnsamblaje del intento anterior:\n{json.dumps(previo, ensure_ascii=False)}"
                      f"\nProblemas:\n- " + "\n- ".join(problemas_previos or []))
        datos = pedir_json(modelo=modelo, sistema=SISTEMA_CONSTRUCTOR, esquema=esquema_agente_constructor(assets),
                           contenido=[{"type": "text", "text": texto}], max_tokens=MAX_TOKENS_AGENTE["constructor"],
                           etiqueta="constructor")
    datos.update(version=1, robot_id=robot_json["id"])
    return validado("ensamblaje", datos)


__all__ = ["ErrorAgente", "Seleccion", "alcance_necesario", "clon", "constructor", "entorno", "frames_de_videos",
           "seleccionar", "tarea"]
