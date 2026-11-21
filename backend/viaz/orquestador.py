"""Orquestador de agentes (Render Background Worker).

    python -m viaz.orquestador

Toma corridas en_cola, corre los agentes en orden, encola los trabajos de GPU y espera al sim runner.
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy import insert, select, update

from . import agentes, catalogo
from . import almacen as alm
from . import db
from .config import Config, cargar
from .esquemas import validar

log = logging.getLogger("viaz.orquestador")


class Corrida:
    def __init__(self, cfg: Config, eng, store: alm.Almacen, fila: dict):
        self.cfg, self.eng, self.store = cfg, eng, store
        self.id = fila["id"]
        self.proyecto_id = fila["proyecto_id"]
        self.etapas = fila["etapas"]
        self.etapa_actual: str | None = None

    # ---- archivos ----
    def escribir(self, archivo: str, contenido: dict | str):
        texto = json.dumps(contenido, ensure_ascii=False, indent=2) if isinstance(contenido, dict) else contenido
        tipo = "application/json" if archivo.endswith(".json") else "text/plain"
        self.store.escribir(alm.clave_corrida(self.id, archivo), texto.encode("utf-8"), tipo)

    def leer_json(self, archivo: str) -> dict:
        return json.loads(self.store.leer(alm.clave_corrida(self.id, archivo)))

    def existe(self, archivo: str) -> bool:
        return self.store.existe(alm.clave_corrida(self.id, archivo))

    # ---- estado ----
    def guardar(self, **campos):
        with self.eng.begin() as cx:
            cx.execute(update(db.corridas).where(db.corridas.c.id == self.id)
                       .values(etapas=self.etapas, actualizado=db.ahora(), **campos))

    def etapa(self, nombre: str, estado: str, artefactos: list[str] | None = None, estado_corrida: str | None = None):
        for e in self.etapas:
            if e["nombre"] == nombre:
                e["estado"] = estado
                if artefactos is not None:
                    e["artefactos"] = artefactos
        self.etapas = [dict(e) for e in self.etapas]  # copia nueva: SQLAlchemy detecta el cambio del JSON
        self.etapa_actual = nombre if estado == "en_curso" else self.etapa_actual
        self.guardar(**({"estado": estado_corrida} if estado_corrida else {}))

    # ---- GPU ----
    def trabajo_gpu(self, tipo: str, entradas: list[str], salidas: list[str]) -> None:
        tid = db.nuevo_id()
        with self.eng.begin() as cx:
            cx.execute(insert(db.trabajos).values(id=tid, corrida_id=self.id, tipo=tipo,
                                                  entradas=entradas, salidas=salidas))
        log.info("corrida %s: encolé %s (%s)", self.id, tipo, tid)
        limite = time.monotonic() + self.cfg.espera_trabajo_s
        while time.monotonic() < limite:
            with self.eng.connect() as cx:
                t = cx.execute(select(db.trabajos.c.estado, db.trabajos.c.error)
                               .where(db.trabajos.c.id == tid)).mappings().first()
            if t["estado"] == "ok":
                return
            if t["estado"] == "error":
                raise agentes.ErrorAgente(f"el sim runner falló en {tipo}: {t['error']}")
            time.sleep(1)
        raise agentes.ErrorAgente(f"el sim runner no terminó {tipo} en {self.cfg.espera_trabajo_s} s (¿pod apagado?)")


def procesar(cfg: Config, eng, store: alm.Almacen, fila: dict) -> None:
    c = Corrida(cfg, eng, store, fila)
    modo, modelo = cfg.agentes, cfg.modelo
    with eng.connect() as cx:
        proyecto = dict(cx.execute(select(db.proyectos).where(db.proyectos.c.id == c.proyecto_id)).mappings().first())

    # 1 y 2. Entorno y tarea (comparten los frames de los videos)
    c.etapa("entorno", "en_curso", estado_corrida="analizando_entorno")
    frames = None
    if modo == "claude":
        videos = [store.leer(v) for v in proyecto["videos"] if store.existe(v)]
        frames = agentes.frames_de_videos(videos) if videos else None
    entorno = agentes.entorno(modo, modelo, proyecto, frames)
    c.escribir("entorno.json", entorno)
    c.trabajo_gpu("generar_escena", ["entorno.json"], ["escena.usd"])
    c.etapa("entorno", "listo", ["entorno.json", "escena.usd"])

    c.etapa("tarea", "en_curso")
    tarea = agentes.tarea(modo, modelo, proyecto, entorno, frames)
    c.escribir("tarea.json", tarea)
    c.etapa("tarea", "listo", ["tarea.json"])

    # 3. Robot
    c.etapa("robot", "en_curso", estado_corrida="eligiendo_robot")
    robot = agentes.robot(modo, modelo, entorno, tarea, catalogo.cargar())
    c.escribir("robot.json", robot)
    c.etapa("robot", "listo", ["robot.json"])

    # 4. Clon
    c.etapa("clon", "en_curso", estado_corrida="clonando")
    clon, urdf_txt = agentes.clon(robot)
    c.escribir("robot.urdf", urdf_txt)
    c.escribir("clon.json", clon)
    c.trabajo_gpu("validar_clon", ["entorno.json", "escena.usd", "clon.json", "robot.urdf"], ["validacion.json"])
    validacion = c.leer_json("validacion.json")
    if not validacion.get("ok"):
        raise agentes.ErrorAgente(f"el clon no pasó la validación en la escena: {validacion.get('problemas')}")
    clon["validado_en_escena"] = True
    c.escribir("clon.json", validar("clon", clon))
    c.etapa("clon", "listo", ["clon.json", "robot.urdf", "validacion.json"])

    # 5. Inteligencia
    c.etapa("inteligencia", "en_curso", estado_corrida="simulando")
    c.trabajo_gpu("ejecutar_tarea",
                  ["entorno.json", "tarea.json", "clon.json", "robot.urdf", "escena.usd"],
                  ["resultado.json", "trayectoria.json", "video.mp4"])
    resultado = validar("resultado", c.leer_json("resultado.json"))
    validar("trayectoria", c.leer_json("trayectoria.json"))
    artefactos = ["resultado.json", "trayectoria.json"] + (["video.mp4"] if resultado["video"] and c.existe("video.mp4") else [])
    c.etapa("inteligencia", "listo", artefactos, estado_corrida="listo")
    log.info("corrida %s lista: %s", c.id, resultado["metricas"])


def procesar_una(cfg: Config, eng, store: alm.Almacen) -> bool:
    """Procesa una corrida en cola. Devuelve False si no había ninguna."""
    fila = db.tomar_con_lock(eng, db.corridas, db.corridas.c.estado == "en_cola",
                             {"estado": "analizando_entorno", "actualizado": db.ahora()})
    if fila is None:
        return False
    log.info("corrida %s: empiezo", fila["id"])
    c = None
    try:
        procesar(cfg, eng, store, fila)
    except Exception as e:  # la corrida queda en error con el motivo; el orquestador sigue con la siguiente
        log.exception("corrida %s falló", fila["id"])
        with eng.connect() as cx:
            etapas = cx.execute(select(db.corridas.c.etapas).where(db.corridas.c.id == fila["id"])).scalar_one()
        etapas = [{**e, "estado": "error"} if e["estado"] == "en_curso" else e for e in etapas]
        with eng.begin() as cx:
            cx.execute(update(db.corridas).where(db.corridas.c.id == fila["id"])
                       .values(estado="error", error=f"{type(e).__name__}: {e}"[:2000], etapas=etapas, actualizado=db.ahora()))
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = cargar()
    eng, store = db.motor(cfg.db_url), alm.crear(cfg)
    log.info("orquestador listo (agentes=%s, almacén=%s)", cfg.agentes, cfg.almacen)
    while True:
        if not procesar_una(cfg, eng, store):
            time.sleep(2)


if __name__ == "__main__":
    main()
