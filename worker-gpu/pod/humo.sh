#!/bin/bash
# Prueba de humo del pod: Cartpole con PPO, headless, 4096 entornos, 100 iteraciones.
#
#   source /workspace/pod.env && bash worker-gpu/pod/humo.sh
#
# Referencia (RTX 5090, 2026-11-21): 62 s en total, ~150 000 pasos/s, recompensa final ~4,9.
set -euo pipefail
: "${ISAACLAB_SH:?Falta source /workspace/pod.env}"
LOG=${WORKSPACE:-/workspace}/humo.log
t0=$(date +%s)
cd "$(dirname "$ISAACLAB_SH")"
"$ISAACLAB_SH" -p scripts/reinforcement_learning/rsl_rl/train.py --task Isaac-Cartpole-v0 --headless \
	--num_envs 4096 --max_iterations 100 >"$LOG" 2>&1 || { tail -30 "$LOG"; exit 1; }
echo "total: $(( $(date +%s) - t0 )) s"
grep "Computation:" "$LOG" | tail -1
grep "Mean reward:" "$LOG" | tail -1
grep "Mean episode length:" "$LOG" | tail -1
