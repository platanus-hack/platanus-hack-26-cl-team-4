"""Inteligencia en vivo: la política entrenada controla al LEAPTING MMR detallado en el terreno realista, con ventana.

    DISPLAY=:1 $ISAACLAB_SH -p sim/rl/en_vivo.py --entorno E --tarea T --robot R --checkpoint C
        [--detallado robot_detallado.usda] [--terreno terreno_texturas_final.usd] [--vueltas 0] [--rapido]

Una sola copia en modo secuencia: la base avanza con el controlador programado y la política instala cada panel.
Al terminar la secuencia el entorno se reinicia y empieza otra, hasta cerrar la ventana (o --vueltas N).

La física es la del entrenamiento: el mismo robot.urdf, el mismo tubo, los mismos postes. Solo cambia lo que se ve:
- el robot se dibuja con las mallas de robot_detallado.usda (esconde las formas simples de cada eslabón),
- el fondo es /World/Terreno del terreno realista, sin colisiones. Su fila 0 es la misma fila 0 del entrenamiento
  (los dos salen de generar_escena), así que el tubo y los postes del fondo calzan con los físicos.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()

DETALLADO = "/workspace/vivo/robot/leapting-mmr/robot_detallado.usda"
TERRENO = "/workspace/vivo/terreno_texturas_final.usd"
COPIA = "/World/envs/env_0"
MATERIALES = "/World/AparienciaReal"
# Cámara: desde el otro lado del tubo, en diagonal, mirando el tramo de 7 m y el robot detrás.
OJO = (-4.5, -10.5, 5.8)
MIRA = (4.6, 1.2, 1.1)
# Crear este archivo detiene la ventana en vivo sin matar el proceso (se borra al partir).
DETENER = Path("/workspace/entorno_rl/DETENER_VIVO")


def main() -> None:
    from isaaclab.app import AppLauncher

    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--detallado", default=DETALLADO)
    ap.add_argument("--terreno", default=TERRENO)
    ap.add_argument("--vueltas", type=int, default=0, help="secuencias a mostrar. 0: hasta cerrar la ventana")
    ap.add_argument("--rapido", action="store_true", help="no espera al reloj: corre tan rápido como pueda")
    ap.add_argument("--paneles", type=int, default=6, help="paneles seguidos por secuencia (la pila lleva los mismos)")
    a = ap.parse_args()
    a.headless = False
    a.salida_tarea = "/workspace/entorno_rl/vivo_tarea.json"
    DETENER.unlink(missing_ok=True)
    app = AppLauncher(a).app
    comun.ejecutar(app, lambda: en_vivo(a, app))


def vestir(entorno, detallado: str, terreno: str) -> dict:
    """Agrega el fondo realista y las mallas del robot detallado. Solo cambia lo visual. Antes de que parta la física."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

    stage = entorno.sim.stage
    raiz = stage.GetRootLayer()
    origen = [float(v) for v in entorno.scene.env_origins[0].tolist()]
    informe = {"origen_copia": origen}

    # 1. Fondo: /World/Terreno del terreno realista, desplazado al origen de la copia y sin colisiones.
    fondo = stage.DefinePrim("/World/Terreno", "Xform")
    fondo.GetReferences().AddReference(terreno, "/World/Terreno")
    UsdGeom.XformCommonAPI(fondo).SetTranslate(Gf.Vec3d(*origen))
    apagadas = 0
    for p in Usd.PrimRange(fondo):
        if p.HasAPI(UsdPhysics.CollisionAPI):
            UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr(False)
            apagadas += 1
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            UsdPhysics.RigidBodyAPI(p).CreateRigidBodyEnabledAttr(False)
    informe["colisiones_fondo_apagadas"] = apagadas

    # 2. Lo que el fondo ya dibuja: llano, cielo y sol del entrenamiento; tubo y postes de la copia (siguen chocando).
    for ruta in ("/World/Cielo", "/World/Sol"):
        p = stage.GetPrimAtPath(ruta)
        if p.IsValid():
            p.SetActive(False)
    escondidos = []
    copia = stage.GetPrimAtPath(COPIA)
    for p in [stage.GetPrimAtPath("/World/Llano")] + [h for h in copia.GetChildren()
                                                       if h.GetName() == "Tubo" or h.GetName().startswith("Poste")]:
        if p.IsValid():
            UsdGeom.Imageable(p).MakeInvisible()
            escondidos.append(p.GetName())
    informe["escondidos"] = escondidos

    # 3. Robot detallado: copia los materiales y la malla "detalle" de cada eslabón, y esconde sus formas simples.
    capa = Sdf.Layer.FindOrOpen(detallado)
    carpeta = Path(detallado).resolve().parent
    Sdf.CopySpec(capa, "/leapting_mmr/AparienciaReal", raiz, MATERIALES)
    robot = f"{COPIA}/Robot"
    vestidos, faltan = [], []
    for eslabon in capa.GetPrimAtPath("/leapting_mmr").nameChildren:
        nombre = eslabon.name
        if "detalle" not in eslabon.nameChildren:
            continue
        destino = f"{robot}/{nombre}"
        if not stage.GetPrimAtPath(destino).IsValid():
            faltan.append(nombre)
            continue
        Sdf.CreatePrimInLayer(raiz, destino)
        Sdf.CopySpec(capa, f"/leapting_mmr/{nombre}/detalle", raiz, f"{destino}/detalle")
        visuales = stage.GetPrimAtPath(f"{destino}/visuals")
        if visuales.IsValid():
            UsdGeom.Imageable(visuales).MakeInvisible()
        vestidos.append(nombre)
    informe["eslabones_vestidos"], informe["eslabones_sin_prim"] = vestidos, faltan

    # Las mallas apuntan a /leapting_mmr/AparienciaReal: se reapuntan a la copia de los materiales.
    for p in Usd.PrimRange(stage.GetPrimAtPath(robot)):
        if not p.IsA(UsdGeom.Mesh) or "/detalle/" not in str(p.GetPath()):
            continue
        rel = UsdShade.MaterialBindingAPI(p).GetDirectBindingRel()
        destinos = [Sdf.Path(str(t).replace("/leapting_mmr/AparienciaReal", MATERIALES)) for t in rel.GetTargets()]
        if destinos:
            rel.SetTargets(destinos)
    # Las texturas vienen con rutas relativas a robot_detallado.usda: se dejan absolutas.
    for p in Usd.PrimRange(stage.GetPrimAtPath(MATERIALES)):
        for at in p.GetAttributes():
            v = at.Get()
            if isinstance(v, Sdf.AssetPath) and v.path.startswith("./"):
                at.Set(Sdf.AssetPath(str(carpeta / v.path[2:])))
    return informe


