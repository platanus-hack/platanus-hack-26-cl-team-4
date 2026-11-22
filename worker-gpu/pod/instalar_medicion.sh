#!/bin/bash
# Entorno aparte para medir el parque en los videos (agente Entorno): MapAnything + SAM 3.
#
#   bash worker-gpu/pod/instalar_medicion.sh
#
# Crea /venv/medicion con su propio torch (cu128, para la RTX 5090). No toca /venv/isaac: MapAnything y SAM 3 piden
# versiones de librerías que romperían Isaac Lab. El runner lo usa con VIAZ_PYTHON_MEDIR (worker-gpu/pod/entorno_rl.env).
#
# SAM 3 es un modelo con acceso restringido: alguien del equipo tiene que aceptar su licencia en
# https://huggingface.co/facebook/sam3 e iniciar sesión en el pod (huggingface-cli login). Sin eso, la medición
# funciona igual, solo con la nube de puntos, y lo avisa en medidas_entorno.json.
set -e
# Algunos pods traen un mirror de PyPI que responde 429 (Too Many Requests): se usa el índice oficial.
export UV_INDEX_URL=https://pypi.org/simple PIP_INDEX_URL=https://pypi.org/simple UV_HTTP_TIMEOUT=120
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
DIR=${VIAZ_DIR_MEDICION:-/workspace/medicion}
mkdir -p "$DIR"
cd "$DIR"
test -x /venv/medicion/bin/python || uv venv /venv/medicion --python 3.12
source /venv/medicion/bin/activate
uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
test -d map-anything || git clone --depth 1 https://github.com/facebookresearch/map-anything.git
uv pip install -e ./map-anything
test -d sam3 || git clone --depth 1 https://github.com/facebookresearch/sam3.git
uv pip install -e ./sam3
uv pip install -r "$RAIZ/worker-gpu/requirements-medicion.txt"
python - <<'PY'
import torch
print("torch", torch.__version__, "cuda:", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
from huggingface_hub import snapshot_download
print("pesos MapAnything (Apache-2.0):", snapshot_download("facebook/map-anything-apache"))
from sam3.model_builder import build_sam3_image_model  # noqa: F401  (el código; los pesos piden login)
print("SAM 3 importa")
PY
echo "LISTO: VIAZ_PYTHON_MEDIR=/venv/medicion/bin/python"
