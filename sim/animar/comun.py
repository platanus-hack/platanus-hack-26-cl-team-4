"""Tarea animar_evento en Isaac Lab: lo que comparten entrenar, evaluar, grabar_clip y validar_robot.

El robot es el modelo publicado para Isaac Lab que dice clon.json → modelo (sin ensamblaje). La política se entrena
con RL para seguir comandos de velocidad (caminar adelante y atrás, de lado y girar) sobre el piso de la sala:
plano, con la fricción de entorno.json. Después, un coreógrafo programado (Coreografo) convierte el recorrido y la
coreografía de tarea.json en comandos de velocidad, y la política entrenada los ejecuta en la escena de la sala.

Contrato de archivos y argumentos: docs/contrato-entorno-rl.md (el mismo de instalar_panel).
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
if str(SIM) not in sys.path:
    sys.path.insert(0, str(SIM))
import fisica  # noqa: E402

# Modelo publicado → configuración de caminata de Isaac Lab que lo entrena. Un robot con piernas nuevo agrega su fila.
LOCOMOCION = {
    "isaaclab_assets.robots.unitree:H1_MINIMAL_CFG": (
        "isaaclab_tasks.manager_based.locomotion.velocity.config.h1.flat_env_cfg:H1FlatEnvCfg",
        "isaaclab_tasks.manager_based.locomotion.velocity.config.h1.agents.rsl_rl_ppo_cfg:H1FlatPPORunnerCfg"),
    "isaaclab_assets.robots.unitree:H1_CFG": (
        "isaaclab_tasks.manager_based.locomotion.velocity.config.h1.flat_env_cfg:H1FlatEnvCfg",
        "isaaclab_tasks.manager_based.locomotion.velocity.config.h1.agents.rsl_rl_ppo_cfg:H1FlatPPORunnerCfg"),
}
# Rango de comandos del entrenamiento: cubre la coreografía (atrás, de lado, girar) y el paso entre puntos.
VEL_X = (-0.4, 1.0)
VEL_Y = (-0.5, 0.5)
GIRO_Z = (-1.0, 1.0)
QUIETOS = 0.1                 # fracción de copias con comando 0: la política también aprende a quedarse parada
# Movimientos de la coreografía → (vx, vy, wz) en el marco del robot.
MOVIMIENTOS = {"avanzar": (0.5, 0.0, 0.0), "retroceder": (-0.3, 0.0, 0.0), "lateral_izq": (0.0, 0.4, 0.0),
               "lateral_der": (0.0, -0.4, 0.0), "girar_izq": (0.0, 0.0, 1.0), "girar_der": (0.0, 0.0, -1.0),
               "quieto": (0.0, 0.0, 0.0)}
VELOCIDAD_M_S = 0.6           # por defecto de animacion.velocidad_m_s
LLEGADA_M = 0.25              # el robot "llegó" a un punto a esta distancia; el error se mide ahí
GANANCIA_GIRO = 1.5           # wz = GANANCIA_GIRO * error de rumbo, acotado a GIRO_Z
GIRA_EN_SITIO_RAD = 0.6       # con más error de rumbo que esto, gira sin avanzar
FUERZA_CHOQUE_N = 30.0        # fuerza de contacto en una pieza que no es un pie: cuenta como choque
HOLGURA_ALTURA_M = 0.1        # el robot cabe si su punto más alto queda esta distancia bajo el techo


def ruta(spec: str):
    modulo, nombre = spec.split(":")
    return getattr(importlib.import_module(modulo), nombre)


def leer_json(p: str | Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


@dataclass
class Corrida:
    entorno: dict
    tarea: dict
    clon: dict
    escena: Path | None

    @property
    def modelo(self) -> str:
        m = self.clon.get("modelo")
        if not m:
            raise SystemExit("animar_evento necesita un clon con `modelo` (modelo publicado para Isaac Lab); "
                             "este clon es un ensamblaje de piezas")
        if m["cfg"] not in LOCOMOCION:
            raise SystemExit(f"no hay configuración de caminata para {m['cfg']}; conocidas: {', '.join(LOCOMOCION)}")
        return m["cfg"]

    @property
    def animacion(self) -> dict:
        return self.tarea["animacion"]


def leer(a) -> Corrida:
    """Archivos de la corrida. --robot apunta a robot_cfg.py; clon.json está al lado (el runner baja los dos)."""
    robot = Path(a.robot)
    return Corrida(entorno=leer_json(a.entorno), tarea=leer_json(a.tarea), clon=leer_json(robot.parent / "clon.json"),
                   escena=Path(a.escena) if a.escena else None)


def argumentos(descripcion: str) -> argparse.ArgumentParser:
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser(description=descripcion)
    ap.add_argument("--entorno", required=True)
    ap.add_argument("--tarea", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--escena")
    AppLauncher.add_app_launcher_args(ap)
    return ap


def lanzar(a: argparse.Namespace, camaras: bool = False):
    from isaaclab.app import AppLauncher

    a.headless = True
    a.enable_cameras = bool(camaras or a.enable_cameras)
    return AppLauncher(a).app


# ---------- configuraciones ----------

def cfg_entrenamiento(c: Corrida, num_envs: int, device: str):
    """Caminata sobre un plano con el roce del piso de la sala. Comandos que cubren la coreografía."""
    env_cfg = ruta(LOCOMOCION[c.modelo][0])()
    env_cfg.scene.num_envs = num_envs
    env_cfg.sim.device = device
    env_cfg.scene.robot = ruta(c.modelo).replace(prim_path="{ENV_REGEX_NS}/Robot")
    cmd = env_cfg.commands.base_velocity
    cmd.debug_vis = False          # sin flechas de comando en los videos
    cmd.heading_command = False
    cmd.rel_heading_envs = 0.0
    cmd.rel_standing_envs = QUIETOS
    cmd.ranges.lin_vel_x, cmd.ranges.lin_vel_y, cmd.ranges.ang_vel_z = VEL_X, VEL_Y, GIRO_Z
    suelo = fisica.material_suelo(c.entorno)
    mat = env_cfg.scene.terrain.physics_material
    mat.static_friction, mat.dynamic_friction = suelo["estatica"], suelo["dinamica"]
    return env_cfg


def cfg_agente(c: Corrida, device: str):
    agente = ruta(LOCOMOCION[c.modelo][1])()
    agente.device = device
    agente.experiment_name = "viaz_animar"
    return agente


def inicio(c: Corrida) -> tuple[float, float, float]:
    """Pose de partida: el primer punto, mirando al segundo (o al centro de la sala si hay uno solo)."""
    p = c.animacion["puntos"]
    x0, y0 = p[0]["x_m"], p[0]["y_m"]
    if len(p) > 1:
        x1, y1 = p[1]["x_m"], p[1]["y_m"]
    else:
        x1, y1 = c.entorno["espacio"]["largo_m"] / 2, c.entorno["espacio"]["ancho_m"] / 2
    return x0, y0, math.atan2(y1 - y0, x1 - x0)


def cfg_sala(c: Corrida, num_envs: int, device: str, render: bool = False):
    """La política en la escena de la sala (escena.usd de generar_escena), una sala por copia, sin empujones."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg

    if c.escena is None:
        raise SystemExit("falta --escena: la evaluación corre en la escena de la sala")
    env_cfg = cfg_entrenamiento(c, num_envs, device)
    esp = c.entorno["espacio"]
    env_cfg.scene.env_spacing = max(esp["largo_m"], esp["ancho_m"]) + 6.0
    env_cfg.scene.sala = AssetBaseCfg(prim_path="{ENV_REGEX_NS}/Sala",
                                      spawn=sim_utils.UsdFileCfg(usd_path=str(c.escena.resolve())))
    env_cfg.commands.base_velocity.rel_standing_envs = 0.0
    env_cfg.commands.base_velocity.resampling_time_range = (1.0e6, 1.0e6)   # los comandos los pone el coreógrafo
    env_cfg.observations.policy.enable_corruption = False
    env_cfg.events.base_external_force_torque = None
    env_cfg.events.push_robot = None
    x0, y0, rumbo = inicio(c)
    env_cfg.events.reset_base.params["pose_range"] = {"x": (x0, x0), "y": (y0, y0), "yaw": (rumbo, rumbo)}
    tmax = c.tarea["criterios_exito"]["tiempo_max_s"] or 300.0
    env_cfg.episode_length_s = float(tmax)
    env_cfg.viewer.resolution = (1280, 720)
    env_cfg.viewer.origin_type = "env"
    env_cfg.viewer.env_index = 0
    return env_cfg


