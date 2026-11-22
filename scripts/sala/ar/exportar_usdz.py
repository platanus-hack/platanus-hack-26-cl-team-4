"""Escena → USDZ con animación (iPhone, AR Quick Look).

    python exportar_usdz.py <carpeta_salida> <carpeta_texturas>

<carpeta_texturas> tiene mural.jpg y matrix.png. La animación se guarda como muestras de tiempo a 30 cuadros/s.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

sys.path.insert(0, str(Path(__file__).parent))
import escena as E  # noqa: E402

FPS = 30


def material(stage, nombre: str, cache: dict) -> UsdShade.Material:
    if nombre in cache:
        return cache[nombre]
    d = E.MATERIALES[nombre]
    base = f"/viaz/Materiales/{nombre}"
    m = UsdShade.Material.Define(stage, base)
    s = UsdShade.Shader.Define(stage, f"{base}/Superficie")
    s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(d["rugosidad"])
    s.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(d["metal"])
    if "emision" in d:
        s.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*d["emision"]))
    if "opacidad" in d:
        s.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(d["opacidad"])
    if "textura" in d:
        st = UsdShade.Shader.Define(stage, f"{base}/LectorST")
        st.CreateIdAttr("UsdPrimvarReader_float2")
        st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        tex = UsdShade.Shader.Define(stage, f"{base}/Textura")
        tex.CreateIdAttr("UsdUVTexture")
        tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(d["textura"])
        tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st.ConnectableAPI(), "result")
        tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
        if d.get("emision_textura"):
            s.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
        if d.get("transparente"):
            tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
            s.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "a")
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
        if E.MATERIALES[nombre].get("doble_cara"):
            g.CreateDoubleSidedAttr(True)
        api = UsdGeom.PrimvarsAPI(g)
        api.CreatePrimvar("normals", Sdf.ValueTypeNames.Normal3fArray, UsdGeom.Tokens.vertex).Set(Vt.Vec3fArray.FromNumpy(n))
        if "textura" in E.MATERIALES[nombre]:
            api.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray.FromNumpy(uv))
        g.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*p.min(0).tolist()), Gf.Vec3f(*p.max(0).tolist())]))
        UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(material(stage, nombre, cache))


def nodo(stage, padre: str, n: E.Nodo, cache: dict, cuadros: int):
    ruta = f"{padre}/{n.nombre}"
    x = UsdGeom.Xform.Define(stage, ruta)
    pose = E.pose_inicial(n)   # pose de reposo (cuadro 0) también como valor por defecto, para cualquier visor
    op_t = x.AddTranslateOp()
    op_t.Set(Gf.Vec3d(*pose["t"]))
    if "t" in n.pistas:
        for k in range(cuadros + 1):
            op_t.Set(Gf.Vec3d(*E.muestrear(n.pistas["t"], k / FPS)), k)
    for clave, conv in (("ry", E.quat_y), ("rx", E.quat_x)):
        if clave in n.pistas:
            op = x.AddOrientOp()
            qx, qy, qz, qw = pose["q"]
            op.Set(Gf.Quatf(qw, qx, qy, qz))
            for k in range(cuadros + 1):
                qx, qy, qz, qw = conv(E.muestrear(n.pistas[clave], k / FPS))
                op.Set(Gf.Quatf(qw, qx, qy, qz), k)
    if "s" in n.pistas:
        op = x.AddScaleOp()
        op.Set(Gf.Vec3f(*E.escala3(pose["s"])))
        for k in range(cuadros + 1):
            op.Set(Gf.Vec3f(*E.escala3(E.muestrear(n.pistas["s"], k / FPS))), k)
    if n.mallas:
        mallas(stage, ruta, n.mallas, cache)
    for h in n.hijos:
        nodo(stage, ruta, h, cache, cuadros)


def exportar(variante: str, salida: Path, texturas: Path) -> Path:
    raiz, fin = E.construir(variante)
    tmp = Path(tempfile.mkdtemp())
    for nombre in sorted({m["textura"] for m in E.MATERIALES.values() if "textura" in m}):
        shutil.copyfile(texturas / nombre, tmp / nombre)
    capa = tmp / f"{variante}.usdc"
    stage = Usd.Stage.CreateNew(str(capa))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    cuadros = int(round(fin * FPS))
    # raíz con la escala de la variante; los hijos cuelgan de ella
    r = UsdGeom.Xform.Define(stage, "/viaz")
    stage.SetDefaultPrim(r.GetPrim())
    r.AddScaleOp().Set(Gf.Vec3f(E.VARIANTES[variante]["escala"]))
    cache: dict = {}
    for h in raiz.hijos:
        nodo(stage, "/viaz", h, cache, cuadros)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(cuadros)
    stage.SetTimeCodesPerSecond(FPS)
    stage.SetFramesPerSecond(FPS)
    stage.GetRootLayer().Save()
    destino = salida / f"{variante}.usdz"
    if not UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(str(capa)), str(destino)):
        raise RuntimeError("no pude crear el usdz")
    return destino


if __name__ == "__main__":
    out, tex = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for v in sys.argv[3:] or E.VARIANTES:   # opcional: solo algunas variantes (p. ej. robot maqueta)
        f = exportar(v, out, tex)
        print(f, f.stat().st_size // 1024, "KB")
