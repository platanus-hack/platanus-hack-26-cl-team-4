"""Medición del parque desde una nube de puntos (sim/medir_geometria.py), con parques sintéticos de geometría conocida.

La nube sale de las mismas reglas de la escena (generar_escena.cuerpos y paneles_visuales): suelo, tubos, postes y
paneles. Se gira y se mueve a un marco de cámara cualquiera, con ruido, como la entregaría MapAnything.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from viaz import agentes  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import generar_escena  # noqa: E402
import medir_geometria as mg  # noqa: E402

RUIDO_M = 0.01


def _caja(centro, tam, densidad: float, rng) -> np.ndarray:
    """Puntos sobre las 6 caras de una caja alineada con los ejes."""
    c, t = np.asarray(centro, float), np.asarray(tam, float)
    puntos = []
    for eje in range(3):
        otros = [k for k in range(3) if k != eje]
        area = t[otros[0]] * t[otros[1]]
        n = max(4, int(area * densidad))
        for signo in (-1, 1):
            p = np.empty((n, 3))
            p[:, eje] = c[eje] + signo * t[eje] / 2
            for k in otros:
                p[:, k] = c[k] + (rng.random(n) - 0.5) * t[k]
            puntos.append(p)
    return np.concatenate(puntos)


def parque(sep=6.0, altura=1.5, cantidad=3, largo=30.0, semilla=0):
    """Nube (N, 3), arriba, etiquetas y paneles, en un marco de cámara al azar. Devuelve también el entorno real."""
    rng = np.random.default_rng(semilla)
    ent = json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))
    ent["filas"].update(cantidad=cantidad, separacion_m=sep, largo_m=largo)
    ent["estructura"]["altura_m"] = altura
    nubes, etiquetas, instancias = [], [], []
    for cuerpo in generar_escena.cuerpos(ent):
        if cuerpo["nombre"] == "Suelo":
            cx, cy = cuerpo["centro"][:2]
            sx, sy = cuerpo["tam"][:2]
            n = int(sx * sy * 15)
            p = np.column_stack([cx + (rng.random(n) - 0.5) * sx, cy + (rng.random(n) - 0.5) * sy, np.zeros(n)])
            nubes.append(p)
            etiquetas.append(np.zeros(n, int))
            continue
        p = _caja(cuerpo["centro"], cuerpo["tam"], 400, rng)
        nubes.append(p)
        etiquetas.append(np.full(len(p), mg.TUBO if "Tubo" in cuerpo["nombre"] else mg.POSTE))
    for panel in generar_escena.paneles_visuales(ent):
        p = _caja(panel["centro"], panel["tam"], 150, rng)
        nubes.append(p)
        etiquetas.append(np.full(len(p), mg.PANEL))
        instancias.append(len(nubes) - 1)
    # Una persona en el pasillo: SAM 3 la marca para excluirla.
    persona = _caja((10.0, -sep / 2, 0.85), (0.4, 0.3, 1.7), 300, rng)
    nubes.append(persona)
    etiquetas.append(np.full(len(persona), mg.EXCLUIR))

    # Marco de cámara: rotación y traslación al azar, más ruido.
    a, b, g = rng.uniform(-math.pi, math.pi, 3)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    rz = np.array([[math.cos(g), -math.sin(g), 0], [math.sin(g), math.cos(g), 0], [0, 0, 1]])
    r, t = rz @ ry @ rx, rng.uniform(-20, 20, 3)

    def mover(p):
        return (p @ r.T + t) + rng.normal(0, RUIDO_M, p.shape)

    todos = mover(np.concatenate(nubes))
    paneles = [mover(nubes[i]) for i in instancias]
    # La vertical de la cámara tiene 2° de error: un celular nunca va perfectamente derecho.
    inclinada = np.array([math.sin(math.radians(2)), 0.0, math.cos(math.radians(2))])
    return todos, r @ inclinada, np.concatenate(etiquetas), paneles, ent


CASOS = [(6.0, 1.5, 3), (5.0, 1.2, 4), (8.0, 2.0, 3), (7.0, 1.8, 2)]


@pytest.mark.parametrize("sep,altura,cantidad", CASOS)
def test_mide_filas_y_altura(sep, altura, cantidad):
    puntos, arriba, etiquetas, paneles, _ = parque(sep, altura, cantidad)
    r = mg.medir(puntos, arriba, etiquetas, paneles)["campos"]
    assert r["filas.cantidad"]["valor"] == cantidad
    assert abs(r["filas.separacion_m"]["valor"] - sep) <= mg.TOLERANCIAS["filas.separacion_m"]
    assert abs(r["estructura.altura_m"]["valor"] - altura) <= mg.TOLERANCIAS["estructura.altura_m"]
    assert r["estructura.tipo"]["valor"] == "tracker_1_eje"
    assert abs(r["estructura.inclinacion_grados"]["valor"]) <= mg.TOLERANCIAS["estructura.inclinacion_grados"]
    assert abs(r["terreno.pendiente_grados"]["valor"] - 2.0) <= 1.0   # el error de la cámara aparece como pendiente


@pytest.mark.parametrize("sep,altura,cantidad", CASOS)
def test_mide_panel_con_sam3(sep, altura, cantidad):
    puntos, arriba, etiquetas, paneles, ent = parque(sep, altura, cantidad)
    r = mg.medir(puntos, arriba, etiquetas, paneles)["campos"]
    assert abs(r["panel.largo_m"]["valor"] - ent["panel"]["largo_m"]) <= mg.TOLERANCIAS["panel.largo_m"]
    assert abs(r["panel.ancho_m"]["valor"] - ent["panel"]["ancho_m"]) <= mg.TOLERANCIAS["panel.ancho_m"]


@pytest.mark.parametrize("sep,altura,cantidad", CASOS)
def test_panel_sin_sam3_mide_o_calla(sep, altura, cantidad):
    """Sin SAM 3 el largo sale del ancho de la banda. El ancho sale del período de los paneles, si se ve:
    si no hay período claro, el campo queda sin medir (y avisa) en vez de inventar un valor."""
    puntos, arriba, etiquetas, _, ent = parque(sep, altura, cantidad)
    m = mg.medir(puntos, arriba, etiquetas, None)
    r = m["campos"]
    assert abs(r["panel.largo_m"]["valor"] - ent["panel"]["largo_m"]) <= mg.TOLERANCIAS["panel.largo_m"]
    if "panel.ancho_m" in r:
        assert abs(r["panel.ancho_m"]["valor"] - ent["panel"]["ancho_m"]) <= 1.5 * mg.TOLERANCIAS["panel.ancho_m"]
    else:
        assert any("panel.ancho_m" in a for a in m["avisos"])


def test_sin_etiquetas_mide_igual():
    """Sin SAM 3: solo la nube. La persona queda como ruido, pero la medida sigue dentro de tolerancia."""
    puntos, arriba, _, _, ent = parque(semilla=3)
    r = mg.medir(puntos, arriba)["campos"]
    assert r["filas.cantidad"]["valor"] == ent["filas"]["cantidad"]
    assert abs(r["filas.separacion_m"]["valor"] - 6.0) <= 0.3
    assert abs(r["estructura.altura_m"]["valor"] - 1.5) <= 0.1


def test_una_fila_avisa():
    puntos, arriba, etiquetas, paneles, _ = parque(cantidad=1)
    m = mg.medir(puntos, arriba, etiquetas, paneles)
    assert m["campos"]["filas.cantidad"]["valor"] == 1
    assert "filas.separacion_m" not in m["campos"]
    assert any("una sola fila" in a for a in m["avisos"])


def test_nube_vacia_falla():
    with pytest.raises(mg.SinGeometria):
        mg.medir(np.zeros((10, 3)), np.array([0, 0, 1.0]))


def test_confianza_baja_con_el_error():
    assert mg.confianza("filas.separacion_m", 0.0) == 0.95
    assert mg.confianza("filas.separacion_m", 0.3) == 0.45
    assert mg.confianza("filas.separacion_m", 5.0) == 0.1