def crear(env_cfg, render: bool = False):
    from isaaclab.envs import ManagerBasedRLEnv

    env = ManagerBasedRLEnv(cfg=env_cfg, render_mode="rgb_array" if render else None)
    if getattr(env_cfg.scene, "sala", None) is not None:
        # El plano de Isaac Lab queda a ras del piso de la sala: solo choca, no se ve (si no, tapa el piso con su grilla).
        from pxr import UsdGeom

        for prim in env.sim.stage.Traverse():
            if str(prim.GetPath()).startswith(env_cfg.scene.terrain.prim_path) and prim.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(prim).MakeInvisible()
                break
    return env


def cargar_politica(env, c: Corrida, checkpoint: str | Path, device: str):
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
    from rsl_rl.runners import OnPolicyRunner

    agente = cfg_agente(c, device)
    envuelto = RslRlVecEnvWrapper(env, clip_actions=agente.clip_actions)
    runner = OnPolicyRunner(envuelto, agente.to_dict(), log_dir=None, device=device)
    runner.load(str(checkpoint))
    return envuelto, runner.get_inference_policy(device=device)


# ---------- coreógrafo: recorrido y coreografía → comandos de velocidad ----------

def _envolver(a):
    import torch
    return torch.atan2(torch.sin(a), torch.cos(a))


