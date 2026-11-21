# Diseño de la web de VIAZ

Plan hecho con la skill `frontend-design`. Si cambias la paleta, la tipografía o la estructura, actualiza este archivo.

## Brief (v2)
- **Qué vende la página:** la **idea** de VIAZ: una cadena de agentes de IA que crea la inteligencia de un robot real para una planta concreta. El robot instalando paneles es la **prueba**, al final, no el tema.
- **Audiencia:** jurado del hack, y jefes de proyecto de empresas que construyen parques solares en Chile.
- **Trabajo de la página:** que en 10 segundos se entienda qué hace VIAZ y por qué importa. Después, el detalle del flujo, el problema con datos verificados y el demo.
- **Requerimientos:** RF-WEB-19 (explicar el flujo completo en pasos), RF-WEB-06..08, 13..16 (demo precalculado). El flujo se explica, no se usa en vivo (v0.6).

## Color: mediodía en el desierto (sin cambios)
| Token | Hex | Uso |
|---|---|---|
| `--cielo` | `#E4EEF3` | Fondo de la página |
| `--tinta` | `#14253A` | Texto y la línea de la cadena |
| `--modulo` | `#22477E` | Datos, enlaces y lo que produce cada paso |
| `--acero` | `#6E7A86` | Texto secundario y reglas |
| `--tierra` | `#B98552` | Terreno del visor 3D |
| `--senal` | `#F4B400` | **Marca de "lo hace un agente de IA"** en la cadena. También el robot |

## Tipografía (sin cambios)
- **Archivo variable:** expandida (`wdth 125`) en títulos y en los nombres de los pasos, ancho normal en el texto.

## Estructura
```
┌──────────────────────────────────────────────────┐
│ VIAZ                          Probar con tu planta │
├──────────────────────────────────────────────────┤
│ HERO: la idea                                     │
│ Título expandido (2-3 líneas) + bajada de 1 frase │
│ [Ver el demo] [Cómo funciona]                     │
│                                                   │
│ ══●══════●══════●══════●══════●══════●══  cadena  │
│ Subir   Extraer  Elegir  Construir Entrenar Mostrar│
│ videos  entorno  robot   robot     intelig. result.│
│ (● amarillo = agente de IA; ● acero = persona/web)│
├──────────────────────────────────────────────────┤
│ El problema: 3-4 hechos con su fuente (frases)    │
├──────────────────────────────────────────────────┤
│ Cómo funciona: los 6 pasos en detalle             │
│ quién lo hace · qué produce                       │
├──────────────────────────────────────────────────┤
│ Por qué confiar: 4 principios                     │
├──────────────────────────────────────────────────┤
│ El demo (al final): visor 3D + resultados         │
├──────────────────────────────────────────────────┤
│ Equipo + probar con tu planta                     │
└──────────────────────────────────────────────────┘
```
- **Alineación:** todo alineado a la izquierda. La cadena ocupa todo el ancho del contenido.

## Principios
- **Una sola audacia: la cadena de agentes del hero.** Es una línea gruesa con 6 nodos y nombres expandidos, como una línea de producción. El amarillo marca solo los pasos que hace un agente de IA: el color comunica, no decora.
- **Un solo momento de movimiento:** al cargar, la línea se dibuja de izquierda a derecha y los nodos se encienden en orden, una vez. Con `prefers-reduced-motion`, aparece entera.
- **Hechos con fuente, en frases:** el problema se cuenta con datos verificados de `docs/investigacion-datasets.md`, cada uno con su enlace. Nada de números gigantes con etiqueta chica.
- **El demo es la prueba, al final:** el visor 3D y las métricas viven en su propia sección, con la honestidad de siempre ("sin física", "robot de referencia", "pendiente").
- **Numeración solo donde hay secuencia:** los 6 pasos del flujo van numerados. Los principios y los hechos no.

## Revisión contra lo genérico
- **v1 → v2:** el hero era el visor 3D del robot. Vendía el demo y no la idea. Ahora el hero es la cadena de agentes, y el visor pasa a la sección del demo.
- **Descartado:** una grilla de tarjetas iguales para los pasos ("SaaS card kit"). La cadena es una sola línea continua: los pasos dependen uno del otro, y la línea lo muestra.
- **Descartado:** estadísticas como números gigantes. Los hechos van como frases con la cifra adentro y la fuente al lado.
