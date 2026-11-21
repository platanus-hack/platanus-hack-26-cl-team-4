"""Escena con texturas: materiales OmniPBR, panel con vidrio, un solo suelo visible, rocas, cielo. Solo se ve: la física no cambia."""
import json
import sys
from pathlib import Path

import pytest

from viaz import agentes

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sim"))
import generar_escena  # noqa: E402


@pytest.fixture
def entorno():
    return json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8"))


def test_la_fisica_es_la_misma_con_y_sin_texturas(entorno):
    plano, con = generar_escena.escena_usda(entorno), generar_escena.escena_usda(entorno, con_texturas=True)
    for clave in ("material:binding:physics", "PhysicsCollisionAPI", "physics:staticFriction"):
        assert plano.count(clave) == con.count(clave)
    assert "PhysicsRigidBodyAPI" not in con and "PhysicsMassAPI" not in con
    assert not any(p in con.lower() for p in ("robot", "pila", "soporte"))


def test_los_mapas_de_datos_se_leen_sin_color_sRGB(entorno):
    """Sin colorSpace raw Isaac lee las normales como color: el suelo sale oscuro y con una costura recta."""
    con = generar_escena.escena_usda(entorno, con_texturas=True)
    for entrada in ("normalmap_texture", "reflectionroughness_texture", "metallic_texture"):
        lineas = [linea for linea in con.splitlines() if f"inputs:{entrada} " in linea]
        assert lineas and all('colorSpace = "raw"' in linea for linea in lineas)
    assert "inputs:diffuse_texture" in con and "colorSpace" not in con.split("inputs:diffuse_texture")[1].splitlines()[0]