class Coreografo:
    """Máquina de estados por copia. Camina al punto i; al llegar hace la coreografía; sigue con el punto i+1.

    Escribe el comando de velocidad del entorno antes de cada paso. Anota el error de llegada a cada punto,
    cuándo terminó el recorrido, y la distancia mínima a los elementos del piso."""

    def __init__(self, env, c: Corrida):
        import torch

        self.env, self.c = env, c
        n, dev = env.num_envs, env.device
        a = c.animacion
        self.puntos = torch.tensor([[p["x_m"], p["y_m"]] for p in a["puntos"]], device=dev)
        self.pasos = [(torch.tensor(MOVIMIENTOS[s["movimiento"]], device=dev), float(s["duracion_s"]))
                      for s in a["coreografia"]]
        vmax = a.get("velocidad_m_s") or VELOCIDAD_M_S
        for r in c.tarea["restricciones"]:
            if r["tipo"] == "velocidad_max_m_s" and r["valor"]:
                vmax = min(vmax, r["valor"])
        self.vmax = min(vmax, VEL_X[1])
        self.dt = env.step_dt
        self.punto = torch.zeros(n, dtype=torch.long, device=dev)
        self.bailando = torch.zeros(n, dtype=torch.bool, device=dev)
        self.paso = torch.zeros(n, dtype=torch.long, device=dev)
        self.t_paso = torch.zeros(n, device=dev)
        self.terminado = torch.zeros(n, dtype=torch.bool, device=dev)
        self.t_fin = torch.full((n,), float("nan"), device=dev)
        self.t = torch.zeros(n, device=dev)
        self.err_llegada = torch.zeros(n, len(a["puntos"]), device=dev)
        self.term = env.command_manager.get_term("base_velocity")

    def posicion(self):
        robot = self.env.scene["robot"]
        return robot.data.root_pos_w[:, :2] - self.env.scene.env_origins[:, :2], robot.data.heading_w

    def actualizar(self) -> None:
        import torch

        pos, rumbo = self.posicion()
        n = self.env.num_envs
        cmd = torch.zeros(n, 3, device=self.env.device)
        idx = self.punto.clamp(max=len(self.puntos) - 1)
        meta = self.puntos[idx]
        d = meta - pos
        dist = d.norm(dim=-1)
        error = _envolver(torch.atan2(d[:, 1], d[:, 0]) - rumbo)
        caminando = ~self.bailando & ~self.terminado
        llega = caminando & (dist < LLEGADA_M)
        if bool(llega.any()):
            filas = torch.nonzero(llega).flatten()
            self.err_llegada[filas, idx[filas]] = dist[filas]
            self.bailando[filas] = True
            self.paso[filas] = 0
            self.t_paso[filas] = 0.0
        caminando = ~self.bailando & ~self.terminado
        wz = (GANANCIA_GIRO * error).clamp(*GIRO_Z)
        vx = self.vmax * torch.cos(error).clamp(min=0.0) * (error.abs() < GIRA_EN_SITIO_RAD)
        vx = torch.minimum(vx, 0.8 * dist + 0.1)
        cmd[caminando, 0] = vx[caminando]
        cmd[caminando, 2] = wz[caminando]
        # Coreografía
        for j, (vel, dur) in enumerate(self.pasos):
            en = self.bailando & (self.paso == j)
            if bool(en.any()):
                cmd[en] = vel
        self.t_paso[self.bailando] += self.dt
        dur = torch.tensor([p[1] for p in self.pasos], device=self.env.device)
        sigue = self.bailando & (self.t_paso >= dur[self.paso.clamp(max=len(self.pasos) - 1)])
        self.paso[sigue] += 1
        self.t_paso[sigue] = 0.0
        fin_baile = self.bailando & (self.paso >= len(self.pasos))
        self.bailando[fin_baile] = False
        self.punto[fin_baile] += 1
        acabo = fin_baile & (self.punto >= len(self.puntos))
        self.terminado |= acabo
        self.t_fin[acabo] = self.t[acabo]
        cmd[self.terminado] = 0.0
        self.term.vel_command_b[:] = cmd
        self.t += self.dt


