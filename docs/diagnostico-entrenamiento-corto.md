# Diagnóstico: por qué la prueba corta de entrenamiento dio 0 % de éxito

> Fecha: 2026-11-21. Corrida `178ab8fee014` en el pod (RTX 5090), con el entorno `sim/rl/` de la rama `feat/terreno-atacama`.
> Método: lectura del código del entorno y de `entrenar.log` y `metricas.jsonl`. **No se entrenó nada para este diagnóstico.**
> Robot de la corrida: el clon genérico de `leapting-mmr` (base de 1,6 × 1,0 m, pila sobre la base).

## 1. Resumen

- La corrida no fue un entrenamiento real. Usó `--max-horas 0.2`: 12 minutos, 170 iteraciones y 22 millones de pasos.
- La política aprendió a tomar el panel y a sostenerlo. No aprendió a llevarlo al tubo.
- La causa más probable es que los inicios con ayuda se acabaron a los 7 minutos.
- Un 0 % de éxito en 12 minutos no dice que el entorno esté mal.

## 2. Qué midió el registro

"Sellar" es que la ventosa toma el panel. Un episodio "con ayuda" parte en un punto del recorrido de referencia, a veces con el panel ya tomado.

| Iteración | Tiempo sellado | Choques por paso | Éxitos con ayuda | Éxitos sin ayuda |
|---|---|---|---|---|
| 0 | 4 % | 6,5 | 0,03 de 13,8 episodios | 0 |
| 80 | 95 % | 0,06 | 0,53 de 2,3 episodios | 0 |
| 169 | 98 % | 0 | Sin episodios con ayuda | 0 |

- La recompensa media subió de −1,1 a 14,4 en la iteración 72. Después quedó cerca de 13,8.
- Desde la iteración 108, todos los episodios duran el máximo: 419 pasos, sin choques y sin caídas.

## 3. Estado de cada afirmación

| Afirmación | Estado |
|---|---|
| La corrida duró 12 minutos y 170 iteraciones | Real, leído en `metricas.jsonl` |
| Al final la política sella el 98 % del tiempo | Real, leído en `entrenar.log` |
| Con ayuda, cerca de 1 de cada 4 episodios terminaba en éxito (iteración 80) | Real, leído en `entrenar.log` |
| La ayuda se acabó cerca de la iteración 100 | Calculado desde `entrenar.py`, no medido |
| La falta de ayuda causó el estancamiento | Inferido, sin probar |
| Sostener el panel sin moverlo es la mejor opción para la política | Inferido, sin probar |

## 4. Causa más probable: la ayuda depende de `--max-horas`

- `entrenar.py` parte con ayuda en el 70 % de los episodios (`ASISTIDO_INICIAL = 0.7`).
- La ayuda baja en línea recta y llega a 0 al 60 % de `--max-horas` (`ASISTIDO_HASTA = 0.6`).
- Con 0,2 horas, la ayuda llegó a 0 a los 7,2 minutos, cerca de la iteración 100.
- La recompensa dejó de subir en ese mismo tramo.
- Con 4 horas, la ayuda duraría 2,4 horas.

## 5. Segunda causa posible: quedarse quieto con el panel conviene

Los pesos salen de `sim/rl/exito.py`.

| Conducta | Recompensa |
|---|---|
| Sostener el panel sellado | 2 por segundo, sin riesgo |
| Acercar el panel a la meta | Hasta 4 por segundo más. Sube 1,6 por cada metro de avance |
| Choque del brazo o panel caído | −10, y el episodio termina |
| Éxito | +50 |

Un choque quita los 10 puntos y también todo lo que el episodio todavía podía pagar. Con ruido alto en las acciones, moverse con el panel arriesga más de lo que paga al principio. El final de la corrida calza con eso: episodios largos, sin choques, con el panel tomado.

## 6. Un dato sin explicar

- La recompensa media final es 13,85 por episodio de 14 segundos.
- Si la política sostiene el panel el 98 % del tiempo, la recompensa debería ser 28 o más.
- Falta saber si la medida `sellados` del registro engaña o si la recompensa se acumula de otra forma.
- Los clips de esa política ya no están en el pod.

## 7. Qué hacer antes de un entrenamiento largo

1. Grabar un clip del checkpoint final de la corrida y mirarlo. Resuelve el dato del punto 6.
2. Separar la duración de la ayuda de `--max-horas`, para que una prueba corta no la corte a los 7 minutos.
3. Si el clip muestra al brazo quieto con el panel, revisar el balance entre "sostener" y "llevar" en `exito.py`.

## 8. Lo que este diagnóstico no cubre

- El entorno `sim/rl/` no está en `main`. Son 22 archivos sin commit en una carpeta local de `feat/terreno-atacama`.
- La rama `feat/robot-leapting-fisica` cambia el robot: la pila va en un remolque y el marco de ventosas mide 1,9 m. El oráculo y la escena de entrenamiento se probaron con el clon genérico. Hay que probarlos de nuevo con el robot nuevo.
