"""Prueba del robot de la corrida dentro del entorno RL, en Isaac Lab. Primer paso en el pod.

    $ISAACLAB_SH -p sim/rl/prueba_robot.py --entorno E --tarea T --robot R --salida prueba_robot.json

Pasa si:
- el robot carga con las 6 articulaciones del URDF y su masa total (±1 %),
- PhysX tiene el recorrido, el torque y la velocidad máximos del URDF en cada articulación (RF-INT-23),
- la cinemática directa del entorno calza con la pose de la ventosa en PhysX (2 mm),
- la base queda donde el entorno la puso, con su ruido (RF-INT-19),
- el brazo sostiene la pose de dejar el panel durante 3 s (error menor que 0,02 rad),
- la pila sigue en su lugar sobre la base (5 mm).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
TOL = {"masa_rel": 0.01, "limite": 1e-3, "cinematica_m": 0.002, "base_m": 0.001, "pose_rad": 0.02, "pila_m": 0.005}
SEGUNDOS = 3.0


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--num-envs", type=int, default=16)
    ap.add_argument("--usd", type=Path, help="exporta la escena a este archivo USD")
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: probar(a), a.salida)


def probar(a) -> dict:
    import torch

    from rl import cinematica as cin
    from rl import tarea as tarea_mod
    from rl.robot import ARTICULACIONES

    env = comun.crear_entorno(a, a.num_envs).unwrapped
    env.reset()
    robot, c, t, dev = env.robot, env.cadena, env.tarea, env.device
    vista = robot.root_physx_view
    urdf = env.corrida.robot
    informe = {"robot_id": env.corrida.clon["robot_id"], "num_envs": env.num_envs, "tolerancias": TOL}

    nombres = [robot.joint_names[i] for i in env.ids]
    masa = float(vista.get_masses()[0].sum())
    informe["articulaciones"] = nombres
    informe["masa_kg"] = {"physx": round(masa, 2), "urdf": round(urdf.masa_kg, 2)}
    ok = nombres == list(ARTICULACIONES) and robot.num_joints == 6
    ok &= abs(masa - urdf.masa_kg) <= TOL["masa_rel"] * urdf.masa_kg

    ids = torch.tensor(env.ids)
    limites = vista.get_dof_limits()[0][ids].cpu()
    torque = vista.get_dof_max_forces()[0][ids].cpu()
    velocidad = vista.get_dof_max_velocities()[0][ids].cpu()
    informe["limites"] = []
    for k, u in enumerate(urdf.articulaciones):
        leido = {"inferior": float(limites[k, 0]), "superior": float(limites[k, 1]), "esfuerzo": float(torque[k]),
                 "velocidad": float(velocidad[k])}
        pedido = {"inferior": u.inferior, "superior": u.superior, "esfuerzo": u.esfuerzo, "velocidad": u.velocidad}
        calza = all(abs(leido[x] - pedido[x]) <= TOL["limite"] * max(1.0, abs(pedido[x])) for x in pedido)
        informe["limites"].append({"articulacion": u.nombre, "physx": {x: round(v, 4) for x, v in leido.items()},
                                   "urdf": pedido, "ok": calza})
        ok &= calza

    # Pose de dejar el panel, con el ruido de base de cada copia. Sin acción: el objetivo no cambia.
    base, rumbo = env.base_pos, env.base_rumbo
    meta_b = cin.a_base(env.meta_w.unbind(-1), base.unbind(-1), rumbo, torch)
    panel_b = tuple(torch.full((env.num_envs,), v, device=dev) for v in t.panel_en_pila(t.en_pila - 1))
    puntos = tarea_mod.recorrido(t, panel_b, torch.zeros_like(rumbo), meta_b, -rumbo)
    q_dejar = torch.stack(tarea_mod.angulos(c, puntos, torch)["retirar"][0], -1)
    todas = robot.data.default_joint_pos.clone()
    todas[:, env.ids] = q_dejar
    robot.write_joint_state_to_sim(todas, torch.zeros_like(todas))
    env.q_obj[:] = q_dejar
    pila_antes = [p.data.root_pos_w.clone() for p in [env.panel, *env.pila]]
    quieto = torch.zeros(env.num_envs, 7, device=dev)
    quieto[:, 6] = -1.0
    for _ in range(int(SEGUNDOS / env.step_dt)):
        env.step(quieto)
        env.episode_length_buf[:] = 0   # la prueba no quiere reinicios
    q = robot.data.joint_pos[:, env.ids]
    error_pose = float((q - q_dejar).abs().max())
    informe["sostener_pose"] = {"error_max_rad": round(error_pose, 4), "torque_max_nm": [
        round(float(v), 1) for v in robot.data.applied_torque[:, env.ids].abs().max(dim=0).values]}
    ok &= error_pose <= TOL["pose_rad"]

    cuerpo = robot.data.body_link_pose_w[:, env.id_ventosa[0]]
    w, x, y, z = cuerpo[:, 3:7].unbind(-1)
    normal = torch.stack([2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)], -1)
    cara_physx = cuerpo[:, :3] + normal * c.placa
    cara_fk = torch.stack(env.ventosa()[0], -1)
    error_fk = float((cara_physx - cara_fk).norm(dim=-1).max())
    error_base = float((robot.data.root_pos_w - base).norm(dim=-1).max())
    informe["cinematica_error_max_m"] = round(error_fk, 5)
    informe["base"] = {"error_max_m": round(error_base, 5), "desvio_max_m": round(float(
        (base - env.scene.env_origins - torch.tensor(t.base, device=dev)).norm(dim=-1).max()), 4),
        "rumbo_max_grados": round(float(torch.rad2deg(rumbo.abs().max())), 2)}
    ok &= error_fk <= TOL["cinematica_m"] and error_base <= TOL["base_m"]

    movida = max(float((p.data.root_pos_w - antes).norm(dim=-1).max()) for p, antes in zip([env.panel, *env.pila], pila_antes))
    informe["pila_corrimiento_max_m"] = round(movida, 5)
    ok &= movida <= TOL["pila_m"]
    informe["fuerza_ventosa_n"] = round(env.fuerza_n, 1)
    if a.usd:
        from rl import vivo
        informe["usd"] = vivo.exportar(env, a.usd)
    informe["ok"] = bool(ok)
    return informe


if __name__ == "__main__":
    main()
