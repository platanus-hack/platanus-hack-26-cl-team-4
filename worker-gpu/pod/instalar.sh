#!/bin/bash
# Deja un pod de Vast.ai listo para Isaac Sim 5.1 + Isaac Lab v2.3.2, en un solo comando.
#
#   bash worker-gpu/pod/instalar.sh
#
# Idempotente: si se corre de nuevo, salta lo que ya está hecho.
# Lecciones del 2026-11-21 en docs/infraestructura.md §5.
set -euo pipefail

export OMNI_KIT_ACCEPT_EULA=YES TERM=xterm
WS=${WORKSPACE:-/workspace}
VENV=/venv/isaac
ISAACLAB=$WS/IsaacLab
ISAACLAB_TAG=v2.3.2
ASSETS=$WS/isaac_assets
ASSETS_RAIZ=$ASSETS/Assets/Isaac/5.1
S3=https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1
POD=$(cd "$(dirname "$0")" && pwd)
t0=$(date +%s)
paso() { echo "[$(( $(date +%s) - t0 ))s] $*"; }

paso "driver"
driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
case "$driver" in
	580.*) echo "driver $driver: ok" ;;
	*) echo "driver $driver: Isaac Sim 5.1 necesita la rama 580. Cambia de máquina." >&2; exit 1 ;;
esac

paso "región"
pais=${VIAZ_PAIS:-$(curl -s -m 10 ipinfo.io/country || echo "??")}
echo "país: $pais"
if [ "$pais" = "CN" ]; then
	# El host trae el espejo de USTC, que corta con 429. Aliyun fue el más rápido (15 MB/s).
	export UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
	# El host exporta PIP_TRUSTED_HOST para USTC: se borra para que pip verifique el certificado.
	unset PIP_TRUSTED_HOST
	TORCH_URL=https://mirrors.aliyun.com/pytorch-wheels/cu128
else
	TORCH_URL=https://download.pytorch.org/whl/cu128
fi
export UV_CONCURRENT_DOWNLOADS=8

paso "librerías del sistema"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libglu1-mesa libxt6 libxrandr2 libxinerama1 libxcursor1 \
	libxi6 vulkan-tools build-essential cmake >/dev/null
vulkaninfo --summary 2>/dev/null | grep -m1 deviceName \
	|| { echo "Vulkan no ve la GPU: crea la instancia con NVIDIA_DRIVER_CAPABILITIES=all." >&2; exit 1; }

paso "python 3.11"
[ -x $VENV/bin/python ] || uv venv -q --seed -p 3.11 $VENV
PY=$VENV/bin/python

paso "pytorch cu128"
# Antes que Isaac Lab: así isaaclab.sh no lo vuelve a bajar desde download.pytorch.org (1 MB/s desde China).
if ! $PY -c "import torch,sys;sys.exit(0 if torch.__version__=='2.7.0+cu128' else 1)" 2>/dev/null; then
	mkdir -p $WS/wheels
	for f in "torch-2.7.0%2Bcu128-cp311-cp311-manylinux_2_28_x86_64.whl" \
		"torchvision-0.22.0%2Bcu128-cp311-cp311-manylinux_2_28_x86_64.whl"; do
		curl -sfL --retry 3 -m 900 -o "$WS/wheels/${f//%2B/+}" "$TORCH_URL/$f"
	done
	uv pip install -q --python $PY $WS/wheels/torch-2.7.0+cu128-*.whl $WS/wheels/torchvision-0.22.0+cu128-*.whl
fi

paso "isaac sim 5.1"
uv pip install -q --python $PY "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com

paso "isaac lab $ISAACLAB_TAG"
[ -d $ISAACLAB ] || git clone -q -c advice.detachedHead=false --branch $ISAACLAB_TAG https://github.com/isaac-sim/IsaacLab.git $ISAACLAB
# flatdict 4.0.1 no compila con setuptools >= 80 (sin pkg_resources).
uv pip install -q --python $PY "setuptools<80" wheel
uv pip install -q --python $PY --no-build-isolation flatdict==4.0.1
(source $VENV/bin/activate && cd $ISAACLAB && ./isaaclab.sh --install >$WS/isaaclab_install.log 2>&1) \
	|| { tail -20 $WS/isaaclab_install.log >&2; exit 1; }

paso "modelos de omniverse"
if [ "$pais" = "CN" ]; then
	# Isaac no logra bajar desde S3 en China, aunque curl sí. Copia local y .kit apuntando a ella.
	[ -x /venv/usdtools/bin/python ] || { uv venv -q -p 3.11 /venv/usdtools && uv pip install -q --python /venv/usdtools/bin/python usd-core; }
	grep -v '^#' $POD/assets.txt | xargs /venv/usdtools/bin/python $POD/espejo_assets.py --destino $ASSETS
	sed -i "s#$S3#$ASSETS_RAIZ#g" $ISAACLAB/apps/*.kit
	echo "kits apuntan a $ASSETS_RAIZ"
fi

paso "entorno"
cat > $WS/pod.env <<EOF
export OMNI_KIT_ACCEPT_EULA=YES TERM=xterm
export ISAACLAB_SH=$ISAACLAB/isaaclab.sh
source $VENV/bin/activate
EOF
$PY -c "import torch;print('torch',torch.__version__,torch.cuda.get_device_name(0),torch.cuda.get_arch_list()[-1])"
paso "LISTO. Usa: source $WS/pod.env && bash $POD/humo.sh"
