"""Orquestador de agentes (Render Background Worker).

    python -m viaz.orquestador

Toma corridas en_cola, corre los agentes en orden, encola los trabajos de GPU y espera al sim runner.

Dos flujos (VIAZ_FLUJO):
- rl (demo): entorno y tarea a mano → selección de robot → agente constructor → entrenar (con el monitor)
  → grabar clips → evaluar. Ver docs/requerimientos.md §1.1. Con 2 o 3 finalistas, cada uno corre en una corrida
  hija y el código elige al ganador (hijas.py, comparacion.py).
- planificador (anterior): agentes Entorno y Tarea → robot → clon determinista → ejecutar_tarea.
"""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy import select, update

from pathlib import Path

from . import agentes, catalogo, hijas, modelos, monitor, urdf
from .agentes import busqueda
from .catalogo import encontrados
from . import robot_cfg as rc
from . import almacen as alm
from . import db
from .config import Config, cargar
from .corrida import Corrida
from .esquemas import validar

log = logging.getLogger("viaz.orquestador")


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


def parametros_busqueda(cfg: Config) -> busqueda.Parametros:
    return busqueda.Parametros(cfg.busqueda, cfg.busqueda_max_robots, cfg.busqueda_max_consultas, cfg.busqueda_tiempo_s)


def seleccionar_robot(cfg: Config, store: alm.Almacen, entorno: dict,
                      tarea: dict) -> tuple[agentes.Seleccion, list[dict]]:
    """Pasos 1 a 4 de la selección v3. Devuelve la selección y las fichas que trajo la búsqueda en esta corrida."""
    conocidas = encontrados.unir(catalogo.cargar(), encontrados.cargar(store))
    requisitos_de_conocidas = agentes.perfiles.requisitos(entorno, tarea, list(conocidas.values()))
    res = busqueda.buscar(cfg.agentes, cfg.modelo, requisitos_de_conocidas, tarea, conocidas,
                          parametros_busqueda(cfg))
    for ficha in res.fichas:
        try:
            encontrados.guardar(store, ficha)
        except Exception as e:
            log.warning("no pude guardar %s en el catálogo compartido: %s", ficha["id"], e)
    candidatas = {**conocidas, **{f["id"]: f for f in res.fichas}}
    r = agentes.seleccionar(cfg.agentes, cfg.modelo, entorno, tarea, candidatas, cfg.max_finalistas,
                            busqueda=res.bloque(), encontrados=[f["id"] for f in res.fichas])
    return r, res.fichas


def elegir_robot(c: Corrida, cfg: Config, entorno: dict, tarea: dict) -> list[dict]:
    """Etapa robot (selección v3, pasos 1 a 4)."""
    c.etapa("robot", "en_curso", estado_corrida="eligiendo_robot")
    r, nuevas = seleccionar_robot(cfg, c.store, entorno, tarea)
    c.escribir("encontrados.json", json.dumps(nuevas, ensure_ascii=False, indent=2))
    c.escribir("requisitos.json", r.requisitos)
    c.escribir("seleccion.json", r.seleccion)
    c.escribir("robot.json", r.robots_por_puesto[0])
    log.info("corrida %s: búsqueda %s (%s); finalistas: %s", c.id, r.seleccion["busqueda"]["estado"],
             r.seleccion["busqueda"]["detalle"], ", ".join(x["id"] for x in r.robots_por_puesto))
    c.etapa("robot", "listo", ["requisitos.json", "encontrados.json", "seleccion.json", "robot.json"])
    return r.robots_por_puesto


def exigir_pipeline(entorno: dict, tarea: dict | None = None) -> None:
    """Entorno y Tarea sirven para cualquier espacio y tarea; Robot → Inteligencia corre solo si la tarea tiene su
    perfil con simulación (RF-GEN-06). Se llama después de escribir tarea.json: la corrida deja entorno.json,
    escena.usd y tarea.json antes de cortar."""
    if agentes.perfiles.simulable(entorno, tarea):
        return
    listos = "entorno.json, escena.usd" + (" y tarea.json" if tarea else "")
    if tarea is None:
        raise agentes.ErrorAgente(
            f"{listos} listos para '{entorno['tipo']}', pero las etapas siguientes "
            f"solo soportan: {', '.join(agentes.perfiles.tipos_con_simulacion())}")
    pt = agentes.perfil_de_tarea(tarea["tarea"])
    if pt.con_simulacion:
        raise agentes.ErrorAgente(
            f"{listos} listos, pero la tarea '{tarea['tarea']}' solo se simula en entornos "
            f"'{pt.entorno_requerido}' y el entorno es '{entorno['tipo']}'")
    raise agentes.ErrorAgente(
        f"{listos} listos para la tarea '{tarea['tarea']}', pero las etapas siguientes "
        f"solo simulan: {', '.join(agentes.perfiles.tareas_con_simulacion())}. "
        f"Falta el perfil de la tarea '{tarea['tarea']}' (backend/viaz/agentes/perfiles.py y sim/tareas.py)")


