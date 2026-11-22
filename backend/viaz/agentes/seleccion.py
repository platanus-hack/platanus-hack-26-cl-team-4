"""Pasos 3 y 4 de la selección v3: descarte por reglas, orden por preferencias y finalistas.

Todo es genérico: lee requisitos.json y las fichas del catálogo, nunca el dominio.
Contrato: docs/agentes/seleccion-robot.md (§3 salidas, §4 reglas que verifica el código).
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Callable, NamedTuple

from ..config import validar_max_finalistas
from ..esquemas import esquema
from .base import ErrorAgente, validado

NUCLEO_FISICA: tuple[str, ...] = tuple(esquema("robot")["properties"]["fisica"]["required"])
MARGEN_CARGA_MAX = 3


# ---------- Datos de una ficha ----------

def specs_estimadas(ficha: dict) -> list[str]:
    """Specs de selección que el fabricante no publica. Las medidas `fisica.*` son del clon, no de la selección."""
    return [k for k in ficha.get("estimados", {}) if not k.startswith("fisica.")]


def tiene_nucleo(ficha: dict) -> bool:
    return set(NUCLEO_FISICA) <= set(ficha.get("fisica") or {})


def alcance_min(ficha: dict, requisitos: dict) -> float | None:
    for fila in requisitos["por_robot"]:
        if fila["id"] == ficha["id"]:
            return fila["alcance_min_m"]
    raise ErrorAgente(f"requisitos.por_robot no tiene una fila para el candidato {ficha['id']}")


# ---------- Preferencias ----------

class Preferencia(NamedTuple):
    descripcion: str
    clave: Callable[[dict, dict], Any]


def _margen(ficha: dict, requisitos: dict) -> tuple[float, float]:
    carga_min = requisitos["carga_min_kg"]
    carga = min(ficha["carga_util_kg"] / carga_min, MARGEN_CARGA_MAX) if carga_min > 0 else 0.0
    minimo = alcance_min(ficha, requisitos)
    alcance = ficha["alcance_m"] - minimo if minimo is not None else 0.0
    return (-carga, -alcance)


PREFERENCIAS: dict[str, Preferencia] = {
    "real_sobre_ficticio": Preferencia("Un robot real antes que uno ficticio", lambda f, r: f["ficticio"]),
    "menos_specs_estimadas": Preferencia("Menos specs en estimados", lambda f, r: len(specs_estimadas(f))),
    "mayor_margen_carga_alcance": Preferencia("Mayor margen de carga útil y de alcance sobre el mínimo", _margen),
    "mayor_velocidad_base": Preferencia("Mayor velocidad de base", lambda f, r: -f["velocidad_base_m_s"]),
}


def preferencias(criterios: tuple[str, ...] | list[str]) -> list[dict]:
    """Bloque `preferencias` de requisitos.json, en el orden dado."""
    return [{"criterio": c, "descripcion": _preferencia(c).descripcion} for c in criterios]


def _preferencia(criterio: str) -> Preferencia:
    if criterio not in PREFERENCIAS:
        raise ErrorAgente(f"preferencia desconocida en requisitos.json: '{criterio}'. "
                          f"Conocidas: {', '.join(PREFERENCIAS)}")
    return PREFERENCIAS[criterio]


def ordenadas(fichas: list[dict], requisitos: dict) -> list[dict]:
    """Fichas de mejor a peor según requisitos.preferencias (la primera pesa más). El id rompe los empates."""
    claves = [_preferencia(p["criterio"]).clave for p in requisitos["preferencias"]]
    return sorted(fichas, key=lambda f: (*(clave(f, requisitos) for clave in claves), f["id"]))


# ---------- 3. Descarte por reglas ----------

def _aceptados(valores: list[str]) -> str:
    return ", ".join(valores)


def fallas(ficha: dict, requisitos: dict) -> list[str]:
    """Requisitos obligatorios que la ficha no cumple. Vacío si pasa."""
    f = []
    if ficha["carga_util_kg"] < requisitos["carga_min_kg"]:
        f.append(f"carga útil de {ficha['carga_util_kg']} kg menor que la mínima ({requisitos['carga_min_kg']} kg)")
    if ficha["efector"] not in requisitos["efectores_aceptados"]:
        f.append(f"efector {ficha['efector']} no está entre los aceptados ({_aceptados(requisitos['efectores_aceptados'])})")
    if ficha["tipo"] not in requisitos["tipos_aceptados"]:
        f.append(f"tipo {ficha['tipo']} no está entre los aceptados ({_aceptados(requisitos['tipos_aceptados'])})")
    minimo = alcance_min(ficha, requisitos)
    if minimo is not None and ficha["alcance_m"] < minimo:
        f.append(f"alcance de {ficha['alcance_m']} m menor que el necesario ({minimo} m)")
    return f


class Particion(NamedTuple):
    pasan: list[dict]
    descartados: list[dict]


def particion(fichas: list[dict], requisitos: dict) -> Particion:
    filas = [(f, fallas(f, requisitos)) for f in fichas]
    return Particion([f for f, x in filas if not x], [{"id": f["id"], "fallas": x} for f, x in filas if x])


def menos_fallas(fichas: list[dict], requisitos: dict) -> dict:
    """Cuando nadie pasa: el candidato con menos fallas. Las preferencias rompen los empates."""
    return min(ordenadas(fichas, requisitos), key=lambda f: len(fallas(f, requisitos)))


# ---------- 4. Selección ----------

def _justificacion(ficha: dict, requisitos: dict, puesto: int) -> str:
    oraciones = []
    if requisitos["carga_min_kg"] > 0:
        oraciones.append(f"{ficha['nombre']} carga {ficha['carga_util_kg']} kg y la tarea pide al menos "
                         f"{requisitos['carga_min_kg']} kg")
    minimo = alcance_min(ficha, requisitos)
    if minimo is not None:
        verbo = "cubre" if ficha["alcance_m"] >= minimo else "no cubre"
        oraciones.append(f"Su alcance de {ficha['alcance_m']} m {verbo} los {minimo} m que necesita")
    oraciones.append("Tiene el núcleo de fisica" if tiene_nucleo(ficha) else
                     f"No tiene el núcleo de fisica ({', '.join(NUCLEO_FISICA)}): el clon usa la base genérica")
    estimadas = specs_estimadas(ficha)
    oraciones.append(f"El fabricante no publica {', '.join(estimadas)}: esos valores son estimaciones" if estimadas
                     else "Ninguna spec de selección es estimada")
    if ficha["ficticio"]:
        oraciones.append("Es un robot de referencia ficticio")
    if puesto > 1:
        orden = ", ".join(p["descripcion"].lower() for p in requisitos["preferencias"])
        oraciones.append(f"Queda en el puesto {puesto} por las preferencias, en este orden: {orden}")
    oraciones += [f"Aviso: {a}" for a in requisitos["advertencias"]]
    return ". ".join(oraciones) + ". (Elección por reglas, sin LLM.)"


def justificacion_sin_candidatos(ficha: dict, requisitos: dict) -> str:
    primera = (f"Ningún candidato cumple los requisitos obligatorios; {ficha['nombre']} es el que falla menos: "
               f"{'; '.join(fallas(ficha, requisitos))}. ")
    return primera + _justificacion(ficha, requisitos, 1)


def justificacion_sin_nucleo(ficha: dict, requisitos: dict) -> str:
    primera = (f"Ningún candidato válido tiene las medidas del vehículo ({', '.join(NUCLEO_FISICA)}), así que "
               f"el clon de {ficha['nombre']} usa la base genérica. ")
    return primera + _justificacion(ficha, requisitos, 1)


def alternativas_sin_nucleo(orden: list[dict], elegido: dict) -> list[dict]:
    """Cuando ningún candidato válido tiene el núcleo: todos menos el elegido, con un por_que_no del código."""
    return [{"id": f["id"], "por_que_no": f"tampoco tiene el núcleo de fisica y queda después de "
                                          f"{elegido['nombre']} por las preferencias"}
            for f in orden if f["id"] != elegido["id"]]


def _por_que_no(ficha: dict, tope: int) -> str:
    if tiene_nucleo(ficha):
        return f"tiene el núcleo de fisica, pero queda fuera del tope de {tope} finalistas por las preferencias"
    motivo = f"sin el núcleo de fisica ({', '.join(NUCLEO_FISICA)})"
    if specs_estimadas(ficha):
        motivo += f"; además {', '.join(specs_estimadas(ficha))} son estimados"
    return motivo + ("; ficticio" if ficha["ficticio"] else "")


BUSQUEDA_OMITIDA = {"estado": "omitida", "invalidas": [],
                    "detalle": "La búsqueda web no corrió: los candidatos son solo las fichas conocidas."}


def nombres(fichas: list[dict]) -> dict[str, str]:
    return {f["id"]: f["nombre"] for f in fichas if f.get("nombre")}


def con_nombre(filas: list[dict], por_id: dict[str, str]) -> list[dict]:
    return [{"id": f["id"], **({"nombre": por_id[f["id"]]} if f["id"] in por_id else {}),
             **{k: v for k, v in f.items() if k not in ("id", "nombre")}} for f in filas]


def armar(fichas: list[dict], finalistas: list[dict], alternativas: list[dict], descartados: list[dict],
          busqueda: dict | None = None, encontrados: list[str] | tuple[str, ...] = ()) -> dict:
    """seleccion.json validado. `busqueda` es el bloque del paso 2; `encontrados`, los ids que trajo en esta corrida."""
    por_id = nombres(fichas)
    return validado("seleccion", {
        "version": 1,
        "requisitos": "requisitos.json",
        "busqueda": copy.deepcopy(busqueda or BUSQUEDA_OMITIDA),
        "encontrados": list(encontrados),
        "descartados": con_nombre(descartados, por_id),
        "finalistas": con_nombre(sorted(finalistas, key=lambda f: f["puesto"]), por_id),
        "alternativas": con_nombre(alternativas, por_id),
    })


def por_reglas(requisitos: dict, fichas: list[dict], tope: int, busqueda: dict | None = None,
               encontrados: list[str] | tuple[str, ...] = ()) -> dict:
    """Modo fijo (sin LLM). Determinista."""
    tope = validar_max_finalistas(tope)
    pasan, descartados = particion(fichas, requisitos)
    if not pasan:
        elegido = menos_fallas(fichas, requisitos)
        return armar(fichas, [{"id": elegido["id"], "puesto": 1,
                              "justificacion": justificacion_sin_candidatos(elegido, requisitos)}],
                     [], descartados, busqueda, encontrados)
    orden = ordenadas(pasan, requisitos)
    elegidos = [f for f in orden if tiene_nucleo(f)][:tope]
    if not elegidos:
        elegido = orden[0]
        return armar(fichas, [{"id": elegido["id"], "puesto": 1,
                              "justificacion": justificacion_sin_nucleo(elegido, requisitos)}],
                     alternativas_sin_nucleo(orden, elegido), descartados, busqueda, encontrados)
    finalistas = [{"id": f["id"], "puesto": n, "justificacion": _justificacion(f, requisitos, n)}
                  for n, f in enumerate(elegidos, 1)]
    alternativas = [{"id": f["id"], "por_que_no": _por_que_no(f, tope)} for f in orden if f not in elegidos]
    return armar(fichas, finalistas, alternativas, descartados, busqueda, encontrados)


def comprobar(eleccion: dict, pasan: list[dict], tope: int) -> None:
    """Reglas 2 a 4 del contrato sobre la respuesta del modelo. Una violación es un ErrorAgente."""
    por_id = {f["id"]: f for f in pasan}
    finalistas, alternativas = eleccion["finalistas"], eleccion["alternativas"]
    for fila in [*finalistas, *alternativas]:
        if fila["id"] not in por_id:
            raise ErrorAgente(f"el agente devolvió {fila['id']}, que no es un candidato que pasó el descarte")
    if not 1 <= len(finalistas) <= tope:
        raise ErrorAgente(f"el agente devolvió {len(finalistas)} finalistas; deben ser de 1 a {tope}")
    if sorted(f["puesto"] for f in finalistas) != list(range(1, len(finalistas) + 1)):
        raise ErrorAgente(f"los puestos {[f['puesto'] for f in finalistas]} deben ser 1..{len(finalistas)} sin repetir")
    for f in finalistas:
        if not tiene_nucleo(por_id[f["id"]]):
            raise ErrorAgente(f"el finalista {f['id']} no tiene el núcleo de fisica ({', '.join(NUCLEO_FISICA)})")
    veces = Counter(fila["id"] for fila in [*finalistas, *alternativas])
    for i in por_id:
        if veces[i] != 1:
            raise ErrorAgente(f"el candidato {i} aparece {veces[i]} veces; debe aparecer una vez, como finalista "
                              f"o como alternativa")


def esquema_eleccion(ids: list[str]) -> dict:
    """Lo que devuelve el modelo: finalistas y alternativas, con los ids restringidos a los candidatos."""
    def filas(campos: dict) -> dict:
        return {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                           "required": ["id", *campos], "properties": {"id": {"enum": ids}, **campos}}}
    return {"type": "object", "additionalProperties": False, "required": ["finalistas", "alternativas"],
            "properties": {"finalistas": filas({"puesto": {"type": "integer"}, "justificacion": {"type": "string"}}),
                           "alternativas": filas({"por_que_no": {"type": "string"}})}}


ESQUEMA_JUSTIFICACION = {"type": "object", "additionalProperties": False, "required": ["justificacion"],
                         "properties": {"justificacion": {"type": "string"}}}


# ---------- robot.json por finalista ----------

def robots_finalistas(seleccion: dict, fichas: dict[str, dict]) -> list[dict]:
    """Un robot.json por finalista, en orden de puesto. Las specs salen de la ficha, nunca del modelo (RNF-02)."""
    def otros(finalista: dict) -> list[dict]:
        return ([{"id": f["id"], "por_que_no": f"finalista {f['puesto']}"}
                 for f in seleccion["finalistas"] if f["id"] != finalista["id"]]
                + [{"id": a["id"], "por_que_no": a["por_que_no"]} for a in seleccion["alternativas"]]
                + [{"id": d["id"], "por_que_no": "; ".join(d["fallas"])}
                   for d in seleccion["descartados"] if d["id"] != finalista["id"]])
    return [validado("robot", {**copy.deepcopy(fichas[f["id"]]), "justificacion": f["justificacion"],
                               "alternativas": otros(f)})
            for f in seleccion["finalistas"]]
