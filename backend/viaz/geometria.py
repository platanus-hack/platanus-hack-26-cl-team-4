"""Revisión geométrica de tarea.json contra entorno.json. Python puro: sin robot, sin Isaac, < 1 ms.

Fase 1 del embudo de factibilidad (docs/agentes/tarea.md §4.1):
1. Geometría de la tarea (aquí): descarta tareas imposibles con las cajas de entorno.json.
2. Cinemática por robot (selección): ¿el brazo alcanza las poses meta?
3. Prueba en Isaac (validar_robot): un oráculo hace la tarea con física.
Pasar esta fase NO prueba que la tarea sea posible. Solo descarta lo que no puede ser.

Modelo: cada elemento es una caja o un cilindro vertical (entorno.json). Marco del espacio: X a lo largo,
Y a lo ancho, Z arriba. posicion_m es el centro de la cara inferior; rotacion_grados gira sobre Z.
"""
from __future__ import annotations

import math

TOL_APOYO_M = 0.03        # el objeto está "sobre" una superficie si su base queda a 3 cm o menos de ella
TOL_LIMITE_M = 0.05       # margen para decir que un elemento se sale del espacio
CONFIANZA_MIN = 0.5       # con menos confianza, un problema geométrico pasa a advertencia
TAREAS_CON_GEOMETRIA = {"tomar_y_dejar", "transportar", "ordenar"}


def huella(el: dict) -> tuple[float, float, float, float]:
    """Caja alineada a los ejes que contiene la planta del elemento girado: (xmin, xmax, ymin, ymax)."""
    d, p = el["dimensiones_m"], el["posicion_m"]
    if el["forma"] == "cilindro":
        hx = hy = max(d["largo_m"], d["ancho_m"]) / 2
    else:
        a = math.radians(el["rotacion_grados"])
        c, s = abs(math.cos(a)), abs(math.sin(a))
        hx = (d["largo_m"] * c + d["ancho_m"] * s) / 2
        hy = (d["largo_m"] * s + d["ancho_m"] * c) / 2
    return p["x_m"] - hx, p["x_m"] + hx, p["y_m"] - hy, p["y_m"] + hy


def tope(el: dict) -> float:
    return el["posicion_m"]["z_m"] + el["dimensiones_m"]["alto_m"]


def planta(el: dict) -> tuple[float, float]:
    """Lados de la planta, el mayor primero. Un objeto se puede girar para que calce."""
    d = el["dimensiones_m"]
    lados = (d["largo_m"], d["ancho_m"]) if el["forma"] == "caja" else (max(d["largo_m"], d["ancho_m"]),) * 2
    return max(lados), min(lados)


def _se_cruzan(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]


def _dentro(punto: tuple[float, float], h) -> bool:
    return h[0] <= punto[0] <= h[1] and h[2] <= punto[1] <= h[3]


def superficie(lugar: dict, el: dict) -> tuple[float | None, str | None]:
    """Altura de apoyo del lugar: lugar.altura_m o la cara superior. Devuelve (z, problema)."""
    z = lugar.get("altura_m")
    if z is None:
        return tope(el), None
    if not el["posicion_m"]["z_m"] - TOL_APOYO_M <= z <= tope(el) + TOL_APOYO_M:
        return None, (f"{lugar['elemento']}: altura_m {z} m queda fuera del elemento "
                      f"(de {el['posicion_m']['z_m']:.2f} a {tope(el):.2f} m)")
    return z, None


def _confianza(entorno: dict, nombres: list[str]) -> float:
    conf = entorno.get("confianza", {})
    valores = [conf[f"elementos.{n}"] for n in nombres if f"elementos.{n}" in conf]
    return min(valores) if valores else 1.0


def _pose(x: float, y: float, z: float, giro: float) -> dict:
    return {"x_m": round(x, 4), "y_m": round(y, 4), "z_m": round(z, 4), "giro_grados": round(giro, 2)}


