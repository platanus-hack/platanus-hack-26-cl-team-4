"""Una corrida: sus archivos en el almacén, su fila en `corridas` y sus trabajos de GPU."""
from __future__ import annotations

import json
import logging
import time

from sqlalchemy import insert, select, update

from . import agentes
from . import almacen as alm
from . import db
from .config import Config

log = logging.getLogger("viaz.orquestador")

ESTADOS_SIN_SUBIR = (None, "listo", "error")


class Corrida:
    def __init__(self, cfg: Config, eng, store: alm.Almacen, fila: dict):
        self.cfg, self.eng, self.store = cfg, eng, store
        self.id = fila["id"]
        self.proyecto_id = fila["proyecto_id"]
        self.padre_id: str | None = fila.get("padre_id")
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
            if self.padre_id and campos.get("estado") not in ESTADOS_SIN_SUBIR:
                cx.execute(update(db.corridas).where(db.corridas.c.id == self.padre_id)
                           .values(estado=campos["estado"], actualizado=db.ahora()))

    def etapa(self, nombre: str, estado: str, artefactos: list[str] | None = None, estado_corrida: str | None = None):
        cambios = {"estado": estado, **({"artefactos": artefactos} if artefactos is not None else {})}
        self.etapas = [{**e, **cambios} if e["nombre"] == nombre else dict(e) for e in self.etapas]
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
