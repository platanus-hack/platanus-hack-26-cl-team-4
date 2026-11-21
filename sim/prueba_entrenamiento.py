"""Prueba de la escena de entrenamiento en Isaac Lab: física en casos conocidos y velocidad con N copias.

    $ISAACLAB_SH -p sim/prueba_entrenamiento.py --headless --dir <carpeta> --escenarios
    $ISAACLAB_SH -p sim/prueba_entrenamiento.py --headless --dir <carpeta> --num-envs 4096 --pasos 1000

La carpeta necesita entorno.json. tarea.json da el tamaño de la pila y clon.json dice dónde va.

--escenarios: una copia por caso de ESCENARIOS, 5 s. Cada caso tiene un resultado esperado. Los casos "se_mueve"
son controles: si un empuje sobre el límite de fricción no mueve el panel, la prueba no está midiendo nada.
Un panel empujado tiene que resbalar lo que predice la fricción de Coulomb con el coeficiente del par (±15 %).
Sin --escenarios: N copias. Primero 5 s de asentamiento (pila quieta, nada bajo z = -1 mm). Después mide
pasos de física por segundo en dos regímenes: en reposo y con el panel cayendo sobre el tubo una vez por segundo.

Escribe prueba_entrenamiento[_escenarios].json en la carpeta y termina con código 1 si algo falla.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

TOL = {"posicion_m": 0.005, "inclinacion_grados": 1.0, "z_minimo_m": -0.001, "resbalon_rel": 0.15}
SEGUNDOS = 5.0
EMPUJE_DESDE_S, EMPUJE_DURA_S = 1.0, 0.5
CAIDA_M = 0.10
BLOQUES = 3

# (nombre, dónde parte el panel, corrimiento a lo largo del panel en m, empuje como fracción del límite de fricción, espera)
ESCENARIOS = [
    ("apoyado_en_tubo", "tubo", 0.0, 0.0, "queda"),
    ("caida_10cm_sobre_tubo", "caida", 0.0, 0.0, "queda"),
    ("descentrado_4cm", "tubo", 0.04, 0.0, "queda"),
    ("descentrado_6cm", "tubo", 0.06, 0.0, "se_mueve"),
    ("empuje_tubo_90", "tubo", 0.0, 0.9, "queda"),
    ("empuje_tubo_110", "tubo", 0.0, 1.1, "se_mueve"),
    ("empuje_pila_90", "pila", 0.0, 0.9, "queda"),
    ("empuje_pila_110", "pila", 0.0, 1.1, "se_mueve"),
    ("empuje_suelo_90", "suelo", 0.0, 0.9, "queda"),
    ("empuje_suelo_110", "suelo", 0.0, 1.1, "se_mueve"),
]


def _leer(carpeta: Path, nombre: str) -> dict | None:
    f = carpeta / nombre
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _gpu_mib() -> int | None:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=20)
        return int(r.stdout.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def resbalon_m(empuje_n: float, limite_n: float, masa_kg: float) -> float:
    """Cuánto resbala un cuerpo con fricción de Coulomb: empuje constante EMPUJE_DURA_S y después frena solo."""
    if empuje_n <= limite_n:
        return 0.0
    acelera, frena = (empuje_n - limite_n) / masa_kg, limite_n / masa_kg
    velocidad = acelera * EMPUJE_DURA_S
    return acelera * EMPUJE_DURA_S ** 2 / 2 + velocidad ** 2 / (2 * frena)


def main() -> None:
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--num-envs", type=int, default=1024)
    ap.add_argument("--pasos", type=int, default=1000)
    ap.add_argument("--pila", type=int, default=None, help="paneles en la pila; por defecto, los de tarea.json")
    ap.add_argument("--escenarios", action="store_true")
    ap.add_argument("--imagen", type=Path, default=None, help="guarda un PNG de la grilla de copias (--enable_cameras)")
    AppLauncher.add_app_launcher_args(ap)
    a = ap.parse_args()
    app = AppLauncher(a).app
    # Isaac termina el proceso con código 0 al cerrar, incluso después de una excepción.
    # Por eso una falla sale antes, con os._exit.
    try:
        ok = _probar(a)
    except Exception:
        traceback.print_exc()
        ok = False
    if not ok:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    app.close()


def _probar(a: argparse.Namespace) -> bool:
    import torch
    import fisica
    import viaz_escena
    import isaaclab.sim as sim_utils
    from isaaclab.scene import InteractiveScene
    from prueba_fisica import guardar_imagen, inclinacion_grados, z_minimo

    entorno = _leer(a.dir, "entorno.json")
    tarea, clon = _leer(a.dir, "tarea.json"), _leer(a.dir, "clon.json")
    en_pila = a.pila if a.pila is not None else (tarea["pila_paneles"]["cantidad"] if tarea else 5)
    n = len(ESCENARIOS) if a.escenarios else a.num_envs
    salida = a.dir / ("prueba_entrenamiento_escenarios.json" if a.escenarios else f"prueba_entrenamiento_{n}.json")
    salida.unlink(missing_ok=True)  # un informe viejo no puede pasar por el de esta corrida

    desc = viaz_escena.describir_entrenamiento(entorno, en_pila, clon=clon)
    dt = desc["dt_s"]
    sim = sim_utils.SimulationContext(viaz_escena.sim_cfg(a.device))
    t0 = time.perf_counter()
    camara = viaz_escena.camara_entrenamiento(n) if a.imagen else None
    escena = InteractiveScene(viaz_escena.construir_cfg_entrenamiento(desc, n, camara=camara))
    sim.reset()
    carga_s = time.perf_counter() - t0
    dev = sim.device

    panel = escena["panel"]
    pila = [escena[p["nombre"]] for p in desc["pila"]]
    dinamicos = [panel, *pila]
    origen = escena.env_origins
    tam = torch.tensor(desc["panel"]["tam_m"], device=dev)
    slot = torch.tensor(desc["panel"]["pos_esperada_m"], device=dev)
    en_la_pila = torch.tensor(desc["panel"]["pos_inicial_m"], device=dev)
    peso_n = desc["panel"]["masa_kg"] * fisica.GRAVEDAD
    mat = {k: fisica.material(k) for k in ("panel", "acero")}
    limite_n = {"tubo": peso_n * fisica.friccion_par(mat["panel"], mat["acero"])["estatica"],
                "pila": peso_n * fisica.friccion_par(mat["panel"], mat["panel"])["estatica"],
                "suelo": peso_n * fisica.friccion_par(mat["panel"], desc["suelo"])["estatica"]}

    def poner_panel(local, ids=None):
        """Deja el panel quieto en una pose local (N, 3), sin rotación."""
        ids = torch.arange(n, device=dev) if ids is None else ids
        pose = torch.zeros(len(ids), 7, device=dev)
        pose[:, :3] = local + origen[ids]
        pose[:, 3] = 1.0
        panel.write_root_pose_to_sim(pose, env_ids=ids)
        panel.write_root_velocity_to_sim(torch.zeros(len(ids), 6, device=dev), env_ids=ids)

    def paso():
        escena.write_data_to_sim()
        sim.step(render=False)
        escena.update(dt)

    def estado_pila() -> dict:
        """Peor corrimiento e inclinación de los paneles de la pila, sobre todas las copias."""
        if not pila:
            return {"corrimiento_max_m": 0.0, "inclinacion_max_grados": 0.0}
        corr = max(float(((o.data.root_pos_w - origen) - torch.tensor(p["pos_esperada_m"], device=dev)).norm(dim=1).max())
                   for o, p in zip(pila, desc["pila"]))
        incl = max(float(inclinacion_grados(o.data.root_quat_w).max()) for o in pila)
        return {"corrimiento_max_m": round(corr, 5), "inclinacion_max_grados": round(incl, 3)}

    def z_min_ahora() -> float:
        return min(float(z_minimo(o.data.root_pos_w, o.data.root_quat_w, tam).min()) for o in dinamicos)

    informe = {"num_envs": n, "paneles_en_pila": en_pila, "dt_s": dt, "carga_s": round(carga_s, 1),
               "tolerancias": TOL, "limite_friccion_n": {k: round(v, 1) for k, v in limite_n.items()}}
    ok = True

    if a.escenarios:
        inicio = torch.zeros(n, 3, device=dev)
        fuerza = torch.zeros(n, 1, 3, device=dev)
        for i, (_, donde, corrimiento, fraccion, _) in enumerate(ESCENARIOS):
            base = {"tubo": slot, "caida": slot + torch.tensor([0.0, 0.0, CAIDA_M], device=dev), "pila": en_la_pila,
                    "suelo": torch.tensor([float(slot[0]), -2.5, float(tam[2]) / 2], device=dev)}[donde]
            inicio[i] = base + torch.tensor([0.0, corrimiento, 0.0], device=dev)
            fuerza[i, 0, 0] = fraccion * limite_n.get(donde, 0.0)
        poner_panel(inicio)
        reposo = inicio.clone()
        reposo[1] = slot  # el panel que cae tiene que terminar en el slot
        z_min = float("inf")
        for k in range(int(SEGUNDOS / dt)):
            t = k * dt
            empujar = EMPUJE_DESDE_S <= t < EMPUJE_DESDE_S + EMPUJE_DURA_S
            panel.set_external_force_and_torque(fuerza if empujar else torch.zeros_like(fuerza), torch.zeros_like(fuerza))
            paso()
            z_min = min(z_min, z_min_ahora())
        movido = ((panel.data.root_pos_w - origen) - reposo).norm(dim=1)
        inclinado = inclinacion_grados(panel.data.root_quat_w)
        informe["escenarios"] = []
        for i, (nombre, donde, _, _, espera) in enumerate(ESCENARIOS):
            m, g, empuje = float(movido[i]), float(inclinado[i]), float(fuerza[i, 0, 0])
            previsto = resbalon_m(empuje, limite_n.get(donde, 0.0), desc["panel"]["masa_kg"])
            if espera == "queda":
                cumple = m <= TOL["posicion_m"] and g <= TOL["inclinacion_grados"]
            elif empuje:
                cumple = abs(m - previsto) <= TOL["resbalon_rel"] * previsto
            else:
                cumple = g > TOL["inclinacion_grados"]
            informe["escenarios"].append({"nombre": nombre, "espera": espera, "empuje_n": round(empuje, 1),
                                          "movido_m": round(m, 4), "resbalon_previsto_m": round(previsto, 4),
                                          "inclinacion_grados": round(g, 2), "ok": cumple})
            ok &= cumple
        informe["z_minimo_m"] = round(z_min, 5)
        ok &= z_min >= TOL["z_minimo_m"]
    else:
        # 1. Asentamiento: el panel parte sobre la pila. Nada se mueve ni baja del suelo.
        z_min = float("inf")
        for _ in range(int(SEGUNDOS / dt)):
            paso()
            z_min = min(z_min, z_min_ahora())
        sobre_pila = float(((panel.data.root_pos_w - origen) - en_la_pila).norm(dim=1).max())
        asentamiento = {**estado_pila(), "panel_sobre_pila_corrimiento_max_m": round(sobre_pila, 5),
                        "z_minimo_m": round(z_min, 5)}
        asentamiento["ok"] = (asentamiento["corrimiento_max_m"] <= TOL["posicion_m"] and sobre_pila <= TOL["posicion_m"]
                              and asentamiento["inclinacion_max_grados"] <= TOL["inclinacion_grados"]
                              and z_min >= TOL["z_minimo_m"])
        informe["asentamiento"] = asentamiento
        ok &= asentamiento["ok"]

        # 2. Velocidad. Cada bloque cronometra solo el lazo de un entorno RL: escribir, paso de física, leer.
        def bloque(caida_cada: int | None) -> float:
            torch.cuda.synchronize()
            t = time.perf_counter()
            for k in range(a.pasos):
                if caida_cada and k % caida_cada == 0:
                    poner_panel((slot + torch.tensor([0.0, 0.0, CAIDA_M], device=dev)).expand(n, 3))
                paso()
            torch.cuda.synchronize()
            return a.pasos / (time.perf_counter() - t)

        def medir(caida_cada: int | None) -> dict:
            v = sorted(bloque(caida_cada) for _ in range(BLOQUES))
            return {"pasos_fisica_s": round(v[len(v) // 2], 1), "rango": [round(v[0], 1), round(v[-1], 1)],
                    "env_pasos_s": round(v[len(v) // 2] * n), "bloques": BLOQUES, "pasos_por_bloque": a.pasos}

        informe["velocidad"] = {"en_reposo": medir(None), "panel_cae_cada_1s": medir(int(1 / dt))}

        # 3. Después de las caídas: 2 s más y el panel tiene que estar en el slot, en todas las copias.
        for _ in range(int(2.0 / dt)):
            paso()
            z_min = min(z_min, z_min_ahora())
        en_slot = ((panel.data.root_pos_w - origen) - slot).norm(dim=1)
        incl = inclinacion_grados(panel.data.root_quat_w)
        final = {**estado_pila(), "panel_error_max_m": round(float(en_slot.max()), 5),
                 "panel_inclinacion_max_grados": round(float(incl.max()), 3),
                 "copias_fuera_de_tolerancia": int(((en_slot > TOL["posicion_m"]) | (incl > TOL["inclinacion_grados"])).sum()),
                 "z_minimo_m": round(z_min, 5),
                 "estados_no_finitos": int(sum((~torch.isfinite(o.data.root_state_w)).sum() for o in dinamicos))}
        final["ok"] = (final["copias_fuera_de_tolerancia"] == 0 and final["corrimiento_max_m"] <= TOL["posicion_m"]
                       and final["inclinacion_max_grados"] <= TOL["inclinacion_grados"]
                       and z_min >= TOL["z_minimo_m"] and final["estados_no_finitos"] == 0)
        informe["final"] = final
        ok &= final["ok"]
        informe["gpu_mib"] = _gpu_mib()
        informe["torch_gpu_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)

    if a.imagen:
        informe["imagen"] = guardar_imagen(sim, escena, camara, a.imagen, dt)
        ok &= informe["imagen"]["brillo_medio"] > 10

    informe["ok"] = bool(ok)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2), flush=True)
    sim.clear_all_callbacks()
    sim.clear_instance()
    return bool(ok)


if __name__ == "__main__":
    main()
