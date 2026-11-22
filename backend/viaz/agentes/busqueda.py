"""Paso 2 de la selección v3: búsqueda web de robots reales que no están en el catálogo.

Dos llamadas: `investigar` (herramienta web_search del servidor, devuelve notas con URL y cita por dato) y
`fichar` (salida estructurada, sin herramientas: notas → borradores). Las citas de la búsqueda no se pueden
combinar con la salida estructurada en una llamada. El modelo nunca escribe la ficha final: el código la arma
desde el borrador, la limpia y la valida. Contrato: docs/agentes/seleccion-robot.md (§2, paso 2).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Callable, NamedTuple
from urllib.parse import urlparse

from ..catalogo.encontrados import validar_ficha
from ..esquemas import esquema
from .base import ErrorAgente, pedir_json

log = logging.getLogger("viaz.agentes.busqueda")

PROMPTS = Path(__file__).resolve().parent / "prompts"
SISTEMA_INVESTIGAR = (PROMPTS / "busqueda.md").read_text(encoding="utf-8")
SISTEMA_FICHAR = (PROMPTS / "busqueda_fichas.md").read_text(encoding="utf-8")

HERRAMIENTA_WEB = "web_search_20250305"   # búsqueda básica: llamadas directas, sin ejecución de código
MAX_TOKENS = 16000
LARGO_NOMBRE = 120
LARGO_TEXTO = 300
LARGO_URL = 2000
LARGO_ID = 80
LARGO_NOTAS = 40000
LARGO_MIN_MOTIVO = 20   # un motivo más corto no alcanza a nombrar la evidencia del estimado

_ROBOT = esquema("robot")["properties"]
SPECS_SELECCION = ("carga_util_kg", "alcance_m", "velocidad_base_m_s", "efector")
CAMPOS_FISICA = tuple(k for k in _ROBOT["fisica"]["properties"] if k != "traccion")
NUCLEO_FISICA = tuple(_ROBOT["fisica"]["required"])
PARES_FISICA: dict[str, list[str]] = _ROBOT["fisica"]["dependentRequired"]
CAMPOS_CON_FUENTE = (*SPECS_SELECCION, "tipo", *(f"fisica.{k}" for k in (*CAMPOS_FISICA, "traccion")))


class Parametros(NamedTuple):
    activa: bool
    max_robots: int
    max_consultas: int
    tiempo_s: float


class Notas(NamedTuple):
    texto: str
    cortada: bool


class Revision(NamedTuple):
    fichas: list[dict]
    invalidas: list[dict]
    sobrantes: list[str]


class Resultado(NamedTuple):
    estado: str
    detalle: str
    invalidas: list[dict]
    fichas: list[dict]

    def bloque(self) -> dict:
        """Bloque `busqueda` de seleccion.json."""
        return {"estado": self.estado, "detalle": self.detalle, "invalidas": [dict(i) for i in self.invalidas]}


class FichaInvalida(ValueError):
    pass


# ---------- Texto que viene de la web ----------

def limpio(texto: object, largo: int) -> str:
    """Sin caracteres de control, con espacios simples y a lo más `largo` caracteres."""
    sin_control = "".join(" " if unicodedata.category(c) in ("Cc", "Cf") else c for c in str(texto or ""))
    return " ".join(sin_control.split())[:largo]


def es_url_web(url: str) -> bool:
    partes = urlparse(url)
    return partes.scheme in ("http", "https") and bool(partes.netloc)


def normalizado(texto: str) -> str:
    """Minúsculas, sin tildes ni puntuación: para comparar nombres."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[\W_]+", " ", sin_tildes.lower()).split())


def slug(fabricante: str, nombre: str) -> str:
    f, n = normalizado(fabricante), normalizado(nombre)
    base = n if n.startswith(f) else f"{f} {n}"
    ascii_ = base.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")[:LARGO_ID].strip("-")


# ---------- Del borrador a la ficha ----------

def _url(texto: object, que: str) -> str:
    url = limpio(texto, LARGO_URL)
    if not url:
        raise FichaInvalida(f"sin URL de {que}")
    if not es_url_web(url):
        raise FichaInvalida(f"la URL de {que} no es http(s): {url[:80]}")
    return url


