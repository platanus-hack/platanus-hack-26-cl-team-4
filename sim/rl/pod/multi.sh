#!/bin/bash
# Uso: multi.sh <script de sim/rl> [argumentos]. Corre desde la copia repo_multi con la corrida leapting.
source /workspace/pod.env
export VIAZ_DIR_POD=/workspace/entorno_rl
C=/workspace/entorno_rl/corridas/leapting
cd /workspace/entorno_rl/repo_multi
script=$1; shift
exec $ISAACLAB_SH -p sim/rl/$script --entorno $C/entorno.json --tarea $C/tarea.json --robot $C/robot_cfg.py "$@"
