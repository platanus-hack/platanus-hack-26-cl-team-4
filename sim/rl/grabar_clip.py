"""Comando `grabar_clip` del contrato (docs/contrato-entorno-rl.md §5): un clip de la política de un checkpoint.

    $ISAACLAB_SH -p sim/rl/grabar_clip.py --entorno E --tarea T --robot R [--escena S] --checkpoint C
        --segundos 7 --salida clip.mp4 [--grilla]

Graba con la cámara lateral 3/4 fija, sin texto. Con --grilla abre con la vista de todas las copias.
Cada episodio instala un panel de la secuencia, al azar, con los anteriores ya instalados (RF-INT-18).

    ... grabar_clip.py --entorno E --tarea T --robot R --checkpoint C --secuencia --segundos 30 --salida clip.mp4

--secuencia graba un solo robot que instala la secuencia completa: entre paneles la base avanza con el
controlador programado. El clip termina cuando instala el último panel. Si la secuencia falla, descarta lo
grabado y graba la siguiente, hasta --intentos. --segundos es el tope de cada intento.
Con --oraculo, la secuencia la instala el oráculo (sim/rl/oraculo.py) en vez de una política: sirve para
revisar la cámara y el viaje de la base sin un checkpoint, y como plan B del demo (RF-INT-01).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl import comun  # noqa: E402

comun.preparar_ruta()
COPIAS = 16
COPIAS_GRILLA = 256
GRILLA_S = 1.5


def main() -> None:
    ap = comun.argumentos(__doc__)
    ap.add_argument("--checkpoint", type=Path)
    ap.add_argument("--oraculo", action="store_true", help="con --secuencia: instala el oráculo, sin checkpoint")
    ap.add_argument("--segundos", type=float, default=7.0)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--grilla", action="store_true")
    ap.add_argument("--secuencia", action="store_true", help="un robot instala todos los paneles, con la base móvil")
    ap.add_argument("--sin-fijar", action="store_true", help="en la secuencia, el panel instalado queda donde cayó")
    ap.add_argument("--intentos", type=int, default=4)
    ap.add_argument("--semilla", type=int)
    a = ap.parse_args()
    if not a.checkpoint and not (a.secuencia and a.oraculo):
        ap.error("falta --checkpoint")
    app = comun.lanzar(a, camaras=True)
    comun.ejecutar(app, lambda: grabar_secuencia(a) if a.secuencia else grabar(a))


def grabar_secuencia(a) -> dict:
    """Un solo robot: así la cámara no muestra la grilla de copias. Devuelve el informe del clip."""
    import torch

    from rl import grabacion

    env_gym = comun.crear_entorno(a, 1, render=True, paneles=0, secuencia=True, fijar_instalados=not a.sin_fijar,
                                  semilla=a.semilla)
    entorno = env_gym.unwrapped
    if a.oraculo:
        from rl import oraculo

        guia = oraculo.Oraculo(entorno)
        entorno.reset()

        def paso() -> bool:
            _, _, terminado, truncado, _ = entorno.step(guia.accion())
            return bool(terminado[0] | truncado[0])
    else:
        env, politica = comun.cargar_politica(env_gym, a.checkpoint)
        estado = {"obs": env.reset()[0]}

        def paso() -> bool:
            estado["obs"], _, fin, _ = env.step(politica(estado["obs"]))
            return bool(fin[0])
    grabacion.camara_lateral(entorno)
    grabacion.descartar_inicio(env_gym)
    informe = {"ok": False, "intentos": 0}
    with torch.inference_mode():
        for intento in range(1, a.intentos + 1):
            salida = grabacion.Video(a.salida)
            instalados, completa = 0, False
            for _ in range(int(a.segundos / entorno.step_dt)):
                fin = paso()
                if bool(entorno.panel_fin[0]):
                    instalados += int(entorno.final["exito"][0] > 0)
                if fin:   # el cuadro de este paso ya muestra la copia reiniciada: no se graba
                    completa = instalados == entorno.paneles
                    break
                salida.cuadro(env_gym.render())
            informe = {**salida.cerrar(), "ok": completa, "intentos": intento, "paneles_instalados": instalados,
                       "paneles": entorno.paneles, "fijar_instalados": not a.sin_fijar,
                       "instala": "oraculo" if a.oraculo else a.checkpoint.name}
            if completa:
                break
    return informe


def grabar(a) -> None:
    import torch

    from rl import grabacion

    env_gym = comun.crear_entorno(a, COPIAS_GRILLA if a.grilla else COPIAS, render=True, paneles=0, semilla=a.semilla)
    entorno = env_gym.unwrapped
    env, politica = comun.cargar_politica(env_gym, a.checkpoint)
    obs, _ = env.reset()
    salida = grabacion.Video(a.salida)
    pasos = int(a.segundos / entorno.step_dt)
    cambio = int(GRILLA_S / entorno.step_dt) if a.grilla else 0
    if a.grilla:
        grabacion.camara_grilla(entorno)
    else:
        grabacion.camara_lateral(entorno)
    grabacion.descartar_inicio(env_gym)
    with torch.inference_mode():
        for k in range(pasos):
            if a.grilla and k == cambio:
                grabacion.camara_lateral(entorno)
            obs, _, _, _ = env.step(politica(obs))
            salida.cuadro(env_gym.render())
    print(json.dumps(salida.cerrar()), flush=True)


if __name__ == "__main__":
    main()
