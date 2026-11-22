"""API de VIAZ (Render Web Service). Contrato: docs/contrato-datos.md § API.

    uvicorn viaz.api:app --reload
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, update

from . import almacen as alm
from . import db, hijas
from .config import Config, cargar


class NuevoProyecto(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(default="", max_length=5000)
    videos: list[str] = Field(default_factory=list, max_length=10, description="Nombres de los videos que se van a subir")


class FinTrabajo(BaseModel):
    ok: bool
    error: str | None = None


class Latido(BaseModel):
    metricas: list[dict[str, Any]] = Field(default_factory=list, max_length=5000,
                                           description="Líneas nuevas de metricas.jsonl desde el último latido")


def _limpiar(fila: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """NaN o infinito → None (Postgres no guarda NaN en JSON). Devuelve (fila limpia, había NaN)."""
    hubo, limpia = False, {}
    for k, v in fila.items():
        if isinstance(v, float) and not math.isfinite(v):
            hubo, v = True, None
        limpia[k] = v
    return limpia, hubo


def _nombre_seguro(nombre: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "-", nombre).strip(".-")
    return limpio[:100] or "video.mp4"


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or cargar()
    eng = db.motor(cfg.db_url)
    store = alm.crear(cfg)

    app = FastAPI(title="VIAZ API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=cfg.origenes, allow_methods=["*"], allow_headers=["*"])
    app.state.cfg, app.state.eng, app.state.almacen = cfg, eng, store

    def es_worker(authorization: str = Header(default="")):
        if authorization != f"Bearer {cfg.worker_token}":
            raise HTTPException(401, "token de worker inválido")

    def es_equipo(authorization: str = Header(default="")):
        if authorization != f"Bearer {cfg.admin_token}":
            raise HTTPException(401, "token del equipo inválido")

    @app.get("/salud")
    def salud():
        return {"ok": True, "agentes": cfg.agentes, "almacen": cfg.almacen}

    # ---------- Web ----------

    @app.post("/proyectos", status_code=201)
    def crear_proyecto(p: NuevoProyecto):
        pid = db.nuevo_id()
        claves = [f"proyectos/{pid}/videos/{_nombre_seguro(v)}" for v in p.videos]
        with eng.begin() as cx:
            cx.execute(insert(db.proyectos).values(id=pid, nombre=p.nombre, descripcion=p.descripcion, videos=claves))
        return {"id": pid, "subida": [{"archivo": c.rsplit("/", 1)[1], "url_firmada": store.url_put(c)} for c in claves]}

    @app.post("/proyectos/{pid}/corridas", status_code=201)
    def crear_corrida(pid: str):
        with eng.begin() as cx:
            if cx.execute(select(db.proyectos.c.id).where(db.proyectos.c.id == pid)).first() is None:
                raise HTTPException(404, "no existe el proyecto")
            cid = db.nuevo_id()
            etapas = [{"nombre": e, "estado": "pendiente", "artefactos": []} for e in db.ETAPAS]
            cx.execute(insert(db.corridas).values(id=cid, proyecto_id=pid, estado="en_cola", etapas=etapas))
        return {"corrida_id": cid}

    @app.get("/corridas/{cid}")
    def ver_corrida(cid: str):
        if cid == "demo":
            if not cfg.corrida_demo:
                raise HTTPException(404, "no hay corrida de demo configurada (VIAZ_CORRIDA_DEMO)")
            cid = cfg.corrida_demo
        with eng.connect() as cx:
            c = cx.execute(select(db.corridas).where(db.corridas.c.id == cid)).mappings().first()
        if c is None:
            raise HTTPException(404, "no existe la corrida")
        etapas = [{**e, "artefactos": {a: store.url_get(alm.clave_corrida(cid, a)) for a in e["artefactos"]}}
                  for e in c["etapas"]]
        return {"id": cid, "estado": c["estado"], "etapas": etapas, "error": c["error"], "padre_id": c["padre_id"],
                "hijas": [{"id": h["id"], "robot_id": _robot_id(store, h["id"]), "estado": h["estado"]}
                          for h in hijas.de_padre(eng, cid)]}

    @app.get("/corridas/{cid}/metricas")
    def metricas_corrida(cid: str, desde: int = -1, limite: int = 2000):
        """Métricas del entrenamiento desde una iteración (para la curva y para depurar).
        Un padre no entrena: devuelve las de su hija activa o ganadora, con su id en `hija_id`."""
        if cid == "demo" and cfg.corrida_demo:
            cid = cfg.corrida_demo
        hija_id = hijas.hija_visible(eng, store, cid)
        with eng.connect() as cx:
            filas = cx.execute(select(db.metricas.c.datos)
                               .where(db.metricas.c.corrida_id == (hija_id or cid), db.metricas.c.iteracion > desde)
                               .order_by(db.metricas.c.iteracion).limit(min(limite, 5000))).scalars().all()
        return {"corrida_id": cid, "hija_id": hija_id, "metricas": filas}

    @app.post("/corridas/{cid}/detener", dependencies=[Depends(es_equipo)])
    def detener_corrida(cid: str):
        """El equipo detiene el entrenamiento de una corrida. El pod guarda un checkpoint y termina (RF-MON-08)."""
        with eng.begin() as cx:
            de_sus_hijas = select(db.corridas.c.id).where(db.corridas.c.padre_id == cid)
            r = cx.execute(update(db.trabajos)
                           .where((db.trabajos.c.corrida_id == cid) | db.trabajos.c.corrida_id.in_(de_sus_hijas),
                                  db.trabajos.c.tipo == "entrenar", db.trabajos.c.estado.in_(["pendiente", "tomado"]))
                           .values(detener=True))
        if not r.rowcount:
            raise HTTPException(404, "la corrida no tiene un entrenamiento en curso")
        return {"ok": True}

    # ---------- Archivos (solo almacén local) ----------

    if isinstance(store, alm.AlmacenLocal):
        @app.get("/archivos/{clave:path}")
        def bajar(clave: str):
            try:
                return Response(store.leer(clave), media_type=_tipo(clave))
            except (FileNotFoundError, ValueError):
                raise HTTPException(404, "no existe el archivo")

        @app.put("/archivos/{clave:path}", status_code=204)
        async def subir(clave: str, request: Request):
            try:
                store.escribir(clave, await request.body())
            except ValueError:
                raise HTTPException(400, "clave inválida")
            return Response(status_code=204)

    # ---------- Sim runner (GPU) ----------

    @app.post("/worker/trabajos/tomar", dependencies=[Depends(es_worker)])
    def tomar_trabajo():
        db.devolver_trabajos_vencidos(eng)
        t = db.tomar_con_lock(eng, db.trabajos, db.trabajos.c.estado == "pendiente",
                              {"estado": "tomado", "tomado_en": db.ahora()})
        if t is None:
            return Response(status_code=204)
        cid = t["corrida_id"]
        return {
            "trabajo_id": t["id"], "tipo": t["tipo"], "corrida_id": cid,
            "parametros": t.get("parametros") or {},
            "entradas": {a: store.url_get(alm.clave_corrida(cid, a)) for a in t["entradas"]},
            "subidas": {a: store.url_put(alm.clave_corrida(cid, a)) for a in t["salidas"]},
        }

    @app.post("/worker/trabajos/{tid}/latido", dependencies=[Depends(es_worker)])
    def latido(tid: str, body: Latido):
        """Mantiene vivo un trabajo largo y guarda las métricas nuevas. Responde seguir o detener (RF-API-06).
        Con NaN en las métricas, pide detener sin esperar al monitor (RF-MON-08)."""
        hubo_nan = False
        with eng.begin() as cx:
            t = cx.execute(select(db.trabajos.c.corrida_id, db.trabajos.c.estado, db.trabajos.c.detener)
                           .where(db.trabajos.c.id == tid)).mappings().first()
            if t is None or t["estado"] != "tomado":
                raise HTTPException(409, "el trabajo no está tomado")
            filas = []
            for m in body.metricas:
                limpia, nan = _limpiar(m)
                hubo_nan |= nan
                if isinstance(limpia.get("iteracion"), int):
                    filas.append({"trabajo_id": tid, "corrida_id": t["corrida_id"], "iteracion": limpia["iteracion"],
                                  "datos": {**limpia, "nan": nan} if nan else limpia})
            if filas:
                cx.execute(insert(db.metricas), filas)
            detener = bool(t["detener"]) or hubo_nan
            cx.execute(update(db.trabajos).where(db.trabajos.c.id == tid)
                       .values(latido_en=db.ahora(), detener=detener))
        return {"accion": "detener" if detener else "seguir", "nan": hubo_nan}

    @app.post("/worker/trabajos/{tid}/fin", dependencies=[Depends(es_worker)])
    def fin_trabajo(tid: str, f: FinTrabajo):
        with eng.begin() as cx:
            r = cx.execute(update(db.trabajos).where(db.trabajos.c.id == tid, db.trabajos.c.estado == "tomado")
                           .values(estado="ok" if f.ok else "error", error=f.error))
        if not r.rowcount:
            raise HTTPException(409, "el trabajo no está tomado")
        return {"ok": True}

    return app


def _robot_id(store: alm.Almacen, cid: str) -> str | None:
    clave = alm.clave_corrida(cid, "robot.json")
    if not store.existe(clave):
        return None
    return json.loads(store.leer(clave)).get("id")


def _tipo(clave: str) -> str:
    for ext, tipo in ((".json", "application/json"), (".mp4", "video/mp4"), (".urdf", "application/xml"),
                      (".usd", "application/octet-stream"), (".jpg", "image/jpeg")):
        if clave.endswith(ext):
            return tipo
    return "application/octet-stream"


_app: FastAPI | None = None


def __getattr__(nombre: str):
    # `uvicorn viaz.api:app` crea la app recién al usarla; importar el módulo en tests no toca ./.datos
    global _app
    if nombre == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(nombre)
