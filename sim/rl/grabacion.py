"""Video del entorno RL: cuadros de la cámara de la vista a un mp4. Solo corre en el pod.

Formato del contrato (docs/contrato-entorno-rl.md §5): 1280 × 720, 30 fps, H.264, sin texto encima.
Necesita la app con cámaras (comun.lanzar(a, camaras=True)) y el entorno con render=True.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import viaz_escena  # noqa: E402
import video  # noqa: E402

CUADROS_DE_AJUSTE = 8   # el trazado de rayos necesita unos cuadros para limpiar el ruido después de mover la cámara
CUADROS_DE_CARGA = 30   # los primeros cuadros de la cámara salen negros o sin texturas: se descartan antes de grabar


class Video:
    """Escribe cuadros RGB (alto, ancho, 3) a un mp4 con ffmpeg, sin archivos intermedios."""

    def __init__(self, salida: str | Path, fps: int = video.FPS):
        self.salida = Path(salida)
        self.salida.parent.mkdir(parents=True, exist_ok=True)
        self.cuadros = 0
        self.brillo = 0.0
        self.proceso = subprocess.Popen(
            [video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{video.ANCHO}x{video.ALTO}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             str(self.salida)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def cuadro(self, rgb) -> None:
        if rgb.shape[:2] != (video.ALTO, video.ANCHO):
            raise ValueError(f"cuadro de {rgb.shape[1]}x{rgb.shape[0]}, se esperaba {video.ANCHO}x{video.ALTO}")
        self.proceso.stdin.write(rgb[..., :3].tobytes())
        self.brillo += float(rgb.mean())
        self.cuadros += 1

    def cerrar(self) -> dict:
        self.proceso.stdin.close()
        error = self.proceso.stderr.read().decode(errors="replace")
        if self.proceso.wait() != 0:
            raise RuntimeError(f"ffmpeg falló: {error[-800:]}")
        return {"archivo": str(self.salida), "cuadros": self.cuadros, "segundos": round(self.cuadros / video.FPS, 2),
                "brillo_medio": round(self.brillo / max(1, self.cuadros), 1)}


def camara_lateral(env, copia: int = 0) -> None:
    """Cámara lateral 3/4 fija sobre una copia (la de cfg.viewer)."""
    origen = env.scene.env_origins[copia].tolist()
    ojo, mira = env.cfg.viewer.eye, env.cfg.viewer.lookat
    env.sim.set_camera_view([origen[k] + ojo[k] for k in range(3)], [origen[k] + mira[k] for k in range(3)])
    _ajustar(env)


def camara_grilla(env) -> None:
    """Cámara alta que muestra todas las copias (RF-INT-13)."""
    c = viaz_escena.camara_entrenamiento(env.num_envs, env.cfg.scene.env_spacing)
    env.sim.set_camera_view(list(c["ojo_m"]), list(c["mira_m"]))
    _ajustar(env)


def descartar_inicio(env_gym) -> None:
    """Pide cuadros sin grabarlos hasta que la cámara entrega la escena con sus texturas. Medido: llegan antes del cuadro 6."""
    for _ in range(CUADROS_DE_CARGA):
        env_gym.render()


def _ajustar(env) -> None:
    for _ in range(CUADROS_DE_AJUSTE):
        env.sim.render()