def test_con_texturas_se_ve_un_solo_suelo_y_el_panel_lleva_vidrio(entorno, tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdShade

    f = tmp_path / "escena.usd"
    f.write_text(generar_escena.escena_usda(entorno, con_texturas=True), encoding="utf-8")
    stage = Usd.Stage.Open(str(f))
    assert UsdGeom.Imageable(stage.GetPrimAtPath("/World/Planta/Suelo")).ComputeVisibility() == "invisible"
    llano = stage.GetPrimAtPath("/World/Visual/Llano")
    tope = UsdGeom.Cube(llano).GetSizeAttr().Get() * 0.5 * llano.GetAttribute("xformOp:scale").Get()[2]
    assert llano.GetAttribute("xformOp:translate").Get()[2] + tope == pytest.approx(0.0, abs=1e-6)
    panel = stage.GetPrimAtPath("/World/Visual/Fila1_Panel0")
    assert UsdShade.MaterialBindingAPI(panel).ComputeBoundMaterial()[0].GetPath() == "/World/Materiales/VisMarco"
    vidrio = stage.GetPrimAtPath("/World/Visual/Fila1_Panel0/Vidrio")
    assert UsdShade.MaterialBindingAPI(vidrio).ComputeBoundMaterial()[0].GetPath() == "/World/Materiales/VisPanel"
    rocas = [p for p in stage.GetPrimAtPath("/World/Visual/Rocas").GetChildren() if p.GetName().startswith("Roca_")]
    assert len(rocas) == generar_escena.ROCAS["cantidad"]
    dentro = [p for p in rocas if -3 <= p.GetAttribute("xformOp:translate").Get()[0] <= 33
              and -9 <= p.GetAttribute("xformOp:translate").Get()[1] <= 8]
    assert dentro == []


def test_las_rocas_salen_iguales_cada_vez(entorno):
    assert generar_escena.posiciones_rocas(entorno) == generar_escena.posiciones_rocas(entorno)


def test_sin_numpy_el_usd_sale_con_colores_planos(entorno, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "texturas", None)   # import texturas -> ImportError
    (tmp_path / "entorno.json").write_text(json.dumps(entorno), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generar_escena.py", "--dir", str(tmp_path)])
    generar_escena.main()
    assert "OmniPBR" not in (tmp_path / "escena.usd").read_text(encoding="utf-8")
    assert not (tmp_path / "texturas").exists()


# ---------- escena de entrenamiento: materiales compartidos ----------

def _stage_con_materiales(carpeta):
    pytest.importorskip("pxr")
    from pxr import Usd

    import viaz_escena

    stage = Usd.Stage.CreateInMemory()
    stage.DefinePrim("/World", "Xform")
    viaz_escena.asegurar_materiales(stage, carpeta)
    return viaz_escena, stage


def test_los_materiales_del_entrenamiento_son_los_del_demo(tmp_path):
    """La escena de entrenamiento no tiene su propia receta: usa generar_escena._aspecto, igual que escena.usd."""
    texto = generar_escena.materiales_usda(generar_escena.ASPECTOS_ENTRENAMIENTO, str(tmp_path))
    assert generar_escena._aspecto("panel", True, str(tmp_path)).replace(str(tmp_path), "./texturas") in \
        generar_escena.escena_usda(json.loads((agentes.FIXTURES / "entorno.json").read_text(encoding="utf-8")), True)
    for aspecto in generar_escena.ASPECTOS_ENTRENAMIENTO:
        assert f'def Material "Vis{aspecto.capitalize()}"' in texto
    assert f"@{tmp_path}/madera_albedo.png@" in texto and "./texturas" not in texto
    plano = generar_escena.materiales_usda(generar_escena.ASPECTOS_ENTRENAMIENTO, None)
    assert "OmniPBR" not in plano and "UsdPreviewSurface" in plano


def test_un_material_por_aspecto_y_cerros_compartidos(tmp_path):
    viaz_escena, stage = _stage_con_materiales(tmp_path)
    from pxr import UsdShade

    materiales = [p for p in stage.GetPrimAtPath("/World/Materiales").GetChildren() if p.IsA(UsdShade.Material)]
    assert sorted(p.GetName() for p in materiales) == sorted(
        f"Vis{a.capitalize()}" for a in generar_escena.ASPECTOS_ENTRENAMIENTO)
    cerros = stage.GetPrimAtPath("/World/Cerros")
    assert UsdShade.MaterialBindingAPI(cerros).ComputeBoundMaterial()[0].GetPath() == "/World/Materiales/VisCerro"
    omni = stage.GetPrimAtPath("/World/Materiales/VisMadera/Omni")
    assert omni.GetAttribute("inputs:diffuse_texture").Get().path == f"{tmp_path}/madera_albedo.png"
    n = len(list(stage.Traverse()))
    viaz_escena.asegurar_materiales(stage, tmp_path)   # las 2.ª, 3.ª... cajas no agregan nada
    assert len(list(stage.Traverse())) == n


def test_el_vidrio_cuelga_del_panel_sin_colision_ni_masa(tmp_path):
    viaz_escena, stage = _stage_con_materiales(tmp_path)
    from pxr import UsdGeom, UsdPhysics, UsdShade

    panel = stage.DefinePrim("/World/envs/env_0/Panel", "Xform")
    UsdPhysics.RigidBodyAPI.Apply(panel)
    tam = (1.13, 2.38, 0.035)
    viaz_escena.agregar_vidrio(stage, "/World/envs/env_0/Panel", tam)
    vidrio = stage.GetPrimAtPath("/World/envs/env_0/Panel/Vidrio")
    assert vidrio.GetParent() == panel
    assert not vidrio.HasAPI(UsdPhysics.CollisionAPI) and not vidrio.HasAPI(UsdPhysics.MassAPI)
    assert UsdShade.MaterialBindingAPI(vidrio).ComputeBoundMaterial()[0].GetPath() == "/World/Materiales/VisPanel"
    puntos = UsdGeom.Mesh(vidrio).GetPointsAttr().Get()
    assert {round(p[2], 6) for p in puntos} == {round(generar_escena.VIDRIO_Z * tam[2], 6)}   # sobre la cara de arriba
    assert (max(p[0] for p in puntos), max(p[1] for p in puntos)) == pytest.approx((tam[0] / 2, tam[1] / 2))


def test_la_carpeta_de_texturas_se_hace_una_vez_y_no_se_pisa(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    import texturas

    primera = texturas.asegurar(["madera"], tmp_path)
    archivos = {f.name: f.stat().st_mtime_ns for f in primera.iterdir()}
    assert set(archivos) == {"madera_albedo.png", "madera_rugosidad.png"}
    assert texturas.asegurar(["madera"], tmp_path) == primera
    assert {f.name: f.stat().st_mtime_ns for f in primera.iterdir()} == archivos
    assert [p.name for p in tmp_path.iterdir()] == [primera.name]   # sin carpetas temporales sueltas
    assert texturas.asegurar(["cielo"], tmp_path) != primera   # otros grupos, otra carpeta


def test_sin_texturas_por_variable_de_entorno(monkeypatch):
    import viaz_escena

    monkeypatch.setenv("VIAZ_SIN_TEXTURAS", "1")
    assert viaz_escena.carpeta_texturas() is None


def test_el_runner_enlaza_las_texturas_a_la_carpeta_de_cada_trabajo(tmp_path, monkeypatch):
    """Cada trabajo corre en su carpeta y solo recibe archivos sueltos: sin el enlace, escena.usd pierde las texturas."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker-gpu"))
    import runner

    monkeypatch.setenv("VIAZ_TEXTURAS", str(tmp_path / "cache"))
    monkeypatch.setattr(generar_escena, "GRUPOS_TEXTURA", ("madera",))
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    runner._enlazar_texturas(trabajo)   # sin escena.usd no hace nada
    assert not (trabajo / "texturas").exists()
    (trabajo / "escena.usd").write_text("#usda 1.0\n", encoding="utf-8")
    runner._enlazar_texturas(trabajo)
    assert (trabajo / "texturas" / "madera_albedo.png").exists() and (trabajo / "texturas").is_symlink()
    runner._enlazar_texturas(trabajo)   # idempotente
