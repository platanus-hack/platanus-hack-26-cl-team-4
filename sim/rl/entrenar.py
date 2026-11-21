"""Comando `entrenar` del contrato (docs/contrato-entorno-rl.md §3): PPO de rsl_rl sobre instalar_panel.

    $ISAACLAB_SH -p sim/rl/entrenar.py --entorno E --tarea T --robot R [--escena S] --salida DIR --max-horas 4
        --tolerancia-pos-m 0.05 --tolerancia-ang-grados 5 [--reanudar DIR/checkpoints/model_N.pt] [--parar-al-cumplir]

Escribe DIR/metricas.jsonl (una línea por iteración), DIR/curriculo.jsonl (la ayuda de inicio, el éxito con y sin
ayuda, los choques y el criterio de parada, por iteración) y DIR/checkpoints/model_N.pt (cada 50 iteraciones).
Cada episodio instala un panel de la secuencia, al azar, con los anteriores ya instalados (RF-INT-18).
Termina con código 0 cuando se cumple --max-horas o aparece el archivo DIR/DETENER, con un checkpoint de la
última iteración. Con --parar-al-cumplir también termina cuando la curva cumple el criterio de sim/rl/criterio.py
y deja de subir; DIR/criterio.json dice en qué iteración se cumplió. Entrena sin cámaras.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun, criterio  # noqa: E402

comun.preparar_ruta()
NUM_ENVS = 4096
ASISTIDO_INICIAL = 0.7          # fracción de episodios que parten en un punto del recorrido de referencia
EXITO_SIN_AYUDA = 0.5           # la ayuda llega a 0 cuando la política logra esta tasa de éxito sin ayuda
SUAVIZADO = 0.1                 # peso de la iteración nueva en el promedio móvil de la tasa de éxito sin ayuda
ENTROPIA_SIN_AYUDA = 0.0        # premio a la exploración cuando ya no queda ayuda de inicio
T_PROCESO = time.monotonic()    # --max-horas cuenta desde que parte el proceso, con el arranque de Isaac


class Detener(Exception):
    """Sale del ciclo de rsl_rl, que no tiene otro punto de salida."""


def fraccion_asistida(exito_sin_ayuda: float) -> float:
    """Ayuda de inicio según lo que la política ya logra sola. No depende del reloj ni de --max-horas.

    Baja en línea recta con la tasa de éxito sin ayuda y llega a 0 en EXITO_SIN_AYUDA. Si el éxito cae, vuelve.
    """
    return ASISTIDO_INICIAL * min(1.0, max(0.0, 1.0 - exito_sin_ayuda / EXITO_SIN_AYUDA))


def coef_entropia(asistido: float, inicial: float) -> float:
    """Premio a la exploración de PPO según la ayuda de inicio que queda. Baja junto con ella.

    Con la ayuda completa vale `inicial` (agente_cfg.py). Sin ayuda vale ENTROPIA_SIN_AYUDA: la política ya resuelve
    la tarea sola y el ruido de las acciones solo le quita precisión. Medido en la corrida de 4 paneles: con el premio
    fijo en 0,005 el ruido subió de 0,60 a 1,26 en 340 iteraciones y casi todos los choques eran contra el panel vecino.
    """
    return ENTROPIA_SIN_AYUDA + (inicial - ENTROPIA_SIN_AYUDA) * min(1.0, max(0.0, asistido / ASISTIDO_INICIAL))


def promedio_movil(previo: float, nuevo: float | None) -> float:
    """Tasa de éxito suavizada. Una iteración sin episodios terminados (None) no la cambia."""
    return previo if nuevo is None else (1 - SUAVIZADO) * previo + SUAVIZADO * nuevo


def linea_previa(salida: Path, iteracion: int) -> dict:
    """Línea de metricas.jsonl de la iteración del checkpoint que se reanuda: de ahí siguen pasos y tiempo."""
    archivo = salida / "metricas.jsonl"
    filas = []
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            try:
                filas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    hasta = [f for f in filas if f["iteracion"] <= iteracion]
    return hasta[-1] if hasta else {"pasos": 0, "tiempo_s": 0.0}


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--max-horas", type=float, default=4.0)
    ap.add_argument("--tolerancia-pos-m", type=float, default=0.05)
    ap.add_argument("--tolerancia-ang-grados", type=float, default=5.0)
    ap.add_argument("--reanudar", type=Path)
    ap.add_argument("--num-envs", type=int, default=NUM_ENVS)
    ap.add_argument("--parar-al-cumplir", action="store_true",
                    help="termina cuando la curva cumple el criterio de sim/rl/criterio.py y deja de subir")
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: entrenar(a))


def entrenar(a) -> None:
    import statistics

    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
    from rsl_rl.runners import OnPolicyRunner

    from rl.agente_cfg import InstalarPanelPPOCfg

    inicio = time.monotonic()
    salida = a.salida
    (salida / "checkpoints").mkdir(parents=True, exist_ok=True)
    env_gym = comun.crear_entorno(a, a.num_envs, tolerancia_pos_m=a.tolerancia_pos_m,
                                  tolerancia_ang_grados=a.tolerancia_ang_grados, asistido=ASISTIDO_INICIAL, paneles=0)
    entorno = env_gym.unwrapped
    cfg = InstalarPanelPPOCfg()
    cfg.device = a.device
    env = RslRlVecEnvWrapper(env_gym, clip_actions=cfg.clip_actions)
    limite_s = a.max_horas * 3600

    class Entrenador(OnPolicyRunner):
        """OnPolicyRunner que escribe metricas.jsonl y obedece DETENER y --max-horas."""

        previo = {"pasos": 0, "tiempo_s": 0.0}
        exito_movil = 0.0
        historia: list[dict] = []        # filas de curriculo.jsonl de esta corrida, para el criterio de parada
        racha = 0                        # iteraciones seguidas con el criterio cumplido
        mejor, sin_mejora = 0.0, 0       # mejor media de éxito desde que se cumplió, e iteraciones sin superarla

        def log(self, locs: dict, width: int = 80, pad: int = 35) -> None:
            infos = locs["ep_infos"]
            suma = {k: sum(float(i[k]) for i in infos) for k in infos[0]} if infos else {}
            suma = {"episodios": 0.0, "exitos": 0.0, "episodios_asistidos": 0.0, "exitos_asistidos": 0.0, "choques": 0.0,
                    "caidas": 0.0, "choques_vecino": 0.0, **suma}
            episodios, exitos = suma["episodios"], suma["exitos"]
            super().log(locs, width, pad)
            perdidas = locs["loss_dict"]
            tiempo_s = self.previo["tiempo_s"] + time.monotonic() - inicio
            fila = {
                "iteracion": locs["it"], "pasos": int(self.previo["pasos"] + self.tot_timesteps),
                "tiempo_s": round(tiempo_s, 1),
                "recompensa_media": statistics.mean(locs["rewbuffer"]) if locs["rewbuffer"] else None,
                "tasa_exito": round(exitos / episodios, 4) if episodios else None,
                "largo_episodio": statistics.mean(locs["lenbuffer"]) if locs["lenbuffer"] else None,
                "perdida_valor": float(perdidas["value_function"]), "perdida_politica": float(perdidas["surrogate"]),
                "entropia": float(perdidas["entropy"]),
            }
            metricas.write(json.dumps(fila) + "\n")   # un NaN se escribe tal cual: la API lo detecta (RF-MON-08)
            metricas.flush()
            Entrenador.exito_movil = promedio_movil(Entrenador.exito_movil, fila["tasa_exito"])
            # curriculo.jsonl: la curva de la ayuda. No va en metricas.jsonl porque su esquema es cerrado.
            asistidos = suma["episodios_asistidos"]
            por_panel = [(suma.get(f"exitos_k{k}", 0.0), suma.get(f"episodios_k{k}", 0.0)) for k in range(entorno.paneles)]
            linea = {
                "iteracion": locs["it"], "tiempo_s": fila["tiempo_s"], "asistido": round(entorno.asistido, 4),
                "tasa_exito_sin_ayuda": fila["tasa_exito"], "episodios_sin_ayuda": int(episodios),
                "exitos_sin_ayuda": int(exitos),
                "tasa_exito_con_ayuda": round(suma["exitos_asistidos"] / asistidos, 4) if asistidos else None,
                "episodios_con_ayuda": int(asistidos), "choques": int(suma["choques"]), "caidas": int(suma["caidas"]),
                "choques_vecino": int(suma["choques_vecino"]),
                "panel_k": [round(e / n, 4) if n else None for e, n in por_panel],
                "sellados": round(statistics.mean(float(i["sellados"]) for i in infos), 4) if infos else None,
                "recompensa_media": fila["recompensa_media"],
                "ruido_acciones": round(float(self.alg.policy.action_std.mean()), 4),
                "coef_entropia": round(self.alg.entropy_coef, 6)}
            # Criterio de parada: medias móviles de éxito sin ayuda, choques y caídas (sim/rl/criterio.py).
            Entrenador.historia.append(linea)
            m = criterio.medias(Entrenador.historia)
            Entrenador.racha = criterio.racha(Entrenador.racha, m)
            if m is not None:
                linea |= {"media_exito": round(m["exito"], 4), "media_choques": round(m["choques"], 5),
                          "media_caidas": round(m["caidas"], 5), "racha_criterio": Entrenador.racha}
            curriculo.write(json.dumps(linea) + "\n")
            curriculo.flush()
            entorno.asistido = fraccion_asistida(Entrenador.exito_movil)
            self.alg.entropy_coef = coef_entropia(entorno.asistido, cfg.algorithm.entropy_coef)
            if Entrenador.racha == criterio.RACHA and not (salida / "criterio.json").exists():
                self.save(str(salida / "checkpoints" / f"model_{locs['it']}.pt"))
                (salida / "criterio.json").write_text(json.dumps(
                    {"iteracion": locs["it"], "tiempo_s": fila["tiempo_s"], "medias": m, "ventana": criterio.VENTANA,
                     "racha": criterio.RACHA}, indent=2), encoding="utf-8")
                print(f"[entrenar] criterio de parada cumplido en la iteración {locs['it']}: {m}", flush=True)
            if Entrenador.racha >= criterio.RACHA:
                Entrenador.mejor, Entrenador.sin_mejora = criterio.sin_mejora(Entrenador.mejor, Entrenador.sin_mejora, m["exito"])
            if (salida / "DETENER").exists():
                raise Detener("archivo DETENER")
            if time.monotonic() - T_PROCESO >= limite_s:
                raise Detener("se cumplió --max-horas")
            if a.parar_al_cumplir and criterio.terminar(Entrenador.racha, Entrenador.sin_mejora):
                raise Detener(f"criterio cumplido y la curva ya no sube: {m}")

    entrenador = Entrenador(env, cfg.to_dict(), log_dir=str(salida / "checkpoints"), device=cfg.device)
    if a.reanudar:
        entrenador.load(str(a.reanudar))
        Entrenador.previo = linea_previa(salida, entrenador.current_learning_iteration)
        Entrenador.exito_movil = Entrenador.previo.get("tasa_exito") or 0.0
        entorno.asistido = fraccion_asistida(Entrenador.exito_movil)
        entrenador.alg.entropy_coef = coef_entropia(entorno.asistido, cfg.algorithm.entropy_coef)
        entrenador.current_learning_iteration += 1   # rsl_rl repetiría la iteración del checkpoint
    with (open(salida / "metricas.jsonl", "a", encoding="utf-8") as metricas,
          open(salida / "curriculo.jsonl", "a", encoding="utf-8") as curriculo):
        try:
            entrenador.learn(num_learning_iterations=cfg.max_iterations, init_at_random_ep_len=True)
        except Detener as motivo:
            ultima = entrenador.current_learning_iteration
            entrenador.save(str(salida / "checkpoints" / f"model_{ultima}.pt"))
            print(f"[entrenar] detenido en la iteración {ultima}: {motivo}", flush=True)


if __name__ == "__main__":
    main()
