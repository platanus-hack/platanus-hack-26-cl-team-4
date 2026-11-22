"""Despacho de comandos por tarea (sim/tareas.py) y piezas con detalle de la escena genérica. Sin Isaac."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from viaz.agentes import perfiles

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import detalles  # noqa: E402
import generar_escena  # noqa: E402
import tareas  # noqa: E402

FIXTURES = RAIZ / "backend" / "viaz" / "fixtures"


def _fixture(n: str) -> dict:
    return json.loads((FIXTURES / f"{n}.json").read_text(encoding="utf-8"))


def test_cada_tarea_con_simulacion_tiene_su_carpeta_en_sim_y_coinciden_con_el_backend():
    con_sim = {t: p.sim for t, p in perfiles.PERFILES_TAREA.items() if p.con_simulacion}
    assert con_sim == tareas.CARPETAS
    for carpeta in tareas.CARPETAS.values():
        for comando in tareas.COMANDOS:
            assert (RAIZ / "sim" / carpeta / f"{comando}.py").exists(), (carpeta, comando)


def test_el_despachador_elige_por_tarea_y_rechaza_lo_que_no_conoce(tmp_path):
    t = tmp_path / "tarea.json"
    t.write_text(json.dumps(_fixture("tarea_animar")), encoding="utf-8")
    assert tareas.script("entrenar", tareas.tarea_de(["--tarea", str(t)])).parent.name == "animar"
    t.write_text(json.dumps(_fixture("tarea")), encoding="utf-8")
    assert tareas.script("evaluar", tareas.tarea_de(["--tarea", str(t)])).parent.name == "rl"
    with pytest.raises(SystemExit, match="tomar_y_dejar"):
        tareas.script("entrenar", "tomar_y_dejar")
    with pytest.raises(SystemExit, match="comando"):
        tareas.script("bailar", "animar_evento")


def test_los_elementos_con_detalle_se_dibujan_con_piezas_y_chocan_con_su_caja():
    usda = generar_escena.escena_usda(_fixture("entorno_evento"))
    assert usda.count('def Cube "S') > 100                     # sillas: asiento y respaldo de cada una
    assert "sillas_bloque_1_Visual" in usda and "Vis" + "Pantalla_led" in usda
    # La caja de colisión de un elemento con detalle no se ve; la de uno sin detalle (mesa_tecnica), sí.
    bloque = usda[usda.index('"E03_sillas_bloque_1"'):usda.index('"E03_sillas_bloque_1_Visual"')]
    assert 'visibility = "invisible"' in bloque and "PhysicsCollisionAPI" in bloque
    tecnica = usda[usda.index('"E08_mesa_tecnica"'):]
    tecnica = tecnica[:tecnica.index("}")]
    assert "invisible" not in tecnica
    # Ninguna pieza visual lleva colisión ni masa
    visuales = re.findall(r'def Xform "E\d+_\w+_Visual"\s*\{.*?\n    \}', usda, re.S)
    assert visuales and not any("Physics" in v for v in visuales)


def test_las_sillas_llenan_su_bloque_sin_salirse():
    s = detalles.DIMENSIONES["silla"]
    texto = detalles.sillas(3.0, 8.0, 0.85)
    xs = [float(m) for m in re.findall(r'"S\d+_\d+_asiento".*?translate = \(([-\d.]+),', texto, re.S)]
    assert len(xs) == int(3.0 // s["paso_x_m"]) * int(8.0 // s["paso_y_m"])
    assert max(abs(x) for x in xs) + s["asiento_m"] / 2 <= 1.5
