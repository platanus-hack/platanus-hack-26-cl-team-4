# Assets aprobados

Escenas, objetos y robots que **pasaron la rúbrica** de [`docs/calidad-virtualizacion.md`](../../docs/calidad-virtualizacion.md). Se reutilizan; **no se regeneran**.

## Registro

| Nombre | Tipo | Dominio | Aprobado | Carpeta |
|---|---|---|---|---|
| _(vacío: registrar aquí el primero)_ | | | | |

## Robots: de "comprobado" a "aprobado"

El backend guarda solo robots **comprobados**: su `ensamblaje.json` pasó `validar_robot` en una escena. Están en el almacén, en `modelos/<clave>/ensamblaje.json` y `modelos/<clave>/modelo.json` ([`backend/viaz/modelos.py`](../../backend/viaz/modelos.py)). Comprobado **no** quiere decir que pasó la rúbrica.

Para promover uno a **aprobado**, una persona:

1. Lee `modelo.json` (`clave`, `robot_id`, `corrida_id`) y baja `ensamblaje.json`, `robot_cfg.py` y `clon.json` de esa corrida.
2. Renderiza las 4 vistas fijas del robot (`1_general.png` … `4_escala.png`) y las **mira**.
3. Evalúa con la rúbrica de [`calidad-virtualizacion.md`](../../docs/calidad-virtualizacion.md) §5. Todo ≥ 4. Máximo 3 intentos.
4. Crea `sim/assets_aprobados/<robot id>/` con `ensamblaje.json`, las 4 vistas, `evaluacion.md` y `ficha.md`. En la ficha anota la clave.
5. Agrega la fila al registro y abre un PR.

El código todavía no lee esta carpeta ni escribe `fidelidad: verificado`. La política entrenada nunca se reusa.

## Qué lleva cada carpeta `sim/assets_aprobados/<nombre>/`

| Archivo | Contenido |
|---|---|
| `<nombre>.usd` (o `receta.py`) | El asset, o el script que lo genera de forma determinista |
| `1_general.png` … `4_escala.png` | Las 4 vistas fijas del intento aprobado |
| `evaluacion.md` | La rúbrica con notas y evidencia |
| `ficha.md` | La ficha de abajo |

## Ficha (`ficha.md`)

```markdown
# <nombre>

- **Tipo:** escena / objeto / robot
- **Dominio:** solar / bodega / minería / ... (o "general")
- **Papel:** A / B / C
- **Medidas y de dónde salen:** <archivo y campo de cada medida>
- **Supuestos:** <datos que faltaban y cómo se resolvieron>
- **Materiales:** <material por pieza>
- **Intentos hasta aprobar:** N
- **Qué cambió para que pasara:** <lo que hizo la diferencia respecto al intento anterior>
- **Cómo reutilizarlo:** <ruta, parámetros que se pueden cambiar y cuáles no>
```
