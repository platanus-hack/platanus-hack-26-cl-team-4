"""Parámetros de física de VIAZ, en un solo lugar. Python puro (sin Isaac).

Los usan generar_escena.py (materiales del USD), viaz_escena.py (escenas de Isaac Lab),
ejecutar_tarea.py y backend/viaz/urdf.py (masas del robot). Unidades SI: m, kg, s.

Cada valor tiene su razón y su fuente en docs/escena-isaac.md, sección "Decisiones de física del terreno".
Los mide sim/prueba_fisica.py (parque del demo) y sim/prueba_entrenamiento.py (escena de entrenamiento) en el pod.
"""
from __future__ import annotations

# ---- Simulación ----
DT_S = 1 / 120              # paso de física. Con paneles de 4 cm, pasos más grandes dejan que atraviesen el tubo.
RENDER_CADA = 4             # 1 frame cada 4 pasos de física = 30 fps. También es la decimación del control del RL.
GRAVEDAD = 9.81
ITER_POSICION = 16          # iteraciones del solver para cuerpos pesados y apilados
ITER_VELOCIDAD = 1
# CCD apagado: PhysX en GPU no hace el barrido de CCD. A 1/120 s un panel necesita más de 16 m/s
# para saltarse el tubo (4 cm de panel + 10 cm de tubo), y la muñeca del robot queda bajo 8 m/s.
CCD = False
UMBRAL_REBOTE_M_S = 0.2     # bajo esta velocidad de choque PhysX no aplica restitución
# El solver TGS aplica la gravedad en cada iteración. Sin esto, los paneles apilados quedan quietos
# pero PhysX informa velocidades de 2 a 3 cm/s (ruido), que ensucian las observaciones del RL.
FUERZAS_EN_CADA_ITERACION = True

# ---- Materiales (fricción estática, dinámica, restitución) ----
# PhysX no tiene fricción por par de cuerpos: combina la de los dos materiales. Aquí, con el promedio.
# Un solo coeficiente por material (estática = dinámica), y es el de deslizamiento. Medido en el pod:
# con estática > dinámica, PhysX en GPU deja resbalar el panel con un empuje bajo el límite estático.
# Restitución 0: nada rebota. Un panel que rebota sobre el tubo es un error de simulación, no de la realidad.
COMBINACION = "average"
MATERIALES = {
    "suelo":   {"estatica": 0.6, "dinamica": 0.6, "restitucion": 0.0},   # tierra seca con gravilla (por defecto)
    "acero":   {"estatica": 0.3, "dinamica": 0.3, "restitucion": 0.0},   # tubo de torsión y postes galvanizados
    "panel":   {"estatica": 0.4, "dinamica": 0.4, "restitucion": 0.0},   # marco de aluminio anodizado
    "ventosa": {"estatica": 1.0, "dinamica": 1.0, "restitucion": 0.0},   # goma de la ventosa
}
# Coeficiente por tipo de suelo (terreno.suelo de entorno.json). Si entorno.json trae terreno.friccion, manda ese valor.
SUELOS = {"desierto_atacama": 0.6, "tierra_compactada": 0.6, "ripio": 0.6, "arena": 0.5, "pasto": 0.4}

# ---- Panel ----
PANEL_ESPESOR_M = 0.04
# Margen de contacto: PhysX genera contactos antes de que los cuerpos se toquen. Con objetos delgados va chico.
CONTACTO_OFFSET_M = 0.005
REPOSO_OFFSET_M = 0.0
DESPENETRACION_MAX_M_S = 1.0  # limita el "salto" cuando dos cuerpos se interpenetran

# ---- Variaciones del entrenamiento (RF-INT-19, RF-INT-24, RF-INT-25). Solo configuración. ----
VARIACIONES = {
    "masa_panel_rel": 0.10,     # masa del panel ±10 %
    "friccion_rel": 0.20,       # fricción de panel, tubo y ventosa ±20 %
    "base_pos_m": 0.15,         # la base se detiene a ±15 cm del punto de montaje
    "base_yaw_grados": 5.0,     # y a ±5° de rumbo
}
# Viento sobre el panel agarrado: F = 1/2 · rho · v² · C · A. Opcional (RF-INT-25).
VIENTO = {"velocidad_max_m_s": 10.0, "densidad_aire_kg_m3": 0.97, "coef_fuerza": 0.5}

# Las masas del robot viven en backend/viaz/urdf.py: el URDF se genera en Render, que no ve sim/.


def material(nombre: str) -> dict:
    return MATERIALES[nombre]


def material_suelo(entorno: dict) -> dict:
    """Material del suelo de este parque: terreno.friccion si viene, o el del tipo de suelo, o el por defecto."""
    terreno = entorno["terreno"]
    friccion = terreno.get("friccion") or SUELOS.get(terreno["suelo"]) or MATERIALES["suelo"]["estatica"]
    return {"estatica": friccion, "dinamica": friccion, "restitucion": MATERIALES["suelo"]["restitucion"]}


def friccion_par(a: dict, b: dict) -> dict:
    """Fricción efectiva entre dos materiales, como la combina PhysX con COMBINACION = "average"."""
    return {k: round((a[k] + b[k]) / 2, 4) for k in ("estatica", "dinamica")}


def rangos_variacion(entorno: dict) -> dict:
    """Rangos absolutos para los eventos de Isaac Lab, a partir de VARIACIONES.

    masa: para randomize_rigid_body_mass con operation="scale".
    friccion: para randomize_rigid_body_material (static_friction_range, dynamic_friction_range) de cada cuerpo.
    viento_n: fuerza máxima para apply_external_force_torque sobre el panel.
    """
    m, f = VARIACIONES["masa_panel_rel"], VARIACIONES["friccion_rel"]
    p = entorno["panel"]
    return {
        "masa_panel_escala": (round(1 - m, 4), round(1 + m, 4)),
        "friccion": {n: {k: (round(MATERIALES[n][k] * (1 - f), 4), round(MATERIALES[n][k] * (1 + f), 4))
                         for k in ("estatica", "dinamica")} for n in ("panel", "acero", "ventosa")},
        "base_pos_m": VARIACIONES["base_pos_m"],
        "base_yaw_grados": VARIACIONES["base_yaw_grados"],
        "viento_n": round(0.5 * VIENTO["densidad_aire_kg_m3"] * VIENTO["velocidad_max_m_s"] ** 2
                          * VIENTO["coef_fuerza"] * p["largo_m"] * p["ancho_m"], 1),
    }
