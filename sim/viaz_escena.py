"""Escenas de VIAZ para Isaac Lab, las dos desde el mismo entorno.json (docs/escena-isaac.md).

- Parque del demo: escena.usd completo + paneles con masa en la fila 0 + pila + robot. 1 entorno.
- Escena de entrenamiento: un tramo de tubo de la fila 0, la pila y el panel que se instala, copiado en N entornos.

Cada escena tiene dos partes:
- describir*(): Python puro. Calcula qué va en la escena (posiciones, tamaños, masas, materiales).
  Se prueba sin Isaac (backend/tests/test_escena.py).
- construir_cfg*(): arma el InteractiveSceneCfg de Isaac Lab. Importa isaaclab: solo corre en el pod.
  Probado en el pod con Isaac Lab 2.3.2 (sim/prueba_fisica.py y sim/prueba_entrenamiento.py).

El terreno no sabe qué robot viene. Lo que depende del robot (dónde va la pila, a qué altura) sale de
clon["geometria"]. Sin clon.json, la pila va sobre un pallet en el suelo.
"""
from __future__ import annotations

import functools
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fisica  # noqa: E402
import generar_escena  # noqa: E402
import plan  # noqa: E402

COLOR_PANEL = generar_escena.COLOR_PANEL
COLOR_SOPORTE = (0.95, 0.75, 0.1)
PALLET_ALTO_M = 0.15            # pallet de madera estándar: la pila sin robot va sobre uno
SEPARACION_ACOPIO_M = 0.5       # sin robot, espacio libre entre los paneles instalados y la pila
ESPACIADO_ENV_M = 8.0           # entre copias de entrenamiento: tramo de 7 m + 1 m libre

# Ganancias de los actuadores del brazo (PD implícito de PhysX). Rígidas para seguir el plan
# con un panel de ~35 kg; calibrar en el pod si el brazo oscila o no llega.
RIGIDEZ = {"shoulder_pan": 8000.0, "shoulder_lift": 12000.0, "elbow": 8000.0,
           "wrist_1": 2000.0, "wrist_2": 1000.0, "wrist_3": 1000.0}
AMORTIGUAMIENTO = {k: v / 10 for k, v in RIGIDEZ.items()}


def altura_reposo_panel(entorno: dict) -> float:
    """Z del centro de un panel apoyado sobre el tubo (cara de arriba del tubo + medio espesor)."""
    return round(entorno["estructura"]["altura_m"] + plan.TUBO_R + fisica.PANEL_ESPESOR_M / 2, 4)


def _panel(nombre: str, entorno: dict, pos_inicial, pos_esperada) -> dict:
    p = entorno["panel"]
    return {
        "nombre": nombre,
        "tam_m": (p["ancho_m"], p["largo_m"], fisica.PANEL_ESPESOR_M),
        "masa_kg": p["peso_kg"],
        "pos_inicial_m": tuple(pos_inicial),
        "pos_esperada_m": tuple(pos_esperada),
        "material": fisica.material("panel"),
    }


def soporte_pila(entorno: dict, geometria: dict | None = None) -> dict:
    """Caja fija donde descansa la pila mientras el robot no está en la escena.

    Con la geometría del clon queda donde el robot lleva su pila: sobre la cubierta, frente al primer slot.
    Sin ella es un pallet en el suelo, al lado de la fila 0. La planta de la caja es la del panel.
    """
    p = entorno["panel"]
    slot = plan.slots(entorno, 1)[0]
    if geometria:
        x = slot[0] - geometria["montaje_x_m"] + geometria["pila_x_m"]
        y, alto = plan.distancia_pasillo(entorno, geometria), geometria["cubierta_z_m"]
    else:
        x, y, alto = slot[0], p["largo_m"] + SEPARACION_ACOPIO_M, PALLET_ALTO_M
    return {"nombre": "soporte", "tam_m": (p["ancho_m"], p["largo_m"], alto),
            "pos_m": (round(x, 4), round(y, 4), round(alto / 2, 4)), "material": fisica.material("acero")}


