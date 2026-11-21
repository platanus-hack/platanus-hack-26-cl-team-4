"""Escena → GLB con animación (Android Scene Viewer, WebXR y el visor web).

    python exportar_glb.py <carpeta_salida> <carpeta_texturas>

<carpeta_texturas> tiene mural.jpg y matrix.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pygltflib as gl

sys.path.insert(0, str(Path(__file__).parent))
import escena as E  # noqa: E402


class Constructor:
    def __init__(self, texturas: Path):
        self.bin = bytearray()
        self.g = gl.GLTF2(asset=gl.Asset(generator="VIAZ scripts/sala/ar"), scene=0, scenes=[gl.Scene(nodes=[])])
        self.mats: dict[str, int] = {}
        self.texturas = texturas

    def _vista(self, datos: bytes, objetivo=None) -> int:
        while len(self.bin) % 4:
            self.bin += b"\0"
        off = len(self.bin)
        self.bin += datos
        self.g.bufferViews.append(gl.BufferView(buffer=0, byteOffset=off, byteLength=len(datos), target=objetivo))
        return len(self.g.bufferViews) - 1

    def acceso(self, arr: np.ndarray, tipo: str, objetivo=None, minmax=False) -> int:
        comp = {np.dtype("f4"): gl.FLOAT, np.dtype("u4"): gl.UNSIGNED_INT}[arr.dtype]
        v = self._vista(arr.tobytes(), objetivo)
        a = gl.Accessor(bufferView=v, componentType=comp, count=len(arr), type=tipo)
        if minmax:
            a.min, a.max = np.atleast_1d(arr.min(0)).tolist(), np.atleast_1d(arr.max(0)).tolist()
        self.g.accessors.append(a)
        return len(self.g.accessors) - 1

    def textura(self, archivo: str) -> int:
        f = self.texturas / archivo
        v = self._vista(f.read_bytes())
        self.g.images.append(gl.Image(bufferView=v, mimeType="image/png" if f.suffix == ".png" else "image/jpeg"))
        self.g.samplers.append(gl.Sampler(magFilter=gl.LINEAR, minFilter=gl.LINEAR_MIPMAP_LINEAR))
        self.g.textures.append(gl.Texture(source=len(self.g.images) - 1, sampler=len(self.g.samplers) - 1))
        return len(self.g.textures) - 1

    def material(self, nombre: str) -> int:
        if nombre in self.mats:
            return self.mats[nombre]
        d = E.MATERIALES[nombre]
        pbr = gl.PbrMetallicRoughness(baseColorFactor=[*d["color"], 1.0], metallicFactor=d["metal"], roughnessFactor=d["rugosidad"])
        m = gl.Material(name=nombre, pbrMetallicRoughness=pbr, emissiveFactor=list(d.get("emision", (0, 0, 0))))
        if "textura" in d:
            tex = self.textura(d["textura"])
            pbr.baseColorTexture = gl.TextureInfo(index=tex)
            if d.get("emision_textura"):
                m.emissiveTexture = gl.TextureInfo(index=tex)
                m.emissiveFactor = [1.0, 1.0, 1.0]
        if d.get("transparente"):
            m.alphaMode = gl.BLEND
        if d.get("doble_cara"):
            m.doubleSided = True
        self.g.materials.append(m)
        self.mats[nombre] = len(self.g.materials) - 1
        return self.mats[nombre]

    def malla(self, grupos: dict[str, E.Malla]) -> int:
        prims = []
        for nombre, m in grupos.items():
            if not m.pos:
                continue
            p, n, uv, i = m.arrays()
            prims.append(gl.Primitive(
                attributes=gl.Attributes(POSITION=self.acceso(p, "VEC3", gl.ARRAY_BUFFER, True),
                                         NORMAL=self.acceso(n, "VEC3", gl.ARRAY_BUFFER),
                                         TEXCOORD_0=self.acceso(uv, "VEC2", gl.ARRAY_BUFFER)),
                indices=self.acceso(i, "SCALAR", gl.ELEMENT_ARRAY_BUFFER), material=self.material(nombre)))
        self.g.meshes.append(gl.Mesh(primitives=prims))
        return len(self.g.meshes) - 1

    def nodo(self, n: E.Nodo, canales: list, muestras: list) -> int:
        hijos = [self.nodo(h, canales, muestras) for h in n.hijos]
        kw = {"name": n.nombre}
        if n.mallas:
            kw["mesh"] = self.malla(n.mallas)
        if hijos:
            kw["children"] = hijos
        # pose de reposo (cuadro 0) también como valor fijo: Scene Viewer y model-viewer miden el objeto con ella
        pose = E.pose_inicial(n)
        if any(pose["t"]):
            kw["translation"] = list(pose["t"])
        if pose["q"] != (0.0, 0.0, 0.0, 1.0):
            kw["rotation"] = list(pose["q"])
        if pose["s"] != 1.0:
            kw["scale"] = [pose["s"]] * 3
        self.g.nodes.append(gl.Node(**kw))
        idx = len(self.g.nodes) - 1
        for clave, claves in n.pistas.items():
            ruta, tipo, conv = {
                "t": ("translation", "VEC3", lambda v: v),
                "ry": ("rotation", "VEC4", E.quat_y),
                "rx": ("rotation", "VEC4", E.quat_x),
                "s": ("scale", "VEC3", lambda v: (v, v, v)),
            }[clave]
            t = np.array([k[0] for k in claves], "f4")
            v = np.array([conv(k[1]) for k in claves], "f4")
            muestras.append(gl.AnimationSampler(input=self.acceso(t, "SCALAR", minmax=True), output=self.acceso(v, tipo),
                                                interpolation="LINEAR"))
            canales.append(gl.AnimationChannel(sampler=len(muestras) - 1, target=gl.AnimationChannelTarget(node=idx, path=ruta)))
        return idx


def exportar(variante: str, salida: Path, texturas: Path) -> Path:
    raiz, _ = E.construir(variante)
    c = Constructor(texturas)
    canales, muestras = [], []
    idx = c.nodo(raiz, canales, muestras)
    c.g.nodes[idx].scale = [E.VARIANTES[variante]["escala"]] * 3
    c.g.scenes[0].nodes = [idx]
    c.g.animations.append(gl.Animation(name="entrega_cafe", samplers=muestras, channels=canales))
    c.g.buffers.append(gl.Buffer(byteLength=len(c.bin)))
    c.g.set_binary_blob(bytes(c.bin))
    destino = salida / f"{variante}.glb"
    c.g.save_binary(str(destino))
    return destino


if __name__ == "__main__":
    out, tex = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for v in E.VARIANTES:
        f = exportar(v, out, tex)
        print(f, f.stat().st_size // 1024, "KB")
