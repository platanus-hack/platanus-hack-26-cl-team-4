"""Escena física sin Isaac: USD estático, descripción de la escena de Isaac Lab y masas del clon."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from viaz import agentes, catalogo, urdf

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "sim"))
import fisica  # noqa: E402
import generar_escena  # noqa: E402
import plan  # noqa: E402
import viaz_escena  # noqa: E402


@pytest.fixture
def entorno():
    return json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))


@pytest.fixture
def clon(entorno):
    t = json.loads((agentes.FIXTURES / "tarea.json").read_text(encoding="utf-8"))
    return agentes.clon(agentes.robot("fijo", "x", entorno, t, catalogo.cargar()))[0]


def test_escena_estatica_tiene_friccion_y_no_tiene_masa(entorno):
    usda = generar_escena.escena_usda(entorno)
    assert "PhysicsScene" not in usda          # la crea Isaac Lab con sim/fisica.py
    assert "PhysicsRigidBodyAPI" not in usda   # todo lo de la planta es estático
    assert "PhysicsMassAPI" not in usda
    cubos = usda.count('def Cube "')
    assert usda.count("material:binding:physics") == cubos
    for nombre in ("Suelo", "Acero"):
        assert f'def Material "{nombre}"' in usda
    assert "physics:restitution = 0.0" in usda


def test_escena_usda_es_usd_valido(entorno, tmp_path):
    """Con usd-core instalado (CI) abre el USD de verdad y revisa los bindings."""
    pxr = pytest.importorskip("pxr")
    from pxr import Usd, UsdPhysics, UsdShade

    f = tmp_path / "escena.usd"
    f.write_text(generar_escena.escena_usda(entorno), encoding="utf-8")
    stage = Usd.Stage.Open(str(f))
    assert stage.GetDefaultPrim().GetPath() == "/World"
    assert UsdPhysics.GetStageKilogramsPerUnit(stage) == 1
    tubo = stage.GetPrimAtPath("/World/Planta/Fila0_Tubo")
    assert tubo.HasAPI(UsdPhysics.CollisionAPI)
    mat, _ = UsdShade.MaterialBindingAPI(tubo).ComputeBoundMaterial("physics")
    assert mat.GetPath() == "/World/Materiales/Acero"
    assert UsdPhysics.MaterialAPI(mat.GetPrim()).GetStaticFrictionAttr().Get() == pytest.approx(0.6)
    del pxr


def test_poste_termina_bajo_el_tubo(entorno):
    usda = generar_escena.escena_usda(entorno)
    alto = entorno["estructura"]["altura_m"]
    m = re.search(r'def Cube "Fila0_Poste0".*?translate = \(([^)]*)\).*?scale = \(([^)]*)\)', usda, re.S)
    z_centro = float(m.group(1).split(",")[2])
    h = float(m.group(2).split(",")[2])
    assert z_centro + h / 2 == pytest.approx(alto - generar_escena.TUBO_LADO_M / 2)


def test_describir_paneles_con_masa_y_reposo_sobre_el_tubo(entorno):
    d = viaz_escena.describir(entorno, 3, caida_m=0.1)
    assert d["dt_s"] == fisica.DT_S
    assert [p["masa_kg"] for p in d["paneles"]] == [entorno["panel"]["peso_kg"]] * 3
    reposo = entorno["estructura"]["altura_m"] + generar_escena.TUBO_LADO_M / 2 + fisica.PANEL_ESPESOR_M / 2
    for p in d["paneles"]:
        assert p["pos_esperada_m"][2] == pytest.approx(reposo)
        assert p["pos_inicial_m"][2] == pytest.approx(reposo + 0.1)
        assert p["material"]["restitucion"] == 0.0
    # paneles vecinos no se tocan
    xs = [p["pos_inicial_m"][0] for p in d["paneles"]]
    assert min(b - a for a, b in zip(xs, xs[1:])) > entorno["panel"]["ancho_m"]


def test_describir_robot_en_el_pasillo(entorno, clon):
    d = viaz_escena.describir(entorno, 1, con_robot=True, clon=clon)
    r = d["robot"]
    assert r["pos_inicial_m"][1] == plan.distancia_pasillo(entorno, clon["geometria"])
    assert list(r["q_inicial"]) == urdf.ARTICULACIONES
    assert set(r["rigidez"]) == set(urdf.ARTICULACIONES)
    # la base no invade el tubo de la fila 0 (medio panel hacia el pasillo)
    assert r["pos_inicial_m"][1] - clon["geometria"]["medio_ancho_m"] > entorno["panel"]["largo_m"] / 2


def test_masas_e_inercias_del_clon():
    texto = urdf.generar("x", 2.4)
    for m in re.finditer(r'<inertia ixx="([\d.]+)" iyy="([\d.]+)" izz="([\d.]+)"', texto):
        ixx, iyy, izz = map(float, m.groups())
        assert min(ixx, iyy, izz) > 0
        # desigualdad triangular de los momentos principales (inercia físicamente posible)
        assert ixx + iyy >= izz and ixx + izz >= iyy and iyy + izz >= ixx
    assert 650 < urdf.masa_total(2.4) < 800
    piezas = {p["link"]: p["masa"] for p in urdf.piezas(2.4)}
    assert piezas["base_link"] > 10 * piezas["brazo"]


def test_hombro_aguanta_panel_con_brazo_extendido(entorno):
    """Torque estático en el hombro con el brazo horizontal y el panel en la punta, menor al límite."""
    g = urdf.geometria(2.4)
    piezas = {p["link"]: p["masa"] for p in urdf.piezas(2.4)}
    l1, l2 = g["l1_m"], g["l2_m"]
    torque = fisica.GRAVEDAD * (piezas["brazo"] * l1 / 2 + piezas["antebrazo"] * (l1 + l2 / 2)
                                + (piezas["efector"] + entorno["panel"]["peso_kg"]) * (l1 + l2 + g["muneca_m"]))
    assert torque < urdf.ESFUERZO_NM["shoulder_lift"]
