#!/bin/bash
# La inteligencia más real (model_1164) en el robot detallado y el terreno detallado, con la física del entrenamiento:
# rieles a ras con el tubo más abajo, grapas físicas, ventosa con fuerza limitada y ráfagas de hasta 8 m/s.
source /workspace/pod.env
export VIAZ_DIR_POD=/workspace/entorno_rl DISPLAY=:1 OMNI_KIT_ALLOW_ROOT=1
export VIAZ_RIELES_BAJO_TUBO_M=0 VIAZ_AGARRE=succion VIAZ_VIENTO_M_S=8 VIAZ_GRAPAS=1
C=/workspace/entorno_rl/corridas/leapting_v2
cd /workspace/viaz-fisica
exec $ISAACLAB_SH -p sim/rl/en_vivo.py --entorno $C/entorno.json --tarea $C/tarea.json --robot $C/robot_cfg.py \
  --checkpoint /workspace/entorno_rl/entrenamiento_succion/checkpoints/model_1164.pt "$@"
