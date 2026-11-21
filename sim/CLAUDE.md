# sim/: reglas para agentes que construyen en Isaac Sim / Isaac Lab

Se suman a las reglas del [`CLAUDE.md`](../CLAUDE.md) raíz. Estándar completo: [`docs/calidad-virtualizacion.md`](../docs/calidad-virtualizacion.md).

## Antes de escribir código de escena, objeto o robot

1. Leer [`sim/assets_aprobados/README.md`](assets_aprobados/README.md). Si existe un asset aprobado para lo que se pide, **usarlo**.
2. Escribir el inventario en `docs/referencias/<escena>/inventario.md`:

| Objeto | Papel (A/B/C) | Origen (aprobado / Isaac / propio) | Material | Medidas (archivo de origen) |
|---|---|---|---|---|

## Al construir

- Mallas visuales detalladas y mallas de colisión simples, por separado.
- Materiales PBR (MDL / OmniPBR) con valores físicos plausibles. Nunca el gris por defecto.
- Luz de cúpula (HDRI del tipo de lugar) + sol o luces de área, con sombras.
- Unidades en metros, Z arriba. Medidas solo de `entorno.json`, `tarea.json`, `robot.json` o `robot_cfg.py` (`PARAMETROS`).
- **Un cambio por intento**, para saber qué arregló qué.

## Antes de decir "listo"

1. Renderizar las 4 vistas fijas en `docs/referencias/<escena>/intento_NN/`: `1_general.png`, `2_detalle.png`, `3_robot.png`, `4_escala.png` (con figura humana de 1,75 m y puerta de 2,1 m).
2. **Abrir y mirar las 4 imágenes.** Compararlas con `docs/referencias/aprobadas/` y `docs/referencias/rechazadas/`.
3. Escribir `evaluacion.md` con la rúbrica (geometría, materiales, iluminación, escala, limpieza, fidelidad), nota de 1 a 5 y evidencia por criterio.
4. Algún criterio < 4: corregir solo eso y repetir. **Máximo 3 intentos**, después pedir revisión humana.
5. Aprobado: copiar a `sim/assets_aprobados/<nombre>/` con su ficha y **qué cambió para que pasara**.

## Nunca

- Regenerar desde cero algo aprobado.
- Declarar "listo" leyendo el código en lugar de mirar las capturas.
- Inventar medidas sin registrarlas como supuesto.
- Dejar una pieza del robot o un objeto que el robot toca como primitiva sin material.
