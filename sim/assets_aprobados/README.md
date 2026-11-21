# Assets aprobados

Escenas, objetos y robots que **pasaron la rúbrica** de [`docs/calidad-virtualizacion.md`](../../docs/calidad-virtualizacion.md). Se reutilizan; **no se regeneran**.

## Registro

| Nombre | Tipo | Dominio | Aprobado | Carpeta |
|---|---|---|---|---|
| _(vacío: registrar aquí el primero)_ | | | | |

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
