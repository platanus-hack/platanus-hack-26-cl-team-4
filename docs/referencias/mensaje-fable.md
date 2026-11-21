Fable: revisamos las 43 capturas del desarrollo de la escena, de la primera versión a la que aprobamos. Esto es lo que cambió en **calidad**, no en técnica. Úsalo como el nivel mínimo para cualquier escena, objeto o robot que construyas, no solo para paneles.

Referencias en el repo (rama `docs/calidad-virtualizacion`, PR #15): `docs/referencias/especificacion-perceptual.md`, con las capturas aprobadas y rechazadas al lado.

**Qué tiene que percibir quien mira:**

1. **Identidad.** Cada objeto se reconoce solo, sin leyenda. En la v1 eran símbolos (rectángulo azul = panel, caja amarilla = pila); en la aprobada, alguien de fuera nombra todo en 5 segundos.
2. **Verdad del material.** Cada superficie dice de qué está hecha y cómo responde a la luz: el vidrio refleja el cielo, el aluminio brilla en el canto, el acero galvanizado tiene manchas, la madera tiene veta y la tierra es granular. En blanco y negro se tendrían que distinguir igual.
3. **Una sola luz, coherente.** Un sol, todas las sombras en la misma dirección y con la misma dureza, y el cielo del mismo color que la luz del suelo. Nada de doble luz, cielo rosado sobre luz blanca ni escenas oscuras.
4. **Escala legible.** Sin cifras, el ojo calcula el tamaño gracias a los detalles conocidos (celdas, gravilla, veta). En la v1 la caja podía medir 20 cm o 20 m.
5. **Continuidad.** Nada delata que es un modelo: sin suelo cortado en dos, sin cosas flotando como losas, sin texturas que se repiten como baldosas hacia el horizonte.
6. **Sentido del lugar.** Se reconoce dónde es (Atacama: ocre pálido, gravilla, cielo despejado, bruma). Compáralo con los frames reales del cliente, no con "un desierto genérico".
7. **Coherencia.** Toda la toma al mismo nivel. Si un objeto sigue provisorio (como la caja amarilla bajo paneles detallados), la toma no está lista.
8. **Detalle donde mira el ojo.** Lo que el robot toca y lo que sale en primer plano tiene que aguantar la vista a 1 m.

**A la versión aprobada todavía le falta** (no la tomes como techo):
- la pila se lee como una caja con un panel de tapa, no como paneles apilados;
- el suelo se repite como baldosas a lo lejos;
- los paneles se ven apoyados sobre el tubo, sin sujeciones.

**Antes de decir "listo"**, haz estas 5 pruebas con las capturas:
1. la de los 5 segundos;
2. la de blanco y negro;
3. la de entrecerrar los ojos (una sola luz, nada "pegado");
4. la de mirar a 1 m;
5. la de compararla con la referencia aprobada: tiene que ser igual o mejor en las 8 cualidades.

Tus revisiones con números (ΔE del suelo, fracción de cielo, frecuencia de la textura, tamaño en pantalla) sirven para medir esto. Esta lista dice hacia dónde apuntan.

**Una regla más:** lo que ya está aprobado (`terreno_texturas_final.usd`) se reutiliza, no se regenera. Súbelo al repo en `sim/assets_aprobados/` con su ficha.
