"""Plan de la tarea instalar_panel, en Python puro (sin Isaac).

Lo usan:
- worker-gpu en modo simulado: genera trayectoria.json sin física, para desarrollar sin GPU.
- sim/ejecutar_tarea.py en Isaac: reproduce el plan con física y mide lo que de verdad pasa.

Convenciones (las mismas que sim/generar_escena.py y web/lib/escena.ts):
- Z arriba, metros. La fila i tiene su tubo de torsión en y = -i * separacion, de x = 0 a x = largo.
- El robot avanza por el pasillo de la fila 0, en y = +d, mirando hacia +X.
- Con shoulder_pan = -pi/2 el brazo apunta a -Y, hacia la fila 0. Con pi apunta a la pila, atrás.
"""
from __future__ import annotations

import math

TUBO_R = 0.05          # radio aproximado del tubo de torsión
PANEL_ESPESOR = 0.04
PASO_PILA = 0.045      # alto de cada panel en la pila del robot
HOLGURA_SLOT = 0.02    # separación entre paneles instalados
INICIO_X = 2.0         # primer panel a 2 m del inicio de la fila
VEL_BASE = 0.8         # m/s en el plan


def _suave(t: float) -> float:
    return t * t * (3 - 2 * t)


def ik_plana(d: float, dz: float, l1: float, l2: float) -> tuple[float, float]:
    """Ángulos (hombro, codo) para que la muñeca llegue a (d, dz) desde el hombro. 0 = brazo vertical."""
    r2 = d * d + dz * dz
    c = (r2 - l1 * l1 - l2 * l2) / (2 * l1 * l2)
    if not -1 <= c <= 1:
        raise ValueError(f"punto fuera de alcance: d={d:.2f} dz={dz:.2f} (alcance {l1 + l2:.2f} m)")
    codo = math.acos(c)
    hombro = math.atan2(d, dz) - math.atan2(l2 * math.sin(codo), l1 + l2 * math.cos(codo))
    return hombro, codo


def _q(pan: float, hombro: float, codo: float) -> list[float]:
    # wrist_1 deja la ventosa mirando hacia abajo (suma de pitch = pi)
    return [pan, hombro, codo, math.pi - hombro - codo, 0.0, 0.0]


def distancia_pasillo(entorno: dict) -> float:
    """Distancia del eje de la fila 0 al centro de la base: medio panel + media base + margen."""
    return round(entorno["panel"]["largo_m"] / 2 + 0.5 + 0.06, 3)


def slots(entorno: dict, n: int) -> list[list[float]]:
    p, e = entorno["panel"], entorno["estructura"]
    z = e["altura_m"] + TUBO_R + PANEL_ESPESOR / 2
    return [[round(INICIO_X + p["ancho_m"] / 2 + k * (p["ancho_m"] + HOLGURA_SLOT), 3), 0.0, round(z, 3)] for k in range(n)]


