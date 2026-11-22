"""Orquestador de agentes (Render Background Worker).

    python -m viaz.orquestador

Toma corridas en_cola, corre los agentes en orden, encola los trabajos de GPU y espera al sim runner.

Dos flujos (VIAZ_FLUJO):
- rl (demo): entorno y tarea a mano → selección de robot → agente constructor → entrenar (con el monitor)
  → grabar clips → evaluar. Ver docs/requerimientos.md §1.1.
- planificador (anterior): agentes Entorno y Tarea → robot → clon determinista → ejecutar_tarea.
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy import insert, select, update

from pathlib import Path

from . import agentes, catalogo, monitor, urdf
from . import robot_cfg as rc
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
        tipo = {"json": "application/json", "jsonl": "application/x-ndjson", "py": "text/x-python"}.get(
            archivo.rsplit(".", 1)[-1], "text/plain")
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
    def trabajo_gpu(self, tipo: str, entradas: list[str], salidas: list[str], parametros: dict | None = None,
                    espera_s: float | None = None, al_esperar=None) -> str:
        tid = db.nuevo_id()
        with self.eng.begin() as cx:
            cx.execute(insert(db.trabajos).values(id=tid, corrida_id=self.id, tipo=tipo,
                                                  entradas=entradas, salidas=salidas, parametros=parametros or {}))
        log.info("corrida %s: encolé %s (%s)", self.id, tipo, tid)
        espera = espera_s if espera_s is not None else self.cfg.espera_trabajo_s
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if al_esperar is not None:
                al_esperar(tid)
            with self.eng.connect() as cx:
                t = cx.execute(select(db.trabajos.c.estado, db.trabajos.c.error)
                               .where(db.trabajos.c.id == tid)).mappings().first()
            if t["estado"] == "ok":
                return tid
            if t["estado"] == "error":
                raise agentes.ErrorAgente(f"el sim runner falló en {tipo}: {t['error']}")
            time.sleep(min(1.0, max(0.05, espera / 1000)))
        raise agentes.ErrorAgente(f"el sim runner no terminó {tipo} en {espera:.0f} s (¿pod apagado?)")


def medir_videos(c: Corrida, cfg: Config, store: alm.Almacen, proyecto: dict) -> tuple[dict | None, bytes | None]:
    """Trabajo de GPU medir_entorno sobre los videos del proyecto (sim/medir_entorno.py). Sin VIAZ_MEDIR: (None, None).

    Copia los videos a la carpeta de la corrida (el pod solo baja archivos de la corrida). Si el pod falla, el
    agente sigue sin medidas: la corrida no se cae por la medición.
    """
    claves = [v for v in proyecto["videos"] if store.existe(v)]
    if not cfg.medir or not claves:
        return None, None
    nombres = []
    for i, clave in enumerate(claves):
        nombre = f"video_{i}{Path(clave).suffix or '.mp4'}"
        store.escribir(alm.clave_corrida(c.id, nombre), store.leer(clave), "video/mp4")
        nombres.append(nombre)
    parametros = {"frames": 64, "altura_camara_m": cfg.altura_camara_m,
                  **({"largo_panel_m": cfg.largo_panel_m} if cfg.largo_panel_m else {}),
                  **({"escala_panel_m": cfg.escala_panel_m} if cfg.escala_panel_m else {})}
    try:
        c.trabajo_gpu("medir_entorno", nombres, ["medidas_entorno.json", "medidas_vista.png"], parametros, espera_s=1800)
        medidas = validar("medidas_entorno", c.leer_json("medidas_entorno.json"))
    except (agentes.ErrorAgente, ValueError) as e:
        log.warning("corrida %s: la medición falló, el agente sigue sin medidas: %s", c.id, e)
        return {"version": 1, "disponible": False, "fuente": "medir_entorno", "frames": 0, "campos": {},
                "avisos": [], "error": str(e)[:500]}, None
    clave_vista = alm.clave_corrida(c.id, "medidas_vista.png")
    vista = store.leer(clave_vista) if medidas.get("disponible") and store.existe(clave_vista) else None
    log.info("corrida %s: medí %s campos en %s frames (%s)", c.id, len(medidas["campos"]), medidas["frames"], medidas["fuente"])
    return medidas, vista


def analizar_entorno(c: Corrida, cfg: Config, store: alm.Almacen, proyecto: dict) -> tuple[dict, list | None, list[str]]:
    """Agente Entorno: mide los videos (si VIAZ_MEDIR) y arma entorno.json. Devuelve (entorno, frames, artefactos)."""
    medidas, vista = medir_videos(c, cfg, store, proyecto)
    frames = None
    if cfg.agentes == "claude":
        videos = [store.leer(v) for v in proyecto["videos"] if store.existe(v)]
        frames = agentes.frames_de_videos(videos) if videos else None
    entorno = agentes.entorno(cfg.agentes, cfg.modelo, proyecto, frames, medidas, vista)
    c.escribir("entorno.json", entorno)
    artefactos = []
    if medidas is not None:
        artefactos.append("medidas_entorno.json")
        if vista is not None:
            artefactos.append("medidas_vista.png")
    return entorno, frames, artefactos


def elegir_robot(c: Corrida, cfg: Config, entorno: dict, tarea: dict) -> dict:
    """Etapa robot (selección v3, pasos 1, 3 y 4)."""
    c.etapa("robot", "en_curso", estado_corrida="eligiendo_robot")
    r = agentes.seleccionar(cfg.agentes, cfg.modelo, entorno, tarea, catalogo.cargar(), cfg.max_finalistas)
    c.escribir("requisitos.json", r.requisitos)
    c.escribir("seleccion.json", r.seleccion)
    primero, *sin_correr = r.robots_por_puesto
    c.escribir("robot.json", primero)
    log.info("corrida %s: sigue con %s; finalistas sin correr: %s", c.id, primero["id"],
             ", ".join(x["id"] for x in sin_correr) or "ninguno")
    c.etapa("robot", "listo", ["requisitos.json", "seleccion.json", "robot.json"])
    return primero


def exigir_pipeline(entorno: dict) -> None:
    """El mapeo sirve para cualquier espacio; Tarea → Inteligencia todavía solo existe para algunos tipos."""
    if entorno["tipo"] not in agentes.TIPOS_CON_PIPELINE:
        raise agentes.ErrorAgente(
            f"entorno.json y escena.usd listos para '{entorno['tipo']}', pero las etapas siguientes "
            f"solo soportan: {', '.join(sorted(agentes.TIPOS_CON_PIPELINE))}")


def procesar(cfg: Config, eng, store: alm.Almacen, fila: dict) -> None:
    if cfg.flujo == "rl":
        return procesar_rl(cfg, eng, store, fila)
    c = Corrida(cfg, eng, store, fila)
    modo, modelo = cfg.agentes, cfg.modelo
    with eng.connect() as cx:
        proyecto = dict(cx.execute(select(db.proyectos).where(db.proyectos.c.id == c.proyecto_id)).mappings().first())

    # 1 y 2. Entorno y tarea (comparten los frames de los videos)
    c.etapa("entorno", "en_curso", estado_corrida="analizando_entorno")
    entorno, frames, artefactos = analizar_entorno(c, cfg, store, proyecto)
    c.trabajo_gpu("generar_escena", ["entorno.json"], ["escena.usd"])
    c.etapa("entorno", "listo", ["entorno.json", "escena.usd", *artefactos])
    exigir_pipeline(entorno)

    c.etapa("tarea", "en_curso")
    tarea = agentes.tarea(modo, modelo, proyecto, entorno, frames)
    c.escribir("tarea.json", tarea)
    c.etapa("tarea", "listo", ["tarea.json"])

    # 3. Robot
    robot = elegir_robot(c, cfg, entorno, tarea)

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


# ---------- Flujo del demo con RL ----------

ENTRADAS_RL = ["entorno.json", "tarea.json", "robot_cfg.py", "clon.json", "escena.usd"]
TOLERANCIAS = "0.05:5,0.02:2"   # RF-INT-11 (entrenamiento) y RF-INT-20 (cifra adicional)


def _manual(ruta: str, fixture: str) -> dict:
    """entorno.json o tarea.json escritos a mano (RF-MAP-11, RF-TAR-04). Sin ruta: el fixture de ejemplo."""
    p = Path(ruta) if ruta else agentes.FIXTURES / f"{fixture}.json"
    return json.loads(p.read_text(encoding="utf-8"))


class Vigia:
    """Corre el monitor mientras el pod entrena: lee métricas de la API, escribe monitoreo.jsonl y hitos.json, avisa."""

    def __init__(self, c: Corrida, cfg: Config):
        self.c, self.cfg = c, cfg
        self.todas: list[dict] = []
        self.chequeos: list[dict] = []
        self.hitos_antes: dict = {}
        self.avisador = monitor.Avisador(cfg.discord_webhook)
        self.proximo = time.monotonic() + cfg.monitor_s

    def _nuevas(self) -> list[dict]:
        desde = self.todas[-1]["iteracion"] if self.todas else -1
        with self.c.eng.connect() as cx:
            filas = cx.execute(select(db.metricas.c.datos)
                               .where(db.metricas.c.corrida_id == self.c.id, db.metricas.c.iteracion > desde)
                               .order_by(db.metricas.c.iteracion)).scalars().all()
        self.todas.extend(filas)
        return list(filas)

    def chequear(self, tid: str | None = None, forzar: bool = False) -> dict | None:
        if not forzar and time.monotonic() < self.proximo:
            return None
        self.proximo = time.monotonic() + self.cfg.monitor_s
        nuevas = self._nuevas()
        if not self.todas:
            return None
        ch = monitor.chequear(self.cfg.agentes, self.cfg.modelo, nuevas, self.todas, self.chequeos,
                              self.cfg.horas_entrenamiento, self.hitos_antes)
        if forzar and ch["estado"] != "terminado":
            ch = {**ch, "estado": "terminado", "hito": "fin", "recomendacion": "detener",
                  "detalle": f"Terminó el entrenamiento. Mejor éxito: {monitor.hitos(self.todas)['mejor_tasa_exito'] or 0:.0%}. "
                             f"Checkpoint recomendado: {ch['checkpoint_recomendado']}."}
        self.chequeos.append(ch)
        self.hitos_antes = monitor.hitos(self.todas)
        self.c.escribir("monitoreo.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in self.chequeos))
        self.c.escribir("hitos.json", validar("hitos", self.hitos_antes))
        self.avisador.avisar(ch, self.cfg.horas_entrenamiento)
        # RNF-17: 90 % en 3 chequeos seguidos o tiempo agotado → el sistema pide detener. Lo demás lo decide el equipo.
        if tid and ch["estado"] == "terminado" and not forzar:
            with self.c.eng.begin() as cx:
                cx.execute(update(db.trabajos).where(db.trabajos.c.id == tid).values(detener=True))
        log.info("corrida %s: monitor %s (%s) %s", self.c.id, ch["estado"], ch["recomendacion"], ch["detalle"])
        return ch


def _clips(h: dict, ultima: int) -> list[dict]:
    """Checkpoints de los clips del video acelerado (RF-INT-13)."""
    clips = [{"iteracion": 0, "etiqueta": "Inicio: el robot todavía no sabe nada"}]
    primero = h["primer_exito"] if h["primer_exito"] is not None else ultima // 4
    clips.append({"iteracion": primero, "etiqueta": "Primeros éxitos" if h["primer_exito"] is not None else "25 % del entrenamiento"})
    if h["exito_50"] is not None:
        clips.append({"iteracion": h["exito_50"], "etiqueta": "Supera el 50 % de éxito"})
    final = h["umbral_alcanzado"] if h["umbral_alcanzado"] is not None else h["mejor_recompensa"]
    clips.append({"iteracion": final if final is not None else ultima,
                  "etiqueta": "Supera el 90 % de éxito" if h["umbral_alcanzado"] is not None else "Mejor resultado"})
    return clips


def construir_robot(c: Corrida, cfg: Config, robot: dict, entorno: dict, tarea: dict) -> list[str]:
    """Agente constructor con hasta N intentos (RF-CLO-05). Si no logra un robot válido, usa el ensamblaje
    por defecto, sin LLM (RF-CLO-07). Devuelve los artefactos de la etapa."""
    assets = rc.cargar_assets()
    necesario = agentes.alcance_necesario(entorno, robot)
    previo, problemas = None, []
    rechazados: list[dict] = []   # intentos que no llegan al pod: van como tarjetas en construccion.mp4
    total = cfg.intentos_constructor
    candidatos = [("agente", i) for i in range(1, total + 1)] + [("determinista", total + 1)]
    for metodo, intento in candidatos:
        titulo = (f"Intento {intento} de {total} del agente constructor" if metodo == "agente"
                  else "Respaldo: ensamblaje por defecto, sin LLM")
        try:
            ens = (agentes.constructor(cfg.agentes, cfg.modelo, robot, entorno, tarea, assets, intento, problemas, previo)
                   if metodo == "agente" else validar("ensamblaje", rc.ensamblaje_por_defecto(robot, assets)))
        except agentes.ErrorAgente as e:
            problemas, previo = [f"respuesta inválida del agente: {e}"], None
            rechazados.append({"intento": intento, "titulo": titulo, "lineas": ["Respuesta inválida del agente.", str(e)[:90]]})
            continue
        problemas = rc.problemas(ens, robot, assets, necesario)
        pieza = (f"{ens['brazo']['asset'].upper()} ×{ens['brazo']['escala_alcance']:.2f} + "
                 f"{ens['efector']['asset'].replace('_', ' ')} sobre {ens['base']['asset'].replace('_', ' ')}")
        if problemas:
            rechazados.append({"intento": intento, "titulo": titulo,
                               "lineas": [pieza, "Rechazado por las reglas antes de ir a Isaac:", *[x[:95] for x in problemas[:3]]]})
        if not problemas:
            clon = rc.clon(ens, robot, assets, intento)
            if metodo == "determinista":
                clon["construccion"] = {**clon["construccion"], "metodo": "determinista"}
                clon["diferencias_con_real"].insert(0, "el agente constructor no logró un robot válido: se usó el ensamblaje por defecto")
            c.escribir("ensamblaje.json", ens)
            c.escribir("robot_cfg.py", rc.generar(ens, assets))
            c.escribir("clon.json", validar("clon", clon))
            c.escribir("robot.urdf", urdf.generar(robot["id"], clon["escala"]["alcance_m"], robot.get("fisica")))
            c.trabajo_gpu("validar_robot", ["entorno.json", "tarea.json", "escena.usd", "robot_cfg.py", "clon.json"],
                          ["validacion.json", "construccion.mp4"],
                          {"intento": intento, "etiqueta": titulo, "pieza": pieza, "rechazados": rechazados})
            v = c.leer_json("validacion.json")
            if v.get("ok"):
                clon["validado_en_escena"] = True
                c.escribir("clon.json", validar("clon", clon))
                log.info("corrida %s: robot construido (%s, intento %s)", c.id, metodo, intento)
                return ["ensamblaje.json", "robot_cfg.py", "clon.json", "robot.urdf", "validacion.json"] + \
                    (["construccion.mp4"] if c.existe("construccion.mp4") else [])
            problemas = v.get("problemas") or ["validar_robot falló sin detalle"]
        log.info("corrida %s: constructor %s intento %s con problemas: %s", c.id, metodo, intento, problemas)
        previo = ens
    raise agentes.ErrorAgente(f"no se pudo construir un robot válido: {problemas}")


def procesar_rl(cfg: Config, eng, store: alm.Almacen, fila: dict) -> None:
    c = Corrida(cfg, eng, store, fila)
    with eng.connect() as cx:
        proyecto = dict(cx.execute(select(db.proyectos).where(db.proyectos.c.id == c.proyecto_id)).mappings().first())

    # 1. Entorno + escena. Con VIAZ_MEDIR y videos, lo mide el agente Entorno; si no, se lee a mano (RF-MAP-11).
    c.etapa("entorno", "en_curso", estado_corrida="analizando_entorno")
    artefactos: list[str] = []
    if cfg.medir and proyecto["videos"] and not cfg.entorno_manual:
        entorno, _, artefactos = analizar_entorno(c, cfg, store, proyecto)
    else:
        entorno = _manual(cfg.entorno_manual, "entorno")
        entorno["videos"] = [v.rsplit("/", 1)[1] for v in proyecto["videos"]] or entorno.get("videos", [])
        c.escribir("entorno.json", validar("entorno", entorno))
    c.trabajo_gpu("generar_escena", ["entorno.json"], ["escena.usd"])
    c.etapa("entorno", "listo", ["entorno.json", "escena.usd", *artefactos])
    exigir_pipeline(entorno)

    # 2. Tarea escrita a mano
    c.etapa("tarea", "en_curso")
    tarea = agentes.revisar_tarea(_manual(cfg.tarea_manual, "tarea"), entorno)   # esquema + reglas 2 a 6 del contrato
    c.escribir("tarea.json", tarea)
    c.etapa("tarea", "listo", ["tarea.json"])

    # 3. Selección de robot
    robot = elegir_robot(c, cfg, entorno, tarea)

    # 4. Agente constructor
    c.etapa("clon", "en_curso", estado_corrida="clonando")
    c.etapa("clon", "listo", construir_robot(c, cfg, robot, entorno, tarea))

    # 5. Entrenamiento (con el monitor), clips y evaluación
    c.etapa("inteligencia", "en_curso", estado_corrida="entrenando")
    vigia = Vigia(c, cfg)
    latido_s = max(1.0, min(300.0, cfg.monitor_s / 2))
    c.trabajo_gpu("entrenar", ENTRADAS_RL, ["curva.json", "checkpoints.json"],
                  {"horas": cfg.horas_entrenamiento, "tolerancia_pos_m": 0.05, "tolerancia_ang_grados": 5, "latido_s": latido_s},
                  espera_s=cfg.horas_entrenamiento * 3600 + 3600, al_esperar=vigia.chequear)
    if not vigia.chequeos or vigia.chequeos[-1]["estado"] != "terminado":
        vigia.chequear(forzar=True)  # chequeo final con el resumen (RF-MON-07)
    ckpts = c.leer_json("checkpoints.json")
    h = monitor.hitos(vigia.todas) if vigia.todas else {**monitor.hitos([]), "ultima_iteracion": ckpts["ultima_iteracion"]}
    c.escribir("hitos.json", validar("hitos", h))

    c.guardar(estado="evaluando")
    c.trabajo_gpu("grabar_clips", ENTRADAS_RL, ["entrenamiento_rapido.mp4", "video_info.json"],
                  {"clips": _clips(h, ckpts["ultima_iteracion"]), "segundos": 7}, espera_s=3 * 3600)
    mejor = max(vigia.todas, key=lambda m: (m.get("tasa_exito") or 0, m["iteracion"]))["iteracion"] if vigia.todas else None
    c.trabajo_gpu("evaluar", ENTRADAS_RL,
                  ["resultado.json", "evaluacion.json", "video.mp4", "trayectoria.json", "politica.pt"],
                  {"checkpoint": mejor, "episodios": cfg.episodios_evaluacion, "tolerancias": TOLERANCIAS}, espera_s=3 * 3600)
    resultado = c.leer_json("resultado.json")
    info = c.leer_json("video_info.json")
    resultado["entrenamiento"]["factor_video"] = info.get("factor_video")
    if resultado["metricas"]["tasa_exito"] < 0.5:
        resultado["notas"] += " Bajo 50 %: corresponde el plan B con planificador (RF-INT-01)."
    c.escribir("resultado.json", validar("resultado", resultado))
    artefactos = ["resultado.json", "evaluacion.json", "entrenamiento_rapido.mp4", "video_info.json", "curva.json",
                  "hitos.json", "monitoreo.jsonl"]
    artefactos += [a for a in ("video.mp4", "trayectoria.json") if c.existe(a)]
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
