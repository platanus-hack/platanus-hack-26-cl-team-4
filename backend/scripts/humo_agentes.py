"""Prueba de humo con Claude real: una llamada por agente, validada contra el esquema local (pendientes, problema 7A).

    cd backend
    ANTHROPIC_API_KEY=... python scripts/humo_agentes.py [--modelo claude-opus-5-5] [--solo entorno,tarea]
                                                         [--video ruta.mov] [--salida humo.json]

Entorno necesita --video (sin frames el agente no corre). Con VIAZ_CLAUDE=suscripcion corre con el Agent SDK
(solo en local). Cuesta unos pocos dólares con la API.
Cada agente recibe un caso de los fixtures. El informe dice, por agente: ok o el error, segundos y la salida.
Los tokens por llamada quedan en el log (logger viaz.claude): ninguno debería pasar el 80 % de su tope (problema 8).
Termina con código 0 solo si los 8 pasos responden y validan.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from viaz import agentes, catalogo, comparacion, monitor  # noqa: E402
from viaz import robot_cfg as rc  # noqa: E402
from viaz.agentes import base, busqueda  # noqa: E402
from viaz.esquemas import validar  # noqa: E402

PASOS = ("entorno", "tarea", "seleccion", "fichas", "constructor", "monitor", "comparacion", "busqueda")


def _f(nombre: str) -> dict:
    return json.loads((agentes.FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def correr(paso: str, modelo: str, frames: list[dict] | None) -> dict:
    entorno, tarea = _f("entorno_evento"), _f("tarea_animar")
    proyecto = {"descripcion": "Queremos un robot que anime la fiesta del evento sin chocar con las sillas.",
                "videos": ["proyectos/humo/videos/lugar.mov"]}
    if paso == "entorno":
        return validar("entorno", agentes.entorno("claude", modelo, proyecto, frames))
    if paso == "tarea":
        return agentes.tarea("claude", modelo, proyecto, entorno, frames)
    if paso == "seleccion":
        return agentes.seleccionar("claude", modelo, entorno, tarea, catalogo.cargar()).seleccion
    if paso == "fichas":
        notas = ("Unitree H1: humanoide de 1,8 m y 47 kg (https://www.unitree.com/h1, «Height about 180CM, "
                 "Weight about 47kg»).")
        return {"robots": busqueda.fichar(modelo=modelo, notas=notas, max_robots=1, tiempo_s=180)}
    if paso == "constructor":
        robot = {**catalogo.cargar()["leapting-mmr"], "justificacion": "humo", "alternativas": []}
        return agentes.constructor("claude", modelo, robot, _f("entorno"), _f("tarea"), rc.cargar_assets(), 1)
    if paso == "monitor":
        m = [{"iteracion": i, "pasos": i * 100, "tiempo_s": i * 10.0, "recompensa_media": float(i), "tasa_exito": i / 40,
              "largo_episodio": 100.0, "perdida_valor": 0.1, "perdida_politica": 0.1, "entropia": 1.0} for i in range(30)]
        ch = monitor.chequear("claude", modelo, m, m, [], 1.0, tarea=tarea, tiempo_s=120)
        if ch["fuente"] != "claude":
            raise base.ErrorAgente(f"el monitor cayó a reglas: {ch['motivo_reglas']}")
        return ch
    if paso == "comparacion":
        hijas = [comparacion.Hija(robot={"id": r, "nombre": r.upper(), "fisica": {"largo_m": 1}}, corrida_id=f"humo-{r}",
                                  resultado={"fuente": "isaac", "metricas": {"tasa_exito": t, "ciclo_promedio_s": 60.0}},
                                  clon={"robot_id": r, "fidelidad": "medido"}, error=None)
                 for r, t in (("unitree-h1", 0.9), ("otro-robot", 0.7))]
        condiciones = {"escena": "escena.usd", "horas_entrenamiento": 1, "semillas": None, "tolerancia_pos_m": 0.5,
                       "tolerancia_ang_grados": 30}
        comp = comparacion.explicar("claude", modelo, comparacion.comparar(hijas, condiciones))
        if comp["fuente_explicacion"] != "claude":
            raise base.ErrorAgente("la comparación cayó a la plantilla")
        return comp
    if paso == "busqueda":
        if base.proveedor() == "suscripcion":
            return {"omitida": "con suscripción la búsqueda no corre (problema 4)"}
        notas = busqueda.investigar(modelo=modelo, texto="Busca 1 robot humanoide real para animar eventos, con su "
                                    "ficha técnica y la URL de la fuente.", max_consultas=2, tiempo_s=180)
        if not notas.texto.strip():
            raise base.ErrorAgente("la investigación no devolvió notas")
        return {"notas": notas.texto[:1500], "cortada": notas.cortada}
    raise ValueError(paso)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", default="claude-opus-5-5")
    ap.add_argument("--solo", help=f"pasos separados por coma; por defecto todos: {','.join(PASOS)}")
    ap.add_argument("--video", type=Path, help="video del lugar para los frames de Entorno y Tarea")
    ap.add_argument("--salida", type=Path, default=Path("humo_agentes.json"))
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    problemas = base.problemas_credenciales()
    if problemas:
        sys.exit("no se puede llamar a Claude: " + "; ".join(problemas))
    frames = base.frames_de_videos([a.video.read_bytes()]) if a.video else None
    pasos = a.solo.split(",") if a.solo else list(PASOS)
    informe = {"modelo": a.modelo, "proveedor": base.proveedor(), "pasos": {}}
    for paso in pasos:
        inicio = time.monotonic()
        try:
            salida = correr(paso, a.modelo, frames)
            informe["pasos"][paso] = {"ok": True, "segundos": round(time.monotonic() - inicio, 1), "salida": salida}
        except Exception as e:  # noqa: BLE001
            informe["pasos"][paso] = {"ok": False, "segundos": round(time.monotonic() - inicio, 1),
                                      "error": f"{type(e).__name__}: {e}"[:1000]}
        print(f"{paso:12s} {'ok' if informe['pasos'][paso]['ok'] else 'FALLA'} "
              f"{informe['pasos'][paso]['segundos']} s {informe['pasos'][paso].get('error', '')}", flush=True)
    a.salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(p["ok"] for p in informe["pasos"].values())
    print(f"{ok} de {len(pasos)} pasos responden y validan. Informe: {a.salida}")
    sys.exit(0 if ok == len(pasos) else 1)


if __name__ == "__main__":
    main()
