"""Prueba del entorno instalar_panel en Isaac Lab: controles sembrados, oráculo y velocidad. Tercer paso en el pod.

    $ISAACLAB_SH -p sim/rl/prueba_entorno.py --entorno E --tarea T --robot R --salida prueba_entorno.json --num-envs 64
    $ISAACLAB_SH -p sim/rl/prueba_entorno.py ... --num-envs 4096 --velocidad

Corre tres políticas, cada una en todas las copias, con las variaciones de base, masa y fricción encendidas:
- "cero" (el brazo no se mueve) y "azar" (acciones al azar) son controles: su éxito tiene que ser 0.
  Si alguna tiene éxito, el criterio de éxito está regalando la tarea.
- "oraculo" (sim/rl/oraculo.py) tiene que lograr 0,95 o más en cada panel de la secuencia (RF-INT-18), con los
  paneles anteriores ya instalados al lado. Si no, la tarea o el criterio no tienen solución.
Ninguna observación ni recompensa puede salir NaN o infinita.
También prueba los inicios asistidos: las copias que parten con el panel en la ventosa lo sostienen 1,5 s.
Y el choque con un panel instalado: corre 2 cm un panel vecino y el episodio de esa copia tiene que terminar con choque.
--velocidad mide pasos de entorno por segundo con acciones al azar. Solo vale si la GPU no tiene otro trabajo.
--secuencia prueba el controlador programado de la base: el oráculo instala la secuencia completa en cada copia,
y entre paneles la base avanza al punto de montaje siguiente. Cada panel tiene que lograr 0,95 o más.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
EXITO_ORACULO_MIN = 0.95
TOLERANCIA_FINA = (0.02, 2.0)
PASOS_VELOCIDAD = 200
BLOQUES_VELOCIDAD = 3


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--num-envs", type=int, default=64)
    ap.add_argument("--velocidad", action="store_true")
    ap.add_argument("--solo-velocidad", action="store_true", help="no corre las tres políticas")
    ap.add_argument("--usd", type=Path, help="exporta la escena y una animación del oráculo junto a este archivo USD")
    ap.add_argument("--secuencia", action="store_true", help="el oráculo instala la secuencia completa con la base móvil")
    ap.add_argument("--sin-fijar", action="store_true", help="en la secuencia, el panel instalado queda donde cayó")
    a = ap.parse_args()
    app = comun.lanzar(a)
    comun.ejecutar(app, lambda: probar(a), a.salida)


def probar(a) -> dict:
    import torch

    from rl import oraculo, vivo

    t0 = time.perf_counter()
    env = comun.crear_entorno(a, a.num_envs, variar=True, paneles=0, secuencia=a.secuencia,
                              fijar_instalados=not a.sin_fijar).unwrapped
    n, dev = env.num_envs, env.device
    informe = {"robot_id": env.corrida.clon["robot_id"], "num_envs": n, "carga_s": round(time.perf_counter() - t0, 1),
               "paso_control_s": round(env.step_dt, 5), "episodio_s": env.cfg.episode_length_s,
               "agarre": env.cfg.agarre, "fuerza_ventosa_n": round(env.fuerza_n, 1), "paneles": env.paneles,
               "base_y_m": round(env.tarea.base[1], 3), "paso_slot_m": env.tarea.paso_slot, "politicas": {}}
    ok = True
    if a.secuencia:
        informe["secuencia"] = probar_secuencia(env, oraculo.Oraculo(env), not a.sin_fijar)
        informe["ok"] = informe["secuencia"]["ok"]
        return informe

    def correr(nombre: str, politica, pasos: int, grabadora=None) -> dict:
        env.reset()
        cuenta = {"episodios": 0.0, "exitos": 0.0, "caidas": 0.0, "choques": 0.0, "choques_vecino": 0.0,
                  **{f"{c}_k{k}": 0.0 for k in range(env.paneles) for c in ("episodios", "exitos")}}
        finos, ciclo, no_finitos, sellados = 0, [], 0, 0.0
        for _ in range(pasos):
            obs, recompensa, terminado, truncado, extras = env.step(politica())
            no_finitos += int((~torch.isfinite(obs["policy"])).sum()) + int((~torch.isfinite(recompensa)).sum())
            for k in cuenta:
                cuenta[k] += float(extras["log"][k])
            sellados = max(sellados, float(extras["log"]["sellados"]))
            fin = terminado | truncado
            logrado = fin & (env.final["exito"] > 0)
            finos += int((logrado & (env.final["err_pos_m"] <= TOLERANCIA_FINA[0])
                          & (env.final["err_ang_grados"] <= TOLERANCIA_FINA[1])).sum())
            ciclo.extend((env.final["pasos"][logrado] * env.step_dt).tolist())
            if grabadora:
                grabadora.cuadro()
        episodios = max(1.0, cuenta["episodios"])
        return {"episodios": int(cuenta["episodios"]), "exitos": int(cuenta["exitos"]),
                "tasa_exito": round(cuenta["exitos"] / episodios, 4), "tasa_exito_2cm_2grados": round(finos / episodios, 4),
                "caidas": int(cuenta["caidas"]), "choques": int(cuenta["choques"]), "choques_vecino": int(cuenta["choques_vecino"]),
                "por_panel": [{"panel": k, "episodios": int(cuenta[f"episodios_k{k}"]), "exitos": int(cuenta[f"exitos_k{k}"]),
                               "tasa_exito": round(cuenta[f"exitos_k{k}"] / max(1.0, cuenta[f"episodios_k{k}"]), 4)}
                              for k in range(env.paneles)],
                "fraccion_sellada_max": round(sellados, 3),
                "ciclo_promedio_s": round(sum(ciclo) / len(ciclo), 2) if ciclo else None, "no_finitos": no_finitos}

    largo = int(env.max_episode_length)
    if not a.solo_velocidad:
        cero = torch.zeros(n, 7, device=dev)
        cero[:, 6] = -1.0
        guia = oraculo.Oraculo(env)
        grabadora = vivo.Grabadora(env) if a.usd else None
        informe["politicas"]["cero"] = correr("cero", lambda: cero, largo + 5)
        informe["politicas"]["azar"] = correr("azar", lambda: torch.rand(n, 7, device=dev) * 2 - 1, largo + 5)
        informe["politicas"]["oraculo"] = correr("oraculo", guia.accion, 2 * largo, grabadora)
        p = informe["politicas"]
        ok &= p["cero"]["exitos"] == 0 and p["azar"]["exitos"] == 0 and p["cero"]["episodios"] >= n
        ok &= p["oraculo"]["episodios"] >= n
        ok &= all(k["episodios"] > 0 and k["tasa_exito"] >= EXITO_ORACULO_MIN for k in p["oraculo"]["por_panel"])
        ok &= all(v["no_finitos"] == 0 for v in p.values())
        informe["inicios_asistidos"] = asistidos = probar_asistidos(env)
        ok &= asistidos["ok"]
        informe["choque_con_vecino"] = vecino = probar_vecino(env)
        ok &= vecino["ok"]
        if a.usd:
            informe["usd"] = [vivo.exportar(env, a.usd), grabadora.guardar(a.usd.with_name(a.usd.stem + "-animacion.usd"))]

    if a.velocidad or a.solo_velocidad:
        env.reset()
        for _ in range(20):
            env.step(torch.rand(n, 7, device=dev) * 2 - 1)
        medidas = []
        for _ in range(BLOQUES_VELOCIDAD):
            torch.cuda.synchronize()
            t = time.perf_counter()
            for _ in range(PASOS_VELOCIDAD):
                env.step(torch.rand(n, 7, device=dev) * 2 - 1)
            torch.cuda.synchronize()
            medidas.append(PASOS_VELOCIDAD / (time.perf_counter() - t))
        medidas.sort()
        mediana = medidas[len(medidas) // 2]
        informe["velocidad"] = {
            "pasos_control_s": round(mediana, 2), "rango": [round(medidas[0], 2), round(medidas[-1], 2)],
            "pasos_entorno_s": round(mediana * n), "pasos_fisica_s": round(mediana * env.cfg.decimation, 1),
            "bloques": BLOQUES_VELOCIDAD, "pasos_por_bloque": PASOS_VELOCIDAD, "acciones": "al azar",
            "gpu_mib_total": comun.gpu_mib(), "torch_gpu_mib": round(torch.cuda.max_memory_allocated() / 2**20)}
    informe["ok"] = bool(ok)
    return informe


def probar_secuencia(env, guia, fijar: bool) -> dict:
    """El oráculo instala la secuencia completa en cada copia. Cuenta la primera secuencia de cada una."""
    import torch

    n, paneles = env.num_envs, env.paneles
    env.reset()
    en_curso = torch.ones(n, dtype=torch.bool, device=env.device)
    cuenta = [{"panel": k, "intentos": 0, "exitos": 0, "choques": 0, "caidas": 0} for k in range(paneles)]
    completas, viaje, no_finitos = 0, [], 0
    for _ in range(paneles * (int(env.max_episode_length) + 300)):
        obs, recompensa, terminado, truncado, _ = env.step(guia.accion())
        no_finitos += int((~torch.isfinite(obs["policy"])).sum()) + int((~torch.isfinite(recompensa)).sum())
        fin = terminado | truncado
        for i in torch.nonzero(env.panel_fin & en_curso).flatten().tolist():
            k, bien = int(env.final["panel"][i]), bool(env.final["exito"][i] > 0)
            cuenta[k]["intentos"] += 1
            cuenta[k]["exitos"] += bien
            cuenta[k]["choques"] += bool(env.final["choque"][i] > 0)
            cuenta[k]["caidas"] += bool(env.final["caida"][i] > 0)
            completas += bien and k == paneles - 1
            if k > 0:
                viaje.append(float(env.final["viaje_s"][i]))
        en_curso &= ~fin
        if not bool(en_curso.any()):
            break
    for c in cuenta:
        c["tasa_exito"] = round(c["exitos"] / max(1, c["intentos"]), 4)
    informe = {"copias": n, "paneles": paneles, "fijar_instalados": fijar, "secuencias_completas": completas,
               "tasa_exito_secuencia": round(completas / n, 4), "por_panel": cuenta, "sin_terminar": int(en_curso.sum()),
               "viaje_promedio_s": round(sum(viaje) / len(viaje), 2) if viaje else None, "no_finitos": no_finitos}
    informe["ok"] = bool(no_finitos == 0 and informe["sin_terminar"] == 0
                         and all(c["intentos"] > 0 and c["tasa_exito"] >= EXITO_ORACULO_MIN for c in cuenta))
    return informe


def probar_vecino(env) -> dict:
    """Control del choque con un panel instalado: sin tocarlo no hay choque; corrido 2 cm, el episodio termina con choque."""
    import torch

    quieto = torch.zeros(env.num_envs, 7, device=env.device)
    quieto[:, 6] = -1.0
    env.reset()
    con_vecino = env.k > 0
    ids = torch.nonzero(con_vecino).flatten()
    falsos = 0
    for _ in range(30):   # 1 s con el brazo quieto: los paneles instalados no se mueven solos
        env.step(quieto)
        falsos += int(env.choque_vecino.sum())
    cuerpo = env.pila[env.cuerpo_de_slot[0]]   # el slot 0 está ocupado siempre que el panel del episodio no es el 0
    pose = cuerpo.data.root_state_w[ids, :7].clone()
    pose[:, 0] += 0.02
    cuerpo.write_root_pose_to_sim(pose, env_ids=ids)
    _, _, terminado, _, _ = env.step(quieto)
    informe = {"copias": env.num_envs, "copias_con_vecino": len(ids), "choques_sin_tocar": falsos,
               "detectados": int((env.choque_vecino & terminado)[ids].sum()),
               "choques_en_copias_sin_vecino": int(env.choque_vecino[~con_vecino].sum())}
    informe["ok"] = bool(len(ids) > 0 and falsos == 0 and informe["detectados"] == len(ids)
                         and informe["choques_en_copias_sin_vecino"] == 0)
    return informe


def probar_asistidos(env) -> dict:
    """Todas las copias parten en un punto del recorrido. Las que llevan el panel lo sostienen con el brazo quieto.

    Ningún inicio puede terminar el episodio de inmediato: sería una pose de partida con el brazo chocando.
    """
    import torch

    env.asistido = 1.0
    env.reset()
    env.asistido = 0.0
    llevan = env.sellada.clone()
    sostener = torch.zeros(env.num_envs, 7, device=env.device)
    sostener[:, 6] = 1.0
    separacion0 = env.medir()["dist_ventosa"]
    terminaron = torch.zeros_like(llevan)
    for _ in range(45):
        _, _, terminado, truncado, _ = env.step(sostener)
        terminaron |= terminado | truncado
    siguen = llevan & ~terminaron
    corrido = (env.medir()["dist_ventosa"] - separacion0).abs()[siguen]
    informe = {"copias": env.num_envs, "copias_con_panel": int(llevan.sum()), "terminan_antes_de_1_5_s": int(terminaron.sum()),
               "siguen_selladas": int((env.sellada & siguen).sum()),
               "corrimiento_max_m": round(float(corrido.max()), 4) if len(corrido) else 0.0}
    informe["ok"] = bool(informe["copias_con_panel"] > 0 and informe["terminan_antes_de_1_5_s"] == 0
                         and informe["siguen_selladas"] == informe["copias_con_panel"] and informe["corrimiento_max_m"] <= 0.005)
    return informe


if __name__ == "__main__":
    main()
