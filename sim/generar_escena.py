"""Genera escena.usd (texto USDA) desde entorno.json: el terreno completo del parque. Python puro.

    python sim/generar_escena.py --dir <carpeta con entorno.json>

Es el primer paso del ciclo: el runner lo corre con el Python del sistema, sin Isaac ni paquetes extra.

Qué lleva:
- /World/Planta: suelo, tubos de torsión y postes, con colisión y material de fricción. Sin masa:
  un colisionador sin RigidBodyAPI es fijo e inamovible.
- /World/Visual: lo que solo se ve (RF-MAP-13, RF-MAP-15). Paneles ya instalados de las filas 1 en adelante,
  el llano del desierto y los cerros lejanos. Sin colisión.
- /World/Visual también lleva las rocas sueltas (RF-MAP-15), sin colisión.
- /World/Luces: sol y cielo despejado de gran altura.
Texturas: texturas.py las escribe en texturas/, al lado de escena.usd, y los materiales las citan con ruta relativa
(la carpeta de la corrida queda autocontenida). Sin numpy o PIL el USD sale con colores planos.
Qué NO lleva: nada del robot (el terreno no sabe qué robot viene después), los paneles con masa
(los agrega sim/viaz_escena.py en Isaac Lab) ni PhysicsScene (la crea Isaac Lab con sim/fisica.py).

Reglas (iguales a web/lib/escena.ts): Z arriba, metros. Fila i: tubo en y = -i * separacion,
a altura_m, de x = 0 a x = largo_m, con postes cada 7 m.

Espacios que no son parque_solar (sala, bodega, taller...): escena_generica_usda() arma el suelo, las paredes si
espacio.interior, y cada elemento de entorno.json como caja o cilindro. Origen en una esquina del espacio; X a lo largo,
Y a lo ancho; posicion_m es el centro de la cara inferior. Un elemento fijo es un colisionador inamovible; uno no fijo
con masa_kg es un cuerpo rígido. Las aberturas (puertas, ventanas) no llevan colisión ni cortan la pared. [Por hacer]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))
import fisica  # noqa: E402
import plan  # noqa: E402

POSTE_CADA_M = 7.0
POSTE_LADO_M = 0.15
TUBO_LADO_M = 0.1
MARGEN_SUELO_M = 10.0       # el suelo con colisión sobra 10 m por cada lado del parque

COLOR_SUELO = (0.60, 0.42, 0.26)   # tierra ocre
COLOR_TUBO = (0.55, 0.57, 0.6)
COLOR_POSTE = (0.45, 0.47, 0.5)
COLOR_PANEL = (0.05, 0.1, 0.35)
COLOR_CERRO = (0.48, 0.33, 0.22)
COLOR_MARCO = (0.55, 0.57, 0.60)   # aluminio anodizado
COLOR_ROCA = (0.42, 0.36, 0.31)
COLOR_MADERA = (0.69, 0.53, 0.36)   # pino de pallet
# Aspecto plano de cada superficie (color, rugosidad, metal): es el USD sin texturas y el color de respaldo en visores simples.
# Solo se ve: la física va en fisica.MATERIALES.
ASPECTOS = {
    "tierra": (COLOR_SUELO, 1.0, 0.0),
    "cerro": (COLOR_CERRO, 1.0, 0.0),
    "tubo": (COLOR_TUBO, 0.5, 0.6),
    "poste": (COLOR_POSTE, 0.5, 0.6),
    "panel": (COLOR_PANEL, 0.25, 0.3),
    "marco": (COLOR_MARCO, 0.35, 0.9),
    "roca": (COLOR_ROCA, 0.9, 0.0),
    "madera": (COLOR_MADERA, 0.8, 0.0),
    # Espacios genéricos (escena_generica_usda): un aspecto por categoría de elemento, más piso y pared.
    "piso": ((0.62, 0.60, 0.56), 0.8, 0.0),
    "pared": ((0.85, 0.85, 0.82), 0.9, 0.0),
    "estructura": ((0.55, 0.57, 0.60), 0.5, 0.6),
    "maquina": ((0.45, 0.50, 0.55), 0.5, 0.5),
    "mueble": ((0.60, 0.45, 0.30), 0.8, 0.0),
    "superficie_trabajo": ((0.70, 0.55, 0.35), 0.7, 0.0),
    "contenedor": ((0.30, 0.45, 0.60), 0.6, 0.0),
    "objeto_manipulable": ((0.85, 0.60, 0.20), 0.7, 0.0),
    "obstaculo": ((0.70, 0.30, 0.25), 0.8, 0.0),
    "abertura": ((0.40, 0.30, 0.20), 0.8, 0.0),
    "otro": ((0.60, 0.60, 0.60), 0.8, 0.0),
}
CATEGORIAS = ("estructura", "maquina", "mueble", "superficie_trabajo", "contenedor", "objeto_manipulable",
              "obstaculo", "abertura", "otro")
MATERIAL_CATEGORIA = {"estructura": "acero", "maquina": "acero"}   # el resto: "objeto" (fisica.MATERIALES)
PARED_ESPESOR_M = 0.1
ALTO_PARED_SIN_TECHO_M = 2.5
TEXTURAS_DIR = "texturas"
RAW = 'colorSpace = "raw"'    # normales, rugosidad y metal son datos: sin esto Isaac los lee como color sRGB
# Metal del acero y del marco. Con 0,85 el acero a la sombra solo refleja el cielo y la cámara de Isaac lo ve azul marino
# (medido en el pod, 2026-11-21); con 0,35 se ve gris zinc, como en la referencia del demo.
METAL_ACERO = 0.35
# Material con texturas por aspecto: qué mapas lleva y cada cuántos metros se repite. Los de proyección van
# en coordenadas del mundo (los cubos no traen UV). OmniPBR viene con Isaac Sim: funciona sin red.
MATERIALES_TEXTURA = {
    "tierra": {"albedo": "suelo_albedo", "normal": "suelo_normal", "rugosidad": "suelo_rugosidad",
               "repite_m": 12.0, "especular": 0.2},
    "cerro": {"albedo": "cerro_albedo", "rugosidad_const": 0.95, "especular": 0.1},
    "tubo": {"albedo": "acero_albedo", "rugosidad": "acero_rugosidad", "repite_m": 0.8, "metal": METAL_ACERO},
    "poste": {"albedo": "acero_albedo", "rugosidad": "acero_rugosidad", "repite_m": 0.8, "metal": METAL_ACERO},
    "panel": {"albedo": "panel_albedo", "rugosidad": "panel_rugosidad", "metal_mapa": "panel_metal", "especular": 0.5},
    "marco": {"color": (0.55, 0.57, 0.60), "rugosidad_const": 0.35, "metal": METAL_ACERO},
    "roca": {"albedo": "roca_albedo", "rugosidad_const": 0.9, "repite_m": 1.0, "especular": 0.25},
    "madera": {"albedo": "madera_albedo", "rugosidad": "madera_rugosidad", "repite_m": 1.2},
}
# Qué materiales y qué grupos de texturas lleva cada escena. La del entrenamiento (viaz_escena.py) no tiene cerros ni rocas.
ASPECTOS_ESCENA = ("tierra", "cerro", "tubo", "poste", "panel", "marco", "roca")
GRUPOS_TEXTURA = ("suelo", "cerro", "acero", "panel", "roca", "cielo")
ASPECTOS_ENTRENAMIENTO = ("tierra", "cerro", "tubo", "poste", "panel", "marco", "madera")
GRUPOS_TEXTURA_ENTRENAMIENTO = ("suelo", "cerro", "acero", "panel", "madera", "cielo")
RAIZ_MATERIALES = "/World/Materiales"
RUTA_CERROS = "/World/Cerros"       # en la escena de entrenamiento; en escena.usd están en /World/Visual/Cerros
VIDRIO_Z = 0.5 + 0.025      # cara del vidrio sobre el centro del cubo unitario del panel (el cubo llega a 0,5)

# Solo apariencia. Sol a 45° de elevación del lado +X: sombras que se leen bien. Luz de gran altura: dura y cálida.
SOL = {"intensidad": 2000.0, "angulo_grados": 0.53, "color": (1.0, 0.93, 0.80), "rotacion_xyz_grados": (0.0, 45.0, 0.0)}
CIELO = {"intensidad": 1100.0, "color": (0.55, 0.72, 0.95)}
LLANO_LADO_M = 4000.0   # el llano llega a 2 km: los cerros (radio 1,5 km) se paran sobre él
CERROS = {"radio_m": 1500.0, "ancho_m": 700.0, "alto_m": 55.0, "segmentos": 144}   # lejos y bajos: ~8 % del cuadro
ROCAS = {"cantidad": 90, "semilla": 7, "modelos": 6, "libre_m": 3.0, "libre_pasillo_m": 8.0, "radio_max_m": 140.0}


def cuerpos(entorno: dict) -> list[dict]:
    """Cuerpos fijos con colisión: suelo, y por cada fila un tubo y sus postes.

    Es la única definición de la geometría de la planta. escena_usda() la escribe en el USD
    y viaz_escena.describir_entrenamiento() la recorta para la escena de entrenamiento.
    """
    f, e = entorno["filas"], entorno["estructura"]
    largo, sep, alto = f["largo_m"], f["separacion_m"], e["altura_m"]
    # Suelo plano en z = 0. La pendiente de entorno.json todavía NO se modela: la base del robot
    # se mueve a z = 0 y el plan supone suelo plano. [Por hacer] suelo inclinado + base que siga el terreno.
    lista = [{"nombre": "Suelo", "centro": (largo / 2, -sep * (f["cantidad"] - 1) / 2, -0.05),
              "tam": (largo + 2 * MARGEN_SUELO_M, sep * f["cantidad"] + 2 * MARGEN_SUELO_M, 0.1),
              "aspecto": "tierra", "material": "suelo"}]
    alto_poste = alto - TUBO_LADO_M / 2
    for i in range(f["cantidad"]):
        y = -i * sep
        lista.append({"nombre": f"Fila{i}_Tubo", "centro": (largo / 2, y, alto), "tam": (largo, TUBO_LADO_M, TUBO_LADO_M),
                      "aspecto": "tubo", "material": "acero"})
        for j in range(int(largo // POSTE_CADA_M) + 1):
            lista.append({"nombre": f"Fila{i}_Poste{j}", "centro": (min(j * POSTE_CADA_M, largo), y, alto_poste / 2),
                          "tam": (POSTE_LADO_M, POSTE_LADO_M, alto_poste), "aspecto": "poste", "material": "acero"})
    return lista


def paneles_visuales(entorno: dict) -> list[dict]:
    """Paneles ya instalados de las filas 1 en adelante. La fila 0 queda vacía: ahí instala el robot."""
    p, sep = entorno["panel"], entorno["filas"]["separacion_m"]
    tam = (p["ancho_m"], p["largo_m"], fisica.PANEL_ESPESOR_M)
    slots = plan.slots(entorno, plan.caben(entorno))
    return [{"nombre": f"Fila{i}_Panel{k}", "centro": (s[0], -i * sep, s[2]), "tam": tam, "aspecto": "panel"}
            for i in range(1, entorno["filas"]["cantidad"]) for k, s in enumerate(slots)]


def _vec(v) -> str:
    return ", ".join(f"{x:.4f}" for x in v)


def _material(nombre: str, m: dict) -> str:
    return f'''
        def Material "{nombre.capitalize()}" (
            prepend apiSchemas = ["PhysicsMaterialAPI"]
        )
        {{
            float physics:staticFriction = {m["estatica"]}
            float physics:dynamicFriction = {m["dinamica"]}
            float physics:restitution = {m["restitucion"]}
        }}'''


def ruta_material(aspecto: str) -> str:
    """Ruta USD del material visual de un aspecto. Las dos escenas lo ponen en el mismo lugar."""
    return f"{RAIZ_MATERIALES}/Vis{aspecto.capitalize()}"


def _ruta_textura(nombre: str, base: str = f"./{TEXTURAS_DIR}") -> str:
    return f"{base}/{nombre}.png"


def _entradas_omnipbr(spec: dict, base: str = f"./{TEXTURAS_DIR}") -> str:
    """Entradas del shader OmniPBR. Con "repite_m" proyecta la textura desde el mundo (1 repetición cada repite_m)."""
    e = []
    if "albedo" in spec:
        e.append(f"asset inputs:diffuse_texture = @{_ruta_textura(spec['albedo'], base)}@")
    if "color" in spec:
        e.append(f"color3f inputs:diffuse_color_constant = ({_vec(spec['color'])})")
    if "normal" in spec:
        e.append(f"asset inputs:normalmap_texture = @{_ruta_textura(spec['normal'], base)}@ ({RAW})")
        e.append("float inputs:bump_factor = 1.0")
    if "rugosidad" in spec:
        e.append(f"asset inputs:reflectionroughness_texture = @{_ruta_textura(spec['rugosidad'], base)}@ ({RAW})")
        e.append("float inputs:reflection_roughness_texture_influence = 1.0")
    if "rugosidad_const" in spec:
        e.append(f"float inputs:reflection_roughness_constant = {spec['rugosidad_const']}")
    e.append(f"float inputs:metallic_constant = {spec.get('metal', 0.0)}")
    if "metal_mapa" in spec:
        e.append(f"asset inputs:metallic_texture = @{_ruta_textura(spec['metal_mapa'], base)}@ ({RAW})")
        e.append("float inputs:metallic_texture_influence = 1.0")
    e.append(f"float inputs:specular_level = {spec.get('especular', 0.5)}")
    if "repite_m" in spec:
        k = 1.0 / spec["repite_m"]
        e += ["bool inputs:project_uvw = 1", "bool inputs:world_or_object = 1",
              f"float2 inputs:texture_scale = ({k:.6f}, {k:.6f})"]
    return "\n                ".join(e)


def _aspecto(nombre: str, con_texturas: bool, base: str = f"./{TEXTURAS_DIR}") -> str:
    """Material visual. Con texturas: OmniPBR (Isaac Sim) y, de respaldo para otros visores, un UsdPreviewSurface plano.

    base: carpeta de las texturas en el USD. "./texturas" cuando el PNG está al lado de escena.usd.
    """
    color, rugosidad, metal = ASPECTOS[nombre]
    ruta = ruta_material(nombre)
    plano = f'''
            def Shader "Shader"
            {{
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = ({_vec(color)})
                float inputs:roughness = {rugosidad}
                float inputs:metallic = {metal}
                token outputs:surface
            }}'''
    if not con_texturas or nombre not in MATERIALES_TEXTURA:
        return f'''
        def Material "Vis{nombre.capitalize()}"
        {{
            token outputs:surface.connect = <{ruta}/Shader.outputs:surface>
{plano}
        }}'''
    return f'''
        def Material "Vis{nombre.capitalize()}"
        {{
            token outputs:surface.connect = <{ruta}/Shader.outputs:surface>
            token outputs:mdl:surface.connect = <{ruta}/Omni.outputs:out>
            token outputs:mdl:displacement.connect = <{ruta}/Omni.outputs:out>
            token outputs:mdl:volume.connect = <{ruta}/Omni.outputs:out>
{plano}

            def Shader "Omni"
            {{
                uniform token info:implementationSource = "sourceAsset"
                uniform asset info:mdl:sourceAsset = @OmniPBR.mdl@
                uniform token info:mdl:sourceAsset:subIdentifier = "OmniPBR"
                {_entradas_omnipbr(MATERIALES_TEXTURA[nombre], base)}
                token outputs:out (
                    renderType = "material"
                )
            }}
        }}'''


def _vidrio(con_texturas: bool) -> str:
    """Cara superior del panel: un cuadrito con UV, 2,5 cm sobre el cubo. Lleva las celdas; el cubo queda de marco."""
    z = VIDRIO_Z
    return f'''
        def Mesh "Vidrio" (
            prepend apiSchemas = ["MaterialBindingAPI"]
        )
        {{
            int[] faceVertexCounts = [4]
            int[] faceVertexIndices = [0, 1, 2, 3]
            point3f[] points = [(-0.5, -0.5, {z}), (0.5, -0.5, {z}), (0.5, 0.5, {z}), (-0.5, 0.5, {z})]
            normal3f[] normals = [(0, 0, 1), (0, 0, 1), (0, 0, 1), (0, 0, 1)] (
                interpolation = "vertex"
            )
            texCoord2f[] primvars:st = [(0, 0), (1, 0), (1, 1), (0, 1)] (
                interpolation = "vertex"
            )
            uniform token subdivisionScheme = "none"
            rel material:binding = </World/Materiales/VisPanel>
        }}'''


def _cubo(c: dict, con_texturas: bool = False) -> str:
    """Un cubo. Con "material" lleva colisión y fricción. Sin "material" solo se ve.

    Con texturas, el panel es un marco de aluminio (el cubo) con el vidrio de celdas encima, y el suelo con colisión
    no se dibuja: el llano, a ras con él, es el único suelo que se ve.
    """
    fisico = "material" in c
    apis = '"PhysicsCollisionAPI", "MaterialBindingAPI"' if fisico else '"MaterialBindingAPI"'
    binding = f'''
        rel material:binding:physics = </World/Materiales/{c["material"].capitalize()}>''' if fisico else ""
    panel = con_texturas and c["aspecto"] == "panel"
    aspecto = "marco" if panel else c["aspecto"]
    oculto = '\n        token visibility = "invisible"' if con_texturas and c["nombre"] == "Suelo" else ""
    return f'''
    def Cube "{c["nombre"]}" (
        prepend apiSchemas = [{apis}]
    )
    {{
        double size = 1
        double3 xformOp:translate = ({_vec(c["centro"])})
        float3 xformOp:scale = ({_vec(c["tam"])})
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        color3f[] primvars:displayColor = [({_vec(ASPECTOS[c["aspecto"]][0])})]
        rel material:binding = </World/Materiales/Vis{aspecto.capitalize()}>{binding}{oculto}{_vidrio(con_texturas) if panel else ""}
    }}'''


def _alto_cerro(angulo: float) -> float:
    """Perfil de la cresta: suma de senos fija, entre 0,35 y 1 del alto máximo. Sin azar: el USD es reproducible."""
    s = 0.5 * math.sin(3 * angulo + 0.7) + 0.3 * math.sin(7 * angulo + 2.1) + 0.2 * math.sin(13 * angulo + 4.0)
    return CERROS["alto_m"] * (0.675 + 0.325 * s)


def _cerros(centro_xy: tuple[float, float]) -> str:
    """Cordón de cerros alrededor del parque: una malla en anillo (pie interior, cresta, pie exterior)."""
    n, r, w = CERROS["segmentos"], CERROS["radio_m"], CERROS["ancho_m"]
    puntos = []
    for radio, con_alto in ((r - w / 2, False), (r, True), (r + w / 2, False)):
        for k in range(n):
            a = 2 * math.pi * k / n
            puntos.append((centro_xy[0] + radio * math.cos(a), centro_xy[1] + radio * math.sin(a),
                           _alto_cerro(a) if con_alto else 0.0))
    caras, uvs = [], []
    for anillo in range(2):
        v0, v1 = float(anillo), float(1 - anillo)   # u da la vuelta al anillo; v: 0 en el pie, 1 en la cresta
        for k in range(n):
            a, b = anillo * n + k, anillo * n + (k + 1) % n
            caras.append((a, b, b + n, a + n))
            uvs += [(k / n, v0), ((k + 1) / n, v0), ((k + 1) / n, v1), (k / n, v1)]
    return f'''
    def Mesh "Cerros" (
        prepend apiSchemas = ["MaterialBindingAPI"]
    )
    {{
        int[] faceVertexCounts = [{", ".join("4" for _ in caras)}]
        int[] faceVertexIndices = [{", ".join(str(i) for c in caras for i in c)}]
        point3f[] points = [{", ".join(f"({x:.1f}, {y:.1f}, {z:.1f})" for x, y, z in puntos)}]
        texCoord2f[] primvars:st = [{", ".join(f"({u:.5f}, {v:.1f})" for u, v in uvs)}] (
            interpolation = "faceVarying"
        )
        uniform token subdivisionScheme = "none"
        uniform bool doubleSided = 1
        color3f[] primvars:displayColor = [({_vec(COLOR_CERRO)})]
        rel material:binding = </World/Materiales/VisCerro>
    }}'''


def _modelo_roca(k: int) -> str:
    """Una roca de 1 m de diámetro: esfera con la cresta torcida por senos, base plana y UV esféricos.

    Hay ROCAS["modelos"] formas. Cada una sale de su propia semilla: el USD es reproducible.
    """
    r = random.Random(ROCAS["semilla"] * 100 + k)
    fase = [r.uniform(0, 6.28) for _ in range(4)]
    achatar, ancho = r.uniform(0.5, 0.85), r.uniform(0.75, 1.0)
    anillos, segmentos = 8, 12
    pts, uvs = [(0.0, 0.0, 0.5 * achatar)], [(0.5, 1.0)]
    for i in range(1, anillos):
        th = math.pi * i / anillos
        for j in range(segmentos + 1):
            ph = 2 * math.pi * (j % segmentos) / segmentos
            f = (1 + 0.20 * math.sin(2 * ph + fase[0] + 1.5 * th) + 0.12 * math.sin(3 * th + fase[1]) * math.cos(ph + fase[2])
                 + 0.07 * math.sin(5 * ph + fase[3] - 2 * th))
            x, y, z = 0.5 * f * math.sin(th) * math.cos(ph), 0.5 * f * ancho * math.sin(th) * math.sin(ph), 0.5 * f * achatar * math.cos(th)
            pts.append((x, y, max(z, -0.22)))
            uvs.append((j / segmentos, 1 - i / anillos))
    pts.append((0.0, 0.0, -0.22))
    uvs.append((0.5, 0.0))
    sur, norte = len(pts) - 1, 0
    ancho_anillo = segmentos + 1
    idx = lambda i, j: 1 + (i - 1) * ancho_anillo + j   # noqa: E731
    caras = [(norte, idx(1, j + 1), idx(1, j)) for j in range(segmentos)]
    for i in range(1, anillos - 1):
        caras += [(idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)) for j in range(segmentos)]
    caras += [(sur, idx(anillos - 1, j), idx(anillos - 1, j + 1)) for j in range(segmentos)]
    normales = [[0.0, 0.0, 0.0] for _ in pts]
    final = []
    for cara in caras:
        a, b, c = (pts[cara[0]], pts[cara[1]], pts[cara[2]])
        n = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]),
             (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        centro = [sum(pts[v][e] for v in cara) / len(cara) for e in range(3)]
        if sum(n[e] * centro[e] for e in range(3)) < 0:   # apunta hacia adentro: da vuelta la cara
            cara = cara[::-1]
            n = tuple(-v for v in n)
        final.append(cara)
        for v in cara:
            for e in range(3):
                normales[v][e] += n[e]
    for v, n in enumerate(normales):
        largo = math.sqrt(sum(e * e for e in n)) or 1.0
        normales[v] = [e / largo for e in n]
    return f'''
            def Xform "Modelo_{k}"
            {{
                def Mesh "Malla" (
                    prepend apiSchemas = ["MaterialBindingAPI"]
                )
                {{
                    int[] faceVertexCounts = [{", ".join(str(len(c)) for c in final)}]
                    int[] faceVertexIndices = [{", ".join(str(i) for c in final for i in c)}]
                    point3f[] points = [{", ".join(f"({x:.4f}, {y:.4f}, {z:.4f})" for x, y, z in pts)}]
                    normal3f[] normals = [{", ".join(f"({x:.3f}, {y:.3f}, {z:.3f})" for x, y, z in normales)}] (
                        interpolation = "vertex"
                    )
                    texCoord2f[] primvars:st = [{", ".join(f"({u:.3f}, {v:.3f})" for u, v in uvs)}] (
                        interpolation = "vertex"
                    )
                    uniform token subdivisionScheme = "none"
                    color3f[] primvars:displayColor = [({_vec(COLOR_ROCA)})]
                    rel material:binding = </World/Materiales/VisRoca>
                }}
            }}'''


def posiciones_rocas(entorno: dict) -> list[dict]:
    """Rocas sueltas alrededor del parque: muchas chicas, pocas grandes. Ninguna cae en el pasillo de trabajo ni entre las filas."""
    f = entorno["filas"]
    cx, cy = f["largo_m"] / 2, -f["separacion_m"] * (f["cantidad"] - 1) / 2
    x0, x1 = -ROCAS["libre_m"], f["largo_m"] + ROCAS["libre_m"]
    y0, y1 = -f["separacion_m"] * (f["cantidad"] - 1) - ROCAS["libre_m"], ROCAS["libre_pasillo_m"]
    r = random.Random(ROCAS["semilla"])
    rocas = []
    while len(rocas) < ROCAS["cantidad"]:
        lejos = r.random() < 0.25
        alcance = ROCAS["radio_max_m"] if lejos else 45.0
        x, y = cx + r.uniform(-alcance, alcance), cy + r.uniform(-alcance, alcance)
        if x0 <= x <= x1 and y0 <= y <= y1:
            continue
        clase = r.random()
        tam = r.uniform(0.05, 0.16) if clase < 0.62 else r.uniform(0.18, 0.45) if clase < 0.92 else r.uniform(0.5, 1.1)
        rocas.append({"nombre": f"Roca_{len(rocas)}", "modelo": r.randrange(ROCAS["modelos"]), "pos": (x, y, -0.12 * tam),
                      "giro": r.uniform(0, 360), "tam": tam * (2.5 if lejos else 1.0)})
    return rocas


def _rocas(entorno: dict) -> str:
    """/World/Visual/Rocas: los modelos (ocultos) y cada roca como referencia a uno de ellos, con su pose y tamaño."""
    modelos = "".join(_modelo_roca(k) for k in range(ROCAS["modelos"]))
    sueltas = "".join(f'''
        def Xform "{r["nombre"]}" (
            references = </World/Visual/Rocas/Modelos/Modelo_{r["modelo"]}>
        )
        {{
            double3 xformOp:translate = ({_vec(r["pos"])})
            float xformOp:rotateZ = {r["giro"]:.1f}
            float3 xformOp:scale = ({r["tam"]:.3f}, {r["tam"]:.3f}, {r["tam"]:.3f})
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateZ", "xformOp:scale"]
            token visibility = "inherited"
        }}''' for r in posiciones_rocas(entorno))
    return f'''
    def Xform "Rocas"
    {{
        def Scope "Modelos"
        {{
            token visibility = "invisible"{modelos}
        }}{sueltas}
    }}'''


def _luces(con_texturas: bool = False) -> str:
    """Sol y cielo. Con texturas el cielo es un degradado generado (texturas.py) y no se tiñe: el color ya viene en la imagen."""
    cielo = (f'''
        asset inputs:texture:file = @{_ruta_textura("cielo")}@
        token inputs:texture:format = "latlong"
        color3f inputs:color = (1, 1, 1)''' if con_texturas else f"""
        color3f inputs:color = ({_vec(CIELO["color"])})""")
    return f'''
    def DistantLight "Sol"
    {{
        float inputs:intensity = {SOL["intensidad"]}
        float inputs:angle = {SOL["angulo_grados"]}
        color3f inputs:color = ({_vec(SOL["color"])})
        float3 xformOp:rotateXYZ = ({_vec(SOL["rotacion_xyz_grados"])})
        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]
    }}

    def DomeLight "Cielo"
    {{
        float inputs:intensity = {CIELO["intensidad"]}{cielo}
    }}'''


def cuerpos_genericos(entorno: dict) -> list[dict]:
    """Suelo y, si espacio.interior, 4 paredes por fuera de la caja del espacio. Todos fijos, con colisión."""
    e = entorno["espacio"]
    largo, ancho = e["largo_m"], e["ancho_m"]
    lista = [{"nombre": "Suelo", "centro": (largo / 2, ancho / 2, -0.05), "tam": (largo + 2, ancho + 2, 0.1),
              "aspecto": "piso", "material": "suelo"}]
    if e["interior"]:
        h, t = e["alto_m"] or ALTO_PARED_SIN_TECHO_M, PARED_ESPESOR_M
        for nombre, centro, tam in (
            ("Pared_Y0", (largo / 2, -t / 2, h / 2), (largo + 2 * t, t, h)),
            ("Pared_YA", (largo / 2, ancho + t / 2, h / 2), (largo + 2 * t, t, h)),
            ("Pared_X0", (-t / 2, ancho / 2, h / 2), (t, ancho, h)),
            ("Pared_XL", (largo + t / 2, ancho / 2, h / 2), (t, ancho, h)),
        ):
            lista.append({"nombre": nombre, "centro": centro, "tam": tam, "aspecto": "pared", "material": "suelo"})
    return lista


def _nombre_usd(texto: str, i: int) -> str:
    limpio = "".join(ch if ch.isalnum() else "_" for ch in texto).strip("_") or "elemento"
    return f"E{i:02d}_{limpio[:40]}"


def _elemento(i: int, el: dict) -> str:
    """Un elemento de entorno.json como Cube o Cylinder vertical. Gira sobre Z alrededor de su centro."""
    d, p = el["dimensiones_m"], el["posicion_m"]
    centro = (p["x_m"], p["y_m"], p["z_m"] + d["alto_m"] / 2)
    aspecto = el["categoria"] if el["categoria"] in CATEGORIAS else "otro"
    material = MATERIAL_CATEGORIA.get(aspecto, "objeto")
    dinamico = not el["fijo"] and bool(el["masa_kg"])
    apis = ["PhysicsCollisionAPI", "MaterialBindingAPI"] + (["PhysicsRigidBodyAPI", "PhysicsMassAPI"] if dinamico else [])
    if el["forma"] == "cilindro":
        prim = "Cylinder"
        forma = (f'double radius = {max(d["largo_m"], d["ancho_m"]) / 2:.4f}\n'
                 f'        double height = {d["alto_m"]:.4f}\n'
                 f'        uniform token axis = "Z"')
        escala, orden = "", '["xformOp:translate", "xformOp:rotateZ"]'
    else:
        prim, forma = "Cube", "double size = 1"
        escala = f'\n        float3 xformOp:scale = ({_vec((d["largo_m"], d["ancho_m"], d["alto_m"]))})'
        orden = '["xformOp:translate", "xformOp:rotateZ", "xformOp:scale"]'
    masa = f'\n        float physics:mass = {el["masa_kg"]}' if dinamico else ""
    return f'''
    def {prim} "{_nombre_usd(el["nombre"], i)}" (
        prepend apiSchemas = [{", ".join(f'"{x}"' for x in apis)}]
    )
    {{
        {forma}
        double3 xformOp:translate = ({_vec(centro)})
        float xformOp:rotateZ = {el["rotacion_grados"]}{escala}
        uniform token[] xformOpOrder = {orden}
        color3f[] primvars:displayColor = [({_vec(ASPECTOS[aspecto][0])})]{masa}
        rel material:binding = </World/Materiales/Vis{aspecto.capitalize()}>
        rel material:binding:physics = </World/Materiales/{material.capitalize()}>
    }}'''


def escena_generica_usda(entorno: dict, con_texturas: bool = False) -> str:
    """El USD de un espacio que no es parque_solar: suelo, paredes y elementos. Sin cerros, rocas ni paneles."""
    elementos = [(i, el) for i, el in enumerate(entorno.get("elementos", [])) if el["categoria"] != "abertura"]
    aspectos = ("piso", "pared", *CATEGORIAS)
    materiales = (_material("suelo", fisica.material_suelo(entorno)) + _material("acero", fisica.material("acero"))
                  + _material("objeto", fisica.material("objeto")) + "".join(_aspecto(n, con_texturas) for n in aspectos))
    planta = "".join(_cubo(c) for c in cuerpos_genericos(entorno)) + "".join(_elemento(i, el) for i, el in elementos)
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    kilogramsPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Scope "Materiales"
    {{{materiales}
    }}

    def Xform "Planta"
    {{{planta}
    }}

    def Xform "Luces"
    {{{_luces(con_texturas)}
    }}
}}
'''


def escena_solar_usda(entorno: dict, con_texturas: bool = False) -> str:
    fijos = cuerpos(entorno)
    suelo = fijos[0]
    centro_xy = suelo["centro"][:2]
    # Con texturas el llano queda a ras del tope del suelo (z = 0) y es el único suelo que se ve: sin costura.
    llano = {"nombre": "Llano", "centro": (*centro_xy, -0.05 if con_texturas else -0.06),
             "tam": (LLANO_LADO_M, LLANO_LADO_M, 0.1), "aspecto": "tierra"}
    materiales = (_material("suelo", fisica.material_suelo(entorno)) + _material("acero", fisica.material("acero"))
                  + "".join(_aspecto(n, con_texturas) for n in ASPECTOS_ESCENA))
    planta = "".join(_cubo(c, con_texturas) for c in fijos)
    visual = ("".join(_cubo(c, con_texturas) for c in [llano, *paneles_visuales(entorno)]) + _cerros(centro_xy)
              + (_rocas(entorno) if con_texturas else ""))
    return f'''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    kilogramsPerUnit = 1
    upAxis = "Z"
)

def Xform "World"
{{
    def Scope "Materiales"
    {{{materiales}
    }}

    def Xform "Planta"
    {{{planta}
    }}

    def Xform "Visual"
    {{{visual}
    }}

    def Xform "Luces"
    {{{_luces(con_texturas)}
    }}
}}
'''


def _resumen_solar(entorno: dict, con_texturas: bool) -> str:
    return (f"escena.usd: {entorno['filas']['cantidad']} filas de {entorno['filas']['largo_m']} m, "
            f"{len(paneles_visuales(entorno))} paneles ya instalados, "
            f"{'con' if con_texturas else 'sin'} texturas")


def _resumen_generico(entorno: dict, con_texturas: bool) -> str:
    e = entorno["espacio"]
    return (f"escena.usd: {entorno['tipo']} de {e['largo_m']} × {e['ancho_m']} m, "
            f"{len(entorno.get('elementos', []))} elementos, {'con' if con_texturas else 'sin'} texturas")


class Escena(NamedTuple):
    usda: Callable[[dict, bool], str]
    resumen: Callable[[dict, bool], str]


ESCENAS = {"parque_solar": Escena(escena_solar_usda, _resumen_solar)}
ESCENA_GENERICA = Escena(escena_generica_usda, _resumen_generico)


def escena_usda(entorno: dict, con_texturas: bool = False) -> str:
    """con_texturas: materiales OmniPBR que citan texturas/ (main() las escribe)."""
    return ESCENAS.get(entorno["tipo"], ESCENA_GENERICA).usda(entorno, con_texturas)


def materiales_usda(aspectos, carpeta_texturas: str | None, cerros_en: tuple[float, float] | None = None) -> str:
    """Los materiales visuales bajo /World/Materiales, con las mismas definiciones que escena.usd, y los cerros.

    carpeta_texturas: carpeta de los PNG (ruta absoluta, para que el USD sirva desde cualquier carpeta).
    None: colores planos. cerros_en: centro (x, y) del cordón de cerros, que queda en /World/Cerros. Sin él no hay cerros.
    La escena de entrenamiento copia todo esto a su stage una sola vez: las copias lo comparten.
    """
    con = carpeta_texturas is not None
    materiales = "".join(_aspecto(n, con, carpeta_texturas) if con else _aspecto(n, False) for n in aspectos)
    cerros = _cerros(cerros_en) if cerros_en is not None else ""
    return f'''#usda 1.0
(
    defaultPrim = "World"
    upAxis = "Z"
)

def Xform "World"
{{
    def Scope "Materiales"
    {{{materiales}
    }}{cerros}
}}
'''


def _escribir_texturas(destino: Path) -> bool:
    """Escribe texturas/ al lado de escena.usd. False si faltan numpy o PIL: el USD sale con colores planos."""
    try:
        import texturas
    except ImportError as e:
        print(f"aviso: sin texturas ({e.name} no está instalado), escena.usd con colores planos", file=sys.stderr)
        return False
    texturas.generar(destino / TEXTURAS_DIR, list(GRUPOS_TEXTURA))
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    a = ap.parse_args()
    entorno = json.loads((a.dir / "entorno.json").read_text(encoding="utf-8"))
    con_texturas = _escribir_texturas(a.dir)
    escena = ESCENAS.get(entorno["tipo"], ESCENA_GENERICA)
    (a.dir / "escena.usd").write_text(escena.usda(entorno, con_texturas), encoding="utf-8")
    print(escena.resumen(entorno, con_texturas))


if __name__ == "__main__":
    main()