def _pila(entorno: dict, soporte: dict, n: int) -> list[dict]:
    """n paneles apoyados uno sobre otro. Parten en reposo: el paso real es el espesor del panel."""
    x, y, _ = soporte["pos_m"]
    tope = soporte["tam_m"][2]
    centros = [(x, y, round(tope + (k + 0.5) * fisica.PANEL_ESPESOR_M, 4)) for k in range(n)]
    return [_panel(f"pila_{k}", entorno, c, c) for k, c in enumerate(centros)]


def describir(entorno: dict, n_paneles: int, caida_m: float = 0.0, con_robot: bool = False,
              clon: dict | None = None, n_pila: int = 0) -> dict:
    """Qué va en el parque del demo, además de escena.usd.

    caida_m > 0: los paneles parten caida_m sobre su slot (prueba de física: se sueltan y se asientan).
    n_pila: paneles en la pila. Con clon van donde el robot los lleva. Sin clon, en un pallet.
    con_robot: agrega el robot en el pasillo de la fila 0, frente al primer slot. La pila queda sobre su base.
    """
    slots = plan.slots(entorno, n_paneles)
    reposo = altura_reposo_panel(entorno)
    paneles = [_panel(f"panel_{k}", entorno, (s[0], s[1], round(s[2] + caida_m, 4)), (s[0], s[1], reposo))
               for k, s in enumerate(slots)]
    soporte = soporte_pila(entorno, clon["geometria"] if clon else None)
    desc = {
        "dt_s": fisica.DT_S,
        "render_cada": fisica.RENDER_CADA,
        "estatica": {"usd": "escena.usd"},
        "paneles": paneles,
        "pila": _pila(entorno, soporte, n_pila),
        "soporte": None if con_robot or not n_pila else soporte,
        "robot": None,
    }
    if con_robot:
        if clon is None:
            raise ValueError("con_robot necesita clon.json")
        x0 = (slots[0][0] if slots else plan.INICIO_X) - clon["geometria"]["montaje_x_m"]
        desc["robot"] = {
            "urdf": "robot.urdf",
            "pos_inicial_m": (round(x0, 4), plan.distancia_pasillo(entorno, clon["geometria"]), 0.0),
            "q_inicial": dict(zip(["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3"],
                                  plan.poses(entorno, clon["geometria"])["casa"])),
            "rigidez": RIGIDEZ, "amortiguamiento": AMORTIGUAMIENTO,
        }
    return desc


def describir_entrenamiento(entorno: dict, paneles_en_pila: int, clon: dict | None = None,
                            con_robot: bool = False) -> dict:
    """Qué va en cada copia de la escena de entrenamiento (RF-MAP-12). Coordenadas del parque del demo.

    Recorta la planta de generar_escena.cuerpos(): el primer tramo de la fila 0 (de poste a poste).
    El panel de arriba de la pila es "panel", el que se instala. Su pose ideal es el primer slot.
    con_robot: el robot ya está en la escena y la pila descansa sobre su base. No se crea el soporte.
    """
    if paneles_en_pila < 1:
        raise ValueError("la pila necesita al menos el panel que se instala")
    tramo = min(generar_escena.POSTE_CADA_M, entorno["filas"]["largo_m"])
    fijos = {c["nombre"]: c for c in generar_escena.cuerpos(entorno)}
    tubo = fijos["Fila0_Tubo"]
    postes = [c for n, c in fijos.items() if n.startswith("Fila0_Poste") and c["centro"][0] <= tramo]
    slot = plan.slots(entorno, 1)[0]
    soporte = soporte_pila(entorno, clon["geometria"] if clon else None)
    pila = _pila(entorno, soporte, paneles_en_pila)
    arriba = pila.pop()
    desc = {
        "dt_s": fisica.DT_S,
        "decimacion": fisica.RENDER_CADA,
        "tramo_m": tramo,
        "suelo": fisica.material_suelo(entorno),
        # "tubo" es la superficie de apoyo de los paneles: tarea.py lee su cara de arriba (altura de traslado y
        # margen de la base). Con rieles, esa cara la forman los rieles; el tubo físico va más abajo (tubo_fisico).
        "tubo": {"nombre": "tubo", "tam_m": (tramo, *tubo["tam"][1:]), "pos_m": (tramo / 2, *tubo["centro"][1:]),
                 "material": fisica.material("acero")},
        "postes": [{"nombre": f"poste_{j}", "tam_m": c["tam"], "pos_m": c["centro"], "material": fisica.material("acero")}
                   for j, c in enumerate(postes)],
        "soporte": None if con_robot else soporte,
        "pila": pila,
        "panel": _panel("panel", entorno, arriba["pos_inicial_m"], (slot[0], slot[1], altura_reposo_panel(entorno))),
        "variaciones": fisica.rangos_variacion(entorno),
    }
    poner_rieles(desc, entorno)
    return desc


