"""Prueba de física del parque del demo en Isaac Lab. Lo primero que hay que correr en el pod.

    python sim/generar_escena.py --dir <carpeta>
    $ISAACLAB_SH -p sim/prueba_fisica.py --headless --dir <carpeta> [--paneles 3] [--pila 5] [--con-robot]
    $ISAACLAB_SH -p sim/prueba_fisica.py --headless --enable_cameras --dir <carpeta> --imagen <carpeta>/parque.png

La carpeta necesita entorno.json. Si falta escena.usd, lo genera. tarea.json da el tamaño de la pila.
clon.json dice dónde lleva el robot la pila (sin él va en un pallet). --con-robot también pide robot.urdf.
Carga escena.usd, revisa que calce con entorno.json, suelta cada panel 10 cm sobre su slot y espera 5 s.
Pasa si:
- cada panel tiene la masa de entorno.json (±1 %),
- cada panel de la fila 0 queda sobre el tubo y cada panel de la pila sigue en su lugar:
  a 5 mm o menos, con menos de 1° de inclinación y a menos de 1 cm/s,
- ningún panel baja de z = -1 mm en ningún paso (no atraviesa el suelo).
Con --con-robot también revisa que el robot cargue con sus 6 articulaciones y su masa total.
Escribe prueba_fisica.json en la carpeta y termina con código 1 si algo falla.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

TOL = {"altura_m": 0.005, "plano_m": 0.005, "inclinacion_grados": 1.0, "velocidad_m_s": 0.01, "masa_rel": 0.01,
       "z_minimo_m": -0.001}
CAIDA_M = 0.10


def inclinacion_grados(quat):
    """Ángulo entre la normal del panel y la vertical. quat: tensor (N, 4) en orden w, x, y, z."""
    import torch

    nz = 1 - 2 * (quat[:, 1] ** 2 + quat[:, 2] ** 2)  # componente Z del eje Z local rotado
    return torch.rad2deg(torch.acos(nz.clamp(-1.0, 1.0)))


def z_minimo(pos, quat, tam):
    """Z de la esquina más baja de una caja. pos (N, 3), quat (N, 4) w, x, y, z, tam (3,) en metros."""
    w, x, y, z = quat.unbind(-1)
    fila_z = (2 * (x * z - w * y)).abs() * tam[0] + (2 * (y * z + w * x)).abs() * tam[1] \
        + (1 - 2 * (x * x + y * y)).abs() * tam[2]
    return pos[:, 2] - fila_z / 2


def _leer(carpeta: Path, nombre: str) -> dict | None:
    f = carpeta / nombre
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def guardar_imagen(sim, escena, camara: dict, destino: Path, dt: float) -> dict:
    """Apunta la cámara de la escena, deja que el render converja y guarda un PNG."""
    import torch
    from PIL import Image

    cam = escena["camara"]
    cam.set_world_poses_from_view(torch.tensor([camara["ojo_m"]], device=sim.device),
                                  torch.tensor([camara["mira_m"]], device=sim.device))
    for _ in range(40):  # el trazado de rayos necesita varios frames para limpiar el ruido
        sim.render()
        escena.update(dt)
    rgb = cam.data.output["rgb"][0, ..., :3].cpu().numpy()
    Image.fromarray(rgb).save(destino)
    return {"archivo": str(destino), "tam_px": [int(rgb.shape[1]), int(rgb.shape[0])],
            "brillo_medio": round(float(rgb.mean()), 1)}


def main() -> None:
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--paneles", type=int, default=3)
    ap.add_argument("--pila", type=int, default=None, help="paneles en la pila; por defecto, los de tarea.json")
    ap.add_argument("--con-robot", action="store_true")
    ap.add_argument("--segundos", type=float, default=5.0)
    ap.add_argument("--imagen", type=Path, default=None, help="guarda un PNG de la cámara del demo (--enable_cameras)")
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
    import generar_escena
    import viaz_escena
    import isaaclab.sim as sim_utils
    from isaaclab.scene import InteractiveScene

    salida = a.dir / "prueba_fisica.json"
    salida.unlink(missing_ok=True)  # un informe viejo no puede pasar por el de esta corrida
    entorno = _leer(a.dir, "entorno.json")
    tarea, clon = _leer(a.dir, "tarea.json"), _leer(a.dir, "clon.json")
    if not (a.dir / "escena.usd").exists():
        (a.dir / "escena.usd").write_text(generar_escena.escena_usda(entorno), encoding="utf-8")
    n_pila = a.pila if a.pila is not None else (tarea["pila_paneles"]["cantidad"] if tarea else 0)

    desc = viaz_escena.describir(entorno, a.paneles, caida_m=CAIDA_M, con_robot=a.con_robot, clon=clon, n_pila=n_pila)
    camara = viaz_escena.camara_demo(entorno) if a.imagen else None
    sim = sim_utils.SimulationContext(viaz_escena.sim_cfg(a.device))
    escena = InteractiveScene(viaz_escena.construir_cfg(desc, a.dir, camara=camara))
    sim.reset()

    informe = {"tolerancias": TOL, "segundos": a.segundos, "paneles": [], "robot": None,
               "escena_usd": viaz_escena.revisar_usd(sim.stage, entorno, raiz="/World/Planta/Planta")}
    ok = not informe["escena_usd"]

    cuerpos = desc["paneles"] + desc["pila"]
    tam = torch.tensor(cuerpos[0]["tam_m"], device=sim.device) if cuerpos else None
    z_min = {p["nombre"]: math.inf for p in cuerpos}
    for _ in range(int(a.segundos / desc["dt_s"])):
        escena.write_data_to_sim()
        sim.step(render=False)
        escena.update(desc["dt_s"])
        for p in cuerpos:
            d = escena[p["nombre"]].data
            z_min[p["nombre"]] = min(z_min[p["nombre"]], float(z_minimo(d.root_pos_w, d.root_quat_w, tam)[0]))

    for p in cuerpos:
        obj = escena[p["nombre"]]
        pos = [float(v) for v in obj.data.root_pos_w[0]]
        vel = float(obj.data.root_lin_vel_w[0].norm())
        masa = float(obj.root_physx_view.get_masses()[0].sum())
        friccion = [round(float(v), 4) for v in obj.root_physx_view.get_material_properties()[0, 0]]
        esp = p["pos_esperada_m"]
        r = {
            "panel": p["nombre"], "pos_m": [round(v, 4) for v in pos], "esperada_m": list(esp),
            "error_altura_m": round(pos[2] - esp[2], 4),
            "error_plano_m": round(math.dist(pos[:2], esp[:2]), 4),
            "inclinacion_grados": round(float(inclinacion_grados(obj.data.root_quat_w)[0]), 3),
            "velocidad_m_s": round(vel, 4),
            "z_minimo_m": round(z_min[p["nombre"]], 4),
            "masa_kg": round(masa, 3), "masa_esperada_kg": p["masa_kg"],
            "friccion_physx": friccion,
        }
        r["ok"] = (abs(r["error_altura_m"]) <= TOL["altura_m"] and r["error_plano_m"] <= TOL["plano_m"]
                   and r["inclinacion_grados"] <= TOL["inclinacion_grados"] and vel <= TOL["velocidad_m_s"]
                   and r["z_minimo_m"] >= TOL["z_minimo_m"]
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

    if a.imagen:
        informe["imagen"] = guardar_imagen(sim, escena, camara, a.imagen, desc["dt_s"])
        ok &= informe["imagen"]["brillo_medio"] > 10

    informe["ok"] = bool(ok)
    salida.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False, indent=2), flush=True)
    sim.clear_all_callbacks()
    sim.clear_instance()
    return bool(ok)


if __name__ == "__main__":
    main()
