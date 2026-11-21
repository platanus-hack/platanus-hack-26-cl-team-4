"""Elige los 4 checkpoints de los clips (RF-INT-13) desde curriculo.jsonl y los checkpoints guardados.

    python3 elegir_hitos.py DIR_ENTRENAMIENTO  ->  hitos.json en esa carpeta y una línea "nombre iteracion" por clip

Hitos sobre la tasa de éxito sin ayuda, suavizada con una media móvil de VENTANA iteraciones.
Si un hito no se alcanzó, el clip usa el reemplazo y su nombre lo dice.
"""
import json
import re
import sys
from pathlib import Path

VENTANA = 10

carpeta = Path(sys.argv[1])
filas = [json.loads(linea) for linea in (carpeta / "curriculo.jsonl").read_text().splitlines() if linea.strip()]
guardados = sorted(int(re.search(r"model_(\d+)\.pt", p.name).group(1)) for p in (carpeta / "checkpoints").glob("model_*.pt"))
ultima = filas[-1]["iteracion"]


def media(clave: str, k: int) -> float:
    valores = [f[clave] for f in filas[max(0, k - VENTANA + 1):k + 1] if f[clave] is not None]
    return sum(valores) / len(valores) if valores else 0.0


def desde(iteracion: int) -> int:
    """Primer checkpoint guardado en esa iteración o después."""
    return next((g for g in guardados if g >= iteracion), guardados[-1])


def cerca(iteracion: float) -> int:
    return min(guardados, key=lambda g: abs(g - iteracion))


def primera(condicion) -> int | None:
    return next((f["iteracion"] for k, f in enumerate(filas) if condicion(k, f)), None)


primer = primera(lambda k, f: (f["tasa_exito_sin_ayuda"] or 0) > 0)
mitad = primera(lambda k, f: media("tasa_exito_sin_ayuda", k) >= 0.5)
umbral = primera(lambda k, f: media("tasa_exito_sin_ayuda", k) >= 0.9)
mejor = max(guardados, key=lambda g: media("recompensa_media", min(g, len(filas) - 1)))

hitos = [{"nombre": "1_inicio", "iteracion": guardados[0], "hito": "inicio", "alcanzado": True}]
hitos.append({"nombre": "2_primer_exito", "iteracion": desde(primer), "hito": "primer_exito", "alcanzado": True, "en_iteracion": primer}
             if primer is not None else
             {"nombre": "2_checkpoint_25pct_sin_primer_exito", "iteracion": cerca(0.25 * ultima), "hito": "primer_exito", "alcanzado": False})
hitos.append({"nombre": "3_exito_50", "iteracion": desde(mitad), "hito": "exito_50", "alcanzado": True, "en_iteracion": mitad}
             if mitad is not None else
             {"nombre": "3_intermedio_sin_exito_50", "iteracion": cerca((hitos[1]["iteracion"] + ultima) / 2), "hito": "exito_50", "alcanzado": False})
hitos.append({"nombre": "4_umbral_alcanzado", "iteracion": desde(umbral), "hito": "umbral_alcanzado", "alcanzado": True, "en_iteracion": umbral}
             if umbral is not None else
             {"nombre": "4_mejor_recompensa", "iteracion": mejor, "hito": "mejor_recompensa", "alcanzado": True})
for h in hitos:
    k = min(h["iteracion"], len(filas) - 1)
    h["exito_sin_ayuda_media"] = round(media("tasa_exito_sin_ayuda", k), 4)
    h["exito_con_ayuda_media"] = round(media("tasa_exito_con_ayuda", k), 4)
    h["tiempo_s"] = filas[k]["tiempo_s"]
(carpeta / "hitos.json").write_text(json.dumps({"ventana": VENTANA, "ultima_iteracion": ultima, "hitos": hitos}, indent=2, ensure_ascii=False))
for h in hitos:
    print(h["nombre"], h["iteracion"])
