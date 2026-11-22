# Inventario: sala de eventos del pitch

> Fuente: `IMG_2653.mov` (36,7 s, 19 frames cada 2 s). Medidas en [`entorno_evento.json`](../../../backend/viaz/fixtures/entorno_evento.json), todas estimadas (confianza 0,4 a 0,6). Generador: [`sim/generar_escena.py`](../../../sim/generar_escena.py) + [`sim/detalles.py`](../../../sim/detalles.py).

Papel: **A** el robot interactúa con él · **B** visible cerca · **C** fondo.

| Objeto | Papel | Origen | Material | Medidas (archivo) |
|---|---|---|---|---|
| Piso de madera | A (el robot camina) | Propio (cubo con colisión) | Madera con textura, roce 0,5 (supuesto) | `espacio` 18 × 12 m |
| Unitree H1 | Robot | Isaac Lab (`H1_MINIMAL_CFG`), mallas del fabricante | Del modelo | `clon.json → modelo` |
| Sillas (2 bloques) | B | Propio (`detalle: sillas`): asiento, respaldo, 4 patas | Plástico negro, patas metal negro | Bloques 3 × 8 m; silla 0,44 m, paso 0,55 × 0,52 m (supuesto) |
| Tarima | B | Propio (`detalle: tarima`) | Madera con textura | 3 × 8 × 0,35 m |
| Pantalla LED | B | Propio (`detalle: pantalla`) | Marco metal negro, cara azul oscuro | 5 × 2,8 m |
| Mesa alta | C | Propio (`detalle: mesa_alta`) | Cubierta madera, pie metal | Ø 0,6 m, 1,1 m |
| Graderías | C | Propio (`detalle: graderia`), 2 escalones | Madera | 8 × 1,2 × 0,9 m |
| Letras de marca | C | Propio (`detalle: letras`): 3 bloques genéricos, sin copiar la marca | Blanco mate | 3 × 1 m |
| Parlante | C | Propio (`detalle: parlante`) | Gabinete negro, rejilla de tela | 0,5 × 0,5 × 1 m |
| Mesa técnica | C | Propio (caja) | Color de categoría | 0,8 × 1,4 × 0,75 m |
| Paredes | C | Propio (cubos) | Blanco | Alto 3,6 m |

## Supuestos registrados

- Todas las medidas salen de mirar frames, sin escala conocida: confianza ≤ 0,6.
- Roce del piso de madera con la suela del robot: 0,5 (`sim/fisica.py → SUELOS`).
- Medidas internas de las piezas (asiento, respaldo, patas, escalones): `sim/detalles.py → DIMENSIONES`.
- No se modelan el mural, los ductos del techo, las lámparas colgantes ni el ventanal.

## Estado

- Sin rúbrica todavía: falta renderizar las 4 vistas (`sim/animar/vistas.py`) y evaluarlas.