def _evidencia(filas: list[dict]) -> dict[str, dict]:
    evidencia = {}
    for fila in filas:
        campo = fila.get("campo")
        if campo not in CAMPOS_CON_FUENTE:
            continue
        cita = limpio(fila.get("cita"), LARGO_TEXTO)
        if not cita:
            raise FichaInvalida(f"la evidencia de {campo} no tiene cita")
        evidencia[campo] = {"url": _url(fila.get("url"), f"la evidencia de {campo}"), "cita": cita}
    return evidencia


def _estimados(filas: list[dict]) -> dict[str, str]:
    """Motivo limpio por campo, también los vacíos o cortos: `_specs` rechaza los que no dicen de dónde salen."""
    return {f["campo"]: limpio(f.get("motivo"), LARGO_TEXTO) for f in filas if f.get("campo") in CAMPOS_CON_FUENTE}


def _con_base(estimados: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in estimados.items() if len(v) >= LARGO_MIN_MOTIVO}


def _specs(borrador: dict, evidencia: dict[str, dict], estimados: dict[str, str]) -> dict:
    specs = {}
    for campo in (*SPECS_SELECCION, "tipo"):
        valor = borrador.get(campo)
        if valor is None:
            raise FichaInvalida(f"{campo} sin valor: la fuente no lo publica y no hay estimación")
        if campo in SPECS_SELECCION and campo not in evidencia:
            if campo not in estimados:
                raise FichaInvalida(f"{campo} sin evidencia ni estimado")
            if len(estimados[campo]) < LARGO_MIN_MOTIVO:
                raise FichaInvalida(f"el estimado de {campo} no dice de dónde sale el valor "
                                    f"(motivo de menos de {LARGO_MIN_MOTIVO} caracteres)")
        specs[campo] = valor
    return specs


def _fisica(borrador: dict, respaldados: set[str]) -> dict | None:
    valores = {f["campo"]: f["valor"] for f in borrador.get("fisica") or [] if f.get("campo") in CAMPOS_FISICA}
    if borrador.get("traccion") is not None:
        valores["traccion"] = borrador["traccion"]
    con_fuente = {k: v for k, v in valores.items() if f"fisica.{k}" in respaldados}
    completos = {k: v for k, v in con_fuente.items() if all(p in con_fuente for p in PARES_FISICA.get(k, []))}
    return completos if set(NUCLEO_FISICA) <= set(completos) else None


def ficha_desde_borrador(borrador: dict, hoy: str) -> dict:
    """Ficha del catálogo (origen: busqueda) armada por el código. FichaInvalida con el motivo si no sirve."""
    nombre, fabricante = limpio(borrador.get("nombre"), LARGO_NOMBRE), limpio(borrador.get("fabricante"), LARGO_NOMBRE)
    if not nombre or not fabricante:
        raise FichaInvalida("sin nombre o sin fabricante")
    fuente_url = _url(borrador.get("fuente_url"), "fuente")
    evidencia, todos = _evidencia(borrador.get("evidencias") or []), _estimados(borrador.get("estimados") or [])
    specs = _specs(borrador, evidencia, todos)
    estimados = _con_base(todos)
    respaldados = set(evidencia) | set(estimados)
    fisica = _fisica(borrador, respaldados)
    quedan = {k for k in respaldados if not k.startswith("fisica.") or (fisica and k[len("fisica."):] in fisica)}
    robot_id = slug(fabricante, nombre)
    if not robot_id:
        raise FichaInvalida("no se pudo armar un id con el fabricante y el nombre")
    ficha = {
        "version": 1, "id": robot_id, "nombre": nombre, "fabricante": fabricante, "ficticio": False,
        **specs, "fuente": {"url": fuente_url, "consultado": hoy}, "origen": "busqueda",
        "capacidades": [c for c in (limpio(x, LARGO_NOMBRE) for x in borrador.get("capacidades") or []) if c],
        "evidencia": {k: v for k, v in evidencia.items() if k in quedan},
        **({"estimados": {k: v for k, v in estimados.items() if k in quedan}}
           if any(k in quedan for k in estimados) else {}),
        **({"fisica": fisica} if fisica else {}),
    }
    try:
        return validar_ficha(ficha)
    except ValueError as e:
        raise FichaInvalida(str(e)) from None


def _clave_nombre(ficha: dict) -> tuple[str, str]:
    return normalizado(ficha["fabricante"]), normalizado(ficha["nombre"])


