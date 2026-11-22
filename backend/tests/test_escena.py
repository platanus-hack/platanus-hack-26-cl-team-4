"""Escena física sin Isaac: USD estático, descripción de la escena de Isaac Lab y masas del clon."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from viaz import agentes, catalogo, urdf
from viaz.esquemas import ErrorEsquema, validar

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
    return agentes.clon(agentes.seleccionar("fijo", "x", entorno, t, catalogo.cargar()).robots_por_puesto[0])[0]


def test_escena_estatica_tiene_friccion_y_no_tiene_masa(entorno):
    usda = generar_escena.escena_usda(entorno)
    assert "PhysicsScene" not in usda          # la crea Isaac Lab con sim/fisica.py
    assert "PhysicsRigidBodyAPI" not in usda   # todo lo de la planta es estático
    assert "PhysicsMassAPI" not in usda
    # todo lo que choca tiene su material de fricción. Lo visual (fila 1, llano, cerros) no choca.
    assert usda.count("material:binding:physics") == usda.count("PhysicsCollisionAPI") == len(generar_escena.cuerpos(entorno))
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
    assert UsdPhysics.MaterialAPI(mat.GetPrim()).GetStaticFrictionAttr().Get() == pytest.approx(
        fisica.material("acero")["estatica"])
    del pxr


def test_fila_1_ya_tiene_paneles_que_solo_se_ven(entorno, tmp_path):
    """RF-MAP-13: la fila 1 llega instalada y sin física. La fila 0 queda vacía para el robot."""
    pytest.importorskip("pxr")
    from pxr import Usd, UsdPhysics

    f = tmp_path / "escena.usd"
    f.write_text(generar_escena.escena_usda(entorno), encoding="utf-8")
    stage = Usd.Stage.Open(str(f))

    visuales = [p for p in stage.GetPrimAtPath("/World/Visual").GetChildren()]
    paneles = [p for p in visuales if "_Panel" in p.GetName()]

    assert len(paneles) == plan.caben(entorno) == 24
    assert all(p.GetName().startswith("Fila1_") for p in paneles)
    assert not any(p.HasAPI(UsdPhysics.CollisionAPI) for p in visuales)
    assert {"Llano", "Cerros"} <= {p.GetName() for p in visuales}
    assert {p.GetName() for p in stage.GetPrimAtPath("/World/Luces").GetChildren()} == {"Sol", "Cielo"}


def test_revisar_usd_calza_con_su_entorno_y_delata_uno_distinto(entorno, tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd

    f = tmp_path / "escena.usd"
    f.write_text(generar_escena.escena_usda(entorno), encoding="utf-8")
    stage = Usd.Stage.Open(str(f))
    otro_parque = {**entorno, "estructura": {**entorno["estructura"], "altura_m": 1.8},
                   "terreno": {**entorno["terreno"], "friccion": 0.3}}

    assert viaz_escena.revisar_usd(stage, entorno) == []
    diferencias = viaz_escena.revisar_usd(stage, otro_parque)
    assert any(d.startswith("Fila0_Tubo: centro") for d in diferencias)
    assert any(d.startswith("Suelo: fricción") for d in diferencias)


def test_el_terreno_no_depende_del_robot(entorno):
    """El terreno es el paso 1 del ciclo: se genera antes de elegir el robot."""
    usda = generar_escena.escena_usda(entorno).lower()
    assert "robot" not in usda and "pila" not in usda and "soporte" not in usda


def test_friccion_del_suelo_sale_de_entorno(entorno):
    sin_dato = {**entorno, "terreno": {"pendiente_grados": 0, "suelo": "pasto"}}
    desconocido = {**entorno, "terreno": {"pendiente_grados": 0, "suelo": "lava"}}
    medido = {**entorno, "terreno": {"pendiente_grados": 0, "suelo": "pasto", "friccion": 0.85}}

    assert fisica.material_suelo(entorno)["estatica"] == entorno["terreno"]["friccion"] == 0.6
    assert fisica.material_suelo(sin_dato)["estatica"] == fisica.SUELOS["pasto"]
    assert fisica.material_suelo(desconocido)["estatica"] == fisica.MATERIALES["suelo"]["estatica"]
    assert fisica.material_suelo(medido)["dinamica"] == 0.85
    assert "physics:staticFriction = 0.85" in generar_escena.escena_usda(medido)


def test_entorno_acepta_friccion_y_rechaza_una_imposible(entorno):
    validar("entorno", entorno)
    with pytest.raises(ErrorEsquema, match="terreno/friccion"):
        validar("entorno", {**entorno, "terreno": {**entorno["terreno"], "friccion": 3.0}})
    assert "friccion" not in agentes.esquema_agente_entorno()["properties"]["terreno"]["properties"]


def test_cada_material_tiene_un_solo_coeficiente():
    """PhysX en GPU no sostiene una estática mayor que la dinámica (medido en el pod): van iguales."""
    for nombre, m in fisica.MATERIALES.items():
        assert m["estatica"] == m["dinamica"], nombre
        assert m["restitucion"] == 0.0


def test_friccion_de_cada_par_de_contacto(entorno):
    panel, acero = fisica.material("panel"), fisica.material("acero")
    assert fisica.COMBINACION == "average"
    assert fisica.friccion_par(panel, acero)["dinamica"] == pytest.approx(0.35)
    assert fisica.friccion_par(panel, panel)["dinamica"] == pytest.approx(0.40)
    assert fisica.friccion_par(panel, fisica.material_suelo(entorno))["dinamica"] == pytest.approx(0.50)


def test_rangos_de_variacion_del_entrenamiento(entorno):
    r = fisica.rangos_variacion(entorno)
    assert r["masa_panel_escala"] == (0.9, 1.1)
    assert r["friccion"]["panel"]["dinamica"] == pytest.approx((0.32, 0.48))
    assert r["friccion"]["acero"]["estatica"] == pytest.approx((0.24, 0.36))
    assert (r["base_pos_m"], r["base_yaw_grados"]) == (0.15, 5.0)
    assert 0 < r["viento_n"] < fisica.GRAVEDAD * entorno["panel"]["peso_kg"]


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


def test_pila_sin_robot_va_en_un_pallet_fuera_de_la_fila(entorno):
    d = viaz_escena.describir(entorno, 3, n_pila=5)
    s, largo = d["soporte"], entorno["panel"]["largo_m"]

    assert s["tam_m"][2] == viaz_escena.PALLET_ALTO_M
    assert s["pos_m"][1] - largo / 2 > largo / 2          # no toca los paneles instalados en la fila 0
    assert [p["pos_inicial_m"][2] for p in d["pila"]] == pytest.approx(
        [s["tam_m"][2] + (k + 0.5) * fisica.PANEL_ESPESOR_M for k in range(5)])
    assert all(p["pos_inicial_m"] == p["pos_esperada_m"] for p in d["pila"])   # la pila parte en reposo
    assert all(p["masa_kg"] == entorno["panel"]["peso_kg"] for p in d["pila"])


def test_pila_con_clon_va_donde_el_robot_la_lleva(entorno, clon):
    g = clon["geometria"]
    sin_robot = viaz_escena.describir(entorno, 1, clon=clon, n_pila=2)
    con_robot = viaz_escena.describir(entorno, 1, clon=clon, n_pila=2, con_robot=True)

    x_base = plan.slots(entorno, 1)[0][0] - g["montaje_x_m"]
    assert sin_robot["soporte"]["pos_m"][:2] == pytest.approx((x_base + g["pila_x_m"], plan.distancia_pasillo(entorno, g)))
    assert sin_robot["pila"][0]["pos_inicial_m"][2] == pytest.approx(g["cubierta_z_m"] + fisica.PANEL_ESPESOR_M / 2)
    assert con_robot["soporte"] is None                     # con el robot, la pila descansa en su base
    assert con_robot["pila"] == sin_robot["pila"]


def test_escena_de_entrenamiento_es_un_recorte_del_parque(entorno, clon):
    """RF-MAP-12: un tramo de tubo de la fila 0, la pila y el panel que se instala, del mismo entorno.json."""
    d = viaz_escena.describir_entrenamiento(entorno, 5, clon=clon)
    fijos = {c["nombre"]: c for c in generar_escena.cuerpos(entorno)}

    assert d["tramo_m"] == generar_escena.POSTE_CADA_M
    assert d["tubo"]["tam_m"] == (7.0, *fijos["Fila0_Tubo"]["tam"][1:])
    assert d["tubo"]["pos_m"] == (3.5, 0.0, entorno["estructura"]["altura_m"])
    assert [p["pos_m"] for p in d["postes"]] == [fijos["Fila0_Poste0"]["centro"], fijos["Fila0_Poste1"]["centro"]]
    assert len(d["pila"]) == 4 and d["panel"]["nombre"] == "panel"
    assert d["panel"]["pos_inicial_m"][2] == pytest.approx(d["pila"][-1]["pos_inicial_m"][2] + fisica.PANEL_ESPESOR_M)
    assert d["panel"]["pos_esperada_m"] == tuple(viaz_escena.describir(entorno, 1)["paneles"][0]["pos_esperada_m"])
    assert d["suelo"] == fisica.material_suelo(entorno)
    assert (d["dt_s"], d["decimacion"]) == (fisica.DT_S, fisica.RENDER_CADA)
    # cabe en su celda: el tramo no llega a la copia vecina
    assert d["tramo_m"] + generar_escena.POSTE_LADO_M < viaz_escena.ESPACIADO_ENV_M


def test_escena_de_entrenamiento_sin_robot_ni_clon(entorno):
    d = viaz_escena.describir_entrenamiento(entorno, 1)
    assert d["pila"] == [] and d["soporte"]["tam_m"][2] == viaz_escena.PALLET_ALTO_M
    assert viaz_escena.describir_entrenamiento(entorno, 3, con_robot=True)["soporte"] is None
    with pytest.raises(ValueError):
        viaz_escena.describir_entrenamiento(entorno, 0)


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


def test_cada_escena_propia_tiene_perfil_de_entorno():
    assert set(generar_escena.ESCENAS) <= set(agentes.PERFILES_ENTORNO)
