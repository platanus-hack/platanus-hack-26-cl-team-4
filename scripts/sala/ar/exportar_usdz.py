"""Escena → USDZ con animación (iPhone, AR Quick Look).

    python exportar_usdz.py <carpeta_salida> <mural.jpg>

Animación por muestras de tiempo (timeSamples) en traslación y rotación, a 30 cuadros por segundo.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

sys.path.insert(0, str(Path(__file__).parent))
import escena as E  # noqa: E402

FPS = 30


def material(stage, nombre: str, cache: dict) -> UsdShade.Material:
    if nombre in cache:
        return cache[nombre]
    d = E.MATERIALES[nombre]
    m = UsdShade.Material.Define(stage, f"/viaz/Materiales/{nombre}")
    s = UsdShade.Shader.Define(stage, f"/viaz/Materiales/{nombre}/Superficie")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(d["rugosidad"])
    s.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(d["metal"])
    if "emision" in d:
        s.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*d["emision"]))
    if "textura" in d:
        st = UsdShade.Shader.Define(stage, f"/viaz/Materiales/{nombre}/LectorST")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        tex = UsdShade.Shader.Define(stage, f"/viaz/Materiales/{nombre}/Textura")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(d["textura"])
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
    else:
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*d["color"]))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface")
    cache[nombre] = m
    return m


def mallas(stage, ruta: str, grupos: dict, cache: dict):
    for nombre, m in grupos.items():
        if not m.pos:
            continue
        p, n, uv, i = m.arrays()
        g = UsdGeom.Mesh.Define(stage, f"{ruta}/{nombre}")
        g.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(p))
        g.CreateFaceVertexCountsAttr(Vt.IntArray([3] * (len(i) // 3)))
        g.CreateFaceVertexIndicesAttr(Vt.IntArray(i.astype(int).tolist()))
        g.CreateSubdivisionSchemeAttr("none")
        g.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
        nv = UsdGeom.PrimvarsAPI(g).CreatePrimvar("normals", Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.vertex)
        nv.Set(Vt.Vec3fArray.FromNumpy(n))
        st = UsdGeom.PrimvarsAPI(g).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
        st.Set(Vt.Vec2fArray.FromNumpy(uv))
        g.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*p.min(0).tolist()), Gf.Vec3f(*p.max(0).tolist())]))
        UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(material(stage, nombre, cache))


def exportar(variante: str, salida: Path, mural: Path) -> Path:
    cfg = E.VARIANTES[variante]
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(mural, tmp / "mural.jpg")
    usda = tmp / f"{variante}.usdc"
    stage = Usd.Stage.CreateNew(str(usda))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    raiz = UsdGeom.Xform.Define(stage, "/viaz")
    stage.SetDefaultPrim(raiz.GetPrim())
    raiz.AddScaleOp().Set(Gf.Vec3f(cfg["escala"]))
    cache: dict = {}
    if cfg["sala"]:
        UsdGeom.Xform.Define(stage, "/viaz/Sala")
        mallas(stage, "/viaz/Sala", E.sala(), cache)

    robot = UsdGeom.Xform.Define(stage, "/viaz/Robot")
    op_t, op_r = robot.AddTranslateOp(), robot.AddOrientOp()
    mallas(stage, "/viaz/Robot", E.robot_cuerpo(), cache)
    brazo = UsdGeom.Xform.Define(stage, "/viaz/Robot/Brazo")
    brazo.AddTranslateOp().Set(Gf.Vec3d(*E.BRAZO_PIVOTE))
    op_b = brazo.AddOrientOp()
    mallas(stage, "/viaz/Robot/Brazo", E.robot_brazo(), cache)

    tr, rot, br = E.animacion(cfg["z_ini"], cfg["z_fin"], cfg.get("x", E.PASILLO_X))
    fin = tr[-1][0]
    n = int(round(fin * FPS))
    for k in range(n + 1):
        t = k / FPS
        op_t.Set(Gf.Vec3d(*E.muestrear(tr, t)), k)
        qx, qy, qz, qw = E.quat_y(E.muestrear(rot, t))
        op_r.Set(Gf.Quatf(qw, qx, qy, qz), k)
        qx, qy, qz, qw = E.quat_x(E.muestrear(br, t))
        op_b.Set(Gf.Quatf(qw, qx, qy, qz), k)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(n)
    stage.SetTimeCodesPerSecond(FPS)
    stage.SetFramesPerSecond(FPS)
    stage.GetRootLayer().Save()

    destino = salida / f"{variante}.usdz"
    if not UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(str(usda)), str(destino)):
        raise RuntimeError("no pude crear el usdz")
    return destino


if __name__ == "__main__":
    out, mural = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for v in E.VARIANTES:
        f = exportar(v, out, mural)
        print(f, f.stat().st_size // 1024, "KB")