def alargar_fila(a) -> dict:
    """Más paneles seguidos que en el entrenamiento: pila y objetivo de --paneles, y tubo físico más largo.

    El entrenamiento usa el primer tramo de la fila 0 (de poste a poste, 7 m: caben 4). Aquí el tubo físico abarca
    los tramos que hagan falta para --paneles, con sus postes. La tarea se copia a vivo_tarea.json: la de la corrida
    no se toca.
    """
    import math

    import fisica
    import generar_escena
    import plan
    import viaz_escena

    tarea = json.loads(Path(a.tarea).read_text(encoding="utf-8"))
    entorno = json.loads(Path(a.entorno).read_text(encoding="utf-8"))
    tarea["pila_paneles"]["cantidad"] = a.paneles
    tarea["objetivo"]["cantidad"] = a.paneles
    copia = Path(a.salida_tarea)
    copia.write_text(json.dumps(tarea, ensure_ascii=False, indent=2), encoding="utf-8")
    a.tarea = str(copia)

    ultimo = plan.slots(entorno, a.paneles)[-1][0] + entorno["panel"]["ancho_m"] / 2
    paso = generar_escena.POSTE_CADA_M
    tramo = min(math.ceil(ultimo / paso - 1e-9) * paso, entorno["filas"]["largo_m"])
    original = viaz_escena.describir_entrenamiento

    def describir(ent, paneles_en_pila, clon=None, con_robot=False):
        d = original(ent, paneles_en_pila, clon=clon, con_robot=con_robot)
        fijos = {c["nombre"]: c for c in generar_escena.cuerpos(ent)}
        tubo = fijos["Fila0_Tubo"]
        d["tramo_m"] = tramo
        d["tubo"]["tam_m"] = (tramo, *tubo["tam"][1:])
        d["tubo"]["pos_m"] = (tramo / 2, *tubo["centro"][1:])
        postes = [c for n, c in fijos.items() if n.startswith("Fila0_Poste") and c["centro"][0] <= tramo + 1e-6]
        d["postes"] = [{"nombre": f"poste_{j}", "tam_m": c["tam"], "pos_m": c["centro"], "material": fisica.material("acero")}
                       for j, c in enumerate(postes)]
        viaz_escena.poner_rieles(d, ent)   # rieles para todos los slots del tramo largo
        return d

    viaz_escena.describir_entrenamiento = describir
    return {"paneles": a.paneles, "tramo_m": tramo, "ultimo_slot_hasta_m": round(ultimo, 3)}


