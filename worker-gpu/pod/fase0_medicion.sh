#!/bin/bash
# Fase 0 del agente Entorno: mide el error de la medición con un parque de geometría conocida.
#
#   bash worker-gpu/pod/fase0_medicion.sh DIR
#
# DIR trae entorno.json (la verdad). Genera la escena, graba un video caminando por el pasillo (Isaac), lo mide
# (MapAnything + SAM 3) y compara contra la verdad: DIR/comparacion.json.
set -e
D=${1:?falta la carpeta con entorno.json}
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ/sim"
/venv/isaac/bin/python generar_escena.py --dir "$D"
OMNI_KIT_ALLOW_ROOT=1 OMNI_KIT_ACCEPT_EULA=YES /venv/isaac/bin/python video_sintetico.py --dir "$D" --segundos 20 --fps 10 \
  2>&1 | grep -E "^\{|Error|Traceback" || true
test -f "$D/video_sintetico.mp4"
"${VIAZ_PYTHON_MEDIR:-/venv/medicion/bin/python}" medir_entorno.py --videos "$D/video_sintetico.mp4" --salida "$D"
"${VIAZ_PYTHON_MEDIR:-/venv/medicion/bin/python}" comparar_medidas.py --verdad "$D/entorno.json" \
  --medidas "$D/medidas_entorno.json" --salida "$D/comparacion.json"