def poner_rieles(desc: dict, entorno: dict) -> None:
    """Rieles de módulo bajo cada slot del tramo, como en un tracker real (fisica.RIELES).

    El panel deja de apoyarse balanceado en un tubo de 10 cm: lo sostienen dos rieles que cruzan el tubo.
    Dos modos (fisica.RIELES["bajo_tubo_m"]):
    - 0: la cara de los rieles queda donde estaba la del tubo; el tubo físico y los postes bajan lo que miden los
      rieles. Es la geometría real, pero el panel aterriza distinto de como aprendió la política (medido: 17 cm de error).
    - > 0: el tubo queda donde estaba y la cara de los rieles, esos metros más abajo. El panel toca primero el tubo,
      como en el entrenamiento, y los rieles lo sostienen apenas se inclina: ya no queda balanceado.
    En los dos, el panel termina a la misma altura. Sin rieles (VIAZ_RIELES=0): desc queda como antes.
    """
    r = fisica.RIELES
    desc["rieles"], desc["tubo_fisico"] = [], None
    if not r["activos"]:
        return
    t, alto, bajo = desc["tubo"], r["alto_m"], r["bajo_tubo_m"]
    arriba_tubo = t["pos_m"][2] + t["tam_m"][2] / 2
    if bajo <= 0:
        desc["tubo_fisico"] = {**t, "nombre": "tubo", "pos_m": (t["pos_m"][0], t["pos_m"][1], t["pos_m"][2] - alto)}
        for p in desc["postes"]:
            lado_x, lado_y, h = p["tam_m"]
            p["tam_m"] = (lado_x, lado_y, h - alto)
            p["pos_m"] = (p["pos_m"][0], p["pos_m"][1], (h - alto) / 2)
    panel = entorno["panel"]
    largo = panel["largo_m"] * r["largo_rel"]
    z = arriba_tubo - max(bajo, 0.0) - alto / 2
    medio = panel["ancho_m"] / 2
    slots = [s for s in plan.slots(entorno, plan.caben(entorno)) if s[0] + medio <= desc["tramo_m"] + 1e-9]
    for k, s in enumerate(slots):
        for lado, signo in (("a", -1), ("b", 1)):
            desc["rieles"].append({"nombre": f"riel_{k}{lado}", "tam_m": (r["ancho_m"], largo, alto),
                                   "pos_m": (s[0] + signo * (medio - r["borde_m"]), t["pos_m"][1], z),
                                   "material": fisica.material("acero")})


def camara_demo(entorno: dict) -> dict:
    """Cámara lateral 3/4 fija del demo: mira la zona de trabajo de la fila 0 con la fila 1 y los cerros de fondo."""
    x = plan.slots(entorno, 1)[0][0]
    return {"ojo_m": (x - 6.0, 8.0, 3.2), "mira_m": (x + 4.0, -2.0, 1.2)}


