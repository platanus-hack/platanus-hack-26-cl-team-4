"""Parámetros de física de VIAZ, en un solo lugar. Python puro (sin Isaac).

Los usan generar_escena.py (materiales del USD), viaz_escena.py (escena de Isaac Lab),
ejecutar_tarea.py y backend/viaz/urdf.py (masas del robot). Unidades SI: m, kg, s.

Los valores son supuestos razonables, no medidos. Hay que calibrarlos con sim/prueba_fisica.py en el pod.
"""
from __future__ import annotations

# ---- Simulación ----
DT_S = 1 / 120              # paso de física. Con paneles de 4 cm, pasos más grandes dejan que atraviesen el tubo.
RENDER_CADA = 4             # 1 frame cada 4 pasos de física = 30 fps
GRAVEDAD = 9.81
ITER_POSICION = 16          # iteraciones del solver para cuerpos pesados y apilados
ITER_VELOCIDAD = 1

# ---- Materiales (fricción estática, dinámica, restitución) ----
# Restitución 0: nada rebota. Un panel que rebota sobre el tubo es un error de simulación, no de la realidad.
MATERIALES = {
    "suelo":   {"estatica": 0.9, "dinamica": 0.7, "restitucion": 0.0},   # tierra compactada
    "acero":   {"estatica": 0.6, "dinamica": 0.5, "restitucion": 0.0},   # tubo de torsión y postes galvanizados
    "panel":   {"estatica": 0.5, "dinamica": 0.4, "restitucion": 0.0},   # marco de aluminio contra acero
    "ventosa": {"estatica": 1.2, "dinamica": 1.0, "restitucion": 0.0},   # goma de la ventosa
}

# ---- Panel ----
PANEL_ESPESOR_M = 0.04
# Margen de contacto: PhysX genera contactos antes de que los cuerpos se toquen. Con objetos delgados va chico.
CONTACTO_OFFSET_M = 0.005
DESPENETRACION_MAX_M_S = 1.0  # limita el "salto" cuando dos cuerpos se interpenetran

# Las masas del robot viven en backend/viaz/urdf.py: el URDF se genera en Render, que no ve sim/.


def material(nombre: str) -> dict:
    return MATERIALES[nombre]