# ---------- choques y despeje ----------

def huella(el: dict) -> tuple[float, float, float, float]:
    """Igual que backend/viaz/geometria.huella: caja alineada que contiene la planta del elemento girado."""
    d, p = el["dimensiones_m"], el["posicion_m"]
    if el["forma"] == "cilindro":
        hx = hy = max(d["largo_m"], d["ancho_m"]) / 2
    else:
        a = math.radians(el["rotacion_grados"])
        co, si = abs(math.cos(a)), abs(math.sin(a))
        hx = (d["largo_m"] * co + d["ancho_m"] * si) / 2
        hy = (d["largo_m"] * si + d["ancho_m"] * co) / 2
    return p["x_m"] - hx, p["x_m"] + hx, p["y_m"] - hy, p["y_m"] + hy


def cajas_de_piso(entorno: dict) -> list[tuple[str, tuple[float, float, float, float]]]:
    return [(e["nombre"], huella(e)) for e in entorno.get("elementos", []) if e["categoria"] != "abertura"]


class Vigilante:
    """Choques (fuerza en piezas que no son pies), caídas y distancia mínima a los elementos, por copia."""

    def __init__(self, env, c: Corrida):
        import torch

        self.env = env
        self.sensor = env.scene["contact_forces"]
        nombres = self.sensor.body_names
        self.cuerpos = [i for i, b in enumerate(nombres) if "ankle" not in b]
        cajas = cajas_de_piso(c.entorno)
        self.nombres_cajas = [n for n, _ in cajas]
        self.cajas = torch.tensor([h for _, h in cajas], device=env.device) if cajas else None
        n = env.num_envs
        self.choque = torch.zeros(n, dtype=torch.bool, device=env.device)
        self.caida = torch.zeros(n, dtype=torch.bool, device=env.device)
        self.dist_min = torch.full((n,), float("inf"), device=env.device)

    def actualizar(self, pos, listo) -> None:
        import torch

        f = self.sensor.data.net_forces_w[:, self.cuerpos].norm(dim=-1).amax(dim=-1)
        activo = ~listo
        self.choque |= activo & (f > FUERZA_CHOQUE_N)
        if self.cajas is not None:
            x, y = pos[:, :1], pos[:, 1:2]
            dx = torch.clamp(torch.maximum(self.cajas[:, 0] - x, x - self.cajas[:, 1]), min=0)
            dy = torch.clamp(torch.maximum(self.cajas[:, 2] - y, y - self.cajas[:, 3]), min=0)
            d = torch.hypot(dx, dy).amin(dim=-1)
            self.dist_min = torch.where(activo, torch.minimum(self.dist_min, d), self.dist_min)