def revisar(borradores: list[dict], conocidas: dict[str, dict], hoy: str, max_robots: int) -> Revision:
    """Borradores → fichas válidas (hasta max_robots), inválidas con su motivo y nombres que quedaron sobre el tope."""
    por_nombre = {_clave_nombre(f): i for i, f in conocidas.items()}
    fichas: list[dict] = []
    invalidas: list[dict] = []
    sobrantes: list[str] = []
    for b in borradores:
        etiqueta = limpio(b.get("nombre"), LARGO_NOMBRE) or "(sin nombre)"
        try:
            ficha = ficha_desde_borrador(b, hoy)
        except FichaInvalida as e:
            invalidas.append({"nombre": etiqueta, "motivo": str(e)})
            continue
        repetida = ficha["id"] if ficha["id"] in conocidas else por_nombre.get(_clave_nombre(ficha))
        de_esta = next((f["id"] for f in fichas if f["id"] == ficha["id"] or _clave_nombre(f) == _clave_nombre(ficha)),
                       None)
        if repetida:
            invalidas.append({"nombre": etiqueta, "motivo": f"duplicado de un robot conocido ({repetida})"})
        elif de_esta:
            invalidas.append({"nombre": etiqueta, "motivo": f"duplicado de otro borrador de esta búsqueda ({de_esta})"})
        elif len(fichas) >= max_robots:
            sobrantes.append(ficha["nombre"])
        else:
            fichas.append(ficha)
    return Revision(fichas, invalidas, sobrantes)


# ---------- Llamada A: investigar (con búsqueda web) ----------

def _cliente():
    import anthropic
    return anthropic.Anthropic(max_retries=0)  # lee ANTHROPIC_API_KEY; sin reintentos: hay un tiempo tope


def _notas_de(bloques: list) -> list[str]:
    partes = []
    for b in bloques:
        if getattr(b, "type", None) != "text":
            continue
        partes.append(b.text)
        for c in getattr(b, "citations", None) or []:
            if getattr(c, "type", None) == "web_search_result_location":
                partes.append(f" [fuente: {c.url} — «{c.cited_text}»]")
    return partes


def investigar(*, modelo: str, texto: str, max_consultas: int, tiempo_s: float,
               reloj: Callable[[], float] = time.monotonic) -> Notas:
    """Notas de investigación. `cortada` si se acabó el tiempo o los tokens antes de que el modelo terminara."""
    cliente, inicio = _cliente(), reloj()
    mensajes: list[dict] = [{"role": "user", "content": texto}]
    partes: list[str] = []
    while True:
        restante = tiempo_s - (reloj() - inicio)
        if restante <= 0:
            return Notas("".join(partes)[:LARGO_NOTAS], True)
        resp = cliente.messages.create(
            model=modelo, max_tokens=MAX_TOKENS, system=SISTEMA_INVESTIGAR, messages=mensajes, timeout=restante,
            tools=[{"type": HERRAMIENTA_WEB, "name": "web_search", "max_uses": max_consultas}])
        if resp.stop_reason == "refusal":
            raise ErrorAgente(f"el modelo rechazó la búsqueda: {getattr(resp.stop_details, 'explanation', '')}")
        partes = [*partes, *_notas_de(resp.content)]
        if resp.stop_reason == "pause_turn":   # el servidor pausó un turno largo: se reenvía tal cual
            mensajes = [*mensajes, {"role": "assistant", "content": resp.content}]
            continue
        return Notas("".join(partes)[:LARGO_NOTAS], resp.stop_reason == "max_tokens")


# ---------- Llamada B: fichar (salida estructurada) ----------

def esquema_borradores() -> dict:
    """Lo que devuelve el modelo. Listas en vez de objetos con claves libres: la API no los acepta."""
    numero_o_nulo = {"type": ["number", "null"]}

    def filas(campos: dict) -> dict:
        return {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                           "required": list(campos), "properties": campos}}
    robot = {
        "nombre": {"type": "string"}, "fabricante": {"type": "string"},
        "tipo": {"enum": [*_ROBOT["tipo"]["enum"], None]}, "efector": {"enum": [*_ROBOT["efector"]["enum"], None]},
        "carga_util_kg": numero_o_nulo, "alcance_m": numero_o_nulo, "velocidad_base_m_s": numero_o_nulo,
        "fuente_url": {"type": "string"}, "capacidades": {"type": "array", "items": {"type": "string"}},
        "evidencias": filas({"campo": {"enum": list(CAMPOS_CON_FUENTE)}, "url": {"type": "string"},
                             "cita": {"type": "string"}}),
        "estimados": filas({"campo": {"enum": list(CAMPOS_CON_FUENTE)}, "motivo": {"type": "string"}}),
        "fisica": filas({"campo": {"enum": list(CAMPOS_FISICA)}, "valor": {"type": "number"}}),
        "traccion": {"enum": [*_ROBOT["fisica"]["properties"]["traccion"]["enum"], None]},
    }
    return {"type": "object", "additionalProperties": False, "required": ["robots"],
            "properties": {"robots": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                 "required": list(robot), "properties": robot}}}}


