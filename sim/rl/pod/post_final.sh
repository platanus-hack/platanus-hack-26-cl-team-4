#!/bin/bash
# Evaluación, clips y USD de model_609 con el código final (copias a 10,25 m y cámara que cubre la secuencia).
R=/workspace/entorno_rl; D=$R/entrenamiento_multi; E=$R/evaluacion_multi/model_609_final; CL=$R/clips_multi/final
cd $R
CK=$D/checkpoints/model_609.pt
mkdir -p $E $CL
VIAZ_SIN_TEXTURAS=1 ./multi.sh prueba_entorno.py --salida $E/prueba_entorno.json --num-envs 256 > $E/prueba_entorno.log 2>&1; echo "prueba entorno $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --episodios 100 --salida $E > $E/evaluar.log 2>&1; echo "evaluar $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --secuencias 100 --salida $E/secuencia > $E/secuencia.log 2>&1; echo "secuencia $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --secuencias 100 --sin-fijar --salida $E/secuencia_sin_fijar > $E/secuencia_sin_fijar.log 2>&1; echo "secuencia sin fijar $?"
VIAZ_SIN_TEXTURAS=1 ./multi.sh evaluar.py --checkpoint $CK --episodios 1000 --salida $E/mil > $E/mil.log 2>&1; echo "mil $?"
./multi.sh evaluar.py --checkpoint $CK --secuencias 16 --salida $E/secuencia_usd --usd $E/secuencia_usd/06-secuencia-paneles-animacion.usd > $E/secuencia_usd.log 2>&1; echo "usd $?"
./multi.sh grabar_clip.py --checkpoint $CK --secuencia --segundos 45 --salida $CL/clip_5_secuencia_4_paneles_model_609.mp4 > $CL/clip_5.log 2>&1; echo "clip secuencia $?"
k=0
while read nombre it; do
  k=$((k+1))
  ./multi.sh grabar_clip.py --checkpoint $D/checkpoints/model_$it.pt --segundos 7 --salida $CL/clip_${nombre}_model_$it.mp4 > $CL/clip_$k.log 2>&1; echo "clip $nombre $?"
done < $R/clips_multi/hitos.txt
echo LISTO
