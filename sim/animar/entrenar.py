"""Comando `entrenar` de animar_evento: PPO de rsl_rl para que el robot camine siguiendo comandos de velocidad.

    $ISAACLAB_SH -p sim/tareas.py entrenar --entorno E --tarea T --robot R --salida DIR --max-horas 1
        [--tolerancia-pos-m X --tolerancia-ang-grados Y] [--reanudar DIR/checkpoints/model_N.pt]

Mismo contrato que sim/rl/entrenar.py: DIR/metricas.jsonl (una línea por iteración), DIR/checkpoints/model_N.pt
cada 50 iteraciones, y obedece DIR/DETENER y --max-horas. Entrena sin cámaras, sobre un plano con el roce del piso.

`tasa_exito` de metricas.jsonl: fracción de episodios logrados. Logrado = termina por tiempo (no se cae) y sigue
el comando de velocidad con error medio < 0,25 m/s y < 0,4 rad/s (comun.envolver_con_metricas).
La evaluación en la sala (evaluar.py) mide el recorrido completo.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun  # noqa: E402

NUM_ENVS = 4096
ITERACIONES_MAX = 3000        # tope de seguridad; normalmente manda --max-horas
T_PROCESO = time.monotonic()


class Detener(Exception):
    pass


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--max-horas", type=float, default=1.0)
    ap.add_argument("--tolerancia-pos-m", type=float, default=0.5)
    ap.add_argument("--tolerancia-ang-grados", type=float, default=30.0)
    ap.add_argument("--reanudar", type=Path)
    ap.add_argument("--num-envs", type=int, default=NUM_ENVS)
    ap.add_argument("--iteraciones", type=int, default=ITERACIONES_MAX)
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: entrenar(a))


def entrenar(a) -> None:
    from rsl_rl.runners import OnPolicyRunner

    c = comun.leer(a)
    salida = a.salida
    (salida / "checkpoints").mkdir(parents=True, exist_ok=True)
    env = comun.crear(comun.cfg_entrenamiento(c, a.num_envs, a.device))
    agente = comun.cfg_agente(c, a.device)
    agente.max_iterations = a.iteraciones
    agente.save_interval = 50
    envuelto = comun.envolver_con_metricas(env, agente.clip_actions)
    limite_s = a.max_horas * 3600
    inicio = time.monotonic()

    class Entrenador(OnPolicyRunner):
        previo = {"pasos": 0, "tiempo_s": 0.0}

        def log(self, locs: dict, width: int = 80, pad: int = 35) -> None:
            logrados, episodios = envuelto.leer_y_reiniciar()
            super().log(locs, width, pad)
            perdidas = locs["loss_dict"]
            fila = {
                "iteracion": locs["it"], "pasos": int(self.previo["pasos"] + self.tot_timesteps),
                "tiempo_s": round(self.previo["tiempo_s"] + time.monotonic() - inicio, 1),
                "recompensa_media": statistics.mean(locs["rewbuffer"]) if locs["rewbuffer"] else None,
                "tasa_exito": round(logrados / episodios, 4) if episodios else None,
                "largo_episodio": statistics.mean(locs["lenbuffer"]) if locs["lenbuffer"] else None,
                "perdida_valor": float(perdidas["value_function"]), "perdida_politica": float(perdidas["surrogate"]),
                "entropia": float(perdidas["entropy"]),
            }
            metricas.write(json.dumps(fila) + "\n")
            metricas.flush()
            if (salida / "DETENER").exists():
                raise Detener("archivo DETENER")
            if time.monotonic() - T_PROCESO >= limite_s:
                raise Detener("se cumplió --max-horas")

    entrenador = Entrenador(envuelto, agente.to_dict(), log_dir=str(salida / "checkpoints"), device=a.device)
    if a.reanudar:
        entrenador.load(str(a.reanudar))
        entrenador.current_learning_iteration += 1
    with open(salida / "metricas.jsonl", "a", encoding="utf-8") as metricas:
        try:
            entrenador.learn(num_learning_iterations=agente.max_iterations, init_at_random_ep_len=True)
        except Detener as motivo:
            print(f"[entrenar] detenido en la iteración {entrenador.current_learning_iteration}: {motivo}", flush=True)
        ultima = entrenador.current_learning_iteration
        entrenador.save(str(salida / "checkpoints" / f"model_{ultima}.pt"))


if __name__ == "__main__":
    main()