CAMARA_DIST_M = 3.5          # distancia horizontal de la cámara al robot
CAMARA_ALTO_M = 2.3          # altura del ojo; mira al pecho del robot
CAMARA_MIRA_M = 1.0
CAMARA_DIRECCIONES = 24      # candidatas alrededor del robot
CAMARA_MARGEN_M = 0.4        # la cámara queda al menos esto dentro de las paredes y fuera de los elementos
CAMARA_SUAVE = 0.06          # fracción del camino a la posición elegida que avanza la cámara por cuadro


class Camarografo:
    """Cámara que sigue al robot sin quedar dentro de un elemento ni detrás de uno.

    Prueba direcciones alrededor del robot, descarta las que caen fuera de la sala o dentro de un elemento y prefiere
    las que ven al robot sin obstáculos. Mantiene la dirección elegida mientras siga sirviendo y se mueve suave."""

    def __init__(self, env, c: Corrida, copia: int = 0):
        self.env, self.c, self.copia = env, c, copia
        esp = c.entorno["espacio"]
        self.largo, self.ancho = esp["largo_m"], esp["ancho_m"]
        self.alto = min(CAMARA_ALTO_M, esp["alto_m"] - 0.3) if esp["interior"] else CAMARA_ALTO_M
        self.cajas = [(huella(e), e["posicion_m"]["z_m"] + e["dimensiones_m"]["alto_m"])
                      for e in c.entorno.get("elementos", []) if e["categoria"] != "abertura"]
        self.angulo: float | None = None
        self.ojo: list[float] | None = None

    def _dentro_de_algo(self, x: float, y: float) -> bool:
        m = CAMARA_MARGEN_M
        if not (m <= x <= self.largo - m and m <= y <= self.ancho - m):
            return True
        return any(h[0] - m <= x <= h[1] + m and h[2] - m <= y <= h[3] + m and tope > self.alto - 0.3
                   for h, tope in self.cajas)

    def _tapado(self, x0: float, y0: float, x1: float, y1: float) -> int:
        """Cuántos elementos cortan la línea de vista (de la cámara al pecho del robot)."""
        n = 0
        for h, tope in self.cajas:
            for k in range(1, 20):
                t = k / 20
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                z = self.alto + (CAMARA_MIRA_M - self.alto) * t
                if h[0] <= x <= h[1] and h[2] <= y <= h[3] and z <= tope:
                    n += 1
                    break
        return n

    def _puntaje(self, ang: float, x: float, y: float) -> float | None:
        cx, cy = x + CAMARA_DIST_M * math.cos(ang), y + CAMARA_DIST_M * math.sin(ang)
        if self._dentro_de_algo(cx, cy):
            return None
        return self._tapado(cx, cy, x, y)

    def mover(self, x: float, y: float, saltar: bool = False) -> None:
        actual = self._puntaje(self.angulo, x, y) if self.angulo is not None else None
        if actual is None or actual > 0:
            mejores = []
            for k in range(CAMARA_DIRECCIONES):
                ang = 2 * math.pi * k / CAMARA_DIRECCIONES
                p = self._puntaje(ang, x, y)
                if p is not None:
                    # Menos obstáculos primero; después, lo más parecido a la dirección que ya tenía.
                    giro = abs(math.remainder(ang - self.angulo, 2 * math.pi)) if self.angulo is not None else 0.0
                    mejores.append((p, giro, ang))
            if mejores:
                self.angulo = min(mejores)[2]
            elif self.angulo is None:
                self.angulo = math.atan2(self.ancho / 2 - y, self.largo / 2 - x)
        meta = [x + CAMARA_DIST_M * math.cos(self.angulo), y + CAMARA_DIST_M * math.sin(self.angulo), self.alto]
        if self.ojo is None or saltar:
            self.ojo = meta
        else:
            self.ojo = [o + CAMARA_SUAVE * (m - o) for o, m in zip(self.ojo, meta)]
        o = self.env.scene.env_origins[self.copia].tolist()
        self.env.sim.set_camera_view([o[k] + self.ojo[k] for k in range(3)], [o[0] + x, o[1] + y, o[2] + CAMARA_MIRA_M])


