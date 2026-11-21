#!/bin/bash
# Evaluación, clips y USD de la corrida entrenamiento_multi. Uso: post_multi.sh [checkpoint]
R=/workspace/entorno_rl; D=$R/entrenamiento_multi; E=$R/evaluacion_multi; CL=$R/clips_multi
cd $R
CK=${1:-$(ls $D/checkpoints/model_*.pt | sort -t_ -k3 -n | tail -1)}
N=$(basename $CK .pt)
echo "checkpoint final: $CK"
mkdir -p $E/$N $CL
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --episodios 100 --salida $E/$N > $E/$N/evaluar.log 2>&1; echo "evaluar $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --secuencias 100 --salida $E/$N/secuencia > $E/$N/secuencia.log 2>&1; echo "secuencia $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --secuencias 100 --sin-fijar --salida $E/$N/secuencia_sin_fijar > $E/$N/secuencia_sin_fijar.log 2>&1; echo "secuencia sin fijar $?"
if [ ! -e /workspace/vivo/06-secuencia-paneles-animacion.usd ]; then
  ./multi.sh evaluar.py --checkpoint $CK --secuencias 16 --salida $E/$N/secuencia_usd --usd /workspace/vivo/06-secuencia-paneles-animacion.usd > $E/$N/secuencia_usd.log 2>&1; echo "usd $?"
fi
./multi.sh grabar_clip.py --checkpoint $CK --secuencia --segundos 45 --salida $CL/clip_5_secuencia_4_paneles_$N.mp4 > $CL/clip_5.log 2>&1; echo "clip secuencia $?"
python3 elegir_hitos_multi.py $D > $CL/hitos.txt; cat $CL/hitos.txt
k=0
while read nombre it; do
  k=$((k+1))
  ./multi.sh grabar_clip.py --checkpoint $D/checkpoints/model_$it.pt --segundos 7 --salida $CL/clip_${nombre}_model_$it.mp4 > $CL/clip_$k.log 2>&1; echo "clip $nombre $?"
done < $CL/hitos.txt
echo LISTO