def tolerancias(tarea: dict) -> tuple[float, float, str]:
    """Tolerancia de éxito de tarea.json (RF-INT-11) y la cadena de evaluar: esa más la fina del perfil de la tarea
    (RF-INT-20; instalar_panel: 2 cm y 2°). Una tarea sin tolerancia fina se evalúa solo con la suya."""
    ce = tarea["criterios_exito"]
    pos, ang = ce["tolerancia_pos_m"], ce["tolerancia_ang_grados"]
    fina = agentes.perfil_de_tarea(tarea["tarea"]).tolerancia_fina
    return pos, ang, f"{pos:g}:{ang:g}" + (f",{fina[0]:g}:{fina[1]:g}" if fina else "")


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

    c.etapa("tarea", "en_curso")
    tarea = agentes.tarea(modo, modelo, proyecto, entorno, frames)
    c.escribir("tarea.json", tarea)
    c.etapa("tarea", "listo", ["tarea.json"])
    exigir_pipeline(entorno, tarea)

    # 3. Robot
    robot = elegir_robot(c, cfg, entorno, tarea)[0]

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


def _manual(ruta: str, fixture: str) -> dict:
    """entorno.json o tarea.json escritos a mano (RF-MAP-11, RF-TAR-04). Sin ruta: el fixture de ejemplo."""
    p = Path(ruta) if ruta else agentes.FIXTURES / f"{fixture}.json"
    return json.loads(p.read_text(encoding="utf-8"))


class Vigia:
    """Corre el monitor mientras el pod entrena: lee métricas de la API, escribe monitoreo.jsonl y hitos.json, avisa."""

    def __init__(self, c: Corrida, cfg: Config, etiqueta: str = "", tarea: dict | None = None):
        self.c, self.cfg, self.tarea = c, cfg, tarea
        self.todas: list[dict] = []
        self.chequeos: list[dict] = []
        self.hitos_antes: dict = {}
        self.avisador = monitor.Avisador(cfg.discord_webhook, etiqueta=etiqueta, tarea=tarea)
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
                              self.cfg.horas_entrenamiento, self.hitos_antes, self.tarea,
                              tiempo_s=max(10.0, self.cfg.monitor_s / 2), max_llamadas=self.cfg.monitor_max_llamadas)
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


def _titulo_intento(metodo: str, intento: int, total: int) -> str:
    return {"comprobado": "Modelo comprobado en una corrida anterior",
            "agente": f"Intento {intento} de {total} del agente constructor"}.get(
        metodo, "Respaldo: ensamblaje por defecto, sin LLM")


def construir_robot(c: Corrida, cfg: Config, robot: dict, entorno: dict, tarea: dict) -> list[str]:
    """Agente constructor con hasta N intentos (RF-CLO-05). Si no logra un robot válido, usa el ensamblaje
    por defecto, sin LLM (RF-CLO-07). Antes prueba el modelo comprobado de este robot, si existe (RF-CLO-10/11):
    pasa por las mismas reglas y por validar_robot con la escena de esta corrida. Devuelve los artefactos."""
    if robot.get("modelo_sim"):
        return construir_desde_modelo(c, robot)
    assets = rc.cargar_assets()
    necesario = agentes.alcance_necesario(entorno, robot)
    clave_modelo = modelos.clave(robot, assets)
    comprobado = modelos.buscar(c.store, clave_modelo)
    previo, problemas = None, []
    rechazados: list[dict] = []   # intentos que no llegan al pod: van como tarjetas en construccion.mp4
    total = cfg.intentos_constructor
    candidatos = ([("comprobado", 0)] if comprobado else []) + \
        [("agente", i) for i in range(1, total + 1)] + [("determinista", total + 1)]
    for metodo, intento in candidatos:
        titulo = _titulo_intento(metodo, intento, total)
        try:
            if metodo == "comprobado":
                ens = comprobado
            elif metodo == "agente":
                ens = agentes.constructor(cfg.agentes, cfg.modelo, robot, entorno, tarea, assets, intento, problemas, previo,
                                          total_intentos=total)
            else:
                ens = validar("ensamblaje", rc.ensamblaje_por_defecto(robot, assets))
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
            if metodo != "agente":
                clon["construccion"] = {**clon["construccion"], "metodo": metodo}
            if metodo == "determinista":
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
                if metodo == "agente":
                    modelos.registrar(c.store, clave_modelo, ens, robot["id"], c.id)
                log.info("corrida %s: robot construido (%s, intento %s)", c.id, metodo, intento)
                return ["ensamblaje.json", "robot_cfg.py", "clon.json", "robot.urdf", "validacion.json"] + \
                    (["construccion.mp4"] if c.existe("construccion.mp4") else [])
            problemas = v.get("problemas") or ["validar_robot falló sin detalle"]
        log.info("corrida %s: constructor %s intento %s con problemas: %s", c.id, metodo, intento, problemas)
        previo = ens
    raise agentes.ErrorAgente(f"no se pudo construir un robot válido: {problemas}")