def revisar_usd(stage, entorno: dict, raiz: str = "/World/Planta") -> list[str]:
    """Compara un escena.usd abierto con lo que entorno.json pide. Devuelve las diferencias (vacío = calza).

    Detecta un escena.usd viejo o de otro parque antes de simular. raiz: dónde quedó /World/Planta del archivo
    ("/World/Planta/Planta" cuando Isaac Lab lo referencia bajo /World/Planta). Necesita pxr (Isaac o usd-core).
    """
    from pxr import UsdGeom, UsdPhysics, UsdShade

    esperado = {"suelo": fisica.material_suelo(entorno), "acero": fisica.material("acero")}
    dif = []
    for c in generar_escena.cuerpos(entorno):
        prim = stage.GetPrimAtPath(f"{raiz}/{c['nombre']}")
        if not prim.IsValid():
            dif.append(f"falta {c['nombre']}")
            continue
        m = UsdGeom.Xformable(prim).GetLocalTransformation()
        centro = tuple(m.ExtractTranslation())
        tam = tuple(m[i][i] for i in range(3))
        if max(abs(a - b) for a, b in zip(centro + tam, tuple(c["centro"]) + tuple(c["tam"]))) > 1e-3:
            dif.append(f"{c['nombre']}: centro {centro} tamaño {tam}, se esperaba {c['centro']} {c['tam']}")
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            dif.append(f"{c['nombre']}: sin colisión")
        mat, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial("physics")
        api = UsdPhysics.MaterialAPI(mat.GetPrim()) if mat else None
        leido = (api.GetStaticFrictionAttr().Get(), api.GetDynamicFrictionAttr().Get()) if api else None
        quiere = (esperado[c["material"]]["estatica"], esperado[c["material"]]["dinamica"])
        if leido is None or max(abs(a - b) for a, b in zip(leido, quiere)) > 1e-4:
            dif.append(f"{c['nombre']}: fricción {leido}, se esperaba {quiere}")
    return dif


def camara_entrenamiento(num_envs: int, env_spacing: float = ESPACIADO_ENV_M) -> dict:
    """Cámara alta que muestra la grilla de copias (para el primer clip, RF-INT-13)."""
    lado = math.ceil(math.sqrt(num_envs)) * env_spacing
    return {"ojo_m": (-0.7 * lado, -0.7 * lado, 0.45 * lado), "mira_m": (0.1 * lado, 0.1 * lado, 0.0)}


# ---------- materiales visuales compartidos (pxr; sirve con usd-core) ----------

def carpeta_texturas() -> Path | None:
    """Carpeta de los PNG del entrenamiento, hecha una vez por pod (texturas.asegurar). None: colores planos.

    Sin numpy o PIL no hay texturas: se avisa y la escena sale con el color plano de antes.
    VIAZ_SIN_TEXTURAS=1 lo fuerza (para comparar velocidad o cargar menos memoria de video).
    """
    if os.getenv("VIAZ_SIN_TEXTURAS"):
        return None
    try:
        import texturas
    except ImportError as e:
        print(f"aviso: escena de entrenamiento con colores planos ({e.name} no está instalado)", file=sys.stderr)
        return None
    return texturas.asegurar(list(generar_escena.GRUPOS_TEXTURA_ENTRENAMIENTO))


def asegurar_materiales(stage, carpeta: Path) -> None:
    """Pone en el stage los materiales visuales del entrenamiento y los cerros, una sola vez.

    Salen de generar_escena.materiales_usda: son los mismos que escena.usd. Cada superficie de cada copia
    cita un material por ruta absoluta (/World/Materiales/Vis*): hay uno por aspecto, no uno por cuerpo y por copia.
    Los cerros son una malla para todo el stage, centrada en el origen de la grilla de copias.
    """
    from pxr import Sdf

    if stage.GetPrimAtPath(generar_escena.RUTA_CERROS).IsValid():
        return
    fuente = Sdf.Layer.CreateAnonymous(".usda")
    fuente.ImportFromString(generar_escena.materiales_usda(
        generar_escena.ASPECTOS_ENTRENAMIENTO, str(carpeta), cerros_en=(0.0, 0.0)))
    destino = stage.GetEditTarget().GetLayer()
    stage.DefinePrim(generar_escena.RAIZ_MATERIALES, "Scope")
    for ruta in [generar_escena.ruta_material(a) for a in generar_escena.ASPECTOS_ENTRENAMIENTO] + [generar_escena.RUTA_CERROS]:
        Sdf.CopySpec(fuente, ruta, destino, ruta)


