"""Entorno instalar_panel para Isaac Lab (RF-INT-10). Solo corre en el pod.

Un episodio: la base está detenida frente al punto de montaje, con ruido (RF-INT-19). El brazo parte sin
panel, con la ventosa sobre la pila. Tiene que tomar el panel de arriba, llevarlo y dejarlo apoyado
sobre el tubo. El éxito se mide después de soltar (sim/rl/exito.py).

Varios paneles (RF-INT-18): cada episodio instala el panel k de la secuencia, con k al azar. La pila tiene k
paneles menos, la base está en el punto de montaje k y los k paneles anteriores ya descansan en sus slots.
Mover uno de esos paneles cuenta como choque. En modo secuencia (evaluación) la copia no se reinicia después
de un éxito: la base avanza al punto siguiente con el controlador programado (sim/rl/base_movil.py), el brazo
vuelve a la pila por el recorrido de referencia y la política instala el panel siguiente.

- Escena: la de entrenamiento del terreno (sim/viaz_escena.py) más el robot de la corrida.
- Acción (7): 6 velocidades de articulación entre -1 y 1, como fracción de la velocidad máxima del
  URDF, y la succión (mayor que 0 = encendida).
- Agarre: una unión fija entre la ventosa y el panel que se activa y se suelta con la simulación corriendo
  (RF-INT-22). El modo "succion" (sim/rl/agarre.py) queda como alternativa.
- Observación (52): todo en el marco de la base, para que el ruido de la base no cambie la tarea.
- Inicios asistidos: una fracción de los episodios parte en un punto del recorrido de referencia,
  con o sin el panel ya en la ventosa. La fracción baja a 0 durante el entrenamiento.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fisica  # noqa: E402
import viaz_escena  # noqa: E402

from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg, ViewerCfg  # noqa: E402
from isaaclab.scene import InteractiveSceneCfg  # noqa: E402
from isaaclab.sim import SimulationCfg  # noqa: E402
from isaaclab.utils import configclass  # noqa: E402

from . import agarre, base_movil, exito, robot_isaac  # noqa: E402
from . import cinematica as cin  # noqa: E402
from . import corrida as corrida_mod  # noqa: E402
from . import tarea as tarea_mod  # noqa: E402
from .robot import ARTICULACIONES, ESLABON_VENTOSA  # noqa: E402

N_ACCIONES = 7
N_OBSERVACIONES = 52
ADELANTO_MAX_RAD = 0.3          # el objetivo de cada articulación no se aleja más que esto de su posición
RUIDO_INICIO_RAD = 0.08         # ruido de las articulaciones al inicio del episodio
FUERZA_CHOQUE_N = 5.0           # fuerza de contacto que cuenta como choque del brazo
CAIDA_BAJO_CUBIERTA_M = 0.3     # el panel "se cayó" si baja esto de la cubierta de la base
CAMARA_ALCANCES = 2.5           # distancia de la cámara de los clips, en alcances del brazo
# Paneles ya instalados al lado del slot. Quedan donde los dejan las grapas: casi en su pose ideal.
RUIDO_VECINO_M = 0.005          # corrimiento de un panel instalado respecto de su slot
RUIDO_VECINO_GRADOS = 0.3       # y su giro: 0,6 cm en la punta de un panel de 2,38 m
VECINO_MOVIDO_M = 0.01          # un panel instalado que se corre más que esto fue chocado
VECINO_GIRADO_GRADOS = 1.0      # o que gira más que esto (2 cm en la punta)
# Viaje entre dos puntos de montaje (modo secuencia).
VEL_RETORNO = 0.6               # el brazo vuelve a la pila a esta fracción de la velocidad máxima de sus articulaciones
PAUSA_PARADA_S = 0.4            # la base ya se detuvo: el brazo se asienta antes de que la política tome el control


@configclass
class InstalarPanelCfg(DirectRLEnvCfg):
    decimation: int = fisica.RENDER_CADA
    episode_length_s: float = 14.0
    action_space: int = N_ACCIONES
    observation_space: int = N_OBSERVACIONES
    state_space: int = 0
    sim: SimulationCfg = None
    scene: InteractiveSceneCfg = None
    viewer: ViewerCfg = ViewerCfg()
    # Archivos de la corrida (docs/contrato-entorno-rl.md §2)
    entorno_json: str = ""
    tarea_json: str = ""
    robot_cfg: str = ""
    en_pila: int = 1
    # Éxito (RF-INT-11)
    tolerancia_pos_m: float = 0.05
    tolerancia_ang_grados: float = 5.0
    # Fracción de episodios con inicio asistido. entrenar.py la baja a 0 durante el entrenamiento.
    asistido: float = 0.0
    # Variaciones (RF-INT-19, RF-INT-24)
    variar: bool = True
    # "union": unión fija que se activa al sellar. "succion": fuerzas de succión virtual (sim/rl/agarre.py).
    agarre: str = "union"
    # Paneles de la secuencia (RF-INT-18). 1: siempre el panel 0, sin vecinos. 0: todos los que caben en el tramo.
    paneles: int = 1
    # Modo secuencia: después de un éxito la base avanza y la misma copia instala el panel siguiente.
    secuencia: bool = False
    # En modo secuencia, el panel instalado se fija en su slot (lo alinean y aprietan las grapas). False: queda donde cayó.
    # Con `grapas` no se teletransporta: queda donde lo dejó la política, unido al tubo con una unión fija.
    fijar_instalados: bool = True
    grapas: bool = fisica.GRAPAS
    # Ráfaga de viento sobre el panel que se maneja: velocidad máxima en m/s (0 = sin viento). Una por episodio.
    viento_m_s: float = fisica.VIENTO_ENTRENAMIENTO_M_S


def crear_cfg(entorno_json: str, tarea_json: str, robot_cfg: str, num_envs: int, device: str = "cuda:0",
              tolerancia_pos_m: float = 0.05, tolerancia_ang_grados: float = 5.0, asistido: float = 0.0,
              variar: bool = True, en_pila: int | None = None, agarre: str = "union", paneles: int = 1,
              secuencia: bool = False, fijar_instalados: bool = True, semilla: int | None = None,
              grapas: bool | None = None, viento_m_s: float | None = None) -> InstalarPanelCfg:
    """Configuración del entorno para una corrida. Llamar después de crear la app de Isaac."""
    from isaaclab.sensors import ContactSensorCfg

    c = corrida_mod.leer(entorno_json, tarea_json, robot_cfg)
    en_pila = en_pila or c.tarea["pila_paneles"]["cantidad"]
    desc, t = tarea_mod.de_corrida(c, en_pila)
    problemas = tarea_mod.problemas_alcance(t, c.cadena)
    if problemas:
        raise ValueError("el robot no puede hacer la tarea: " + "; ".join(problemas))
    # Las copias se separan lo que ocupa la base al recorrer la secuencia: si no, se mete en la copia de al lado.
    cuantos = min(paneles or t.paneles, t.paneles)
    recorrido_m = (cuantos - 1) * t.paso_slot
    espaciado = base_movil.espaciado_copias_m(c.robot, recorrido_m, viaz_escena.ESPACIADO_ENV_M)
    escena = viaz_escena.construir_cfg_entrenamiento(desc, num_envs, env_spacing=espaciado)
    q_espera, _ = tarea_mod.nominal(t, c.cadena)["espera"]
    escena.robot = robot_isaac.articulacion_cfg(c, t.base, q_espera)
    sin_contacto = "|".join(robot_isaac.ESLABONES_SIN_CONTACTO)
    # Cámara lateral 3/4 del lado del tubo: encuadra el robot, su pila y el panel instalado, con cualquier robot.
    centro_x = t.base[0] + (c.cadena.montaje_x + t.pila_x) / 2
    lejos = CAMARA_ALCANCES * c.cadena.alcance
    # La base se detiene en varios puntos de montaje: la cámara fija se centra en el recorrido y se aleja.
    centro_x, lejos = centro_x + recorrido_m / 2, lejos + 0.6 * recorrido_m
    escena.contactos = ContactSensorCfg(prim_path=f"{{ENV_REGEX_NS}}/Robot/({sin_contacto})", history_length=1)
    return InstalarPanelCfg(
        sim=viaz_escena.sim_cfg(device), scene=escena,
        viewer=ViewerCfg(eye=(centro_x + 0.8 * lejos, -0.5 * lejos, 0.5 * lejos), lookat=(centro_x, t.base[1] / 2, 1.4),
                         resolution=(1280, 720), origin_type="env", env_index=0),
        entorno_json=str(entorno_json), tarea_json=str(tarea_json), robot_cfg=str(robot_cfg), en_pila=en_pila,
        tolerancia_pos_m=tolerancia_pos_m, tolerancia_ang_grados=tolerancia_ang_grados,
        asistido=asistido, variar=variar, agarre=agarre, paneles=paneles, secuencia=secuencia,
        fijar_instalados=fijar_instalados, seed=semilla,
        grapas=fisica.GRAPAS if grapas is None else grapas,
        viento_m_s=fisica.VIENTO_ENTRENAMIENTO_M_S if viento_m_s is None else viento_m_s)


def _cols(x: torch.Tensor) -> tuple[torch.Tensor, ...]:
    return x.unbind(-1)


def _camino(desde: torch.Tensor, hasta: torch.Tensor, avance: torch.Tensor) -> torch.Tensor:
    """Punto del camino entre dos poses del brazo. avance: de 0 a 1, forma (n, 1).

    Todas las articulaciones giran a la misma velocidad y cada una se detiene al llegar, como las mueve el
    oráculo. Una interpolación recta de los 6 ángulos pasa por poses donde el brazo toca el panel que lleva.
    """
    delta = hasta - desde
    recorrido = delta.abs().max(dim=-1, keepdim=True).values
    return desde + delta.sign() * torch.minimum(delta.abs(), avance * recorrido)


class InstalarPanelEnv(DirectRLEnv):
    cfg: InstalarPanelCfg

    def __init__(self, cfg: InstalarPanelCfg, render_mode: str | None = None, **kwargs):
        self.corrida = corrida_mod.leer(cfg.entorno_json, cfg.tarea_json, cfg.robot_cfg)
        self.cadena = self.corrida.cadena
        desc, self.tarea = tarea_mod.de_corrida(self.corrida, cfg.en_pila)
        self.variaciones = desc["variaciones"]
        # _setup_scene (dentro de super().__init__) crea las grapas: necesita los nombres de la pila y los slots.
        self._prims_pila = [p["nombre"].capitalize() for p in desc["pila"]]
        self._slots_grapa = min(cfg.paneles or self.tarea.paneles, self.tarea.paneles) - 1
        super().__init__(cfg, render_mode, **kwargs)

        n, dev = self.num_envs, self.device
        self.robot, self.panel = self.scene["robot"], self.scene["panel"]
        self.pila = [self.scene[p["nombre"]] for p in desc["pila"]]
        self.contactos = self.scene["contactos"]
        self.ids, _ = self.robot.find_joints(list(ARTICULACIONES), preserve_order=True)
        self.id_ventosa = self.robot.find_bodies(ESLABON_VENTOSA)[0]
        c = self.cadena
        self.q_min = torch.tensor(c.inferior, device=dev) + cin.MARGEN_LIMITE_RAD
        self.q_max = torch.tensor(c.superior, device=dev) - cin.MARGEN_LIMITE_RAD
        self.vel_max = torch.tensor(c.velocidad, device=dev)
        self.fuerza_n = agarre.fuerza_ventosa_n(self.corrida.carga_util_kg)
        # Secuencia de paneles: una fila por panel k. Cada copia lleva el índice del panel que instala.
        t = self.tarea
        self.paneles = min(cfg.paneles or t.paneles, t.paneles)
        indices = range(self.paneles)
        self.metas = torch.tensor([t.meta_k(k) for k in indices], device=dev)
        self.bases = torch.tensor([t.base_k(k) for k in indices], device=dev)
        self.dist_inicial = torch.tensor([t.dist_inicial_k(k) for k in indices], device=dev)
        self.k = torch.zeros(n, dtype=torch.long, device=dev)
        self.meta_w = self.scene.env_origins + self.metas[0]
        self.base_pos = self.scene.env_origins + self.bases[0]
        # Vecinos: el slot s (0 .. paneles-2) lo ocupa un cuerpo de la pila cuando ya está instalado.
        self.cuerpo_de_slot = [t.en_pila - 2 - s for s in range(self.paneles - 1)]
        self.vecino_pos0 = torch.zeros(n, len(self.cuerpo_de_slot), 3, device=dev)    # dónde quedó instalado
        self.vecino_quat0 = torch.zeros(n, len(self.cuerpo_de_slot), 4, device=dev)
        self.choque_vecino = torch.zeros(n, dtype=torch.bool, device=dev)
        # Viaje entre puntos de montaje (modo secuencia).
        self.por_viajar = torch.zeros(n, dtype=torch.bool, device=dev)     # acaba de instalar y le queda otro panel
        self.viajando = torch.zeros(n, dtype=torch.bool, device=dev)
        self.viaje_t = torch.zeros(n, device=dev)                           # segundos desde que partió
        self.viaje_dur = torch.zeros(n, device=dev)
        self.viaje_inicio = torch.zeros(n, 3, device=dev)                   # x, y, rumbo de la base
        self.viaje_fin = torch.zeros(n, 3, device=dev)
        self.retorno = torch.zeros(n, 4, 6, device=dev)                     # poses del brazo de vuelta a la pila
        self.panel_fin = torch.zeros(n, dtype=torch.bool, device=dev)      # en este paso terminó el intento de un panel
        self.base_rumbo = torch.zeros(n, device=dev)
        self.q_obj = torch.zeros(n, 6, device=dev)
        self.acciones = torch.zeros(n, N_ACCIONES, device=dev)
        self.acciones_prev = torch.zeros(n, N_ACCIONES, device=dev)
        self.succion = torch.zeros(n, dtype=torch.bool, device=dev)
        self.sellada = torch.zeros(n, dtype=torch.bool, device=dev)
        self.quieto = torch.zeros(n, dtype=torch.long, device=dev)
        self.choque = torch.zeros(n, dtype=torch.bool, device=dev)
        self.logro = torch.zeros(n, dtype=torch.bool, device=dev)
        self.caido = torch.zeros(n, dtype=torch.bool, device=dev)
        self.asistido = cfg.asistido                                         # fracción de inicios asistidos
        self.con_ayuda = torch.zeros(n, dtype=torch.bool, device=dev)       # este episodio partió asistido
        self.unida = torch.zeros(n, dtype=torch.bool, device=dev)           # la unión fija de esta copia está activa
        self.potencial = torch.zeros(n, device=dev)                         # potencial del paso anterior (sim/rl/exito.py)
        self.masa_nominal = self.panel.root_physx_view.get_masses().clone()
        self.inercia_nominal = self.panel.root_physx_view.get_inertias().clone()
        # Lo que evaluar.py lee al terminar cada episodio.
        self.final = {k: torch.zeros(n, device=dev) for k in ("err_pos_m", "err_ang_grados", "exito", "choque", "pasos",
                                                               "caida", "panel", "viaje_s")}
        # Grapas: (copia, slot) con la unión activa. Viento: dirección, fuerza máxima y fase de la ráfaga de cada copia.
        self.engrapado = torch.zeros(n, max(1, len(self.cuerpo_de_slot)), dtype=torch.bool, device=dev)
        self.viento_dir = torch.zeros(n, 3, device=dev)
        self.viento_n = torch.zeros(n, device=dev)
        self.viento_fase = torch.zeros(n, device=dev)
        ancho, largo = t.panel_tam[0], t.panel_tam[1]
        self.area_panel = float(ancho * largo)
        if cfg.variar:
            self._variar_friccion()

    # ---------- uniones: ventosa–panel y grapas panel–tubo ----------

    def _setup_scene(self) -> None:
        """Uniones fijas apagadas, creadas antes de que parta la física: una por copia entre la ventosa y el panel
        (agarre "union") y, en modo secuencia con grapas, una por slot entre el panel instalado y el tubo."""
        from pxr import Gf, UsdPhysics

        escenario = self.sim.stage
        n = self.cfg.scene.num_envs
        self._union, self._grapas = [], []
        if self.cfg.agarre == "union":
            for i in range(n):
                copia = f"/World/envs/env_{i}"
                union = UsdPhysics.FixedJoint.Define(escenario, f"{copia}/Agarre")
                union.CreateBody0Rel().SetTargets([f"{copia}/Robot/{ESLABON_VENTOSA}"])
                union.CreateBody1Rel().SetTargets([f"{copia}/Panel"])
                union.CreateExcludeFromArticulationAttr(True)
                # (activa, posición del panel en el marco de la ventosa, orientación del panel en ese marco)
                self._union.append((union.CreateJointEnabledAttr(False), union.CreateLocalPos0Attr(), union.CreateLocalRot0Attr()))
        if self.cfg.secuencia and self.cfg.grapas and self._slots_grapa > 0:
            en_pila = self.tarea.en_pila
            for i in range(n):
                copia, fila = f"/World/envs/env_{i}", []
                for s in range(self._slots_grapa):
                    cuerpo = self._prims_pila[en_pila - 2 - s]     # el mismo cuerpo que ocupa el slot (cuerpo_de_slot)
                    # Sin body1: la grapa ancla el panel al mundo. El tubo es cinemático y no se mueve, así que es lo
                    # mismo, y PhysX no acepta despertar un cuerpo cinemático al activar una unión con él.
                    g = UsdPhysics.FixedJoint.Define(escenario, f"{copia}/Grapa_{s}")
                    g.CreateBody0Rel().SetTargets([f"{copia}/{cuerpo}"])
                    g.CreateLocalPos0Attr(Gf.Vec3f(0.0, 0.0, 0.0))
                    g.CreateLocalRot0Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
                    g.CreateExcludeFromArticulationAttr(True)
                    # (activa, posición del panel en el marco del tubo, orientación del panel en ese marco)
                    fila.append((g.CreateJointEnabledAttr(False), g.CreateLocalPos1Attr(), g.CreateLocalRot1Attr()))
                self._grapas.append(fila)

    def _engrapar(self, ids: torch.Tensor, slots: torch.Tensor, pose: torch.Tensor) -> None:
        """Activa la grapa del slot de cada copia en la pose donde quedó el panel: no lo mueve (sin teletransporte)."""
        from pxr import Gf, Sdf

        rel = pose[:, :3].tolist()                    # anclada al mundo: la pose del panel, en coordenadas del mundo
        rot = pose[:, 3:].tolist()
        with Sdf.ChangeBlock():
            for i, s, p, q in zip(ids.tolist(), slots.tolist(), rel, rot):
                activa, pos1, rot1 = self._grapas[i][s]
                pos1.Set(Gf.Vec3f(*p))
                rot1.Set(Gf.Quatf(q[0], q[1], q[2], q[3]))
                activa.Set(True)
        self.engrapado[ids, slots] = True

    def _soltar_grapas(self, ids: torch.Tensor) -> None:
        from pxr import Sdf

        if not self._grapas:
            return
        cuales = ids[self.engrapado[ids].any(dim=1)]
        with Sdf.ChangeBlock():
            for i in cuales.tolist():
                for s, (activa, _, _) in enumerate(self._grapas[i]):
                    if bool(self.engrapado[i, s]):
                        activa.Set(False)
        self.engrapado[ids] = False

    def _sincronizar_union(self, m: dict, reinicio: torch.Tensor | None = None) -> None:
        """Activa la unión de las copias que sellaron y suelta la de las que dejaron de sellar.

        Al activar, la unión toma la pose que el panel tiene en ese momento respecto de la ventosa: no lo mueve.
        Escribe atributos USD, uno por copia que cambia. PhysX en GPU los aplica en el paso siguiente.
        reinicio: copias que acaban de reiniciarse. Su unión se suelta y, si parten con el panel, se rehace.
        """
        from pxr import Gf, Sdf

        if reinicio is not None:
            with Sdf.ChangeBlock():
                for i in reinicio[self.unida[reinicio]].tolist():
                    self._union[i][0].Set(False)
            self.unida[reinicio] = False
        cambian = torch.nonzero(self.sellada != self.unida).flatten()
        if len(cambian) == 0:
            return
        vp, vq, pp, pq = m["ventosa_pos"], m["ventosa_quat"], m["panel_pos"], m["panel_quat"]
        inverso = cin.quat_conj(vq)
        pos = cin.quat_rotar(inverso, tuple(pp[k] - vp[k] for k in range(3)))
        # La pose de `ventosa()` es la de la cara de la placa. El marco del eslabón está `placa` más atrás.
        pos = torch.stack([pos[0], pos[1], pos[2] + self.cadena.placa], -1)[cambian].tolist()
        giro = torch.stack(cin.quat_mul(inverso, pq), -1)[cambian].tolist()
        activar = self.sellada[cambian].tolist()
        with Sdf.ChangeBlock():
            for i, si, p, g in zip(cambian.tolist(), activar, pos, giro):
                activa, pos0, rot0 = self._union[i]
                if si:
                    pos0.Set(Gf.Vec3f(*p))
                    rot0.Set(Gf.Quatf(g[0], g[1], g[2], g[3]))
                activa.Set(si)
        self.unida[cambian] = self.sellada[cambian]

    # ---------- medidas ----------

    def ventosa(self) -> tuple[tuple, tuple]:
        """Pose de la cara de la ventosa en el mundo, por cinemática directa desde las articulaciones.

        No se lee de PhysX: justo después de un reinicio, las poses de los eslabones todavía son las viejas.
        """
        q = _cols(self.robot.data.joint_pos[:, self.ids])
        pos, quat = cin.directa(self.cadena, q, torch)
        return (cin.a_mundo(pos, _cols(self.base_pos), self.base_rumbo, torch),
                cin.quat_mul(cin.quat_eje(2, self.base_rumbo, torch), quat))

    def medir(self) -> dict:
        t = self.tarea
        vp, vq = self.ventosa()
        pp, pq = _cols(self.panel.data.root_pos_w), _cols(self.panel.data.root_quat_w)
        arriba = cin.quat_rotar(pq, (0.0, 0.0, t.panel_tam[2] / 2))
        dist_ventosa = torch.stack([vp[k] - pp[k] - arriba[k] for k in range(3)], -1).norm(dim=-1)
        err_pos = exito.error_posicion_m(pp, _cols(self.meta_w))
        err_ang = exito.error_angulo_grados(pq)   # la pose ideal tiene rumbo 0: el relativo es el del panel
        vel = self.panel.data.root_lin_vel_w.norm(dim=-1)
        giro = self.panel.data.root_ang_vel_w.norm(dim=-1)
        return {"ventosa_pos": vp, "ventosa_quat": vq, "panel_pos": pp, "panel_quat": pq, "dist_ventosa": dist_ventosa,
                "err_pos": err_pos, "err_ang": err_ang, "err_altura": pp[2] - self.meta_w[:, 2], "vel": vel, "giro": giro}

    # ---------- ciclo de Isaac Lab ----------

    def _pre_physics_step(self, actions: torch.Tensor) -> None:
        """Una vez por paso de control: objetivo de las articulaciones, sello y fuerzas de la ventosa."""
        self.acciones_prev = self.acciones
        self.acciones = actions.clamp(-1.0, 1.0)
        if self.cfg.secuencia:
            self._viajar()
        q = self.robot.data.joint_pos[:, self.ids]
        objetivo = self.q_obj + self.acciones[:, :6] * self.vel_max * self.step_dt
        objetivo = torch.minimum(torch.maximum(objetivo, q - ADELANTO_MAX_RAD), q + ADELANTO_MAX_RAD)
        self.q_obj = torch.minimum(torch.maximum(objetivo, self.q_min), self.q_max)
        self.robot.set_joint_position_target(self.q_obj, joint_ids=self.ids)
        self.succion = self.acciones[:, 6] > 0
        m = self.medidas   # medidas de la última observación: nada se movió desde entonces
        vp, vq, pp, pq = m["ventosa_pos"], m["ventosa_quat"], m["panel_pos"], m["panel_quat"]
        self.sellada = agarre.actualizar(self.sellada, self.succion, vp, vq, pp, pq, self.cadena.ventosa, self.tarea.panel_tam)
        viento = self._viento(pq) if self.cfg.viento_m_s > 0 else None
        if self.cfg.agarre == "union":
            self._sincronizar_union(m)
            if viento is not None:
                self.panel.permanent_wrench_composer.set_forces_and_torques(
                    forces=viento.unsqueeze(1), torques=torch.zeros_like(viento).unsqueeze(1))
            return
        activa = self.sellada.float()
        f, tq = agarre.llave(self.fuerza_n * activa, vp, vq, pp, pq)
        fuerza = torch.stack(f, -1) + (viento if viento is not None else 0.0)
        self.panel.permanent_wrench_composer.set_forces_and_torques(
            forces=fuerza.unsqueeze(1), torques=torch.stack(tq, -1).unsqueeze(1))
        reaccion = torch.zeros(self.num_envs, 1, 3, device=self.device)
        reaccion[:, 0, 2] = self.fuerza_n * activa
        self.robot.permanent_wrench_composer.set_forces_and_torques(
            forces=reaccion, torques=torch.zeros_like(reaccion), body_ids=self.id_ventosa)

    def _viento(self, panel_quat) -> torch.Tensor:
        """Fuerza del viento sobre el panel, en el marco del panel (como la aplica el wrench composer). (n, 3).

        Cada copia tiene su ráfaga del episodio (dirección y fuerza máxima, _reset_idx). La fuerza sube y baja con un
        período de 3 s, entre el 60 % y el 100 % de la máxima: viento con ráfagas, no un empuje constante.
        """
        t = self.episode_length_buf.float() * self.step_dt
        racha = 0.8 + 0.2 * torch.sin(2 * math.pi * t / 3.0 + self.viento_fase)
        mundo = self.viento_dir * (self.viento_n * racha).unsqueeze(-1)
        return torch.stack(cin.quat_rotar(cin.quat_conj(panel_quat), _cols(mundo)), -1)

    def _apply_action(self) -> None:
        """Nada por paso de física: los objetivos y las fuerzas de _pre_physics_step siguen vigentes."""

    def _get_dones(self) -> tuple[torch.Tensor, torch.Tensor]:
        m = self.medidas = self.medir()
        cfg = self.cfg
        bien = exito.colocado(m["err_pos"], m["err_ang"], m["err_altura"], m["vel"], m["giro"], self.sellada, self.succion,
                              m["dist_ventosa"], cfg.tolerancia_pos_m, cfg.tolerancia_ang_grados)
        viajando = self.viajando.clone()
        self.quieto = torch.where(bien & ~viajando, self.quieto + 1, torch.zeros_like(self.quieto))
        fuerza = self.contactos.data.net_forces_w.norm(dim=-1).max(dim=-1).values
        self.choque_vecino = self._vecino_movido()
        self.choque = (fuerza > FUERZA_CHOQUE_N) | self.choque_vecino
        self.caido = m["panel_pos"][2] < self.tarea.cubierta_z - CAIDA_BAJO_CUBIERTA_M
        self.logro = (self.quieto >= exito.PASOS_QUIETO) & ~self.choque
        # Modo secuencia: un éxito con paneles por instalar no termina el episodio. La base viaja al punto siguiente.
        self.por_viajar = self.logro & (self.k + 1 < self.paneles) & cfg.secuencia
        terminado = (self.logro & ~self.por_viajar) | self.caido | self.choque
        tiempo = (self.episode_length_buf >= self.max_episode_length - 1) & ~viajando
        fin = self.panel_fin = terminado | tiempo | self.por_viajar
        for k, v in (("err_pos_m", m["err_pos"]), ("err_ang_grados", m["err_ang"]), ("exito", self.logro.float()),
                     ("choque", self.choque.float()), ("pasos", self.episode_length_buf.float()),
                     ("caida", self.caido.float()), ("panel", self.k.float()), ("viaje_s", self.viaje_dur)):
            self.final[k] = torch.where(fin, v, self.final[k])
        if cfg.secuencia:
            self._fin_de_viaje(viajando, m)
        # La tasa de éxito cuenta solo los episodios que partieron sin ayuda: es la tarea completa.
        propio = ~self.con_ayuda
        self.extras["log"] = {
            "episodios": (fin & propio).sum().float(), "exitos": (self.logro & propio).sum().float(),
            "episodios_asistidos": (fin & self.con_ayuda).sum().float(),
            "exitos_asistidos": (self.logro & self.con_ayuda).sum().float(),
            "caidas": self.caido.sum().float(), "choques": self.choque.sum().float(),
            "choques_vecino": self.choque_vecino.sum().float(),
            "sellados": self.sellada.float().mean()}
        for k in range(self.paneles):   # éxito sin ayuda de cada panel de la secuencia
            este = propio & (self.k == k)
            self.extras["log"][f"episodios_k{k}"] = (fin & este).sum().float()
            self.extras["log"][f"exitos_k{k}"] = (self.logro & este).sum().float()
        return terminado, tiempo & ~terminado

    def _vecino_movido(self) -> torch.Tensor:
        """True en las copias donde un panel ya instalado se corrió o giró: el brazo o el panel que lleva lo chocó."""
        if not self.cuerpo_de_slot:
            return torch.zeros_like(self.choque_vecino)
        cuerpos = [self.pila[j] for j in self.cuerpo_de_slot]
        pos = torch.stack([c.data.root_pos_w for c in cuerpos], 1)
        quat = torch.stack([c.data.root_quat_w for c in cuerpos], 1)
        instalado = torch.arange(len(cuerpos), device=self.device).unsqueeze(0) < self.k.unsqueeze(1)
        corrido = (pos - self.vecino_pos0).norm(dim=-1) > VECINO_MOVIDO_M
        girado = 2 * torch.acos((quat * self.vecino_quat0).sum(-1).abs().clamp(max=1.0)) > math.radians(VECINO_GIRADO_GRADOS)
        return ((corrido | girado) & instalado).any(dim=1)

    def _potencial(self, m: dict) -> torch.Tensor:
        cfg = self.cfg
        en_meta = (exito.en_tolerancia(m["err_pos"], m["err_ang"], cfg.tolerancia_pos_m, cfg.tolerancia_ang_grados)
                   & exito.apoyado(m["err_altura"], m["vel"], m["giro"]) & ~self.sellada)
        return exito.potencial(m["dist_ventosa"], m["err_pos"], m["err_ang"], self.sellada.float(), en_meta.float(),
                               self.dist_inicial[self.k])

    def _get_rewards(self) -> torch.Tensor:
        """Avance del potencial en este paso, menos el costo de moverse, más el premio o el castigo final."""
        ahora = self._potencial(self.medidas)
        avance = ahora - self.potencial
        self.potencial = ahora
        cambio = (self.acciones - self.acciones_prev).square().sum(dim=-1)
        velocidad = (self.robot.data.joint_vel[:, self.ids] / self.vel_max).square().sum(dim=-1)
        return (avance + exito.costo(cambio, velocidad) * self.step_dt
                + exito.PREMIO_EXITO * self.logro + exito.CASTIGO_CHOQUE * self.choque
                + exito.CASTIGO_FALLA * (self.caido & ~self.choque))

    def _get_observations(self) -> dict:
        m = self.medidas = self.medir()
        base, rumbo = _cols(self.base_pos), self.base_rumbo
        q = self.robot.data.joint_pos[:, self.ids]
        vp = cin.a_base(m["ventosa_pos"], base, rumbo, torch)
        pp = cin.a_base(m["panel_pos"], base, rumbo, torch)
        mp = cin.a_base(_cols(self.meta_w), base, rumbo, torch)
        giro_base = cin.quat_eje(2, -rumbo, torch)
        normal_ventosa = cin.quat_rotar(cin.quat_mul(giro_base, m["ventosa_quat"]), (0.0, 0.0, 1.0))
        normal_panel = cin.quat_rotar(cin.quat_mul(giro_base, m["panel_quat"]), (0.0, 0.0, 1.0))
        rumbo_ventosa = cin.rumbo(m["ventosa_quat"], torch) - rumbo
        rumbo_panel = cin.rumbo(m["panel_quat"], torch) - rumbo
        vel = self.panel.data.root_lin_vel_w
        c, s = torch.cos(rumbo), torch.sin(rumbo)
        obs = torch.cat([
            (2 * (q - self.q_min) / (self.q_max - self.q_min) - 1),
            self.robot.data.joint_vel[:, self.ids] / self.vel_max,
            (self.q_obj - q) / ADELANTO_MAX_RAD,
            torch.stack([*vp, torch.sin(rumbo_ventosa), torch.cos(rumbo_ventosa), *normal_ventosa], -1),
            # El panel es simétrico: su rumbo entra con el ángulo doble.
            torch.stack([pp[0] - vp[0], pp[1] - vp[1], pp[2] - vp[2],
                         torch.sin(2 * (rumbo_panel - rumbo_ventosa)), torch.cos(2 * (rumbo_panel - rumbo_ventosa)),
                         *normal_panel], -1),
            torch.stack([c * vel[:, 0] + s * vel[:, 1], -s * vel[:, 0] + c * vel[:, 1], vel[:, 2]], -1),
            torch.stack([mp[0] - pp[0], mp[1] - pp[1], mp[2] - pp[2],
                         torch.sin(2 * (-rumbo - rumbo_panel)), torch.cos(2 * (-rumbo - rumbo_panel))], -1),
            self.sellada.float().unsqueeze(-1), self.succion.float().unsqueeze(-1), self.acciones,
            (self.k > 0).float().unsqueeze(-1),   # hay un panel instalado al lado del slot, del lado de -X
        ], dim=-1)
        return {"policy": obs}

    def _reset_idx(self, env_ids) -> None:
        super()._reset_idx(env_ids)
        ids = torch.as_tensor(env_ids, device=self.device)
        n, dev, t, cfg = len(ids), self.device, self.tarea, self.cfg
        # Las grapas se sueltan antes de mover los paneles de vuelta a la pila.
        self._soltar_grapas(ids)
        # Ráfaga del episodio: velocidad al azar hasta viento_m_s, dirección horizontal al azar y algo de sustentación.
        if cfg.viento_m_s > 0:
            v = torch.rand(n, device=dev) * cfg.viento_m_s
            rumbo_v = torch.rand(n, device=dev) * 2 * math.pi
            d = torch.stack([torch.cos(rumbo_v), torch.sin(rumbo_v), torch.full_like(rumbo_v, 0.25)], -1)
            self.viento_dir[ids] = d / d.norm(dim=-1, keepdim=True)
            self.viento_n[ids] = fisica.fuerza_viento_n(1.0, self.area_panel) * v * v
            self.viento_fase[ids] = torch.rand(n, device=dev) * 2 * math.pi

        # Base detenida con ruido (RF-INT-19).
        ruido = self.variaciones if cfg.variar else {"base_pos_m": 0.0, "base_yaw_grados": 0.0}
        desvio = (torch.rand(n, 2, device=dev) * 2 - 1) * ruido["base_pos_m"]
        rumbo = (torch.rand(n, device=dev) * 2 - 1) * math.radians(ruido["base_yaw_grados"])
        # Panel de la secuencia que toca en este episodio. En modo secuencia siempre se parte del panel 0.
        origen = self.scene.env_origins[ids]
        toca = torch.zeros(n, dtype=torch.long, device=dev) if cfg.secuencia else torch.randint(0, self.paneles, (n,), device=dev)
        self.k[ids] = toca
        self.meta_w[ids] = origen + self.metas[toca]
        base = origen + self.bases[toca]   # el punto de montaje k: la misma regla que usa la base al viajar
        base[:, :2] += desvio
        self.base_pos[ids], self.base_rumbo[ids] = base, rumbo
        giro = torch.stack(cin.quat_eje(2, rumbo, torch), -1)
        self.robot.write_root_pose_to_sim(torch.cat([base, giro], -1), env_ids=ids)
        self.robot.write_root_velocity_to_sim(torch.zeros(n, 6, device=dev), env_ids=ids)

        # Recorrido de referencia de cada copia, en el marco de su base.
        panel_b = self._arriba_de_la_pila(toca)
        meta_b = cin.a_base(_cols(self.meta_w[ids]), _cols(base), rumbo, torch)
        cero = torch.zeros(n, device=dev)
        q_de = self._poses_recorrido(panel_b, meta_b, rumbo)

        # Inicio normal: ventosa sobre la pila, sin panel. Inicio asistido: un punto de un tramo del recorrido.
        q0 = q_de["espera"] + (torch.rand(n, 6, device=dev) * 2 - 1) * RUIDO_INICIO_RAD
        con_panel = torch.zeros(n, dtype=torch.bool, device=dev)
        asistido = torch.rand(n, device=dev) < self.asistido
        tramo = torch.randint(0, len(tarea_mod.TRAMOS), (n,), device=dev)
        avance = torch.rand(n, 1, device=dev)
        for k, (desde, hasta, lleva) in enumerate(tarea_mod.TRAMOS):
            aqui = asistido & (tramo == k)
            q0 = torch.where(aqui.unsqueeze(-1), _camino(q_de[desde], q_de[hasta], avance), q0)
            con_panel |= aqui & lleva
        # Entre dos puntos del recorrido la muñeca 1 mantiene la placa horizontal. Sin esto la placa parte inclinada,
        # el panel (que parte horizontal) queda fuera del sello y se cae al primer paso.
        q0[:, 3] = torch.where(asistido, math.pi - q0[:, 1] - q0[:, 2], q0[:, 3])
        q0 = torch.minimum(torch.maximum(q0, self.q_min), self.q_max)
        q_todas = self.robot.data.default_joint_pos[ids].clone()
        q_todas[:, self.ids] = q0
        self.robot.write_joint_state_to_sim(q_todas, torch.zeros_like(q_todas), env_ids=ids)
        self.q_obj[ids] = q0
        self.robot.set_joint_position_target(q0, joint_ids=self.ids, env_ids=ids)

        # Pila sobre la base. El panel va arriba de la pila o, si el inicio lo lleva, sellado en la ventosa.
        def al_mundo(punto_b):
            return torch.stack(cin.a_mundo(punto_b, _cols(base), rumbo, torch), -1)

        for j, cuerpo in enumerate(self.pila):
            pos = al_mundo(tuple(torch.full((n,), v, device=dev) for v in t.panel_en_pila(j)))
            pose = torch.cat([pos, giro], -1)
            s = t.slot_del_cuerpo(j)
            if s < len(self.cuerpo_de_slot):   # ya instalado si su slot es anterior al de este episodio
                corrido = (torch.rand(n, 2, device=dev) * 2 - 1) * RUIDO_VECINO_M
                girado = (torch.rand(n, device=dev) * 2 - 1) * math.radians(RUIDO_VECINO_GRADOS)
                en_slot = origen + self.metas[s]
                en_slot[:, :2] += corrido
                en_slot = torch.cat([en_slot, torch.stack(cin.quat_eje(2, girado, torch), -1)], -1)
                pose = torch.where((s < toca).unsqueeze(-1), en_slot, pose)
                self.vecino_pos0[ids, s], self.vecino_quat0[ids, s] = pose[:, :3], pose[:, 3:]
            cuerpo.write_root_pose_to_sim(pose, env_ids=ids)
            cuerpo.write_root_velocity_to_sim(torch.zeros(n, 6, device=dev), env_ids=ids)
        vp, vq = cin.directa(self.cadena, _cols(q0), torch)
        en_ventosa = torch.stack([vp[0], vp[1], vp[2] - t.panel_tam[2] / 2], -1)
        rumbo_ventosa = cin.rumbo(vq, torch)
        pos_b = torch.where(con_panel.unsqueeze(-1), en_ventosa, torch.stack(panel_b, -1))
        self.viajando[ids] = False
        self.por_viajar[ids] = False
        self.viaje_dur[ids] = 0.0
        rumbo_panel = torch.where(con_panel, rumbo_ventosa - t.giro_agarre, cero) + rumbo
        self.panel.write_root_pose_to_sim(
            torch.cat([al_mundo(_cols(pos_b)), torch.stack(cin.quat_eje(2, rumbo_panel, torch), -1)], -1), env_ids=ids)
        self.panel.write_root_velocity_to_sim(torch.zeros(n, 6, device=dev), env_ids=ids)
        if cfg.variar:
            self._variar_masa(ids)

        self.con_ayuda[ids] = asistido
        self.sellada[ids] = con_panel
        inicio = self.medir()
        if cfg.agarre == "union":
            self._sincronizar_union(inicio, reinicio=ids)
        self.potencial[ids] = self._potencial(inicio)[ids]   # el episodio nuevo parte sin avance a su favor
        self.succion[ids] = con_panel
        self.acciones[ids] = 0.0
        self.acciones[ids, 6] = torch.where(con_panel, 1.0, -1.0)
        self.acciones_prev[ids] = self.acciones[ids]
        self.quieto[ids] = 0
        self.choque[ids] = False
        self.logro[ids] = False
        self.caido[ids] = False

    def _arriba_de_la_pila(self, k: torch.Tensor) -> tuple[torch.Tensor, ...]:
        """Centro del panel de arriba de la pila cuando toca el panel k, en el marco de la base."""
        t = self.tarea
        nivel = (t.en_pila - 1 - k).float()
        return (torch.full_like(nivel, t.pila_x), torch.zeros_like(nivel), t.cubierta_z + (nivel + 0.5) * t.panel_tam[2])

    def _poses_recorrido(self, panel_b, meta_b, rumbo: torch.Tensor) -> dict:
        """Ángulos del brazo en cada punto del recorrido de referencia: {punto: tensor (n, 6)}."""
        puntos = tarea_mod.recorrido(self.tarea, panel_b, torch.zeros_like(rumbo), meta_b, -rumbo)
        return {nombre: torch.stack(q, -1) for nombre, (q, _) in tarea_mod.angulos(self.cadena, puntos, torch).items()}

    # ---------- viaje entre puntos de montaje (RF-INT-18, modo secuencia) ----------

    def _viajar(self) -> None:
        """Un paso de control del controlador programado: mueve la base y lo que lleva, y devuelve el brazo a la pila.

        La base no tiene tracción: su pose se escribe en cada paso, sobre una recta con velocidad en trapecio
        (base_movil.pose_en_viaje). La pila viaja con ella. La política no actúa mientras dura el viaje.
        """
        nuevos = torch.nonzero(self.por_viajar).flatten()
        if len(nuevos):
            self._partir(nuevos)
            self.por_viajar[:] = False
        ids = torch.nonzero(self.viajando).flatten()
        if len(ids) == 0:
            return
        t, n, dev = self.tarea, len(ids), self.device
        self.viaje_t[ids] += self.step_dt
        ahora = self.viaje_t[ids]
        x, y, rumbo = base_movil.pose_en_viaje(_cols(self.viaje_inicio[ids]), _cols(self.viaje_fin[ids]), ahora)
        base = torch.stack([x, y, self.base_pos[ids, 2]], -1)
        self.base_pos[ids], self.base_rumbo[ids] = base, rumbo
        giro = torch.stack(cin.quat_eje(2, rumbo, torch), -1)
        cero = torch.zeros(n, 6, device=dev)
        self.robot.write_root_pose_to_sim(torch.cat([base, giro], -1), env_ids=ids)
        self.robot.write_root_velocity_to_sim(cero, env_ids=ids)

        def llevar(cuerpo, punto_b, cuales: torch.Tensor) -> None:
            if not bool(cuales.any()):
                return
            pos = torch.stack(cin.a_mundo(punto_b, _cols(base), rumbo, torch), -1)
            cuerpo.write_root_pose_to_sim(torch.cat([pos, giro], -1)[cuales], env_ids=ids[cuales])
            cuerpo.write_root_velocity_to_sim(cero[cuales], env_ids=ids[cuales])

        k = self.k[ids]
        for j, cuerpo in enumerate(self.pila):   # los que siguen en la pila
            llevar(cuerpo, tuple(torch.full((n,), v, device=dev) for v in t.panel_en_pila(j)), t.slot_del_cuerpo(j) >= k)
        llevar(self.panel, self._arriba_de_la_pila(k), torch.ones(n, dtype=torch.bool, device=dev))

        # Brazo: recorre las poses de vuelta, con todas las articulaciones a la misma velocidad.
        poses = self.retorno[ids]
        largos = (poses[:, 1:] - poses[:, :-1]).abs().max(dim=-1).values
        hecho = ahora * VEL_RETORNO * float(self.vel_max.min())
        q = poses[:, 0]
        for i in range(largos.shape[1]):
            fraccion = ((hecho - largos[:, :i].sum(dim=-1)) / (largos[:, i] + 1e-6)).clamp(0.0, 1.0).unsqueeze(-1)
            # Es el camino de ida recorrido al revés: el de ida es el que se sabe libre de choques.
            q = torch.where(fraccion > 0, _camino(poses[:, i + 1], poses[:, i], 1 - fraccion), q)
        self.q_obj[ids] = q
        self.acciones[ids] = 0.0
        self.acciones[ids, 6] = -1.0

    def _partir(self, ids: torch.Tensor) -> None:
        """Empieza el viaje de las copias que acaban de instalar un panel y tienen otro por instalar."""
        t, n, dev, cfg = self.tarea, len(ids), self.device, self.cfg
        k = self.k[ids]
        origen = self.scene.env_origins[ids]
        base, rumbo = self.base_pos[ids], self.base_rumbo[ids]

        # El panel instalado se queda en el tubo. Los cuerpos son iguales: el de arriba de la pila toma el lugar del
        # instalado y el cuerpo "panel" (el que la ventosa puede sellar) vuelve arriba de la pila.
        instalado = self.panel.data.root_state_w[ids, :7].clone()
        # Con grapas el panel queda donde lo dejó la política y se une al tubo. Sin grapas, el teletransporte de antes.
        engrapar = bool(self._grapas)
        if cfg.fijar_instalados and not engrapar:
            instalado[:, :3] = origen + self.metas[k]
            instalado[:, 3:] = torch.tensor([1.0, 0.0, 0.0, 0.0], device=dev)
        for s, j in enumerate(self.cuerpo_de_slot):
            cuales = k == s
            if bool(cuales.any()):
                self.pila[j].write_root_pose_to_sim(instalado[cuales], env_ids=ids[cuales])
                self.pila[j].write_root_velocity_to_sim(torch.zeros(int(cuales.sum()), 6, device=dev), env_ids=ids[cuales])
                self.vecino_pos0[ids[cuales], s], self.vecino_quat0[ids[cuales], s] = instalado[cuales, :3], instalado[cuales, 3:]
                if engrapar:
                    self._engrapar(ids[cuales], torch.full((int(cuales.sum()),), s, device=dev), instalado[cuales])
        self.k[ids] = k + 1
        self.meta_w[ids] = origen + self.metas[k + 1]
        if cfg.variar:
            self._variar_masa(ids)

        # Destino: el punto de montaje siguiente, con el error de parada de RF-INT-19.
        ruido = self.variaciones if cfg.variar else {"base_pos_m": 0.0, "base_yaw_grados": 0.0}
        fin = origen + self.bases[k + 1]
        fin[:, :2] += (torch.rand(n, 2, device=dev) * 2 - 1) * ruido["base_pos_m"]
        rumbo_fin = (torch.rand(n, device=dev) * 2 - 1) * math.radians(ruido["base_yaw_grados"])
        self.viaje_inicio[ids] = torch.cat([base[:, :2], rumbo.unsqueeze(-1)], -1)
        self.viaje_fin[ids] = torch.cat([fin[:, :2], rumbo_fin.unsqueeze(-1)], -1)

        # Brazo: de donde quedó, sube sobre el slot, gira hasta la pila y espera sobre el panel de arriba.
        meta_vieja = cin.a_base(_cols(origen + self.metas[k]), _cols(base), rumbo, torch)
        q_de = self._poses_recorrido(self._arriba_de_la_pila(k + 1), meta_vieja, rumbo)
        q = self.robot.data.joint_pos[ids][:, self.ids]
        poses = torch.stack([q, q_de["sobre_meta"], q_de["subir"], q_de["espera"]], 1)
        poses = torch.minimum(torch.maximum(poses, self.q_min), self.q_max)
        self.retorno[ids] = poses
        t_brazo = (poses[:, 1:] - poses[:, :-1]).abs().max(dim=-1).values.sum(dim=-1) / (VEL_RETORNO * float(self.vel_max.min()))
        t_base = base_movil.duracion_s((fin[:, :2] - base[:, :2]).norm(dim=-1))
        self.viaje_dur[ids] = torch.maximum(t_base, t_brazo) + PAUSA_PARADA_S
        self.viaje_t[ids] = 0.0
        self.viajando[ids] = True
        self.sellada[ids] = False

    def _fin_de_viaje(self, viajando: torch.Tensor, m: dict) -> None:
        """Las copias que llegaron al punto de montaje quedan como al inicio de un episodio: la política toma el control."""
        self.episode_length_buf[viajando] = 0     # el tiempo del episodio no corre durante el viaje
        llego = viajando & (self.viaje_t >= self.viaje_dur)
        if not bool(llego.any()):
            return
        self.viajando &= ~llego
        self.potencial = torch.where(llego, self._potencial(m), self.potencial)
        self.acciones[llego] = 0.0
        self.acciones[llego, 6] = -1.0
        self.quieto[llego] = 0

    # ---------- variaciones (RF-INT-24) ----------

    def _variar_masa(self, ids: torch.Tensor) -> None:
        """Masa del panel ±10 % en cada episodio. La inercia cambia en la misma proporción."""
        lo, hi = self.variaciones["masa_panel_escala"]
        cpu = ids.cpu()
        escala = torch.rand(len(cpu), 1) * (hi - lo) + lo
        vista = self.panel.root_physx_view
        masas, inercias = vista.get_masses(), vista.get_inertias()
        masas[cpu] = self.masa_nominal[cpu] * escala
        inercias[cpu] = self.inercia_nominal[cpu] * escala
        vista.set_masses(masas, cpu)
        vista.set_inertias(inercias, cpu)

    def _variar_friccion(self) -> None:
        """Fricción de panel, tubo y ventosa ±20 %, un valor por copia, fijado al crear el entorno.

        PhysX no deja cambiar materiales en la GPU en cada episodio sin costo. Con miles de copias,
        el entrenamiento ve todo el rango en cada iteración.
        """
        rangos = self.variaciones["friccion"]
        todas = torch.arange(self.num_envs)

        def fijar(vista, forma: int | None, nombre: str) -> None:
            lo, hi = rangos[nombre]["estatica"]
            mat = vista.get_material_properties()
            valor = torch.rand(self.num_envs) * (hi - lo) + lo
            if forma is None:
                mat[:, :, 0] = mat[:, :, 1] = valor.unsqueeze(-1)
            else:
                mat[:, forma, 0] = mat[:, forma, 1] = valor
            vista.set_material_properties(mat, todas)

        fijar(self.panel.root_physx_view, None, "panel")
        fijar(self.scene["tubo"].root_physx_view, None, "acero")
        # Las formas de colisión del robot van en el orden de sus eslabones, una por eslabón del brazo.
        formas, forma_ventosa = 0, None
        for ruta in self.robot.root_physx_view.link_paths[0]:
            cantidad = self.robot._physics_sim_view.create_rigid_body_view(ruta).max_shapes
            if ruta.endswith("/" + ESLABON_VENTOSA):
                if cantidad != 1:
                    raise RuntimeError(f"la ventosa tiene {cantidad} formas de colisión y se esperaba 1")
                forma_ventosa = formas
            formas += cantidad
        fijar(self.robot.root_physx_view, forma_ventosa, "ventosa")
