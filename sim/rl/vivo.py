"""Exporta lo que pasa en el entorno RL a archivos USD que se abren en Isaac Sim o en usdview. Solo en el pod.

- exportar(): la escena completa del entorno (con física), aplanada en un solo archivo.
- Grabadora: una animación sin física de las primeras copias. Cada cuerpo es una caja o un cilindro con su
  pose por cuadro. Se abre en cualquier visor de USD y basta apretar Play: no simula nada.
  Con texturas lleva los materiales del terreno y de los paneles, el cielo y el sol. El robot va con sus colores.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generar_escena  # noqa: E402
import viaz_escena  # noqa: E402

COPIAS_MAX = 16
SALTO_DE_CUERPO_M = 0.5   # un cuerpo que se mueve más que esto entre dos cuadros fue reubicado por el entorno


def exportar(env, ruta: str | Path) -> str:
    """Escribe la escena del entorno, aplanada. Las poses son las del inicio: PhysX en GPU no las devuelve a USD."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    env.sim.stage.Export(str(ruta))
    return str(ruta)


class Grabadora:
    """Guarda la pose de cada cuerpo en cada paso de control y escribe una animación USD."""

    def __init__(self, env, copias: int = COPIAS_MAX):
        self.env = env
        self.copias = list(range(min(copias, env.num_envs)))
        self.cuadros: list[dict] = []
        self.cuerpos = {"Panel": env.panel, **{f"Pila_{k}": p for k, p in enumerate(env.pila)}}

    def cuadro(self) -> None:
        env, n = self.env, len(self.copias)
        self.cuadros.append({
            "robot": env.robot.data.body_link_pose_w[:n].cpu().numpy(),
            "sellada": env.sellada[:n].cpu().numpy(),
            **{nombre: c.data.root_state_w[:n, :7].cpu().numpy() for nombre, c in self.cuerpos.items()}})

    def guardar(self, ruta: str | Path, fps: float | None = None, texturas: Path | None = None,
                solo: int | None = None, hasta: int | None = None) -> str:
        """texturas: carpeta de los PNG (viaz_escena.carpeta_texturas()). None: colores planos y sin luces.

        solo: escribe una sola copia, con el suelo alargado para una secuencia de paneles. hasta: solo los primeros cuadros.
        """
        from pxr import Gf, Usd, UsdGeom, UsdLux, UsdShade

        env = self.env
        copias = self.copias if solo is None else [solo]
        cuadros = self.cuadros[:hasta]
        largo_suelo = env.cfg.scene.env_spacing * (1 if solo is None else 1.5)
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        stage = Usd.Stage.CreateNew(str(ruta))
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        stage.SetStartTimeCode(0)
        stage.SetEndTimeCode(max(0, len(cuadros) - 1))
        stage.SetTimeCodesPerSecond(fps or round(1 / env.step_dt))
        stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
        if texturas:
            viaz_escena.asegurar_materiales(stage, texturas)
            cielo, sol = generar_escena.CIELO, generar_escena.SOL
            domo = UsdLux.DomeLight.Define(stage, "/World/Cielo")
            domo.CreateIntensityAttr(cielo["intensidad"])
            domo.CreateTextureFileAttr(str(texturas / "cielo.png"))
            domo.CreateTextureFormatAttr("latlong")
            luz = UsdLux.DistantLight.Define(stage, "/World/Sol")
            luz.CreateIntensityAttr(sol["intensidad"])
            luz.CreateAngleAttr(sol["angulo_grados"])
            luz.CreateColorAttr(Gf.Vec3f(*sol["color"]))
            luz.AddRotateXYZOp().Set(Gf.Vec3f(*sol["rotacion_xyz_grados"]))

        def forma(prim_ruta: str, tipo: str, dims, centro, color, giro_x_grados: float = 0.0, aspecto: str | None = None):
            if tipo == "caja":
                g = UsdGeom.Cube.Define(stage, prim_ruta)
                g.CreateSizeAttr(1.0)
                g.AddTranslateOp().Set(Gf.Vec3d(*centro))
                g.AddScaleOp().Set(Gf.Vec3f(*dims))
            else:
                g = UsdGeom.Cylinder.Define(stage, prim_ruta)
                g.CreateRadiusAttr(dims[0])
                g.CreateHeightAttr(dims[1])
                g.CreateAxisAttr("Z")
                g.AddTranslateOp().Set(Gf.Vec3d(*centro))
                if giro_x_grados:
                    g.AddRotateXOp().Set(giro_x_grados)
            g.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            if texturas and aspecto:
                material = UsdShade.Material(stage.GetPrimAtPath(generar_escena.ruta_material(aspecto)))
                UsdShade.MaterialBindingAPI.Apply(g.GetPrim()).Bind(material)

        def movil(prim_ruta: str):
            x = UsdGeom.Xform.Define(stage, prim_ruta)
            return x.AddTranslateOp(), x.AddOrientOp()

        desc = viaz_escena.describir_entrenamiento(env.corrida.entorno, env.cfg.en_pila, clon=env.corrida.clon, con_robot=True)
        origenes = env.scene.env_origins.cpu().numpy()
        robot = env.corrida.robot
        fijas = {u.hijo: u for u in robot.uniones if u.tipo == "fixed"}
        nombres = env.robot.body_names
        ops = []
        for i in copias:
            raiz = f"/World/env_{i}"
            UsdGeom.Xform.Define(stage, raiz)
            o = origenes[i]
            fijos = ((desc["tubo"], generar_escena.COLOR_TUBO, "tubo"),
                     *((p, generar_escena.COLOR_POSTE, "poste") for p in desc["postes"]))
            for fijo, color, aspecto in fijos:
                forma(f"{raiz}/{fijo['nombre'].capitalize()}", "caja", fijo["tam_m"],
                      [fijo["pos_m"][k] + o[k] for k in range(3)], color, aspecto=aspecto)
            forma(f"{raiz}/Suelo", "caja", (largo_suelo, env.cfg.scene.env_spacing, 0.02),
                  (o[0] + largo_suelo / 2 - 0.5, o[1] + 1.0, -0.01), generar_escena.COLOR_SUELO, aspecto="tierra")
            for nombre in self.cuerpos:
                ops.append((nombre, i, None, *movil(f"{raiz}/{nombre}")))
                forma(f"{raiz}/{nombre}/caja", "caja", desc["panel"]["tam_m"], (0, 0, 0), generar_escena.COLOR_PANEL,
                      aspecto="marco")
                if texturas:
                    viaz_escena.agregar_vidrio(stage, f"{raiz}/{nombre}", tuple(desc["panel"]["tam_m"]))
            for b, eslabon in enumerate(nombres):
                ops.append(("robot", i, b, *movil(f"{raiz}/Robot_{eslabon}")))
                p = robot.piezas[eslabon]
                forma(f"{raiz}/Robot_{eslabon}/forma", p.forma, p.dims, p.centro, p.color)
                if eslabon == "base_link":   # ruedas, orugas, gabinete y remolque van unidos a la base
                    for hijo, u in fijas.items():
                        r = robot.piezas[hijo]
                        forma(f"{raiz}/Robot_{eslabon}/{hijo}", r.forma, r.dims, [u.xyz[k] + r.centro[k] for k in range(3)],
                              r.color, giro_x_grados=math.degrees(u.rpy[0]))
        # En una secuencia, el entorno intercambia dos cuerpos iguales cuando un panel queda instalado: el instalado pasa
        # a ser un cuerpo de la pila y el de arriba de la pila pasa a ser "Panel". En la animación cada prim sigue al
        # panel que se ve, no al cuerpo: así ningún panel salta del tubo a la pila entre dos cuadros.
        sigue = {(nombre, i): nombre for nombre in self.cuerpos for i in copias}
        for f, cuadro in enumerate(cuadros):
            if solo is not None and f > 0:
                for i in copias:
                    salto = {n: float(((cuadro[n][i, :3] - cuadros[f - 1][n][i, :3]) ** 2).sum()) ** 0.5 > SALTO_DE_CUERPO_M
                             for n in self.cuerpos}
                    if salto["Panel"]:
                        for otro in (n for n in self.cuerpos if n != "Panel" and salto[n]):
                            prims = {pista: prim for prim, pista in sigue.items() if prim[1] == i}
                            sigue[prims["Panel"]], sigue[prims[otro]] = otro, "Panel"
            for nombre, i, b, mover, girar in ops:
                pose = cuadro[sigue[nombre, i]][i] if b is None else cuadro[nombre][i, b]
                mover.Set(Gf.Vec3d(*map(float, pose[:3])), f)
                girar.Set(Gf.Quatf(float(pose[3]), *map(float, pose[4:7])), f)
        stage.GetRootLayer().Save()
        return str(ruta)