def agregar_vidrio(stage, panel: str, tam: tuple[float, float, float]) -> None:
    """Vidrio con celdas sobre la cara de arriba del panel: un cuadrito hijo de su cuerpo rígido, igual al del demo.

    Sin colisión y sin masa: PhysX solo cuenta el cubo. Se mueve con el panel porque cuelga de él.
    El material VisPanel ya tiene que estar en el stage (asegurar_materiales).
    """
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    ancho, largo, espesor = tam
    z = generar_escena.VIDRIO_Z * espesor
    vidrio = UsdGeom.Mesh.Define(stage, f"{panel}/Vidrio")
    vidrio.CreateFaceVertexCountsAttr([4])
    vidrio.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    vidrio.CreatePointsAttr([(-ancho / 2, -largo / 2, z), (ancho / 2, -largo / 2, z), (ancho / 2, largo / 2, z),
                             (-ancho / 2, largo / 2, z)])
    vidrio.CreateNormalsAttr([(0, 0, 1)] * 4)
    vidrio.SetNormalsInterpolation("vertex")
    vidrio.CreateSubdivisionSchemeAttr("none")
    st = UsdGeom.PrimvarsAPI(vidrio).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(Vt.Vec2fArray([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]))
    material = UsdShade.Material(stage.GetPrimAtPath(generar_escena.ruta_material("panel")))
    UsdShade.MaterialBindingAPI.Apply(vidrio.GetPrim()).Bind(material)


# ---------- Isaac Lab (solo en el pod) ----------

def sim_cfg(device: str = "cuda:0"):
    """SimulationCfg con los parámetros de sim/fisica.py. La usan las dos escenas."""
    import isaaclab.sim as sim_utils

    return sim_utils.SimulationCfg(
        device=device,
        dt=fisica.DT_S,
        render_interval=fisica.RENDER_CADA,
        gravity=(0.0, 0.0, -fisica.GRAVEDAD),
        physx=sim_utils.PhysxCfg(
            enable_ccd=fisica.CCD,
            bounce_threshold_velocity=fisica.UMBRAL_REBOTE_M_S,
            enable_external_forces_every_iteration=fisica.FUERZAS_EN_CADA_ITERACION,
        ),
        physics_material=_material_cfg(fisica.material("suelo")),
    )


def _material_cfg(m: dict):
    import isaaclab.sim as sim_utils

    return sim_utils.RigidBodyMaterialCfg(
        static_friction=m["estatica"], dynamic_friction=m["dinamica"], restitution=m["restitucion"],
        friction_combine_mode=fisica.COMBINACION, restitution_combine_mode=fisica.COMBINACION)


@functools.cache
def _clases_isaac():
    """Material compartido y caja de panel con vidrio. Se definen aquí porque importan isaaclab."""
    from collections.abc import Callable

    import isaaclab.sim as sim_utils
    from isaaclab.sim.utils import find_matching_prim_paths, get_current_stage
    from isaaclab.utils import configclass

    def poner_material(prim_path: str, cfg):
        """Función de spawn del material: lo deja en el stage si falta y devuelve el prim. No crea uno por llamada."""
        stage = get_current_stage()
        asegurar_materiales(stage, Path(cfg.carpeta))
        return stage.GetPrimAtPath(prim_path)

    def spawn_caja_panel(prim_path: str, cfg, *args, **kwargs):
        """Spawn de la caja y, si se pide, el vidrio con celdas colgado del cuerpo rígido."""
        prim = sim_utils.spawn_cuboid(prim_path, cfg, *args, **kwargs)
        if cfg.con_vidrio:
            stage = get_current_stage()
            for ruta in find_matching_prim_paths(prim_path):
                agregar_vidrio(stage, ruta, tuple(cfg.size))
        return prim

    @configclass
    class MaterialCompartidoCfg(sim_utils.VisualMaterialCfg):
        func: Callable = poner_material
        carpeta: str = ""

    @configclass
    class CajaPanelCfg(sim_utils.CuboidCfg):
        func: Callable = spawn_caja_panel
        con_vidrio: bool = True

    return MaterialCompartidoCfg, CajaPanelCfg


