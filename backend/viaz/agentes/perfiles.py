"""Paso 1 de la selección v3: perfiles de dominio. Traducen entorno.json y tarea.json a requisitos.json.

Cada PerfilEntorno trae un ConstructorRequisitos: una función pura (entorno, tarea, fichas) -> requisitos.
La selección solo lee requisitos.json: el vocabulario del dominio (panel, tubo, parque) vive aquí y en ningún otro paso.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .. import geometria, urdf
from ..esquemas import esquema
from .base import ErrorAgente, validado
from .seleccion import preferencias

ConstructorRequisitos = Callable[[dict, dict, list[dict]], dict]


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


MAX_AVISOS_SUELTOS = 3   # con más datos estimados, un solo aviso que los agrupa (no tapa la justificación)


def advertencias_de_confianza(confianza: dict[str, float]) -> list[str]:
    bajos = {c: v for c, v in confianza.items() if v < 1}
    if len(bajos) <= MAX_AVISOS_SUELTOS:
        return [f"{campo} tiene confianza {_numero(valor)}: es un valor supuesto, no medido"
                for campo, valor in bajos.items()]
    rango = f"{_numero(min(bajos.values()))} a {_numero(max(bajos.values()))}"
    return [f"{len(bajos)} datos del entorno son estimados, no medidos (confianza {rango}): {', '.join(bajos)}"]


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


# ---------- Perfil animar_evento (humanoide que anima un evento) ----------

ORDEN_PREFERENCIAS_ANIMAR = ("capacidades_de_la_tarea", "real_sobre_ficticio", "menos_specs_estimadas",
                             "mayor_velocidad_base")
# Lo que la tarea agradece de un robot. Preferencia, no filtro: cualquier robot móvil que quepa pasa a la selección,
# y el agente de selección decide cuál es el más adecuado y lo justifica.
CAPACIDADES_ANIMAR = ["caminar", "animar_evento", "interactuar_con_personas"]
RADIO_ROBOT_MIN_M = 0.3               # media huella del robot móvil más angosto que se considera (la tarea no sabe cuál será)
DISTANCIA_PUBLICO_M = 0.5             # valor por defecto de animacion.distancia_publico_m
PASO_REVISION_M = 0.1                 # cada cuánto se revisa el despeje a lo largo de un tramo
SIN_PISO = ("abertura",)              # categorías que no ocupan el piso


def _distancia_a_caja(x: float, y: float, h: tuple[float, float, float, float]) -> float:
    dx = max(h[0] - x, 0.0, x - h[1])
    dy = max(h[2] - y, 0.0, y - h[3])
    return math.hypot(dx, dy)


def _cajas_de_piso(entorno_json: dict) -> list[tuple[str, tuple[float, float, float, float]]]:
    return [(e["nombre"], geometria.huella(e)) for e in entorno_json.get("elementos", []) if e["categoria"] not in SIN_PISO]


def _distancia_publico(a: dict) -> float:
    return a["distancia_publico_m"] if a.get("distancia_publico_m") is not None else DISTANCIA_PUBLICO_M


def despeje_recorrido(tarea_json: dict, entorno_json: dict) -> list[tuple[str, str, str, float]]:
    """(desde, hasta, elemento, distancia mínima) de cada tramo del recorrido a cada elemento que ocupa el piso.
    Un recorrido de un solo punto se revisa como un tramo de largo 0."""
    puntos = tarea_json["animacion"]["puntos"]
    tramos = list(zip(puntos, puntos[1:])) or [(puntos[0], puntos[0])]
    filas = []
    for p, q in tramos:
        n = max(1, math.ceil(math.dist((p["x_m"], p["y_m"]), (q["x_m"], q["y_m"])) / PASO_REVISION_M))
        for nombre, h in _cajas_de_piso(entorno_json):
            peor = min(_distancia_a_caja(p["x_m"] + (q["x_m"] - p["x_m"]) * i / n,
                                         p["y_m"] + (q["y_m"] - p["y_m"]) * i / n, h) for i in range(n + 1))
            filas.append((p["nombre"], q["nombre"], nombre, peor))
    return filas


def ancho_libre_m(tarea_json: dict, entorno_json: dict) -> float | None:
    """Ancho máximo de un robot que recorre la ruta dejando la distancia al público a cada lado. None: sin obstáculos."""
    filas = despeje_recorrido(tarea_json, entorno_json)
    if not filas:
        return None
    return round(2 * max(0.0, min(f[3] for f in filas) - _distancia_publico(tarea_json["animacion"])), 2)


def problemas_animar(tarea_json: dict, entorno_json: dict) -> list[str]:
    """El recorrido de animar_evento cabe en el piso libre, para el robot móvil más angosto que se considera:
    cada punto queda dentro del espacio y cada tramo recto, a la distancia del público de todo elemento del piso.
    El ancho del robot elegido se revisa después, en la selección (requisitos.ancho_max_m)."""
    a = tarea_json["animacion"]
    libre = RADIO_ROBOT_MIN_M + _distancia_publico(a)
    esp = entorno_json["espacio"]
    problemas = []
    for p in a["puntos"]:
        if not (RADIO_ROBOT_MIN_M <= p["x_m"] <= esp["largo_m"] - RADIO_ROBOT_MIN_M
                and RADIO_ROBOT_MIN_M <= p["y_m"] <= esp["ancho_m"] - RADIO_ROBOT_MIN_M):
            problemas.append(f"el punto {p['nombre']} ({p['x_m']:g}, {p['y_m']:g}) queda fuera del espacio "
                             f"de {esp['largo_m']:g} × {esp['ancho_m']:g} m")
    for desde, hasta, nombre, peor in despeje_recorrido(tarea_json, entorno_json):
        if peor < libre:
            tramo = f"el punto {desde}" if desde == hasta else f"el tramo {desde} → {hasta}"
            problemas.append(f"{tramo} pasa a {peor:.2f} m de {nombre}; necesita {libre:.2f} m "
                             f"(robot más angosto + distancia al público)")
    return problemas


def perfil_animar(entorno_json: dict, tarea_json: dict, fichas: list[dict]) -> dict:
    """Requisitos de animar un evento. Solo filtra lo físico: moverse por el piso y caber en el recorrido.
    No elige el tipo de robot: un humanoide, una base con brazo o un vehículo pasan si caben. El agente de selección
    decide entre ellos, con capacidades_deseadas como preferencia."""
    robot = esquema("robot")["properties"]
    return {
        "version": 1,
        "dominio": "animar_evento",
        "tarea": tarea_json["tarea"],
        "objeto": None,
        "carga_min_kg": 0,
        "efectores_aceptados": list(robot["efector"]["enum"]),
        "tipos_aceptados": [t for t in robot["tipo"]["enum"] if t != "brazo_fijo"],
        "movilidad": "movil",
        "pendiente_grados": entorno_json["terreno"]["pendiente_grados"],
        "ancho_max_m": ancho_libre_m(tarea_json, entorno_json),
        # Límite de VIAZ, no de la tarea: sim/animar entrena caminata sobre el modelo publicado del robot.
        "requiere_modelo_sim": True,
        "capacidades_deseadas": CAPACIDADES_ANIMAR,
        "por_robot": [{"id": f["id"], "alcance_min_m": None} for f in fichas],
        "preferencias": preferencias(ORDEN_PREFERENCIAS_ANIMAR),
        "advertencias": advertencias_de_confianza(entorno_json.get("confianza") or {}),
    }


# ---------- Registro ----------

@dataclass(frozen=True)
class PerfilEntorno:
    tipo: str
    bloques_propios: tuple[str, ...]
    campos_medibles: tuple[str, ...]
    requisitos: ConstructorRequisitos | None
    fixture_tarea: str
    con_simulacion: bool


@dataclass(frozen=True)
class PerfilTarea:
    """Todo lo que una tarea necesita para correr de punta a punta (RF-GEN-03).

    requisitos: si la tarea fija qué robot sirve, manda sobre el perfil del entorno (ej.: animar pide un humanoide
    en cualquier lugar). sim: carpeta de sim/ con los comandos entrenar, evaluar, grabar_clip y validar_robot
    (sim/tareas.py). entorno_requerido: tipo de entorno obligatorio, o None si sirve en cualquiera."""
    tarea: str
    bloques_propios: tuple[str, ...]
    entorno_requerido: str | None
    con_simulacion: bool
    requisitos: ConstructorRequisitos | None = None
    sim: str | None = None
    problemas: Callable[[dict, dict], list[str]] | None = None   # reglas propias contra entorno.json
    tolerancia_fina: tuple[float, float] | None = None           # RF-INT-20: (m, grados) que también se informa


PERFILES_ENTORNO: dict[str, PerfilEntorno] = {
    "parque_solar": PerfilEntorno(
        tipo="parque_solar",
        bloques_propios=("filas", "estructura", "panel"),
        campos_medibles=("filas.cantidad", "filas.separacion_m", "filas.largo_m", "estructura.tipo",
                         "estructura.altura_m", "estructura.inclinacion_grados", "panel.largo_m", "panel.ancho_m",
                         "terreno.pendiente_grados"),
        requisitos=perfil_solar,
        fixture_tarea="tarea",
        con_simulacion=True,
    ),
}
ENTORNO_GENERICO = PerfilEntorno("generico", (), (), None, "tarea_sala", False)

PERFILES_TAREA: dict[str, PerfilTarea] = {
    "instalar_panel": PerfilTarea("instalar_panel", ("pila_paneles",), "parque_solar", True, sim="rl",
                                  tolerancia_fina=(0.02, 2.0)),
    "animar_evento": PerfilTarea("animar_evento", ("animacion",), None, True, requisitos=perfil_animar,
                                 sim="animar", problemas=problemas_animar),
}
TAREA_GENERICA = PerfilTarea("generica", (), None, False)


def perfil_de(tipo: str | None) -> PerfilEntorno:
    return PERFILES_ENTORNO.get(tipo or "", ENTORNO_GENERICO)


def perfil_de_tarea(tarea: str | None) -> PerfilTarea:
    return PERFILES_TAREA.get(tarea or "", TAREA_GENERICA)


def tipos_con_simulacion() -> list[str]:
    return sorted(t for t, p in PERFILES_ENTORNO.items() if p.con_simulacion)


def tareas_con_simulacion() -> list[str]:
    return sorted(t for t, p in PERFILES_TAREA.items() if p.con_simulacion)


def simulable(entorno_json: dict, tarea_json: dict | None) -> bool:
    """Robot → Inteligencia corre si la tarea tiene simulación y sirve en este entorno.
    Sin tarea todavía: basta con que el entorno tenga perfil con simulación o alguna tarea sirva en cualquier entorno."""
    if tarea_json is None:
        return perfil_de(entorno_json.get("tipo")).con_simulacion or any(
            p.con_simulacion and p.entorno_requerido is None for p in PERFILES_TAREA.values())
    pt = perfil_de_tarea(tarea_json.get("tarea"))
    return pt.con_simulacion and pt.entorno_requerido in (None, entorno_json.get("tipo"))


def requisitos(entorno_json: dict, tarea_json: dict, fichas: list[dict]) -> dict:
    """requisitos.json validado. Manda el perfil de la tarea si tiene requisitos; si no, el del entorno."""
    tipo = str(entorno_json.get("tipo"))
    constructor = perfil_de_tarea(tarea_json.get("tarea")).requisitos or perfil_de(tipo).requisitos
    if constructor is None:
        con_perfil = sorted(t for t, p in PERFILES_ENTORNO.items() if p.requisitos is not None)
        con_tarea = sorted(t for t, p in PERFILES_TAREA.items() if p.requisitos is not None)
        raise ErrorAgente(f"no hay perfil de dominio para entornos tipo '{tipo}' con la tarea "
                          f"'{tarea_json.get('tarea')}'. Entornos con perfil: {', '.join(con_perfil)}; "
                          f"tareas con perfil: {', '.join(con_tarea)}")
    return validado("requisitos", constructor(entorno_json, tarea_json, fichas))
