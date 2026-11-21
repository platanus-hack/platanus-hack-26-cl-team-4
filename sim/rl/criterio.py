"""Cuándo se detiene el entrenamiento: criterio sobre la curva, no sobre el reloj. Sin Isaac.

El criterio mira la media móvil de las últimas VENTANA iteraciones de tres tasas, medidas sobre episodios terminados:
- éxito sin ayuda (episodios que partieron con la ventosa sobre la pila, sin inicio asistido),
- episodios con choque (un eslabón del brazo tocó algo o un panel instalado se movió),
- episodios con el panel caído.
Se cumple cuando las tres medias pasan su umbral durante RACHA iteraciones seguidas.
Después el entrenamiento sigue mientras la curva sube: termina cuando la media de éxito lleva PACIENCIA
iteraciones sin mejorar (sim/rl/entrenar.py). --max-horas sigue siendo el tope duro.
"""
from __future__ import annotations

VENTANA = 20             # iteraciones de la media móvil
RACHA = 20               # iteraciones seguidas que el criterio tiene que cumplirse
EXITO_MIN = 0.95         # éxito sin ayuda
CHOQUES_MAX = 0.01       # episodios con choque / episodios
CAIDAS_MAX = 0.005       # episodios con caída / episodios
PACIENCIA = 40           # iteraciones sin mejorar la media de éxito, después de cumplir, para terminar
MEJORA_MIN = 0.002       # una mejora menor que 0,2 puntos no cuenta


def medias(filas: list[dict], ventana: int = VENTANA) -> dict | None:
    """Tasas de las últimas `ventana` filas de curriculo.jsonl, sumando episodios. None si faltan iteraciones.

    Suma episodios y no promedia tasas: una iteración con pocos episodios no pesa lo mismo que una con muchos.
    Sin episodios sin ayuda en la ventana (todos asistidos) el éxito sin ayuda vale 0.
    """
    if len(filas) < ventana:
        return None
    ultimas = filas[-ventana:]
    sin_ayuda = sum(f["episodios_sin_ayuda"] for f in ultimas)
    exitos = sum(f["exitos_sin_ayuda"] for f in ultimas)
    total = sum(f["episodios_sin_ayuda"] + f["episodios_con_ayuda"] for f in ultimas)
    return {"exito": exitos / sin_ayuda if sin_ayuda else 0.0,
            "choques": sum(f["choques"] for f in ultimas) / total if total else 0.0,
            "caidas": sum(f["caidas"] for f in ultimas) / total if total else 0.0}


def cumple(m: dict | None) -> bool:
    return m is not None and m["exito"] >= EXITO_MIN and m["choques"] <= CHOQUES_MAX and m["caidas"] <= CAIDAS_MAX


def racha(previa: int, m: dict | None) -> int:
    """Iteraciones seguidas con el criterio cumplido, contando esta."""
    return previa + 1 if cumple(m) else 0


def sin_mejora(mejor: float, desde: int, exito: float) -> tuple[float, int]:
    """Lleva la mejor media de éxito y cuántas iteraciones pasaron desde que mejoró. Devuelve (mejor, desde)."""
    return (exito, 0) if exito > mejor + MEJORA_MIN else (mejor, desde + 1)


def terminar(racha_actual: int, iteraciones_sin_mejora: int) -> bool:
    """El criterio ya se sostuvo RACHA iteraciones y la curva dejó de subir."""
    return racha_actual >= RACHA and iteraciones_sin_mejora >= PACIENCIA