def construir_desde_modelo(c: Corrida, robot: dict) -> list[str]:
    """Clon = el modelo del robot publicado para Isaac Lab (robot.json → modelo_sim). Sin agente constructor ni
    ensamblaje: el modelo ya trae la cinemática, las masas y los límites del fabricante. Pasa igual por validar_robot
    en la escena de esta corrida (RF-CLO-05/06), una sola vez: si falla, no hay otro intento que probar."""
    m = robot["modelo_sim"]
    modulo, objeto = m["cfg"].split(":")
    clon = {
        "version": 1, "robot_id": robot["id"], "usd": m["usd"], "urdf": None, "modelo": m,
        "escala": {"alcance_m": robot["alcance_m"], "carga_util_kg": robot["carga_util_kg"]},
        "diferencias_con_real": [
            f"modelo publicado para Isaac Lab ({m['cfg']}), no medido por VIAZ",
            "los actuadores son los del modelo de Isaac Lab, no los del firmware del fabricante",
            *[f"{k}: estimado ({v})" for k, v in (robot.get("estimados") or {}).items()][:3],
        ],
        "validado_en_escena": False,
    }
    c.escribir("robot_cfg.py", f'"""Clon de {robot['id']}: el modelo publicado en Isaac Lab, sin ensamblaje (robot.json → modelo_sim)."""\n'
                               f"from {modulo} import {objeto} as ROBOT_CFG  # noqa: F401\n\n"
                               f"MODELO = {json.dumps(m, ensure_ascii=False)}\n")
    c.escribir("clon.json", validar("clon", clon))
    titulo = f"Modelo de Isaac Lab: {robot['nombre']}"
    c.trabajo_gpu("validar_robot", ["entorno.json", "tarea.json", "escena.usd", "robot_cfg.py", "clon.json"],
                  ["validacion.json", "construccion.mp4"], {"intento": 1, "etiqueta": titulo, "pieza": m["cfg"],
                                                            "rechazados": []})
    v = c.leer_json("validacion.json")
    if not v.get("ok"):
        raise agentes.ErrorAgente(f"el modelo {m['cfg']} no pasó validar_robot: {v.get('problemas')}")
    clon["validado_en_escena"] = True
    c.escribir("clon.json", validar("clon", clon))
    log.info("corrida %s: robot desde el modelo de Isaac Lab %s", c.id, m["cfg"])
    return ["robot_cfg.py", "clon.json", "validacion.json"] + (["construccion.mp4"] if c.existe("construccion.mp4") else [])


def procesar_rl(cfg: Config, eng, store: alm.Almacen, fila: dict) -> None:
    c = Corrida(cfg, eng, store, fila)
    with eng.connect() as cx:
        proyecto = dict(cx.execute(select(db.proyectos).where(db.proyectos.c.id == c.proyecto_id)).mappings().first())

    # 1. Entorno + escena. Con videos y sin VIAZ_ENTORNO_MANUAL, lo escribe el agente Entorno si hay medición
    # (VIAZ_MEDIR) o Claude (VIAZ_AGENTES=claude). Si no, se lee a mano (RF-MAP-11). Pendientes, problema 1.
    c.etapa("entorno", "en_curso", estado_corrida="analizando_entorno")
    artefactos: list[str] = []
    frames = None
    if (cfg.medir or cfg.agentes == "claude") and proyecto["videos"] and not cfg.entorno_manual:
        entorno, frames, artefactos = analizar_entorno(c, cfg, store, proyecto)
    else:
        entorno = _manual(cfg.entorno_manual, "entorno")
        entorno["videos"] = [v.rsplit("/", 1)[1] for v in proyecto["videos"]] or entorno.get("videos", [])
        c.escribir("entorno.json", validar("entorno", entorno))
    c.trabajo_gpu("generar_escena", ["entorno.json"], ["escena.usd"])
    c.etapa("entorno", "listo", ["entorno.json", "escena.usd", *artefactos])

    # 2. Tarea. Con VIAZ_TAREA_AGENTE=1 la escribe el agente Tarea (descripción del cliente + frames); si no, se lee
    # a mano. En los dos casos tiene que calzar con entorno.json. Pendientes, problema 1.
    c.etapa("tarea", "en_curso")
    if cfg.tarea_agente:
        if frames is None and cfg.agentes == "claude":
            videos = [store.leer(v) for v in proyecto["videos"] if store.existe(v)]
            frames = agentes.frames_de_videos(videos) if videos else None
        tarea = agentes.tarea(cfg.agentes, cfg.modelo, proyecto, entorno, frames)
    else:
        tarea = agentes.validar_tarea(_manual(cfg.tarea_manual, "tarea"), entorno)
    c.escribir("tarea.json", tarea)
    c.etapa("tarea", "listo", ["tarea.json"])
    exigir_pipeline(entorno, tarea)

    # 3. Selección de robot
    robots = elegir_robot(c, cfg, entorno, tarea)
    if len(robots) == 1:
        entrenar_y_evaluar(c, cfg, robots[0], entorno, tarea)
        return
    tol_pos, tol_ang, _ = tolerancias(tarea)
    condiciones = {"escena": "escena.usd", "horas_entrenamiento": cfg.horas_entrenamiento, "semillas": None,
                   "tolerancia_pos_m": tol_pos, "tolerancia_ang_grados": tol_ang}
    hijas.correr_finalistas(c, robots, condiciones,
                            lambda hija, robot, etiqueta: entrenar_y_evaluar(hija, cfg, robot, entorno, tarea, etiqueta))


