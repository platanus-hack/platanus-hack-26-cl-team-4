"""Prueba del agarre por succión virtual en Isaac Lab: toma, sostiene y suelta un panel. Segundo paso en el pod.

    $ISAACLAB_SH -p sim/rl/prueba_agarre.py --entorno E --tarea T --robot R --salida prueba_agarre.json

El oráculo toma el panel de la pila, lo lleva sobre el tubo y se detiene ahí 3 s. Después lo apoya y lo suelta.
Pasa si, en todas las copias:
- la ventosa sella el panel de la pila,
- mientras lo sostiene quieto, el panel se corre menos de 1 mm y gira menos de 0,1° respecto de la ventosa,
- el hombro carga el peso real del panel: su torque sube lo que pesa el panel por su distancia al hombro (±10 %),
- al soltar, el panel queda apoyado sobre el tubo dentro de 5 cm y 5°, y la ventosa ya no lo sostiene.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
TOL = {"deriva_m": 0.001, "deriva_grados": 0.1, "torque_rel": 0.10, "pos_m": 0.05, "ang_grados": 5.0}
SOSTENER_S = 3.0
PASOS_MAX = 600


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--num-envs", type=int, default=16)
    ap.add_argument("--usd", type=Path, help="exporta la escena y una animación de la prueba junto a este archivo USD")
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: probar(a), a.salida)


def probar(a) -> dict:
    import math

    import torch

    from rl import agarre, oraculo, tarea as tarea_mod, vivo
    from rl import cinematica as cin

    env = comun.crear_entorno(a, a.num_envs, variar=False).unwrapped
    env.reset()
    robot, c, t, dev, n = env.robot, env.cadena, env.tarea, env.device, env.num_envs
    hombro = env.ids[1]
    quieto = torch.zeros(n, 7, device=dev)
    quieto[:, 6] = -1.0
    informe = {"robot_id": env.corrida.clon["robot_id"], "num_envs": n, "tolerancias": TOL,
               "agarre": env.cfg.agarre, "fuerza_ventosa_n": round(env.fuerza_n, 1), "panel_kg": t.panel_masa_kg}

    def pasos(cantidad: int, accion=None, grabadora=None) -> None:
        for _ in range(cantidad):
            env.step(quieto if accion is None else accion())
            env.episode_length_buf[:] = 1   # la prueba no quiere reinicios por tiempo
            if grabadora:
                grabadora.cuadro()

    # Referencia: torque del hombro en la pose de traslado sobre el tubo, sin panel.
    meta_b = cin.a_base(env.meta_w.unbind(-1), env.base_pos.unbind(-1), env.base_rumbo, torch)
    panel_b = tuple(torch.full((n,), v, device=dev) for v in t.panel_en_pila(t.en_pila - 1))
    cero = torch.zeros(n, device=dev)
    q_sobre = torch.stack(tarea_mod.angulos(c, tarea_mod.recorrido(t, panel_b, cero, meta_b, cero), torch)["sobre_meta"][0], -1)
    todas = robot.data.default_joint_pos.clone()
    todas[:, env.ids] = q_sobre
    robot.write_joint_state_to_sim(todas, torch.zeros_like(todas))
    env.q_obj[:] = q_sobre
    pasos(60)
    torque_sin = robot.data.applied_torque[:, hombro].clone()

    # Tomar y llevar: el oráculo se detiene sobre el tubo.
    env.reset()
    guia = oraculo.Oraculo(env)
    grabadora = vivo.Grabadora(env) if a.usd else None
    guia.fase_max = oraculo.FASES.index("llevar")
    k = 0
    while k < PASOS_MAX and not bool(((guia.fase == guia.fase_max) & (guia.error < 0.02)).all()):
        pasos(1, guia.accion, grabadora)
        k += 1
    informe["pasos_hasta_sostener"] = k
    informe["sellan"] = int(env.sellada.sum())
    pasos(30, guia.accion, grabadora)   # deja que el brazo termine de asentarse

    def relativo():
        m = env.medir()
        inverso = cin.quat_conj(m["ventosa_quat"])
        pos = cin.quat_rotar(inverso, tuple(m["panel_pos"][j] - m["ventosa_pos"][j] for j in range(3)))
        return torch.stack(pos, -1), cin.rumbo(m["panel_quat"], torch) - cin.rumbo(m["ventosa_quat"], torch)

    pos0, rumbo0 = relativo()
    pasos(int(SOSTENER_S / env.step_dt), guia.accion, grabadora)
    pos1, rumbo1 = relativo()
    deriva = float((pos1 - pos0).norm(dim=-1).max())
    giro = float(torch.rad2deg(cin.envolver(rumbo1 - rumbo0, math.pi, torch).abs().max()))
    torque_con = robot.data.applied_torque[:, hombro]
    m = env.medir()
    panel_base = cin.a_base(m["panel_pos"], env.base_pos.unbind(-1), env.base_rumbo, torch)
    brazo_m = torch.hypot(panel_base[0] - c.montaje_x, panel_base[1])
    esperado = t.panel_masa_kg * agarre.GRAVEDAD * brazo_m
    medido = (torque_con - torque_sin).abs()
    error_torque = float(((medido - esperado).abs() / esperado).max())
    informe["sostener"] = {"segundos": SOSTENER_S, "deriva_max_m": round(deriva, 5), "giro_max_grados": round(giro, 4),
                           "siguen_selladas": int(env.sellada.sum())}
    informe["torque_hombro_nm"] = {"sin_panel": round(float(torque_sin.abs().mean()), 1),
                                   "con_panel": round(float(torque_con.abs().mean()), 1),
                                   "sube": round(float(medido.mean()), 1), "esperado": round(float(esperado.mean()), 1),
                                   "error_rel_max": round(error_torque, 4)}

    # Apoyar, soltar y retirar.
    guia.fase_max = len(oraculo.FASES) - 1
    listo = torch.zeros(n, dtype=torch.bool, device=dev)
    final = {"err_pos": torch.zeros(n, device=dev), "err_ang": torch.zeros(n, device=dev)}
    k = 0
    while k < PASOS_MAX and not bool(listo.all()):
        accion = guia.accion()
        _, _, terminado, truncado, _ = env.step(accion)
        if grabadora:
            grabadora.cuadro()
        nuevos = (terminado | truncado) & ~listo
        final["err_pos"] = torch.where(nuevos, env.final["err_pos_m"], final["err_pos"])
        final["err_ang"] = torch.where(nuevos, env.final["err_ang_grados"], final["err_ang"])
        listo |= nuevos & (env.final["exito"] > 0)
        k += 1
    informe["soltar"] = {"pasos": k, "exitos": int(listo.sum()), "err_pos_max_m": round(float(final["err_pos"].max()), 4),
                         "err_ang_max_grados": round(float(final["err_ang"].max()), 3)}
    ok = (informe["sellan"] == n and informe["sostener"]["siguen_selladas"] == n and deriva <= TOL["deriva_m"]
          and giro <= TOL["deriva_grados"] and error_torque <= TOL["torque_rel"] and int(listo.sum()) == n
          and float(final["err_pos"].max()) <= TOL["pos_m"] and float(final["err_ang"].max()) <= TOL["ang_grados"])
    if a.usd:
        informe["usd"] = [vivo.exportar(env, a.usd), grabadora.guardar(a.usd.with_name(a.usd.stem + "-animacion.usd"))]
    informe["ok"] = bool(ok)
    return informe


if __name__ == "__main__":
    main()
