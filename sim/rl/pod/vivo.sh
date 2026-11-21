#!/bin/bash
# Uso: vivo.sh [argumentos de en_vivo.py]. La política final controla al robot detallado en el terreno realista,
# con ventana en el escritorio VNC (:1). Corre desde la copia repo_vivo: no toca repo_multi.
source /workspace/pod.env
export VIAZ_DIR_POD=/workspace/entorno_rl
export DISPLAY=:1 OMNI_KIT_ALLOW_ROOT=1
C=/workspace/entorno_rl/corridas/leapting
cd /workspace/entorno_rl/repo_vivo
exec $ISAACLAB_SH -p sim/rl/en_vivo.py --entorno $C/entorno.json --tarea $C/tarea.json --robot $C/robot_cfg.py \
  --checkpoint /workspace/entorno_rl/entrenamiento_multi/checkpoints/model_609.pt "$@"
