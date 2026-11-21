"""Física propia de cada robot: las medidas de la ficha del catálogo llegan al URDF, al clon y al plan."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from viaz import agentes, catalogo, urdf
from viaz.esquemas import esquema, sin_campos

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import plan  # noqa: E402


@pytest.fixture
def entorno():
    return json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))


@pytest.fixture
def tarea():
    return json.loads((agentes.FIXTURES / "tarea.json").read_text(encoding="utf-8"))


@pytest.fixture
def leapting():
    return catalogo.cargar()["leapting-mmr"]


def _cajas(texto: str, link: str) -> tuple[float, ...]:
    bloque = re.search(rf'<link name="{link}">(.*?)</link>', texto, re.S).group(1)
    return tuple(float(v) for v in re.search(r'<collision>.*?<box size="([\d. ]+)"', bloque, re.S).group(1).split())


def test_la_ficha_del_leapting_trae_las_medidas_del_fabricante(leapting):
    f = leapting["fisica"]
    assert (f["largo_m"], f["ancho_m"], f["masa_kg"], f["traccion"]) == (3.145, 1.8, 4500, "orugas")
    # lo que el fabricante no publica queda declarado como estimado
    assert {"fisica.altura_cubierta_m", "fisica.brazo_x_m"} <= set(leapting["estimados"])


def test_el_urdf_del_leapting_usa_sus_medidas(leapting):
    texto = urdf.generar("leapting", leapting["alcance_m"], leapting["fisica"])
    largo, ancho, _ = _cajas(texto, "base_link")
    assert (largo, ancho) == (3.145, 1.8)
    # la máquina pesa lo que dice la ficha; el remolque va aparte
    piezas = urdf.piezas(leapting["alcance_m"], leapting["fisica"])
    assert sum(p["masa"] for p in piezas if "remolque" not in p["link"]) == pytest.approx(4500, abs=1)
    assert sum(p["masa"] for p in piezas if "remolque" in p["link"]) == pytest.approx(2300, abs=1)
    assert _cajas(texto, "efector")[:2] == (1.9, 0.5)
    pan = re.search(r'<joint name="shoulder_pan".*?<origin xyz="([-\d. ]+)"', texto, re.S).group(1).split()
    assert float(pan[2]) == leapting["fisica"]["altura_cubierta_m"]
    assert "oruga_0" in texto and "rueda_0" not in texto
    for m in re.finditer(r'<inertia ixx="([\d.]+)" iyy="([\d.]+)" izz="([\d.]+)"', texto):
        ixx, iyy, izz = map(float, m.groups())
        assert min(ixx, iyy, izz) > 0
        assert ixx + iyy >= izz and ixx + izz >= iyy and iyy + izz >= ixx


def test_un_robot_sin_ficha_fisica_conserva_el_clon_de_siempre():
    texto = urdf.generar("x", 2.4)
    assert _cajas(texto, "base_link") == urdf.BASE
    assert "rueda_3" in texto and "oruga_0" not in texto
    assert urdf.geometria(2.4) == {"l1_m": 1.092, "l2_m": 1.008, "muneca_m": 0.3, "montaje_x_m": 0.45,
                                   "hombro_z_m": 1.1, "cubierta_z_m": 0.8, "pila_x_m": -0.35}


def test_el_clon_del_leapting_lleva_su_geometria(entorno, tarea, leapting):
    clon, texto = agentes.clon(agentes.robot("fijo", "x", entorno, tarea, catalogo.cargar()))
    g = clon["geometria"]
    assert clon["robot_id"] == "leapting-mmr"
    assert g["cubierta_z_m"] == leapting["fisica"]["altura_cubierta_m"]
    assert g["hombro_z_m"] == pytest.approx(g["cubierta_z_m"] + urdf.HOMBRO_ALTO)
    assert g["medio_ancho_m"] == 0.9
    assert g["pila_x_m"] > leapting["fisica"]["largo_m"] / 2     # la pila va sobre el remolque, delante del vehículo
    assert "remolque" in texto
    assert "oruga_0" in texto


def test_el_plan_alcanza_con_la_geometria_real(entorno, tarea):
    clon, _ = agentes.clon(agentes.robot("fijo", "x", entorno, tarea, catalogo.cargar()))
    assert plan.validar(entorno, tarea, clon) == {"ok": True, "problemas": [], "paneles_planificados": 5}
    d = plan.distancia_pasillo(entorno, clon["geometria"])
    # el vehículo de 1,8 m de ancho no invade el panel ya instalado
    assert d - clon["geometria"]["medio_ancho_m"] > entorno["panel"]["largo_m"] / 2
    tray = plan.generar(entorno, tarea, clon)
    assert tray["frames"][-1]["instalados"] == [0, 1, 2, 3, 4]
    assert tray["pila"]["pos_m"][0] == clon["geometria"]["pila_x_m"]


def test_el_alcance_necesario_depende_del_robot(entorno, leapting):
    assert agentes.alcance_necesario(entorno) == 2.28          # clon de siempre
    necesario = agentes.alcance_necesario(entorno, leapting)
    assert 2.28 < necesario <= leapting["alcance_m"]           # el vehículo ancho queda más lejos del tubo
    assert agentes.eleccion_por_reglas(entorno, catalogo.cargar())["id"] == "leapting-mmr"


NUCLEO = {"largo_m": 2.0, "ancho_m": 1.2, "masa_kg": 500, "altura_cubierta_m": 0.9, "traccion": "ruedas"}


def _errores_fisica(fisica: dict) -> list[str]:
    ficha = {**catalogo.cargar()["viaz-instalador-ficticio"], "fisica": fisica}
    validador = Draft202012Validator(sin_campos(esquema("robot"), ["justificacion", "alternativas"]))
    return [e.message for e in validador.iter_errors(ficha)]


def _inercias_validas(texto: str) -> None:
    for m in re.finditer(r'<inertia ixx="([\d.]+)" iyy="([\d.]+)" izz="([\d.]+)"', texto):
        ixx, iyy, izz = map(float, m.groups())
        assert min(ixx, iyy, izz) > 0
        assert ixx + iyy >= izz and ixx + izz >= iyy and iyy + izz >= ixx


def test_el_esquema_acepta_solo_el_nucleo_de_fisica():
    assert _errores_fisica(NUCLEO) == []
    assert _errores_fisica({**NUCLEO, "traccion": "orugas"}) == []


@pytest.mark.parametrize("campo", sorted(NUCLEO))
def test_el_esquema_rechaza_fisica_sin_un_campo_del_nucleo(campo):
    assert _errores_fisica({k: v for k, v in NUCLEO.items() if k != campo})


@pytest.mark.parametrize("mitad", [{"gabinete_largo_m": 1.0}, {"gabinete_alto_m": 1.0}, {"ventosa_largo_m": 1.0},
                                   {"ventosa_ancho_m": 0.5}, {"remolque_largo_m": 2.0}, {"remolque_masa_kg": 900}])
def test_el_esquema_rechaza_medio_par(mitad):
    assert _errores_fisica({**NUCLEO, **mitad})


def test_la_ficha_del_bison_trae_las_medidas_publicadas():
    bison = catalogo.cargar()["relu-bison"]
    f = bison["fisica"]
    assert (f["largo_m"], f["ancho_m"], f["masa_kg"], f["traccion"]) == (5.2, 2.1, 9000, "orugas")
    assert bison["fuente"] == {"url": "https://www.pv-magazine.com/2026/07/17/ai-powered-9-ton-tracked-robot-for-large-scale-pv-construction/",
                               "consultado": "2026-11-21"}
    assert {"fisica.altura_cubierta_m", "fisica.brazo_x_m", "fisica.gabinete"} <= set(bison["estimados"])
    assert not {"remolque_largo_m", "ventosa_largo_m", "brazo_grosor_m"} & set(f)


def test_el_urdf_del_bison_usa_sus_medidas():
    bison = catalogo.cargar()["relu-bison"]
    texto = urdf.generar("bison", bison["alcance_m"], bison["fisica"])
    assert _cajas(texto, "base_link")[:2] == (5.2, 2.1)
    assert urdf.masa_total(bison["alcance_m"], bison["fisica"]) == pytest.approx(9000, abs=1)
    assert "oruga_0" in texto and "oruga_1" in texto and "gabinete" in texto
    assert "remolque" not in texto and "rueda" not in texto
    _inercias_validas(texto)
    g = urdf.geometria(bison["alcance_m"], bison["fisica"])
    assert g["montaje_x_m"] < 0 < g["pila_x_m"] < bison["fisica"]["largo_m"] / 2


def test_un_robot_con_ruedas_y_solo_el_nucleo_genera_un_urdf_valido():
    texto = urdf.generar("ruedas", 2.4, NUCLEO)
    assert _cajas(texto, "base_link")[:2] == (2.0, 1.2)
    assert urdf.masa_total(2.4, NUCLEO) == pytest.approx(500, abs=1)
    assert "gabinete" not in texto and "remolque" not in texto and "oruga" not in texto
    _inercias_validas(texto)
    for i in range(4):
        xyz = re.search(rf'<joint name="rueda_{i}_fija".*?<origin xyz="([-\d. ]+)"', texto).group(1).split()
        x, y = abs(float(xyz[0])), abs(float(xyz[1]))
        assert x + urdf.RUEDA_R <= NUCLEO["largo_m"] / 2 and y + urdf.RUEDA_ANCHO / 2 <= NUCLEO["ancho_m"] / 2
    g = urdf.geometria(2.4, NUCLEO)
    assert abs(g["pila_x_m"]) < NUCLEO["largo_m"] / 2 and g["medio_ancho_m"] == 0.6


CON_FISICA = ["leapting-mmr", "relu-bison",
              pytest.param("trinatracker-buildex-e", marks=pytest.mark.xfail(strict=True, reason=(
                  "El alcance del catálogo (2,5 m, estimado) no cubre el que pide su ancho de 2,47 m y su cubierta "
                  "de 0,85 m. No cambiamos el número: una persona debe decidir el alcance real (investigación §7).")))]


def test_cada_robot_con_fisica_tiene_su_prueba_de_plan():
    con_fisica = {i for i, r in catalogo.cargar().items() if "fisica" in r}
    assert con_fisica == {p if isinstance(p, str) else p.values[0] for p in CON_FISICA}


@pytest.mark.parametrize("robot_id", CON_FISICA)
def test_el_plan_de_cada_robot_con_fisica_pasa_validar(entorno, tarea, robot_id):
    r = catalogo.cargar()[robot_id]
    clon = {"geometria": urdf.geometria(r["alcance_m"], r["fisica"]), "escala": {"carga_util_kg": r["carga_util_kg"]}}
    assert plan.validar(entorno, tarea, clon)["ok"]
    assert agentes.alcance_necesario(entorno, r) <= r["alcance_m"]
