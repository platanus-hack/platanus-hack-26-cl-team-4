"""Comando `evaluar` del contrato (docs/contrato-entorno-rl.md §4): mide la política de un checkpoint.

    $ISAACLAB_SH -p sim/rl/evaluar.py --entorno E --tarea T --robot R [--escena S] --checkpoint C --episodios 100
        --tolerancias 0.05:5,0.02:2 --salida DIR [--video DIR/video.mp4] [--trayectoria DIR/trayectoria.json]

Corre un episodio por copia, sin exploración ni inicios asistidos, con el ruido de base (RF-INT-19).
Cada episodio instala un panel de la secuencia, al azar, con los anteriores ya instalados (RF-INT-18).
Escribe DIR/evaluacion.json. La primera tolerancia es la del éxito del entorno. Las demás cuentan los
episodios exitosos cuyo panel además quedó dentro de esa tolerancia. DIR/evaluacion_detalle.json trae lo que
el esquema de evaluacion.json no admite: caídas, tiempo agotado y el resultado de cada panel de la secuencia.
--video graba la copia 0 con la cámara lateral: varios episodios seguidos en la escena de entrenamiento.
--trayectoria guarda un episodio (el primero exitoso, o el de la copia 0) para el visor web.

    ... evaluar.py --entorno E --tarea T --robot R --checkpoint C --secuencias 20 --salida DIR [--sin-fijar]

--secuencias N cambia el modo: cada copia instala todos los paneles de la secuencia, uno tras otro. Entre
paneles la base avanza con el controlador programado (sim/rl/base_movil.py) y el brazo vuelve a la pila.
Escribe DIR/secuencia.json: éxito de la secuencia completa y de cada panel, choques, caídas y ciclo.
Una secuencia termina en su primer panel fallado. --sin-fijar deja cada panel donde cayó, sin fijarlo en su slot.
En este modo --video graba la secuencia de la copia 0 y --usd la primera copia que la completa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
VIDEO_S = 24.0
USD_S = 10.0     # duración mínima de la animación de --usd


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--episodios", type=int, default=100)
    ap.add_argument("--tolerancias", default="0.05:5,0.02:2")
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--trayectoria", type=Path)
    ap.add_argument("--usd", type=Path, help="exporta una animación USD de las primeras copias")
    ap.add_argument("--secuencias", type=int, default=0, help="evalúa N secuencias completas en vez de episodios de un panel")
    ap.add_argument("--sin-fijar", action="store_true", help="en una secuencia, el panel instalado queda donde cayó")
    ap.add_argument("--semilla", type=int)
    a = ap.parse_args()
    app = comun.lanzar(a, camaras=bool(a.video))
    comun.ejecutar(app, lambda: evaluar_secuencias(a) if a.secuencias else evaluar(a))


def evaluar_secuencias(a) -> None:
    """N copias instalan la secuencia completa. Anota cada panel y se queda con la primera secuencia de cada copia."""
    import torch

    import viaz_escena
    from rl import grabacion, vivo

    pos, ang = (float(x) for x in a.tolerancias.split(",")[0].split(":"))
    fina = tuple(float(x) for x in a.tolerancias.split(",")[-1].split(":"))
    a.salida.mkdir(parents=True, exist_ok=True)
    env_gym = comun.crear_entorno(a, a.secuencias, render=bool(a.video), tolerancia_pos_m=pos, tolerancia_ang_grados=ang,
                                  paneles=0, secuencia=True, fijar_instalados=not a.sin_fijar, semilla=a.semilla)
    entorno = env_gym.unwrapped
    env, politica = comun.cargar_politica(env_gym, a.checkpoint)
    n, paneles, dt = entorno.num_envs, entorno.paneles, entorno.step_dt
    obs, _ = env.reset()
    grabadora = vivo.Grabadora(entorno) if a.usd else None
    salida = grabacion.Video(a.video) if a.video else None
    if salida:
        grabacion.camara_lateral(entorno)
        grabacion.descartar_inicio(env_gym)
    en_curso = torch.ones(n, dtype=torch.bool, device=entorno.device)
    intentos: list[list[dict]] = [[] for _ in range(n)]
    pasos_total = [0] * n
    with torch.inference_mode():
        for paso in range(1, paneles * (int(entorno.max_episode_length) + 300)):
            obs, _, fin, _ = env.step(politica(obs))
            if grabadora:
                grabadora.cuadro()
            if salida and bool(en_curso[0]) and not bool(fin[0]):   # el cuadro del fin ya muestra la copia reiniciada
                salida.cuadro(env_gym.render())
            for i in torch.nonzero(entorno.panel_fin & en_curso).flatten().tolist():
                intentos[i].append({k: float(v[i]) for k, v in entorno.final.items()})
            for i in torch.nonzero(fin.bool() & en_curso).flatten().tolist():
                pasos_total[i] = paso
            en_curso &= ~fin.bool()
            if not bool(en_curso.any()):
                break

    todos = [x for lista in intentos for x in lista]
    completas = [i for i in range(n) if len(intentos[i]) == paneles and all(x["exito"] > 0 for x in intentos[i])]

    def media(valores: list[float]) -> float | None:
        return round(sum(valores) / len(valores), 2) if valores else None

    por_panel = []
    for k in range(paneles):
        de_k = [x for x in todos if int(x["panel"]) == k]
        bien = [x for x in de_k if x["exito"] > 0]
        choques, caidas = sum(x["choque"] > 0 for x in de_k), sum(x["caida"] > 0 and x["choque"] == 0 for x in de_k)
        por_panel.append({
            "panel": k, "intentos": len(de_k), "exitos": len(bien), "tasa_exito": round(len(bien) / len(de_k), 4) if de_k else None,
            "exitos_fino": sum(x["err_pos_m"] <= fina[0] and x["err_ang_grados"] <= fina[1] for x in bien),
            "choques": choques, "caidas": caidas, "tiempo_agotado": len(de_k) - len(bien) - choques - caidas,
            "ciclo_politica_s": media([x["pasos"] * dt for x in bien]), "viaje_s": media([x["viaje_s"] for x in de_k if k > 0]),
            "error_pos_medio_m": round(sum(x["err_pos_m"] for x in bien) / len(bien), 4) if bien else None})
    informe = {
        "version": 1, "checkpoint": a.checkpoint.name, "secuencias": n, "paneles_por_secuencia": paneles,
        "fijar_instalados": not a.sin_fijar, "tolerancia": {"pos_m": pos, "ang_grados": ang},
        "tolerancia_fina": {"pos_m": fina[0], "ang_grados": fina[1]},
        "secuencias_completas": len(completas), "tasa_exito_secuencia": round(len(completas) / n, 4),
        "paneles_intentados": len(todos), "paneles_instalados": sum(x["exito"] > 0 for x in todos),
        "tasa_exito_panel": round(sum(x["exito"] > 0 for x in todos) / max(1, len(todos)), 4),
        "choques": sum(p["choques"] for p in por_panel), "caidas": sum(p["caidas"] for p in por_panel),
        "tiempo_agotado": sum(p["tiempo_agotado"] for p in por_panel),
        "duracion_secuencia_s": media([pasos_total[i] * dt for i in completas]),
        "ciclo_por_panel_s": media([pasos_total[i] * dt / paneles for i in completas]),
        "por_panel": por_panel, "fuente": "isaac"}
    (a.salida / "secuencia.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(informe, ensure_ascii=False), flush=True)
    if salida:
        print(json.dumps(salida.cerrar()), flush=True)
    if grabadora:
        grabadas = [i for i in completas if i in grabadora.copias]
        copia = grabadas[0] if grabadas else 0
        print(grabadora.guardar(a.usd, texturas=viaz_escena.carpeta_texturas(), solo=copia,
                                hasta=pasos_total[copia] - 1 if pasos_total[copia] else None),
              flush=True)


def evaluar(a) -> None:
    import torch

    from rl import grabacion, vivo
    from rl.robot import ARTICULACIONES

    tolerancias = [tuple(float(x) for x in par.split(":")) for par in a.tolerancias.split(",")]
    a.salida.mkdir(parents=True, exist_ok=True)
    env_gym = comun.crear_entorno(a, a.episodios, render=bool(a.video), tolerancia_pos_m=tolerancias[0][0],
                                  tolerancia_ang_grados=tolerancias[0][1], paneles=0, semilla=a.semilla)
    entorno = env_gym.unwrapped
    env, politica = comun.cargar_politica(env_gym, a.checkpoint)
    n, dev = entorno.num_envs, entorno.device

    # Un episodio por copia: se anota el resultado del primero que termina en cada una.
    obs, _ = env.reset()
    listo = torch.zeros(n, dtype=torch.bool, device=dev)
    primero = {k: torch.zeros(n, device=dev) for k in entorno.final}
    grabadora = vivo.Grabadora(entorno) if a.usd else None
    historia = []
    with torch.inference_mode():
        for _ in range(int(entorno.max_episode_length) + 2):
            if a.trayectoria:
                historia.append((entorno.robot.data.joint_pos[:, entorno.ids].clone(), entorno.sellada.clone(), listo.clone()))
            obs, _, fin, _ = env.step(politica(obs))
            if grabadora:
                grabadora.cuadro()
            nuevos = fin.bool() & ~listo
            for k in primero:
                primero[k] = torch.where(nuevos, entorno.final[k], primero[k])
            listo |= nuevos
            if bool(listo.all()):
                break
        while grabadora and len(grabadora.cuadros) < int(USD_S / entorno.step_dt):   # la animación muestra varios episodios
            obs, _, _, _ = env.step(politica(obs))
            grabadora.cuadro()
    exito = (primero["exito"] > 0) & listo
    filas = []
    for k, (pos, ang) in enumerate(tolerancias):
        cuenta = exito if k == 0 else exito & (primero["err_pos_m"] <= pos) & (primero["err_ang_grados"] <= ang)
        filas.append({"pos_m": pos, "ang_grados": ang, "exitos": int(cuenta.sum()), "tasa_exito": round(float(cuenta.float().mean()), 4)})
    ciclo = primero["pasos"][exito] * entorno.step_dt
    evaluacion = {"version": 1, "checkpoint": a.checkpoint.name, "episodios": n, "tolerancias": filas,
                  "ciclo_promedio_s": round(float(ciclo.mean()), 2) if len(ciclo) else 0.0,
                  "colisiones": int(((primero["choque"] > 0) & listo).sum()), "fuente": "isaac"}
    (a.salida / "evaluacion.json").write_text(json.dumps(evaluacion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evaluacion, ensure_ascii=False), flush=True)
    # Lo que el esquema cerrado de evaluacion.json no admite.
    choque, caida = (primero["choque"] > 0) & listo, (primero["caida"] > 0) & (primero["choque"] == 0) & listo
    fino = exito & (primero["err_pos_m"] <= tolerancias[-1][0]) & (primero["err_ang_grados"] <= tolerancias[-1][1])
    detalle = {"version": 1, "checkpoint": a.checkpoint.name, "episodios": n, "exitos": int(exito.sum()),
               "choques": int(choque.sum()), "caidas": int(caida.sum()),
               "tiempo_agotado": int((listo & ~exito & ~choque & ~caida).sum()), "sin_terminar": int((~listo).sum()),
               "por_panel": [{"panel": k, "episodios": int((primero["panel"] == k).sum()),
                              "exitos": int((exito & (primero["panel"] == k)).sum()),
                              "exitos_fino": int((fino & (primero["panel"] == k)).sum()),
                              "choques": int((choque & (primero["panel"] == k)).sum())} for k in range(entorno.paneles)]}
    (a.salida / "evaluacion_detalle.json").write_text(json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(detalle, ensure_ascii=False), flush=True)

    if a.trayectoria:
        copia = int(torch.nonzero(exito)[0]) if bool(exito.any()) else 0
        t, origen, slot = entorno.tarea, entorno.scene.env_origins[copia], int(entorno.k[copia])
        base = (entorno.base_pos[copia] - origen).tolist()
        rumbo = float(torch.rad2deg(entorno.base_rumbo[copia]))
        cuadros = []
        for f, (q, sellada, terminado) in enumerate(historia):
            if bool(terminado[copia]):
                break
            cuadros.append({"t_s": round(f * entorno.step_dt, 4), "base": {"pos_m": [round(v, 4) for v in base], "yaw_grados": round(rumbo, 3)},
                            "q": [round(float(v), 4) for v in q[copia]], "agarre": 0 if bool(sellada[copia]) else None,
                            "instalados": []})
        if cuadros and bool(exito[copia]):
            cuadros.append({**cuadros[-1], "t_s": round(len(cuadros) * entorno.step_dt, 4), "agarre": None, "instalados": [0]})
        trayectoria = {"version": 1, "fps": round(1 / entorno.step_dt), "articulaciones": list(ARTICULACIONES),
                       "paneles": [{"id": 0, "pos_m": list(t.meta_k(slot)), "quat": [1.0, 0.0, 0.0, 0.0]}],
                       "pila": {"en_base": True, "pos_m": [t.pila_x, 0.0, t.cubierta_z], "paso_m": t.panel_tam[2]},
                       "frames": cuadros}
        a.trayectoria.write_text(json.dumps(trayectoria), encoding="utf-8")

    if a.usd:
        import viaz_escena

        print(grabadora.guardar(a.usd, texturas=viaz_escena.carpeta_texturas()), flush=True)

    if a.video:
        salida = grabacion.Video(a.video)
        with torch.inference_mode():   # el reinicio también: el entorno ya guarda tensores de inferencia
            obs, _ = env.reset()
            grabacion.camara_lateral(entorno)
            for _ in range(int(VIDEO_S / entorno.step_dt)):
                obs, _, _, _ = env.step(politica(obs))
                salida.cuadro(env_gym.render())
        print(json.dumps(salida.cerrar()), flush=True)


if __name__ == "__main__":
    main()