def en_vivo(a, app) -> dict:
    import torch

    from rl import entorno as ent

    fila = alargar_fila(a)
    print(json.dumps({"fila": fila}), flush=True)

    vestido = {}
    original = ent.InstalarPanelEnv._setup_scene

    def setup(self):
        original(self)
        vestido.update(vestir(self, a.detallado, a.terreno))

    ent.InstalarPanelEnv._setup_scene = setup
    # La cámara del visor se fija en la configuración: Isaac Lab la aplica al crear el entorno y no la cambia después.
    crear_original = ent.crear_cfg

    def crear_cfg(*args, **kwargs):
        cfg = crear_original(*args, **kwargs)
        cfg.viewer.eye, cfg.viewer.lookat = OJO, MIRA
        cfg.viewer.origin_type, cfg.viewer.env_index = "env", 0
        return cfg

    ent.crear_cfg = crear_cfg
    env_gym = comun.crear_entorno(a, 1, paneles=0, secuencia=True, en_pila=a.paneles)
    entorno = env_gym.unwrapped
    print(json.dumps({"vestido": vestido}, ensure_ascii=False), flush=True)
    env, politica = comun.cargar_politica(env_gym, a.checkpoint)
    print(json.dumps({"en_vivo": True, "paneles_por_secuencia": entorno.paneles, "paso_s": entorno.step_dt}), flush=True)

    obs, _ = env.reset()
    dt = entorno.step_dt
    vueltas, instalados, intentos = 0, 0, 0
    with torch.inference_mode():
        while app.is_running() and not DETENER.exists():
            t0 = time.perf_counter()
            obs, _, fin, _ = env.step(politica(obs))
            if bool(entorno.panel_fin[0]):
                r = {k: round(float(v[0]), 4) for k, v in entorno.final.items()}
                intentos += 1
                instalados += int(r["exito"] > 0)
                print(json.dumps({"panel": int(r["panel"]), "exito": r["exito"] > 0, "err_pos_m": r["err_pos_m"],
                                  "err_ang_grados": r["err_ang_grados"], "choque": r["choque"] > 0}), flush=True)
            if bool(fin[0]):
                vueltas += 1
                print(json.dumps({"secuencia": vueltas, "instalados": instalados, "intentos": intentos}), flush=True)
                if a.vueltas and vueltas >= a.vueltas:
                    break
            if not a.rapido:
                espera = dt - (time.perf_counter() - t0)
                if espera > 0:
                    time.sleep(espera)
    return {"ok": True, "secuencias": vueltas, "paneles_instalados": instalados, "intentos": intentos}


if __name__ == "__main__":
    main()
