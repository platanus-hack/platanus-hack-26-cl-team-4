"""Prueba de física de la escena en Isaac Lab. Lo primero que hay que correr en el pod.

    $ISAACLAB_SH -p sim/prueba_fisica.py --headless --dir <carpeta> [--paneles 3] [--con-robot]

La carpeta necesita entorno.json (y clon.json + robot.urdf con --con-robot). Si falta escena.usd, lo genera.
Suelta cada panel 10 cm sobre su slot y espera 3 s. Pasa si cada panel:
- tiene la masa de entorno.json (±1 %),
- queda apoyado sobre el tubo: ±1 cm de altura, ±2 cm en el plano y menos de 2° de inclinación,
- queda quieto: menos de 1 cm/s.
Con --con-robot también revisa que el robot cargue con sus 6 articulaciones y su masa total.
Escribe prueba_fisica.json en la carpeta y termina con código 1 si algo falla.
SIN PROBAR EN ISAAC LAB: la API es de Isaac Lab 2.x; el primer error real va a aparecer aquí.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

TOL = {"altura_m": 0.01, "plano_m": 0.02, "inclinacion_grados": 2.0, "velocidad_m_s": 0.01, "masa_rel": 0.01}
CAIDA_M = 0.10


def _inclinacion_grados(quat_wxyz) -> float:
    """Ángulo entre la normal del panel y la vertical."""
    w, x, y, z = (float(v) for v in quat_wxyz)
    nz = 1 - 2 * (x * x + y * y)  # componente Z del eje Z local rotado
    return math.degrees(math.acos(max(-1.0, min(1.0, nz))))


def main() -> None:
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--paneles", type=int, default=3)
    ap.add_argument("--con-robot", action="store_true")
    ap.add_argument("--segundos", type=float, default=3.0)
    AppLauncher.add_app_launcher_args(ap)
    a = ap.parse_args()
    app = AppLauncher(a).app

    import generar_escena
    import viaz_escena
    import isaaclab.sim as sim_utils
    from isaaclab.scene import InteractiveScene

    entorno = json.loads((a.dir / "entorno.json").read_text(encoding="utf-8"))
    clon = json.loads((a.dir / "clon.json").read_text(encoding="utf-8")) if a.con_robot else None
    if not (a.dir / "escena.usd").exists():
        (a.dir / "escena.usd").write_text(generar_escena.escena_usda(entorno), encoding="utf-8")

    desc = viaz_escena.describir(entorno, a.paneles, caida_m=CAIDA_M, con_robot=a.con_robot, clon=clon)
    sim = sim_utils.SimulationContext(viaz_escena.sim_cfg())
    escena = InteractiveScene(viaz_escena.construir_cfg(desc, a.dir))
    sim.reset()

    pasos = int(a.segundos / desc["dt_s"])
    for _ in range(pasos):
        escena.write_data_to_sim()
        sim.step(render=False)
        escena.update(desc["dt_s"])

    informe = {"tolerancias": TOL, "paneles": [], "robot": None}
    ok = True
    for p in desc["paneles"]:
        obj = escena[p["nombre"]]
        pos = [float(v) for v in obj.data.root_pos_w[0]]
        quat = obj.data.root_quat_w[0]
        vel = float(obj.data.root_lin_vel_w[0].norm())
        masa = float(obj.root_physx_view.get_masses()[0].sum())
        esp = p["pos_esperada_m"]
        r = {
            "panel": p["nombre"], "pos_m": [round(v, 4) for v in pos], "esperada_m": list(esp),
            "error_altura_m": round(pos[2] - esp[2], 4),
            "error_plano_m": round(math.dist(pos[:2], esp[:2]), 4),
            "inclinacion_grados": round(_inclinacion_grados(quat), 2),
            "velocidad_m_s": round(vel, 4),
            "masa_kg": round(masa, 3), "masa_esperada_kg": p["masa_kg"],
        }
        r["ok"] = (abs(r["error_altura_m"]) <= TOL["altura_m"] and r["error_plano_m"] <= TOL["plano_m"]
                   and r["inclinacion_grados"] <= TOL["inclinacion_grados"] and vel <= TOL["velocidad_m_s"]
                   and abs(masa - p["masa_kg"]) <= TOL["masa_rel"] * p["masa_kg"])
        ok &= r["ok"]
        informe["paneles"].append(r)

    if desc["robot"]:
        robot = escena["robot"]
        nombres = list(robot.joint_names)
        faltan = [j for j in desc["robot"]["q_inicial"] if j not in nombres]
        informe["robot"] = {
            "articulaciones": nombres, "faltan": faltan,
            "masa_total_kg": round(float(robot.root_physx_view.get_masses()[0].sum()), 1),
            "pos_base_m": [round(float(v), 3) for v in robot.data.root_pos_w[0]],
        }
        ok &= not faltan

    informe["ok"] = ok
    (a.dir / "prueba_fisica.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    app.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