def cantidad(entorno: dict, tarea: dict) -> int:
    p = entorno["panel"]
    caben = int((entorno["filas"]["largo_m"] - INICIO_X) // (p["ancho_m"] + HOLGURA_SLOT))
    return max(0, min(tarea["objetivo"]["paneles"], tarea["pila_paneles"]["cantidad"], caben))


def poses(entorno: dict, geo: dict) -> dict:
    """Poses clave del brazo. 'tomar' depende de cuántos paneles quedan en la pila."""
    l1, l2, mu = geo["l1_m"], geo["l2_m"], geo["muneca_m"]
    hz = geo["hombro_z_m"]
    d = distancia_pasillo(entorno)
    # Dejar: la cara de abajo del panel queda sobre el tubo.
    z_muneca = entorno["estructura"]["altura_m"] + TUBO_R + PANEL_ESPESOR + mu
    dejar = _q(-math.pi / 2, *ik_plana(d, z_muneca - hz, l1, l2))
    d_pila = geo["montaje_x_m"] - geo["pila_x_m"]

    def tomar(restantes: int) -> list[float]:
        tope = geo["cubierta_z_m"] + restantes * PASO_PILA
        return _q(math.pi, *ik_plana(d_pila, tope + mu - hz, l1, l2))

    return {"casa": _q(0.0, 0.0, 1.2), "dejar": dejar, "tomar": tomar, "d": d}


def validar(entorno: dict, tarea: dict, clon: dict, carga_util_kg: float | None = None) -> dict:
    problemas = []
    n = cantidad(entorno, tarea)
    if n == 0:
        problemas.append("no cabe ningún panel en la fila o el objetivo es 0")
    try:
        p = poses(entorno, clon["geometria"])
        p["tomar"](max(tarea["pila_paneles"]["cantidad"], 1))
        p["tomar"](1)
    except ValueError as e:
        problemas.append(str(e))
    carga = carga_util_kg if carga_util_kg is not None else clon["escala"]["carga_util_kg"]
    if carga < entorno["panel"]["peso_kg"]:
        problemas.append(f"carga útil {carga} kg menor que el panel ({entorno['panel']['peso_kg']} kg)")
    return {"ok": not problemas, "problemas": problemas, "paneles_planificados": n}


def generar(entorno: dict, tarea: dict, clon: dict, fps: int = 30) -> dict:
    """Trayectoria sintética (sin física). Devuelve trayectoria.json."""
    geo = clon["geometria"]
    n = cantidad(entorno, tarea)
    p = poses(entorno, geo)
    destinos = slots(entorno, n)
    pila = tarea["pila_paneles"]["cantidad"]

    frames: list[dict] = []
    estado = {"x": -1.0, "q": list(p["casa"]), "agarre": None, "instalados": []}
    t = 0.0

    def emitir(x: float, q: list[float]):
        frames.append({"t_s": round(t, 4), "base": {"pos_m": [round(x, 4), p["d"], 0.0], "yaw_grados": 0.0},
                       "q": [round(v, 4) for v in q], "agarre": estado["agarre"], "instalados": list(estado["instalados"])})

    def mover(dur: float, x_fin: float | None = None, q_fin: list[float] | None = None):
        nonlocal t
        x0, q0 = estado["x"], estado["q"]
        x1 = x0 if x_fin is None else x_fin
        q1 = q0 if q_fin is None else q_fin
        pasos = max(1, round(dur * fps))
        for i in range(1, pasos + 1):
            s = _suave(i / pasos)
            t += 1 / fps
            emitir(x0 + (x1 - x0) * s, [a + (b - a) * s for a, b in zip(q0, q1)])
        estado["x"], estado["q"] = x1, list(q1)

    emitir(estado["x"], estado["q"])
    for k in range(n):
        x_base = destinos[k][0] - geo["montaje_x_m"]
        mover(max(1.0, abs(x_base - estado["x"]) / VEL_BASE), x_fin=x_base)
        mover(1.5, q_fin=p["tomar"](pila - k))
        mover(0.4)
        estado["agarre"] = k
        mover(1.2, q_fin=p["casa"])
        mover(1.6, q_fin=p["dejar"])
        mover(0.4)
        estado["agarre"] = None
        estado["instalados"].append(k)
        mover(1.2, q_fin=p["casa"])

    return {
        "version": 1, "fps": fps,
        "articulaciones": ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"],
        "paneles": [{"id": k, "pos_m": destinos[k], "quat": [1.0, 0.0, 0.0, 0.0]} for k in range(n)],
        "pila": {"en_base": True, "pos_m": [geo["pila_x_m"], 0.0, geo["cubierta_z_m"]], "paso_m": PASO_PILA},
        "frames": frames,
    }


def resultado_simulado(trayectoria: dict) -> dict:
    n = len(trayectoria["paneles"])
    total = trayectoria["frames"][-1]["t_s"] if trayectoria["frames"] else 0.0
    return {
        "version": 1, "metodo": "planificador", "fuente": "simulado", "politica": None,
        "metricas": {"paneles_instalados": n, "intentos": n, "tasa_exito": 1.0 if n else 0.0,
                     "ciclo_promedio_s": round(total / n, 2) if n else 0.0},
        "video": None,
        "notas": "Trayectoria sintética sin física (worker en modo simulado). No es un resultado de Isaac.",
    }