def revisar(tarea: dict, entorno: dict) -> tuple[list[str], list[str], dict]:
    """(problemas, advertencias, geometria). Los problemas rechazan la tarea; las advertencias solo informan."""
    vacia = {"origen_pose": None, "destino_pose": None, "distancia_m": None, "altura_max_m": None}
    elementos = {e["nombre"]: e for e in entorno.get("elementos", [])}
    obj = elementos.get(tarea["objeto"]["elemento"])
    ori = elementos.get(tarea["origen"]["elemento"])
    des = elementos.get(tarea["destino"]["elemento"])
    if tarea["tarea"] not in TAREAS_CON_GEOMETRIA or obj is None:
        return [], [], vacia
    problemas, advertencias = [], []
    alto_obj = obj["dimensiones_m"]["alto_m"]
    esp = entorno["espacio"]
    caja_espacio = (-TOL_LIMITE_M, esp["largo_m"] + TOL_LIMITE_M, -TOL_LIMITE_M, esp["ancho_m"] + TOL_LIMITE_M)

    # Límites: los elementos de la tarea dentro del espacio.
    for el in (obj, ori, des):
        if el is not None:
            h = huella(el)
            if not (caja_espacio[0] <= h[0] and h[1] <= caja_espacio[1] and caja_espacio[2] <= h[2] and h[3] <= caja_espacio[3]):
                advertencias.append(f"{el['nombre']} se sale de la caja del espacio "
                                    f"({esp['largo_m']} × {esp['ancho_m']} m): revisar entorno.json")

    # Soporte: el objeto está apoyado sobre el origen.
    origen_pose = _pose(obj["posicion_m"]["x_m"], obj["posicion_m"]["y_m"], obj["posicion_m"]["z_m"], obj["rotacion_grados"])
    if ori is not None:
        z_ori, prob = superficie(tarea["origen"], ori)
        if prob:
            problemas.append(prob)
        else:
            centro = (obj["posicion_m"]["x_m"], obj["posicion_m"]["y_m"])
            base = obj["posicion_m"]["z_m"]
            if abs(base - z_ori) > TOL_APOYO_M or not _dentro(centro, huella(ori)):
                problemas.append(f"{obj['nombre']} no está sobre {ori['nombre']}: su base está a {base:.2f} m y la "
                                 f"superficie de {ori['nombre']} a {z_ori:.2f} m, o su centro cae fuera de la planta")

    # Encaje, despeje y techo en el destino.
    destino_pose = None
    if des is not None:
        z_des, prob = superficie(tarea["destino"], des)
        if prob:
            problemas.append(prob)
        else:
            (ol, oa), (dl, da) = planta(obj), planta(des)
            if ol > dl + 1e-6 or oa > da + 1e-6:
                problemas.append(f"{obj['nombre']} ({ol:.2f} × {oa:.2f} m) no cabe en {des['nombre']} "
                                 f"({dl:.2f} × {da:.2f} m)")
            arriba = z_des + alto_obj
            if esp["alto_m"] is not None and arriba > esp["alto_m"]:
                problemas.append(f"{obj['nombre']} sobre {des['nombre']} llega a {arriba:.2f} m, sobre el techo "
                                 f"({esp['alto_m']} m)")
            h_des = huella(des)
            for el in elementos.values():
                if el is des or el is obj:
                    continue
                if _se_cruzan(huella(el), h_des) and el["posicion_m"]["z_m"] < arriba and tope(el) > z_des + 1e-6:
                    problemas.append(f"{el['nombre']} ocupa el espacio sobre {des['nombre']} "
                                     f"(entre {z_des:.2f} y {arriba:.2f} m): el objeto no cabe ahí")
            if z_des < tope(des) - TOL_APOYO_M:
                advertencias.append(f"{des['nombre']} es un bloque sólido en entorno.json: la superficie a {z_des:.2f} m "
                                    f"no existe en escena.usd todavía (falta modelar repisas)")
            destino_pose = _pose(*(((h_des[0] + h_des[1]) / 2, (h_des[2] + h_des[3]) / 2)), z_des, des["rotacion_grados"])

    # Con medidas poco confiables, un problema geométrico es una advertencia: la caja puede estar mal medida.
    involucrados = [e["nombre"] for e in (obj, ori, des) if e is not None]
    conf = _confianza(entorno, involucrados)
    if problemas and conf < CONFIANZA_MIN:
        advertencias += [f"{p} (confianza {conf:.1f}: no se rechaza)" for p in problemas]
        problemas = []

    poses = [p for p in (origen_pose, destino_pose) if p is not None]
    geometria = {
        "origen_pose": origen_pose,
        "destino_pose": destino_pose,
        "distancia_m": (round(math.hypot(destino_pose["x_m"] - origen_pose["x_m"], destino_pose["y_m"] - origen_pose["y_m"]), 3)
                        if destino_pose else None),
        "altura_max_m": round(max(p["z_m"] for p in poses) + alto_obj, 3),
    }
    return problemas, advertencias, geometria