def _caja(tam, material: dict, color, masa_kg: float | None = None, cinematico: bool = False,
          aspecto: str | None = None, carpeta: Path | None = None, vidrio: bool = False, visible: bool = True):
    """Caja con colisión. Con masa es dinámica. Cinemática: no se mueve pero es un cuerpo rígido. Sin nada: fija.

    Con carpeta de texturas y un aspecto, la caja usa el material visual compartido de ese aspecto
    (/World/Materiales/Vis*) y, con vidrio, lleva las celdas del panel. Sin carpeta: color plano, como antes.
    """
    import isaaclab.sim as sim_utils

    cuerpo = None
    if masa_kg is not None or cinematico:
        cuerpo = sim_utils.RigidBodyPropertiesCfg(
            kinematic_enabled=cinematico,
            solver_position_iteration_count=fisica.ITER_POSICION,
            solver_velocity_iteration_count=fisica.ITER_VELOCIDAD,
            max_depenetration_velocity=fisica.DESPENETRACION_MAX_M_S,
        )
    # Un material de fricción por valor, compartido por todas las copias. Con un material por cuerpo
    # y por copia, PhysX llega a su límite de 64 000 materiales cerca de las 7 000 copias.
    milesimas = "_".join(str(round(material[k] * 1000)) for k in ("estatica", "dinamica", "restitucion"))
    if carpeta is not None and aspecto is not None:
        compartido, caja_panel = _clases_isaac()
        visual = {"visual_material": compartido(carpeta=str(carpeta)),
                  "visual_material_path": generar_escena.ruta_material(aspecto)}
        clase, extra = (caja_panel, {"con_vidrio": True}) if vidrio else (sim_utils.CuboidCfg, {})
    else:
        visual = {"visual_material": sim_utils.PreviewSurfaceCfg(diffuse_color=tuple(color), metallic=0.4, roughness=0.35)}
        clase, extra = sim_utils.CuboidCfg, {}
    return clase(
        size=tuple(tam),
        rigid_props=cuerpo,
        mass_props=sim_utils.MassPropertiesCfg(mass=masa_kg) if masa_kg is not None else None,
        collision_props=sim_utils.CollisionPropertiesCfg(
            contact_offset=fisica.CONTACTO_OFFSET_M, rest_offset=fisica.REPOSO_OFFSET_M),
        physics_material=_material_cfg(material),
        physics_material_path=f"/World/Materiales/friccion_{milesimas}",
        visible=visible,
        **visual, **extra,
    )


def _panel_cfg(prim: str, p: dict, carpeta: Path | None = None, vidrio: bool = False):
    """Panel con masa. Con carpeta de texturas: marco de aluminio y, con vidrio, las celdas encima."""
    from isaaclab.assets import RigidObjectCfg

    caja = _caja(p["tam_m"], p["material"], COLOR_PANEL, masa_kg=p["masa_kg"], aspecto="marco", carpeta=carpeta, vidrio=vidrio)
    return RigidObjectCfg(prim_path=prim, spawn=caja, init_state=RigidObjectCfg.InitialStateCfg(pos=p["pos_inicial_m"]))


def _fijo_cfg(prim: str, c: dict, color, grupo: int = 0, aspecto: str | None = None, carpeta: Path | None = None,
              visible: bool = True):
    from isaaclab.assets import AssetBaseCfg

    return AssetBaseCfg(prim_path=prim, spawn=_caja(c["tam_m"], c["material"], color, aspecto=aspecto, carpeta=carpeta, visible=visible),
                        init_state=AssetBaseCfg.InitialStateCfg(pos=c["pos_m"]), collision_group=grupo)


