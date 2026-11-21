"""Comando `validar_robot` del contrato (docs/contrato-entorno-rl.md §6): prueba el robot en la escena.

    $ISAACLAB_SH -p sim/rl/validar_robot.py --entorno E --tarea T --robot R [--escena S] --salida validacion.json
        [--video construccion.mp4]

Revisa, en este orden:
1. Sin Isaac: que el URDF sea de la familia que el entorno sabe mover, que la ventosa alcance cada punto del
   recorrido y que la carga útil sostenga el panel. Con el agarre por succión, que la ventosa también lo sostenga.
2. En Isaac: que el robot cargue sin chocar al inicio y que el oráculo tome el panel de la pila y lo deje
   sobre el tubo sin saturar el torque de ninguna articulación.
Escribe {"ok", "problemas", "fuente": "isaac"}. Cada problema es una oración con números (RF-CLO-05).
Con --video graba la construcción (RF-CLO-09): escena vacía, base, brazo, ventosa y la prueba de alcance.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
TORQUE_USO_MAX = 0.98       # fracción del torque máximo sobre la cual la articulación está saturada
PASOS_SATURADA = 10         # pasos de control seguidos en saturación que cuentan como "sin margen" (0,33 s)
MARGEN_SUCCION = 1.2        # la succión tiene que sostener el panel más pesado (+10 %) con este margen
PASOS_INICIO = 30           # 1 s quieto: nada debe chocar ni moverse
PASOS_PRUEBA = 420          # tiempo máximo de la prueba de alcance con el oráculo
APARECE_CADA = 30           # cuadros entre una pieza y la siguiente en el video (1 s)
PIEZAS = (("base_link",), ("hombro", "brazo", "antebrazo", "muneca_1", "muneca_2"), ("efector",))


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--video", type=Path)
    a = ap.parse_args()
    app = comun.lanzar(a, camaras=bool(a.video))
    comun.ejecutar(app, lambda: validar(a), a.salida)


def problemas_sin_isaac(a) -> list[str]:
    """Lo que se puede decidir leyendo los archivos de la corrida."""
    import viaz_escena
    from rl import agarre, corrida as corrida_mod, tarea as tarea_mod

    try:
        c = corrida_mod.leer(a.entorno, a.tarea, a.robot)
    except (ValueError, FileNotFoundError, KeyError) as e:
        return [str(e)]
    panel_kg = c.entorno["panel"]["peso_kg"]
    lista = []
    if c.carga_util_kg < panel_kg:
        lista.append(f"carga útil {c.carga_util_kg:g} kg menor que el panel ({panel_kg:g} kg)")
    rangos = viaz_escena.fisica.rangos_variacion(c.entorno)
    peso_max_n = panel_kg * rangos["masa_panel_escala"][1] * agarre.GRAVEDAD
    fuerza = agarre.fuerza_ventosa_n(c.carga_util_kg)
    if a.agarre == "succion" and fuerza < MARGEN_SUCCION * peso_max_n:
        lista.append(f"la ventosa aprieta con {fuerza:.0f} N y el panel más pesado pide {MARGEN_SUCCION * peso_max_n:.0f} N; "
                     f"sube la carga útil sobre {MARGEN_SUCCION * peso_max_n / (agarre.FACTOR_VENTOSA * agarre.GRAVEDAD):.0f} kg")
    return lista + tarea_mod.problemas_alcance(tarea_mod.de_corrida(c)[1], c.cadena)


def validar(a) -> dict:
    problemas = problemas_sin_isaac(a)
    if problemas:
        return {"ok": False, "problemas": problemas, "fuente": "isaac"}

    import torch

    from rl import grabacion, oraculo
    from rl.entorno import FUERZA_CHOQUE_N
    from rl.robot import ARTICULACIONES

    env_gym = comun.crear_entorno(a, 1, render=bool(a.video), variar=False)
    env = env_gym.unwrapped
    env.reset()
    quieto = torch.zeros(1, 7, device=env.device)
    quieto[:, 6] = -1.0
    salida = grabacion.Video(a.video) if a.video else None
    if salida:
        from pxr import UsdGeom

        grabacion.camara_lateral(env)
        copia = "/World/envs/env_0"
        prims = {n: [f"{copia}/Robot/{n}"] for g in PIEZAS for n in g}
        prims["base_link"] += [f"{copia}/Panel", *(f"{copia}/Pila_{k}" for k in range(len(env.pila)))]   # la pila llega con la base
        prims = {n: [UsdGeom.Imageable(env.sim.stage.GetPrimAtPath(r)) for r in rutas] for n, rutas in prims.items()}
        for p in sum(prims.values(), []):
            p.MakeInvisible()
        for grupo in ((), *PIEZAS):   # escena vacía, después una pieza por segundo
            for p in sum((prims[n] for n in grupo), []):
                p.MakeVisible()
            for _ in range(APARECE_CADA):
                env.step(quieto)
                salida.cuadro(env_gym.render())

    # Inicio: 1 s quieto. Ningún eslabón del brazo toca nada y la pila no se mueve.
    panel_antes = env.panel.data.root_pos_w.clone()
    fuerza_inicio = 0.0
    for _ in range(PASOS_INICIO):
        env.step(quieto)
        fuerza_inicio = max(fuerza_inicio, float(env.contactos.data.net_forces_w.norm(dim=-1).max()))
    if fuerza_inicio > FUERZA_CHOQUE_N:
        problemas.append(f"el brazo choca al inicio: fuerza de contacto de {fuerza_inicio:.0f} N en la pose de espera")
    corrido = float((env.panel.data.root_pos_w - panel_antes).norm())
    if corrido > 0.005:
        problemas.append(f"la pila no queda quieta sobre la base: el panel se corre {corrido * 100:.1f} cm en 1 s")

    # Prueba de alcance: el oráculo hace la tarea completa.
    env.reset()
    guia = oraculo.Oraculo(env)
    uso = torch.zeros(6, device=env.device)
    seguidos = torch.zeros(6, dtype=torch.long, device=env.device)
    saturada = torch.zeros(6, dtype=torch.long, device=env.device)
    contacto = torch.zeros(len(env.contactos.body_names), device=env.device)   # mayor fuerza sobre cada eslabón del brazo
    limite = torch.tensor(env.cadena.esfuerzo, device=env.device)
    resultado = None
    for k in range(PASOS_PRUEBA):
        _, _, terminado, truncado, _ = env.step(guia.accion())
        contacto = torch.maximum(contacto, env.contactos.data.net_forces_w[0].norm(dim=-1))
        ahora = env.robot.data.applied_torque[0, env.ids].abs() / limite
        uso = torch.maximum(uso, ahora)
        seguidos = torch.where(ahora > TORQUE_USO_MAX, seguidos + 1, torch.zeros_like(seguidos))
        saturada = torch.maximum(saturada, seguidos)
        if salida and k % 3 != 2:   # la prueba va a 1,5 veces la velocidad real, para que el clip dure menos de 10 s
            salida.cuadro(env_gym.render())
        if bool(terminado[0] | truncado[0]):
            resultado = {k: float(v[0]) for k, v in env.final.items()}
            break
    if resultado is None or not resultado["exito"]:
        fase = oraculo.FASES[int(guia.fase[0])]
        if resultado and resultado["choque"]:
            k = int(contacto.argmax())
            detalle = f"el eslabón '{env.contactos.body_names[k]}' choca con {float(contacto[k]):.0f} N en la fase '{fase}'"
        else:
            detalle = f"se quedó en la fase '{fase}'"
        lejos_m = resultado["err_pos_m"] if resultado else float(env.medir()["err_pos"][0])
        problemas.append(f"el brazo no logra dejar el panel sobre el tubo: {detalle}, con el panel a "
                         f"{lejos_m * 100:.0f} cm de su lugar")
    for nombre, pasos, maximo in zip(ARTICULACIONES, saturada.tolist(), env.cadena.esfuerzo):
        if pasos >= PASOS_SATURADA:
            problemas.append(f"{nombre} trabaja en su torque máximo de {maximo:.0f} N·m durante {pasos * env.step_dt:.1f} s "
                             f"con el panel: no tiene margen")
    informe = {"ok": not problemas, "problemas": problemas, "fuente": "isaac",
               "torque_usado": {n: round(f, 3) for n, f in zip(ARTICULACIONES, uso.tolist())}}
    if salida:
        informe["video"] = salida.cerrar()
    return informe


if __name__ == "__main__":
    main()
