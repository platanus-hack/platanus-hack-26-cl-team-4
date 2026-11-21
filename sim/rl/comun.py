"""Lo que comparten los comandos y las pruebas del entorno RL: argumentos, app de Isaac y entorno.

Cada script fija --headless por su cuenta (docs/contrato-entorno-rl.md §1): el runner no pasa banderas de Isaac.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]


def preparar_ruta() -> None:
    """Deja sim/ primero en la ruta de módulos, para importar `rl`, `fisica`, `plan` y `video`.

    Quita sim/rl/: Python la agrega al lanzar un script de esa carpeta y sus módulos taparían a otros.
    """
    aqui = str(Path(__file__).resolve().parent)
    sys.path[:] = [p for p in sys.path if p != aqui]
    if str(SIM) not in sys.path:
        sys.path.insert(0, str(SIM))


def argumentos(descripcion: str) -> argparse.ArgumentParser:
    """Argumentos comunes del contrato (§2) y los de la app de Isaac."""
    from isaaclab.app import AppLauncher

    ap = argparse.ArgumentParser(description=descripcion)
    ap.add_argument("--entorno", required=True)
    ap.add_argument("--tarea", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--escena", help="escena.usd del parque. La escena de entrenamiento no la usa")
    ap.add_argument("--agarre", choices=["union", "succion"], default=os.getenv("VIAZ_AGARRE", "union"),
                    help="unión fija que se activa al sellar, o succión virtual. Perilla: VIAZ_AGARRE")
    AppLauncher.add_app_launcher_args(ap)
    return ap


def lanzar(a: argparse.Namespace, camaras: bool = False):
    """Crea la app de Isaac sin ventana. Las cámaras solo se activan si el comando graba video."""
    from isaaclab.app import AppLauncher

    a.headless = True
    a.enable_cameras = bool(camaras or a.enable_cameras)
    return AppLauncher(a).app


def crear_entorno(a: argparse.Namespace, num_envs: int, render: bool = False, **opciones):
    """Entorno instalar_panel de la corrida. Devuelve el entorno de gymnasium; el de Isaac Lab es .unwrapped."""
    import gymnasium as gym

    import rl
    from rl.entorno import crear_cfg

    rl.registrar()
    cfg = crear_cfg(a.entorno, a.tarea, a.robot, num_envs, device=a.device, agarre=a.agarre, **opciones)
    return gym.make(rl.ID_TAREA, cfg=cfg, render_mode="rgb_array" if render else None)


def cargar_politica(env_gym, checkpoint: str | Path):
    """Política de un checkpoint de entrenar.py, sin exploración. Devuelve (entorno para rsl_rl, política)."""
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
    from rsl_rl.runners import OnPolicyRunner

    from rl.agente_cfg import InstalarPanelPPOCfg

    cfg = InstalarPanelPPOCfg()
    cfg.device = env_gym.unwrapped.device
    env = RslRlVecEnvWrapper(env_gym, clip_actions=cfg.clip_actions)
    entrenador = OnPolicyRunner(env, cfg.to_dict(), log_dir=None, device=cfg.device)
    entrenador.load(str(checkpoint))
    return env, entrenador.get_inference_policy(device=cfg.device)


def gpu_mib() -> int | None:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=20)
        return int(r.stdout.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def ejecutar(app, trabajo, salida: Path | None = None) -> None:
    """Corre trabajo() y cierra la app. Si falla, imprime el error y sale con código 1.

    Isaac deja el código de salida en 0 aunque el script termine con una excepción.
    """
    try:
        informe = trabajo()
    except BaseException:  # noqa: BLE001
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
    terminar(app, informe, salida)


def terminar(app, informe: dict | None = None, salida: Path | None = None) -> None:
    """Escribe el informe, lo imprime y termina el proceso. Con "ok": false sale con código 1.

    No llama a app.close(): en el pod se queda colgado después de un entorno con GPU. Sale directo.
    """
    codigo = 0
    if informe is not None:
        texto = json.dumps(informe, ensure_ascii=False, indent=2)
        if salida is not None:
            salida.write_text(texto, encoding="utf-8")
        print(texto, flush=True)
        codigo = 0 if informe.get("ok", True) else 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(codigo)