def camara_sala(env, c: Corrida, copia: int = 0, sigue: tuple[float, float] | None = None) -> None:
    """Cámara fija sobre el primer punto (para la vista inicial). Para seguir al robot, usar Camarografo."""
    x, y = sigue if sigue is not None else inicio(c)[:2]
    Camarografo(env, c, copia).mover(x, y, saltar=True)


ERROR_VEL_OK_M_S = 0.25      # error medio de velocidad (adelante y de lado) de un episodio logrado
ERROR_GIRO_OK_RAD_S = 0.4    # y de giro
LARGO_MIN = 0.5              # fracción del episodio que tiene que durar para contar: descarta los cortos del inicio


def envolver_con_metricas(env, clip_actions):
    """RslRlVecEnvWrapper que cuenta episodios logrados: terminan por tiempo (sin caerse) y siguen el comando.

    Isaac Lab solo registra promedios por lote; aquí el éxito es por episodio, para que `tasa_exito` no llegue
    a 100 % con un robot que se queda parado sin caerse."""
    import torch
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper

    class ConMetricas(RslRlVecEnvWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            u = self.unwrapped
            self.err_v = torch.zeros(u.num_envs, device=u.device)
            self.err_w = torch.zeros(u.num_envs, device=u.device)
            self.n = torch.zeros(u.num_envs, device=u.device)
            self.logrados = 0
            self.terminados = 0

        def step(self, acciones):
            u = self.unwrapped
            cmd = u.command_manager.get_command("base_velocity").clone()
            salida = super().step(acciones)
            robot = u.scene["robot"]
            self.err_v += (robot.data.root_lin_vel_b[:, :2] - cmd[:, :2]).norm(dim=-1)
            self.err_w += (robot.data.root_ang_vel_b[:, 2] - cmd[:, 2]).abs()
            self.n += 1
            hechos = salida[2].bool()
            if bool(hechos.any()):
                tiempo = u.termination_manager.time_outs & hechos
                largo = self.n >= LARGO_MIN * u.max_episode_length
                n = self.n.clamp(min=1)
                bien = tiempo & (self.err_v / n < ERROR_VEL_OK_M_S) & (self.err_w / n < ERROR_GIRO_OK_RAD_S)
                cuentan = hechos & (largo | ~tiempo)        # una caída corta sí cuenta; un tiempo agotado corto no
                self.terminados += int(cuentan.sum())
                self.logrados += int((bien & largo).sum())
                self.err_v[hechos], self.err_w[hechos], self.n[hechos] = 0.0, 0.0, 0.0
            return salida

        def leer_y_reiniciar(self) -> tuple[int, int]:
            r = (self.logrados, self.terminados)
            self.logrados = self.terminados = 0
            return r

    return ConMetricas(env, clip_actions=clip_actions)


def terminar(app, informe: dict | None = None, salida: Path | None = None) -> None:
    sys.path.insert(0, str(SIM))
    from rl import comun as rl_comun

    rl_comun.terminar(app, informe, salida)


def ejecutar(app, trabajo, salida: Path | None = None) -> None:
    sys.path.insert(0, str(SIM))
    from rl import comun as rl_comun

    rl_comun.ejecutar(app, trabajo, salida)