def fichar(*, modelo: str, notas: str, max_robots: int, tiempo_s: float) -> list[dict]:
    texto = f"Tope de robots: {max_robots}\n\nNotas de la búsqueda web:\n{notas}"
    datos = pedir_json(modelo=modelo, sistema=SISTEMA_FICHAR, esquema=esquema_borradores(),
                       contenido=[{"type": "text", "text": texto}], tiempo_s=tiempo_s)
    return list(datos["robots"])


# ---------- El paso completo ----------

def texto_investigar(requisitos: dict, tarea: dict, conocidas: dict[str, dict], max_robots: int) -> str:
    lista = [{"id": f["id"], "nombre": f["nombre"], "fabricante": f["fabricante"]} for f in conocidas.values()]
    return (f"requisitos.json:\n{json.dumps(requisitos, ensure_ascii=False)}\n\n"
            f"tarea.json:\n{json.dumps(tarea, ensure_ascii=False)}\n\n"
            f"Robots conocidos (no los busques):\n{json.dumps(lista, ensure_ascii=False)}\n\n"
            f"Tope de robots: {max_robots}")


def _omitida(detalle: str) -> Resultado:
    return Resultado("omitida", detalle, [], [])


def _detalle(rev: Revision, notas: Notas, max_robots: int) -> str:
    partes = [f"{len(rev.fichas)} fichas válidas y {len(rev.invalidas)} inválidas"]
    if rev.sobrantes:
        partes.append(f"tope de {max_robots} robots: quedaron fuera {', '.join(rev.sobrantes)}")
    if notas.cortada:
        partes.append("se acabó el tiempo o el largo de la investigación antes de terminarla")
    return "; ".join(partes) + "."


def buscar(modo: str, modelo: str, requisitos: dict, tarea: dict, conocidas: dict[str, dict], parametros: Parametros,
           hoy: str | None = None, reloj: Callable[[], float] = time.monotonic) -> Resultado:
    """Corre el paso 2. Nunca lanza: una falla queda como estado `fallida` con su detalle."""
    if modo == "fijo":
        return _omitida("Modo fijo: sin LLM ni búsqueda web. Los candidatos son las fichas conocidas.")
    if not parametros.activa:
        return _omitida("VIAZ_BUSQUEDA=0: búsqueda apagada. Los candidatos son las fichas conocidas.")
    inicio = reloj()
    try:
        notas = investigar(modelo=modelo, texto=texto_investigar(requisitos, tarea, conocidas, parametros.max_robots),
                           max_consultas=parametros.max_consultas, tiempo_s=parametros.tiempo_s)
        if not notas.texto.strip():
            raise ErrorAgente("la investigación terminó sin notas")
        restante = parametros.tiempo_s - (reloj() - inicio)
        if restante <= 0:
            raise ErrorAgente(f"se acabó el tiempo ({parametros.tiempo_s} s) antes de fichar")
        borradores = fichar(modelo=modelo, notas=notas.texto, max_robots=parametros.max_robots, tiempo_s=restante)
    except Exception as e:
        log.warning("búsqueda fallida: %s: %s", type(e).__name__, e)
        return Resultado("fallida", limpio(f"{type(e).__name__}: {e}", LARGO_TEXTO), [], [])
    rev = revisar(borradores, conocidas, hoy or dt.date.today().isoformat(), parametros.max_robots)
    for i in rev.invalidas:
        log.warning("búsqueda: ficha inválida %s: %s", i["nombre"], i["motivo"])
    estado = "cortada" if rev.sobrantes or notas.cortada else "completa"
    return Resultado(estado, _detalle(rev, notas, parametros.max_robots), rev.invalidas, rev.fichas)
