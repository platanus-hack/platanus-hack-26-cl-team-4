#!/bin/bash
# Corrida real sin Render ni R2 (pendientes, problema 10): API + orquestador + runner (modo isaac) en el pod.
# El almacén es local y el runner baja los archivos por localhost: el pod ve su propio localhost.
# Probado el 2026-11-22: la corrida 5e72191bab0c terminó en `listo` (escena, selección, clon, validación,
# entrenamiento, monitor, clips y evaluación en Isaac).
#
# Uso, desde la raíz del repo en el pod:
#   bash worker-gpu/pod/todo_en_el_pod.sh            # levanta los tres procesos en segundo plano
#   bash worker-gpu/pod/todo_en_el_pod.sh parar      # los detiene
# Variables útiles antes de lanzar: VIAZ_AGENTES (fijo/claude), ANTHROPIC_API_KEY, VIAZ_ENTORNO_MANUAL,
# VIAZ_TAREA_MANUAL, VIAZ_TAREA_AGENTE, VIAZ_HORAS_ENTRENAMIENTO, VIAZ_EPISODIOS_EVALUACION.
# Para ver la web desde un Mac: ssh -L 8100:localhost:8100 viaz-pod  y  NEXT_PUBLIC_API_URL=http://localhost:8100
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
DATOS="${VIAZ_DATOS_POD:-/workspace/viaz-datos}"
PUERTO="${VIAZ_PUERTO:-8100}"
PY_BACKEND="${VIAZ_PYTHON_BACKEND:-/venv/viaz-backend/bin/python}"
mkdir -p "$DATOS"
if [ "${1:-}" = "parar" ]; then
  for f in api orquestador runner; do
    [ -f "$DATOS/$f.pid" ] && kill "$(cat "$DATOS/$f.pid")" 2>/dev/null || true
    rm -f "$DATOS/$f.pid"
  done
  echo "detenidos"; exit 0
fi
export DATABASE_URL="sqlite:///$DATOS/viaz.db" VIAZ_ALMACEN=local VIAZ_DIR_LOCAL="$DATOS/archivos"
export VIAZ_URL_PUBLICA="http://localhost:$PUERTO" WORKER_TOKEN="${WORKER_TOKEN:-dev-token}"
export VIAZ_ORIGENES="${VIAZ_ORIGENES:-http://localhost:3000,http://localhost:3001}"
export VIAZ_FLUJO="${VIAZ_FLUJO:-rl}" VIAZ_MAX_FINALISTAS="${VIAZ_MAX_FINALISTAS:-1}"
cd "$RAIZ/backend"
setsid nohup "$PY_BACKEND" -m uvicorn viaz.api:app --host 127.0.0.1 --port "$PUERTO" > "$DATOS/api.log" 2>&1 < /dev/null &
echo $! > "$DATOS/api.pid"
sleep 3
setsid nohup "$PY_BACKEND" -m viaz.orquestador > "$DATOS/orquestador.log" 2>&1 < /dev/null &
echo $! > "$DATOS/orquestador.pid"
# shellcheck disable=SC1091
source /workspace/pod.env
cd "$RAIZ"
# shellcheck disable=SC1091
source worker-gpu/pod/entorno_rl.env
export VIAZ_DIR_POD="$DATOS/pod" VIAZ_API="http://localhost:$PUERTO"
setsid nohup "$PY_BACKEND" worker-gpu/runner.py --modo isaac > "$DATOS/runner.log" 2>&1 < /dev/null &
echo $! > "$DATOS/runner.pid"
sleep 2
curl -sf "http://localhost:$PUERTO/salud" && echo
echo "listo: API en http://localhost:$PUERTO · registros en $DATOS/{api,orquestador,runner}.log"
