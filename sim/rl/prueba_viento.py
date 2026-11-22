"""Prueba de viento sobre los paneles ya instalados: ¿se quedan en su lugar? Solo corre en el pod.

    $ISAACLAB_SH -p sim/rl/prueba_viento.py --entorno E --tarea T --robot R --checkpoint C --salida DIR
        [--secuencias 32] [--rafagas 10,20,30,40] [--sin-grapas]

Cada copia instala la secuencia con la política. Cuando la base llega al último panel, el brazo se detiene y el
viento sopla sobre los paneles ya instalados: una ráfaga por velocidad, 1,5 s cada una, de lado y hacia arriba
(la sustentación es lo que arranca paneles en un parque real). Se mide cuánto se mueve cada panel.

Escribe DIR/viento.json: por ráfaga, la fuerza, el desplazamiento máximo y cuántos paneles se corrieron más de
1 cm o salieron volando (más de 10 cm). Con --sin-grapas los paneles solo se apoyan en los rieles: para comparar.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
RAFAGA_S = 1.5
DIRECCION = (0.0, math.cos(math.radians(40)), math.sin(math.radians(40)))   # de lado (cruzando la fila) y hacia arriba
CORRIDO_M, VOLADO_M = 0.01, 0.10


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--secuencias", type=int, default=32)
    ap.add_argument("--rafagas", default="10,20,30,40", help="velocidades del viento en m/s")
    ap.add_argument("--sin-grapas", action="store_true")
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: probar(a), a.salida / "viento.json")


def probar(a) -> dict:
    import torch

    import fisica
    from rl import cinematica as cin

    from rl import entorno as ent

    a.salida.mkdir(parents=True, exist_ok=True)
    # Episodios largos: las copias que llegan primero al último panel esperan quietas a las demás y después
    # vienen las ráfagas. Con 14 s se acabaría el tiempo y la copia se reiniciaría con sus paneles.
    crear_original = ent.crear_cfg

    def crear_cfg(*args, **kwargs):
        cfg = crear_original(*args, **kwargs)
        cfg.episode_length_s = 120.0
        return cfg

    ent.crear_cfg = crear_cfg
    env_gym = comun.crear_entorno(a, a.secuencias, paneles=0, secuencia=True, grapas=not a.sin_grapas, viento_m_s=0.0)
    entorno = env_gym.unwrapped
    env, politica = comun.cargar_politica(env_gym, a.checkpoint)
    n, ultimo, dev = entorno.num_envs, entorno.paneles - 1, entorno.device
    if ultimo < 1:
        raise RuntimeError("la secuencia tiene un solo panel: no hay paneles instalados que probar")

    # 1. La política instala hasta que cada copia llega al último panel (o falla antes). La que llega, espera quieta.
    obs, _ = env.reset()
    listas = torch.zeros(n, dtype=torch.bool, device=dev)
    fallo = torch.zeros(n, dtype=torch.bool, device=dev)
    quieto = torch.zeros(n, entorno.cfg.action_space, device=dev)
    quieto[:, 6] = -1.0
    with torch.inference_mode():
        for _ in range(entorno.paneles * 900):
            acciones = politica(obs)
            acciones[listas] = quieto[listas]
            obs, _, fin, _ = env.step(acciones)
            fallo |= fin.bool() & ~listas
            listas |= (entorno.k == ultimo) & ~entorno.viajando & ~fallo
            if bool((listas | fallo).all()):
                break
    copias = torch.nonzero(listas).flatten()
    if len(copias) == 0:
        raise RuntimeError("ninguna copia llegó al último panel")

    # 2. El brazo se queda quieto (acción cero: sin mover articulaciones ni succión) y sopla el viento.
    cuerpos = [entorno.pila[j] for j in entorno.cuerpo_de_slot[:ultimo]]
    d = torch.tensor(DIRECCION, device=dev)
    pasos = int(RAFAGA_S / entorno.step_dt)
    cero = torch.zeros(n, entorno.cfg.action_space, device=dev)
    cero[:, 6] = -1.0
    resultados = []
    with torch.inference_mode():
        for v in (float(x) for x in a.rafagas.split(",")):
            fuerza = fisica.fuerza_viento_n(v, entorno.area_panel)
            maximo = torch.zeros(len(copias), len(cuerpos), device=dev)
            for _ in range(pasos):
                for c in cuerpos:
                    q = c.data.root_quat_w.unbind(-1)          # cinematica trabaja con columnas (w, x, y, z)
                    local = torch.stack(cin.quat_rotar(cin.quat_conj(q), tuple(d[k].expand(n) * fuerza for k in range(3))), -1)
                    c.permanent_wrench_composer.set_forces_and_torques(
                        forces=local.unsqueeze(1), torques=torch.zeros_like(local).unsqueeze(1))
                env.step(cero)
                for s, c in enumerate(cuerpos):
                    corrido = (c.data.root_pos_w[copias] - entorno.vecino_pos0[copias, s]).norm(dim=-1)
                    maximo[:, s] = torch.maximum(maximo[:, s], corrido)
            for c in cuerpos:   # entre ráfagas, sin viento
                c.permanent_wrench_composer.set_forces_and_torques(
                    forces=torch.zeros(n, 1, 3, device=dev), torques=torch.zeros(n, 1, 3, device=dev))
            peso = float(entorno.masa_nominal.mean()) * fisica.GRAVEDAD
            resultados.append({
                "viento_m_s": v, "fuerza_n": round(fuerza, 1), "fuerza_sobre_peso": round(fuerza / peso, 2),
                "paneles": int(maximo.numel()),
                "corridos_1cm": int((maximo > CORRIDO_M).sum()), "volados_10cm": int((maximo > VOLADO_M).sum()),
                "desplazamiento_max_m": round(float(maximo.max()), 4),
                "desplazamiento_medio_m": round(float(maximo.mean()), 4)})
            print(json.dumps(resultados[-1]), flush=True)
    return {"version": 1, "checkpoint": a.checkpoint.name, "grapas": not a.sin_grapas,
            "rieles": fisica.RIELES["activos"], "secuencias": n, "llegaron_al_ultimo_panel": len(copias),
            "paneles_por_copia": ultimo, "direccion": "de lado y 40° hacia arriba", "rafaga_s": RAFAGA_S,
            "rafagas": resultados}


if __name__ == "__main__":
    main()