def entrenar_y_evaluar(c: Corrida, cfg: Config, robot: dict, entorno: dict, tarea: dict,
                       etiqueta: str = "") -> hijas.Artefactos:
    tol_pos, tol_ang, tols_evaluar = tolerancias(tarea)

    # 4. Agente constructor
    c.etapa("clon", "en_curso", estado_corrida="clonando")
    de_clon = construir_robot(c, cfg, robot, entorno, tarea)
    c.etapa("clon", "listo", de_clon)

    # 5. Entrenamiento (con el monitor), clips y evaluación
    c.etapa("inteligencia", "en_curso", estado_corrida="entrenando")
    vigia = Vigia(c, cfg, etiqueta, tarea)
    latido_s = max(1.0, min(300.0, cfg.monitor_s / 2))
    c.trabajo_gpu("entrenar", ENTRADAS_RL, ["curva.json", "checkpoints.json"],
                  {"horas": cfg.horas_entrenamiento, "tolerancia_pos_m": tol_pos, "tolerancia_ang_grados": tol_ang, "latido_s": latido_s},
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
                  {"checkpoint": mejor, "episodios": cfg.episodios_evaluacion, "tolerancias": tols_evaluar}, espera_s=3 * 3600)
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
    return de_clon, artefactos


def procesar_una(cfg: Config, eng, store: alm.Almacen) -> bool:
    """Procesa una corrida en cola. Devuelve False si no había ninguna."""
    fila = db.tomar_con_lock(eng, db.corridas, (db.corridas.c.estado == "en_cola") & db.corridas.c.padre_id.is_(None),
                             {"estado": "analizando_entorno", "actualizado": db.ahora()})
    if fila is None:
        return False
    log.info("corrida %s: empiezo", fila["id"])
    try:
        procesar(cfg, eng, store, fila)
    except Exception as e:  # la corrida queda en error con el motivo; el orquestador sigue con la siguiente
        log.exception("corrida %s falló", fila["id"])
        hijas.registrar_error(eng, fila["id"], e)
    return True


ESQUEMA_PRUEBA = {"type": "object", "additionalProperties": False, "required": ["ok"],
                  "properties": {"ok": {"type": "boolean"}}}


def comprobar_claude(cfg: Config) -> None:
    """Chequeo previo en modo claude (pendientes, problema 6A): una llamada mínima antes de tomar corridas.
    Si falla, el orquestador no arranca: una clave mala o sin cupo no termina en una corrida "lista" con reglas."""
    if cfg.agentes != "claude":
        return
    from .agentes import base
    base.pedir_json(modelo=cfg.modelo, sistema="Responde con ok=true.", esquema=ESQUEMA_PRUEBA, effort="low",
                    contenido=[{"type": "text", "text": "Chequeo de credenciales de VIAZ."}], max_tokens=1024,
                    tiempo_s=60, etiqueta="chequeo_previo")
    log.info("chequeo previo: Claude responde (proveedor %s, modelo %s)", base.proveedor(), cfg.modelo)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = cargar()
    try:
        comprobar_claude(cfg)
    except agentes.ErrorAgente as e:
        log.error("el orquestador no arranca: Claude no responde en modo claude: %s", e)
        raise SystemExit(2) from e
    eng, store = db.motor(cfg.db_url), alm.crear(cfg)
    log.info("orquestador listo (agentes=%s, almacén=%s)", cfg.agentes, cfg.almacen)
    while True:
        if not procesar_una(cfg, eng, store):
            time.sleep(2)


if __name__ == "__main__":
    main()
