"""Corridas hijas: una por finalista (selección v3, paso 5). Contrato: docs/agentes/seleccion-robot.md.

Cada hija es una fila de `corridas` con `padre_id`. Nunca nace en `en_cola`: la corre su padre, en orden, dentro de
su propio proceso. Recibe una copia de la escena del padre y el robot.json de su finalista.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from . import almacen as alm
from . import comparacion, db
from .corrida import Corrida

log = logging.getLogger("viaz.orquestador")

Artefactos = tuple[list[str], list[str]]  # de la etapa clon y de la etapa inteligencia
EtapasTrasSeleccion = Callable[[Corrida, dict, str], Artefactos]  # (corrida, robot, etiqueta del aviso)

ARCHIVOS_ESCENA = ("entorno.json", "tarea.json", "escena.usd")
ESTADO_INICIAL = "clonando"


def etapas_iniciales(etapas_padre: list[dict]) -> list[dict]:
    hechas = {"entorno": [a for a in ARCHIVOS_ESCENA if a != "tarea.json"], "tarea": ["tarea.json"],
              "robot": ["robot.json"]}
    return [{"nombre": e["nombre"], "estado": "listo" if e["nombre"] in hechas else "pendiente",
             "artefactos": hechas.get(e["nombre"], [])} for e in etapas_padre]


def copiar_los_que_existen(store: alm.Almacen, origen: str, destino: str, archivos: list[str] | tuple[str, ...]) -> list[str]:
    copiados = [a for a in archivos if store.existe(alm.clave_corrida(origen, a))]
    for a in copiados:
        store.escribir(alm.clave_corrida(destino, a), store.leer(alm.clave_corrida(origen, a)))
    return copiados


def crear(padre: Corrida, robot: dict) -> dict:
    eng, store, cid = padre.eng, padre.store, db.nuevo_id()
    copiar_los_que_existen(store, padre.id, cid, ARCHIVOS_ESCENA)
    store.escribir(alm.clave_corrida(cid, "robot.json"),
                   json.dumps(robot, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
    fila = {"id": cid, "proyecto_id": padre.proyecto_id, "estado": ESTADO_INICIAL, "padre_id": padre.id,
            "etapas": etapas_iniciales(padre.etapas)}
    with eng.begin() as cx:
        cx.execute(insert(db.corridas).values(**fila))
    return fila


def de_padre(eng: Engine, padre_id: str) -> list[dict]:
    with eng.connect() as cx:
        return [dict(f) for f in cx.execute(
            select(db.corridas.c.id, db.corridas.c.estado, db.corridas.c.error)
            .where(db.corridas.c.padre_id == padre_id).order_by(db.corridas.c.creado)).mappings()]


TERMINADAS = ("listo", "error")


def _leer_json(store: alm.Almacen, cid: str, archivo: str) -> dict | None:
    clave = alm.clave_corrida(cid, archivo)
    return json.loads(store.leer(clave)) if store.existe(clave) else None


def hija_visible(eng: Engine, store: alm.Almacen, padre_id: str) -> str | None:
    lista = de_padre(eng, padre_id)
    if not lista:
        return None
    activa = next((h["id"] for h in lista if h["estado"] not in TERMINADAS), None)
    if activa:
        return activa
    def robot_de(cid: str) -> str | None:
        return (_leer_json(store, cid, "robot.json") or {}).get("id")

    robot = robot_de(padre_id)
    por_robot = next((h["id"] for h in lista if robot and robot_de(h["id"]) == robot), None)
    ranking = (_leer_json(store, padre_id, "comparacion.json") or {}).get("ranking") or []
    ids = {h["id"] for h in lista}
    primera = next((f["corrida_id"] for f in ranking if f.get("corrida_id") in ids), None)
    return por_robot or primera or lista[-1]["id"]


def registrar_error(eng: Engine, cid: str, error: Exception) -> str:
    motivo = f"{type(error).__name__}: {error}"[:2000]
    with eng.connect() as cx:
        etapas = cx.execute(select(db.corridas.c.etapas).where(db.corridas.c.id == cid)).scalar_one()
    etapas = [{**e, "estado": "error"} if e["estado"] == "en_curso" else e for e in etapas]
    with eng.begin() as cx:
        cx.execute(update(db.corridas).where(db.corridas.c.id == cid)
                   .values(estado="error", error=motivo, etapas=etapas, actualizado=db.ahora()))
    return motivo


def etiqueta(puesto: int, total: int, robot_id: str) -> str:
    return f"finalista {puesto} de {total}: {robot_id}"


def correr_hija(hija: Corrida, robot: dict, etiqueta_aviso: str,
                etapas: EtapasTrasSeleccion) -> tuple[comparacion.Hija, Artefactos]:
    log.info("corrida %s: %s en la corrida hija %s", hija.padre_id, etiqueta_aviso, hija.id)
    try:
        artefactos = etapas(hija, robot, etiqueta_aviso)
    except Exception as e:
        log.exception("corrida hija %s (%s) falló", hija.id, robot["id"])
        return comparacion.Hija(robot, hija.id, None, None, registrar_error(hija.eng, hija.id, e)), ([], [])
    return (comparacion.Hija(robot, hija.id, hija.leer_json("resultado.json"), hija.leer_json("clon.json"), None),
            artefactos)


def mostrar_ganador(padre: Corrida, comp: dict, artefactos: Artefactos) -> None:
    de_clon, de_inteligencia = artefactos
    ganadora = comp["ranking"][0]["corrida_id"]
    copiar_los_que_existen(padre.store, ganadora, padre.id, [*de_clon, *de_inteligencia, "robot.json"])
    padre.escribir("comparacion.json", comp)
    padre.etapa("clon", "listo", de_clon)
    padre.etapa("inteligencia", "listo", [*de_inteligencia, "comparacion.json"], estado_corrida="listo")


def correr_finalistas(padre: Corrida, robots: list[dict], condiciones: dict, etapas: EtapasTrasSeleccion) -> dict:
    total, horas = len(robots), padre.cfg.horas_entrenamiento
    log.info("corrida %s: %s finalistas en corridas hijas, %s h de entrenamiento cada uno (%s h en total)",
             padre.id, total, horas, total * horas)
    padre.etapa("clon", "en_curso", estado_corrida=ESTADO_INICIAL)
    corridas = [correr_hija(Corrida(padre.cfg, padre.eng, padre.store, crear(padre, robot)), robot,
                            etiqueta(puesto, total, robot["id"]), etapas)
                for puesto, robot in enumerate(robots, start=1)]
    comp = comparacion.explicar(padre.cfg.agentes, padre.cfg.modelo,
                                comparacion.comparar([h for h, _ in corridas], condiciones))
    por_corrida = {h.corrida_id: a for h, a in corridas}
    mostrar_ganador(padre, comp, por_corrida[comp["ranking"][0]["corrida_id"]])
    log.info("corrida %s: ganó %s (%s)", padre.id, comp["ganador"], comp["regla"])
    return comp
