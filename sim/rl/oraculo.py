"""Oráculo: una política programada que resuelve instalar_panel con las mismas acciones que la política RL.

Sirve para tres cosas: probar que la tarea y el criterio de éxito tienen solución (sim/rl/prueba_entorno.py),
probar el agarre (sim/rl/prueba_agarre.py) y como plan B si el RL no converge (RF-INT-01).
Sigue el recorrido de sim/rl/tarea.py con cinemática inversa. No usa nada que la política no pueda ver.
Necesita torch: solo corre en el pod.
"""
from __future__ import annotations

import math

import torch

from . import cinematica as cin
from . import tarea as tarea_mod

FASES = ("acercar", "bajar", "subir", "llevar", "apoyar", "soltar", "retirar")
PUNTO = {"acercar": "espera", "bajar": "tomar", "subir": "subir", "llevar": "sobre_meta", "apoyar": "dejar",
         "soltar": "dejar", "retirar": "retirar"}
CON_SUCCION = ("bajar", "subir", "llevar", "apoyar")
GANANCIA = 0.25           # fracción del error de cada articulación que se corrige en un paso de control
VELOCIDAD = {"acercar": 1.0, "bajar": 0.5, "subir": 0.5, "llevar": 0.5, "apoyar": 0.3, "soltar": 0.3, "retirar": 0.5}
CERCA_RAD = {"acercar": 0.03, "subir": 0.05, "llevar": 0.02, "apoyar": 0.01}
APOYO_SOBRE_TUBO_M = 0.003    # el panel se suelta a esta altura sobre su posición de reposo
PASOS_ESPERA = {"bajar": 5, "soltar": 8}   # pasos de control que espera después de sellar y de soltar
PASOS_MAX = {"apoyar": 75}                 # si no llega a la pose en este tiempo, suelta igual


class Oraculo:
    def __init__(self, env):
        self.env = env
        n, dev = env.num_envs, env.device
        self.fase = torch.zeros(n, dtype=torch.long, device=dev)
        self.pasos = torch.zeros(n, dtype=torch.long, device=dev)      # pasos de control en la fase actual
        self.desfase = torch.zeros(n, 3, device=dev)                    # ventosa respecto del panel: dx, dy, drumbo
        self.ancla = torch.zeros(n, 3, device=dev)                      # dónde selló la ventosa: x, y, rumbo
        self.fase_max = len(FASES) - 1                                  # las pruebas lo bajan para detener el recorrido
        self.error = torch.zeros(n, device=dev)                         # mayor error de articulación respecto del punto

    def accion(self) -> torch.Tensor:
        env = self.env
        t, c = env.tarea, env.cadena
        nuevos = env.episode_length_buf == 0
        self.fase[nuevos] = 0
        self.pasos[nuevos] = 0
        m = env.medidas   # las de la última observación
        base, rumbo = env.base_pos.unbind(-1), env.base_rumbo
        ventosa = cin.a_base(m["ventosa_pos"], base, rumbo, torch)
        panel = cin.a_base(m["panel_pos"], base, rumbo, torch)
        meta = cin.a_base(env.meta_w.unbind(-1), base, rumbo, torch)
        rumbo_ventosa = cin.rumbo(m["ventosa_quat"], torch) - rumbo
        rumbo_panel = cin.rumbo(m["panel_quat"], torch) - rumbo

        # Con el panel sellado mide dónde quedó la ventosa respecto del panel, para dejar el panel en la meta.
        dx, dy = ventosa[0] - panel[0], ventosa[1] - panel[1]
        cs, sn = torch.cos(rumbo_panel), torch.sin(rumbo_panel)
        medido = torch.stack([cs * dx + sn * dy, -sn * dx + cs * dy,
                              cin.envolver(rumbo_ventosa - rumbo_panel, math.pi, torch)], -1)
        self.desfase = torch.where(env.sellada.unsqueeze(-1), medido, self.desfase)
        sin_sello = ~env.sellada
        aqui = torch.stack([ventosa[0], ventosa[1], rumbo_ventosa], -1)
        self.ancla = torch.where(sin_sello.unsqueeze(-1), aqui, self.ancla)

        puntos = tarea_mod.recorrido(t, panel, rumbo_panel, meta, -rumbo, self.desfase.unbind(-1))
        (_, _, z_subir), _ = puntos["subir"]
        puntos["subir"] = ((self.ancla[:, 0], self.ancla[:, 1], z_subir), self.ancla[:, 2])
        (x, y, z), r = puntos["dejar"]
        puntos["dejar"] = ((x, y, z + APOYO_SOBRE_TUBO_M), r)
        angulos = tarea_mod.angulos(c, puntos, torch)

        q = env.robot.data.joint_pos[:, env.ids]
        objetivo, limite, succion = torch.zeros_like(q), torch.ones_like(q[:, 0]), torch.zeros_like(q[:, 0])
        for k, nombre in enumerate(FASES):
            en_fase = self.fase == k
            objetivo = torch.where(en_fase.unsqueeze(-1), torch.stack(angulos[PUNTO[nombre]][0], -1), objetivo)
            limite = torch.where(en_fase, VELOCIDAD[nombre], limite)
            succion = torch.where(en_fase, 1.0 if nombre in CON_SUCCION else -1.0, succion)
        error = objetivo - q
        giro = (GANANCIA * error / (env.vel_max * env.step_dt)).clamp(-1.0, 1.0) * limite.unsqueeze(-1)

        # Cambios de fase.
        llego = error.abs().max(dim=-1).values
        avanza = torch.zeros_like(nuevos)
        for k, nombre in enumerate(FASES[:-1]):
            en_fase = self.fase == k
            if nombre == "bajar":
                listo = env.sellada & (self.pasos >= PASOS_ESPERA["bajar"])
            elif nombre == "soltar":
                listo = sin_sello & (self.pasos >= PASOS_ESPERA["soltar"])
            else:
                listo = llego < CERCA_RAD[nombre]
                if nombre in PASOS_MAX:
                    listo |= self.pasos >= PASOS_MAX[nombre]
            avanza |= en_fase & listo
        avanza &= self.fase < self.fase_max
        self.error = llego
        self.fase = torch.where(avanza, self.fase + 1, self.fase)
        self.pasos = torch.where(avanza, torch.zeros_like(self.pasos), self.pasos + 1)
        return torch.cat([giro, succion.unsqueeze(-1)], -1)