def _quat_xyz(grados) -> tuple[float, float, float, float]:
    """Cuaternión (w, x, y, z) de una rotación xformOp:rotateXYZ de USD."""
    q = (1.0, 0.0, 0.0, 0.0)
    for eje, g in enumerate(grados):
        s, c = math.sin(math.radians(g) / 2), math.cos(math.radians(g) / 2)
        r = [c, 0.0, 0.0, 0.0]
        r[eje + 1] = s
        w1, x1, y1, z1 = r
        w2, x2, y2, z2 = q
        q = (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
             w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)
    return q


def construir_cfg(desc: dict, carpeta: Path, camara: dict | None = None):
    """InteractiveSceneCfg del parque del demo a partir de describir(). Llamar después de crear la app.

    Las luces y lo visual vienen dentro de escena.usd. camara: camara_demo(); necesita --enable_cameras.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.utils import configclass

    @configclass
    class EscenaViazCfg(InteractiveSceneCfg):
        planta = AssetBaseCfg(prim_path="/World/Planta",
                              spawn=sim_utils.UsdFileCfg(usd_path=str(carpeta / desc["estatica"]["usd"])))

    cfg = EscenaViazCfg(num_envs=1, env_spacing=0.0, replicate_physics=False)

    for p in desc["paneles"]:
        setattr(cfg, p["nombre"], _panel_cfg(f"/World/Paneles/{p['nombre']}", p))
    for p in desc["pila"]:
        setattr(cfg, p["nombre"], _panel_cfg(f"/World/Pila/{p['nombre']}", p))
    if desc["soporte"]:
        cfg.soporte = _fijo_cfg("/World/Soporte", desc["soporte"], COLOR_SOPORTE)

    if camara:
        cfg.camara = _camara_cfg()

    r = desc["robot"]
    if r:
        from isaaclab.actuators import ImplicitActuatorCfg
        from isaaclab.assets import ArticulationCfg
        from isaaclab.sim.converters import UrdfConverterCfg

        cfg.robot = ArticulationCfg(
            prim_path="/World/Robot",
            spawn=sim_utils.UrdfFileCfg(
                asset_path=str(carpeta / r["urdf"]),
                fix_base=False,
                merge_fixed_joints=False,
                joint_drive=UrdfConverterCfg.JointDriveCfg(
                    gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=0.0)),
                activate_contact_sensors=False,
            ),
            init_state=ArticulationCfg.InitialStateCfg(pos=r["pos_inicial_m"], joint_pos=r["q_inicial"]),
            actuators={"brazo": ImplicitActuatorCfg(
                joint_names_expr=list(r["rigidez"]), stiffness=r["rigidez"], damping=r["amortiguamiento"])},
        )
    return cfg


def _camara_cfg():
    import isaaclab.sim as sim_utils
    from isaaclab.sensors import CameraCfg

    return CameraCfg(prim_path="/World/Camara", update_period=0, height=720, width=1280, data_types=["rgb"],
                     spawn=sim_utils.PinholeCameraCfg(focal_length=18.0, clipping_range=(0.1, 5000.0)))


def construir_cfg_entrenamiento(desc: dict, num_envs: int, env_spacing: float = ESPACIADO_ENV_M,
                                camara: dict | None = None, texturas: Path | None | str = "auto"):
    """InteractiveSceneCfg de entrenamiento a partir de describir_entrenamiento(). Llamar después de crear la app.

    El entorno RL agrega el robot en "{ENV_REGEX_NS}/Robot" y sus eventos sobre "panel" y "tubo".
    El tubo es un cuerpo cinemático: randomize_rigid_body_material solo acepta cuerpos rígidos.
    El suelo es una sola caja para todas las copias.

    texturas: carpeta de los PNG. "auto" la saca de carpeta_texturas() (se hace una vez por pod). None: colores planos.
    Con texturas la escena se ve como el demo (docs/escena-isaac.md, "Materiales visuales del demo") y solo cambia lo
    que se ve: colisiones, materiales de fricción y masas son los mismos. Los materiales, los cerros, el llano y el cielo
    son uno para todo el stage. Por copia hay un vidrio de celdas en cada panel: el que se instala y los de la pila.
    """
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.utils import configclass

    carpeta = carpeta_texturas() if isinstance(texturas, str) else texturas
    sol, cielo = generar_escena.SOL, generar_escena.CIELO
    lado = (math.ceil(math.sqrt(num_envs)) + 2) * env_spacing
    suelo = {"tam_m": (lado, lado, 0.1), "pos_m": (0.0, 0.0, -0.05), "material": desc["suelo"]}
    t = desc.get("tubo_fisico") or desc["tubo"]     # con rieles, el tubo físico va más abajo (poner_rieles)
    # Con texturas el llano (visual, sin colisión) es el único suelo que se ve, a ras del físico: igual que el demo.
    domo = (sim_utils.DomeLightCfg(intensity=cielo["intensidad"], color=(1.0, 1.0, 1.0),
                                   texture_file=str(carpeta / "cielo.png"), texture_format="latlong")
            if carpeta else sim_utils.DomeLightCfg(intensity=cielo["intensidad"], color=cielo["color"]))

    @configclass
    class EscenaEntrenamientoCfg(InteractiveSceneCfg):
        cielo_luz = AssetBaseCfg(prim_path="/World/Cielo", spawn=domo)
        sol_luz = AssetBaseCfg(
            prim_path="/World/Sol",
            spawn=sim_utils.DistantLightCfg(intensity=sol["intensidad"], color=sol["color"], angle=sol["angulo_grados"]),
            init_state=AssetBaseCfg.InitialStateCfg(rot=_quat_xyz(sol["rotacion_xyz_grados"])))
        suelo_fijo = _fijo_cfg("/World/Suelo", suelo, generar_escena.COLOR_SUELO, grupo=-1, aspecto="tierra",
                               carpeta=carpeta, visible=carpeta is None)
        tubo = RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/Tubo",
            spawn=_caja(t["tam_m"], t["material"], generar_escena.COLOR_TUBO, cinematico=True, aspecto="tubo", carpeta=carpeta),
            init_state=RigidObjectCfg.InitialStateCfg(pos=t["pos_m"]))
        panel = _panel_cfg("{ENV_REGEX_NS}/Panel", desc["panel"], carpeta, vidrio=True)

    cfg = EscenaEntrenamientoCfg(num_envs=num_envs, env_spacing=env_spacing, replicate_physics=True)
    for c in desc["postes"]:
        setattr(cfg, c["nombre"], _fijo_cfg(f"{{ENV_REGEX_NS}}/{c['nombre'].capitalize()}", c, generar_escena.COLOR_POSTE,
                                            aspecto="poste", carpeta=carpeta))
    for r in desc.get("rieles", []):
        # Fijos (sin cuerpo rígido): solo colisión. Baratos aunque sean 8 a 12 por copia.
        setattr(cfg, r["nombre"], _fijo_cfg(f"{{ENV_REGEX_NS}}/{r['nombre'].capitalize()}", r, generar_escena.COLOR_TUBO,
                                            aspecto="tubo", carpeta=carpeta))
    for p in desc["pila"]:
        # Todos llevan vidrio: en la secuencia de paneles (RF-INT-18) cada uno queda arriba de la pila o instalado.
        setattr(cfg, p["nombre"], _panel_cfg(f"{{ENV_REGEX_NS}}/{p['nombre'].capitalize()}", p, carpeta, vidrio=True))
    if desc["soporte"]:
        cfg.soporte = _fijo_cfg("{ENV_REGEX_NS}/Soporte", desc["soporte"], COLOR_SOPORTE, aspecto="madera", carpeta=carpeta)
    if carpeta:
        compartido, _ = _clases_isaac()
        ancho = generar_escena.LLANO_LADO_M
        cfg.llano = AssetBaseCfg(
            prim_path="/World/Llano",
            spawn=sim_utils.CuboidCfg(size=(ancho, ancho, 0.1), visual_material=compartido(carpeta=str(carpeta)),
                                      visual_material_path=generar_escena.ruta_material("tierra")),
            init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, -0.05)))
    if camara:
        cfg.camara = _camara_cfg()
    return cfg
