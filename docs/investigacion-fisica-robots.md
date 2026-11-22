# Investigación: medidas físicas de Bison, BUILDEX E y Maximo

> Estado: **consultado el 2026-11-21**. Cada dato lleva su fuente.
> `publicado` = una fuente lo dice con texto. `estimado` = lo medimos en una foto o render, con una escala conocida.
> `sin dato` = no hay texto ni una foto que permita medirlo.
> Un estimado nunca se presenta como publicado.

## 1. Resumen

| Dato | `relu-bison` | `trinatracker-buildex-e` | `aes-maximo` |
|---|---|---|---|
| Largo | publicado (5,2 m) | publicado* (4,98 m) | sin dato |
| Ancho | publicado (2,1 m) | publicado* (2,47 m) | sin dato |
| Alto total | publicado (2,45 m) | publicado* (2,28 m) | sin dato |
| Masa | publicado (9 t) | publicado* (8 t; otra fuente dice 9 t) | sin dato |
| Tracción | publicado (orugas de acero) | estimado (orugas en los renders) | publicado (orugas) |
| Altura de cubierta | estimado | estimado | sin dato (solo proporción) |
| Posición del brazo (`brazo_x_m`) | estimado | estimado | sin dato (solo proporción) |
| Marca y modelo del brazo | sin dato | sin dato | sin dato |
| Carga útil del brazo | publicado (50 kg) | publicado* (100 kg, ver nota) | sin dato |
| Alcance | publicado ("más de 5 m") | sin dato (solo altura de montaje) | sin dato |
| Efector | estimado (ventosas en fotos) | estimado (ventosas en render) | estimado (ventosas en fotos) |
| Marco de ventosas | sin dato | sin dato | sin dato (solo proporción) |
| Origen de los paneles | estimado (pallets sobre el robot) | publicado* (horquilla propia) | publicado (cuna sobre el robot) |
| Remolque | no tiene (estimado) | no tiene (publicado*) | no tiene (publicado) |
| Gabinete | estimado | estimado | sin dato (solo proporción) |

\* Trinabot: la página del fabricante **no cargó** (error TLS). Los valores vienen del índice del buscador web, que sí leyó la página.
No pudimos copiar la cita exacta. Ver sección 3.

## 2. `relu-bison` (Beijing Relu Robotics, Bison)

Fuente principal: [pv magazine, 2026-07-17](https://www.pv-magazine.com/2026/07/17/ai-powered-9-ton-tracked-robot-for-large-scale-pv-construction/). Las 3 fotos del artículo son de Relu.

| Dato | Valor | Estado | Fuente | Cita o método |
|---|---|---|---|---|
| Largo × ancho × alto | 5,2 × 2,1 × 2,45 m | publicado | pv magazine | "The platform measures 5,200 mm × 2,100 mm × 2,450 mm" |
| Masa | 9 000 kg | publicado | pv magazine | "features a 9-ton platform". No dice si incluye el combustible ni la carga de módulos |
| Tracción | orugas de acero, 3,44 m × 0,40 m | publicado | pv magazine | "steel tracks measuring 3,440 mm in length and 400 mm in width" |
| Velocidad máxima | 4 km/h = 1,11 m/s | publicado | pv magazine | "can reach a maximum speed of 4 km/h" |
| Carga útil del brazo | 50 kg | publicado | pv magazine | "payloads of up to 50 kg" |
| Alcance | más de 5 m | publicado | pv magazine | "effective working range exceeding 5 meters" |
| Pendiente | 20° | publicado | pv magazine | "maximum climbing capability of 20 degrees" |
| Energía | batería 33,4 kWh + extensor 30 kW, estanque 200 L | publicado | pv magazine | "33.4 kWh CATL battery and a 30 kW range extender" |
| Marca del brazo | — | sin dato | — | El brazo va cubierto con una funda en las 3 fotos. Es un brazo industrial de 6 ejes, pero no se ve la marca |
| Efector | marco con ventosas | estimado | [foto 2](https://www.pv-magazine.com/wp-content/uploads/2026/07/Screenshot-2026-07-17-082757.png) | El marco del brazo lleva ventosas visibles y sostiene un módulo. El texto no nombra el efector |
| Marco de ventosas | — | sin dato | — | Ninguna foto lo muestra de frente. No hay medida defendible |
| Origen de los paneles | pallets sobre la cubierta trasera | estimado | [foto 1](https://www.pv-magazine.com/wp-content/uploads/2026/07/Screenshot-2026-07-17-081157-1024x762.png), foto 2 | Dos rumas de módulos en cajas de madera, en un marco negro sobre la cubierta. No hay remolque. El texto dice "the robotic arm performs module pickup, transport, alignment, and installation" |
| Altura de cubierta | 0,6 m ± 0,2 m | estimado | foto 1 (vista trasera) | Escala: el ancho publicado de 2,1 m ≈ 375 px en la cara trasera. La cubierta está a ≈ 115 px del suelo |
| Alto de las rumas de módulos | tope a 1,7 m ± 0,25 m del suelo | estimado | foto 1 | Misma escala: el tope está a ≈ 305 px del suelo |
| Posición del brazo | +1,0 m ± 0,5 m (hacia el extremo del gabinete) | estimado | foto 2 (vista lateral oblicua) | Escala: largo de 5,2 m. El brazo va sobre un pedestal blanco reticulado, entre el gabinete y las rumas. La perspectiva acorta el extremo lejano |
| Altura de la base del brazo | ≈ 1,7 m ± 0,3 m del suelo | estimado | fotos 1 y 2 | El tope del pedestal queda a la altura del tope de las rumas |
| Gabinete | largo 1,1 m ± 0,4 m; alto 1,1 m ± 0,3 m sobre la cubierta | estimado | fotos 1, 2 y 3 | Caja blanca con rejillas en un extremo (generador y batería). Su techo queda cerca del tope de las rumas |

**Queda sin saber:** marca, modelo y grosor del brazo; medida del marco de ventosas; si los 9 t incluyen la carga.

**Reintento de la página del fabricante:** `www.pv-bot.com` sigue fallando (`getaddrinfo ENOTFOUND`).
La nota de prensa en [accessnewswire](https://www.accessnewswire.com/newsroom/en/electronics-and-engineering/relu-robotics-deploys-aipowered-photovoltaic-installation-robot-in-alg-1191828) devolvió HTTP 403 hoy.
pv magazine trae las mismas cifras de la nota y más (medidas, orugas). Por eso la proponemos como fuente principal.

## 3. `trinatracker-buildex-e` (Trinabot / TrinaTracker, Buildex E)

Fuentes:

- **Ficha del fabricante:** [trinarobot.com, Buildex](https://www.trinarobot.com/auxiliary-module-installation-robot/auxiliary-module-installation-robot.html).
  **No cargó** con WebFetch: `TLSV1_ALERT_INTERNAL_ERROR`, con y sin `www`. El dominio `www.trinabot.com` da `ENOTFOUND`.
  El buscador web sí la tiene indexada y devolvió su tabla de dos modelos. Las cifras de abajo vienen de ese índice.
  No tenemos el texto exacto, solo el valor. **Hay que confirmarlas en la página antes del pitch.**
- **pv magazine:** [2025-08-26](https://www.pv-magazine.com/2025/08/26/trinabot-offers-installation-robots-for-large-pv-projects/), leída directo.
- **Robotics & Automation News:** [2026-10-08](https://roboticsandautomationnews.com/2026/10/08/trinatracker-launches-robots-to-automate-solar-farm-construction-and-maintenance/105710/), leída directo.

| Dato | Valor | Estado | Fuente | Cita o método |
|---|---|---|---|---|
| Largo × ancho × alto (E) | 4,98 × 2,47 × 2,28 m | publicado* | ficha (índice) | Tabla: Buildex E "4.98 × 2.47 × 2.28 m". El modelo S mide 5,4 × 2,52 × 2,83 m |
| Masa (E) | 8 000 kg | publicado* | ficha (índice) | Tabla: Buildex E "8 t", S "9.5 t" |
| Masa (E), otra fuente | 9 000 kg | publicado | pv magazine 2025 | "weighing respectively 9.5 T and 9 T" (S y E) |
| Carga | 2 t + 100 kg | publicado* | ficha (índice) | Tabla: E "2 t + 100 kg", S "1.5 t + 100 kg". Lectura nuestra: 2 t en la horquilla (pallet) y 100 kg en el brazo. La ficha no lo explica |
| Velocidad (E) | menos de 5 km/h = < 1,39 m/s, 6 marchas | publicado* | ficha (índice) | Tabla: E "< 5 km/h", S "max 5.5 km/h" |
| Velocidad, otra fuente | ≈ 5,5 km/h = 1,53 m/s | publicado | pv magazine 2025 | "maximum speed of about 5.5 km/h". No dice de qué modelo |
| Altura del borde inferior del módulo (E) | 0,5 a 1,5 m | publicado* | ficha (índice) | Tabla: E "0.5–1.5 m". S: 0,5–2,5 m en estructura fija y 0,5–2,2 m en trackers |
| Inclinación | E 35° a 45° | publicado* | ficha (índice) | S: 27° a 45°. pv magazine 2025: "between 27 to 45 degrees" |
| Pendiente | 20° | publicado | pv magazine 2025 | "up to a 20 degree slope" |
| Nivelación | 17° | publicado | R&A News 2026 | "With 17 degree platform levelling capability" |
| Origen de los paneles | horquilla propia, pallet atrás | publicado | pv magazine 2025, R&A News 2026 | "a built-in forklift, a robotic arm"; "fork-and-flip mechanism supports automatic feeding" |
| Tracción | orugas | estimado | [render pv magazine](https://www.pv-magazine.com/wp-content/uploads/2025/08/TRINABOT-INSTALLER-1024x547.png), [render R&A News](https://roboticsandautomationnews.com/wp-content/uploads/2026/10/TrinaTracker-Buildex-Aurora-1.png) | Los dos renders muestran orugas. Ningún texto lo dice |
| Marca del brazo | — | sin dato | — | El render muestra un brazo blanco de paletizado con paralelogramo. No vemos marca ni texto |
| Efector | marco con ventosas | estimado | render pv magazine | Un marco con ≈ 9 ventosas. El texto dice "adaptive gripping" |
| Marco de ventosas | — | sin dato | — | El render lo muestra en perspectiva, sin escala fiable |
| Altura de cubierta | 0,85 m ± 0,25 m | estimado | render pv magazine | Escala: la ruma de módulos en la horquilla, con el largo de un módulo de 2,38 m (supuesto) ≈ 215 px. Las orugas y el chasis suman ≈ 75 px |
| Posición del brazo | −0,75 m ± 0,4 m (detrás del centro, lado de la horquilla) | estimado | render pv magazine | El pedestal está a ≈ 65 % del largo, contado desde el gabinete. Escala: largo de 4,98 m |
| Gabinete | largo 2,3 m ± 0,4 m; alto 1,4 m ± 0,3 m sobre la cubierta | estimado | render pv magazine | Caja delantera blanca. Control: cubierta 0,85 m + gabinete 1,4 m ≈ 2,25 m, cerca del alto publicado de 2,28 m |

**Aviso sobre el render:** el gabinete del render tiene un tubo de escape. Eso apunta al modelo híbrido S, no al E eléctrico.
Las proporciones del E pueden ser otras. Los estimados de cubierta, brazo y gabinete valen para la forma general, no para el E exacto.

**Queda sin saber:** marca y alcance del brazo; marco de ventosas; tracción con texto; cita exacta de la ficha.

**Si las fuentes no concuerdan:**

| Dato | Ficha del fabricante (índice) | pv magazine 2025 | Confiamos en |
|---|---|---|---|
| Masa del E | 8 t | 9 t | La ficha: es del fabricante y separa los dos modelos. Pero falta leerla directo |
| Velocidad | E < 5 km/h; S 5,5 km/h | ≈ 5,5 km/h, sin modelo | La ficha: los 5,5 km/h son del S |
| Módulos por hora | (SGS: más de 60) | 60 | R&A News 2026 dice 90. Es un comunicado nuevo, probablemente de otra versión |

## 4. `aes-maximo` (AES / Maximo)

Fuentes: [página de AES](https://www.aes.com/about-us/innovation/maximo), [The Robot Report](https://www.therobotreport.com/transforming-solar-farms-ai-robotics-and-industry-partnerships-at-aes/), [Fuseproject](https://fuseproject.com/case-studies/maximo/), [Electrek, 2026-03-29](https://electrek.co/2026/03/29/this-friendly-robot-just-installed-100-mw-of-solar-power/).
Ninguna publica largo, ancho, alto ni masa. Fast Company devolvió HTTP 403.

| Dato | Valor | Estado | Fuente | Cita o método |
|---|---|---|---|---|
| Tracción | orugas, 2 juegos | publicado | AES | "The system has tracks that enable it to maneuver on a variety of ground conditions" |
| Movimiento entre filas | lo remolca un minicargador | publicado | AES, The Robot Report | "a skid steer driver tows the robot"; "is towed by a tractor" |
| Brazos | brazo industrial de 6 ejes arriba; brazo pequeño al costado para apretar las grapas | publicado | The Robot Report, AES | "an industrial six-axis robot arm, mounted on top of a mobile platform"; "A second, smaller industrial arm is mounted on the side" |
| Marca del brazo | — | sin dato | — | Ninguna fuente la nombra |
| Efector | ventosas | estimado | AES (texto alternativo de la imagen y foto lateral) | Texto alternativo: "A robotic arm with suction cups". No es una spec, pero las ventosas se ven en la [foto lateral](https://www.aes.com/sites/global/files/styles/original/public/2025-04/tracked-robotic-vehicle-maximo.png.webp?itok=yxw1SWO8) |
| Origen de los paneles | cuna sobre el robot ("dynamic cradle"), cargada con un pallet | publicado | AES | "lift a pallet of modules and load it into the module storage space through Maximo's back panel" |
| Remolque | no tiene | publicado | AES | Los paneles van en la cuna. Un minicargador o un manipulador telescópico la rellena |
| Módulos que maneja | 6,5 × 3,25 ft = 1,98 × 0,99 m; más de 60 lb = más de 27 kg | publicado (prensa) | Fast Company vía buscador | No leímos la página (403). The Robot Report cita "about 80 pounds" = 36 kg para los módulos de una cuadrilla manual |
| Rapidez | más de 1 módulo por minuto (v3.0) | publicado | Electrek | "consistently surpassing an installation rate of one module per minute" |
| Largo, ancho, alto, masa | — | sin dato | — | Ver abajo |

**Por qué no estimamos el largo.** Ninguna foto trae una medida conocida en el mismo plano que el robot:

- En la [foto con una persona](https://www.aes.com/sites/global/files/styles/387_x_272/public/2025-07/industrial-machine-robotic-arm.png.webp?h=948ffbae&itok=XX0GH3fU), la persona está en primer plano, lejos del robot.
- En la foto lateral, la ruma de la cuna sirve de escala solo si sabemos si los módulos van parados por el lado corto o por el largo.
  Con el lado corto (0,99 m) el robot mediría ≈ 3,4 m. Con el largo (1,98 m), ≈ 6,7 m. La diferencia es del doble.
- Con un tubo de torque de 1,4 m (supuesto, no medido) en la foto de la persona, el largo daría ≈ 5,3 m. Es un supuesto apilado sobre otro.

**Lo que sí sirve: proporciones.** La foto lateral de AES es casi ortogonal. Medimos todo como fracción del largo de la carrocería L (± 10 %):

| Parte | Medida relativa |
|---|---|
| Altura de la cubierta donde va el brazo | 0,26 L sobre el suelo |
| Eje del brazo | en el centro del largo (≈ 0,0 L) |
| Gabinete delantero | 0,35 L de largo; techo a 0,43 L del suelo (0,17 L sobre la cubierta) |
| Cuna trasera | 0,32 L de largo; tope de los módulos a 0,64 L del suelo |
| Viga de ventosas (proyección lateral) | 0,26 L |

Si alguien publica el largo, estas proporciones dan el resto del clon.

**Queda sin saber:** largo, ancho, alto, masa, marca y alcance del brazo, velocidad propia (se mueve remolcado).

## 5. Bloques `fisica` propuestos

Valores redondeados. El esquema actual exige todos los campos y solo acepta `traccion: "orugas"`.
Los campos que faltan quedan fuera a propósito: el esquema va a cambiar para permitirlo.

### `relu-bison`

```json
"fisica": {
  "largo_m": 5.2,
  "ancho_m": 2.1,
  "masa_kg": 9000,
  "traccion": "orugas",
  "altura_cubierta_m": 0.6,
  "brazo_x_m": 1.0,
  "gabinete_largo_m": 1.1,
  "gabinete_alto_m": 1.1
},
"estimados": {
  "fisica.altura_cubierta_m": "No publicada. Medida en la foto trasera de Relu (pv magazine, 2026-07-17), con el ancho de 2,1 m como escala: 0,6 m ± 0,2 m.",
  "fisica.brazo_x_m": "No publicado. Medido en la foto lateral de Relu, con el largo de 5,2 m como escala: el pedestal del brazo va a 1,0 m ± 0,5 m del centro, hacia el gabinete.",
  "fisica.gabinete": "No publicado. Medido en las fotos de Relu: caja de 1,1 m ± 0,4 m de largo y 1,1 m ± 0,3 m sobre la cubierta.",
  "efector": "El texto no lo nombra. Las fotos de Relu muestran un marco con ventosas."
}
```

- **Sin remolque:** los módulos van en pallets sobre la cubierta trasera.
- **Sin marco de ventosas ni grosor de brazo:** no hay medida defendible.

### `trinatracker-buildex-e`

```json
"fisica": {
  "largo_m": 4.98,
  "ancho_m": 2.47,
  "masa_kg": 8000,
  "traccion": "orugas",
  "altura_cubierta_m": 0.85,
  "brazo_x_m": -0.75,
  "gabinete_largo_m": 2.3,
  "gabinete_alto_m": 1.4
},
"estimados": {
  "fisica.dimensiones": "4,98 × 2,47 × 2,28 m y 8 t según la ficha de Trinabot, leída por el índice del buscador; la página no cargó el 2026-11-21. pv magazine 2025 dice 9 t.",
  "fisica.traccion": "No está en el texto. Los renders del fabricante muestran orugas.",
  "fisica.altura_cubierta_m": "No publicada. Medida en el render de Trinabot (pv magazine 2025), con un módulo de 2,38 m como escala: 0,85 m ± 0,25 m. El render parece el modelo S.",
  "fisica.brazo_x_m": "No publicado. En el render, el pedestal está a 0,75 m ± 0,4 m detrás del centro, del lado de la horquilla.",
  "fisica.gabinete": "No publicado. En el render: 2,3 m ± 0,4 m de largo y 1,4 m ± 0,3 m sobre la cubierta; su techo calza con el alto publicado de 2,28 m.",
  "efector": "El texto dice 'adaptive gripping'. El render muestra un marco con ventosas."
}
```

- **Sin remolque:** el robot trae su propia horquilla con un pallet de hasta 2 t (lectura nuestra de "2 t + 100 kg").
  El clon podría dibujar el pallet como carga en voladizo atrás. Hoy el esquema no tiene un campo para eso.
- **Sin marco de ventosas ni grosor de brazo:** no hay medida defendible.

### `aes-maximo`

```json
"fisica": {
  "traccion": "orugas"
}
```

- Solo la tracción tiene respaldo. Largo, ancho y masa no se pueden estimar sin una escala (sección 4).
- **Sin remolque:** la cuna va sobre el robot.
- **Propuesta:** dejar el clon de Maximo en la base genérica, o usar las proporciones de la sección 4 con un largo supuesto y declararlo en `estimados`.

## 6. Qué tan fiel puede ser cada clon

Los 5 campos base: largo, ancho, masa, altura de cubierta y tracción.

| Robot | Publicados | Estimados | Sin dato | Comentario |
|---|---|---|---|---|
| `relu-bison` | 4 (largo, ancho, masa, tracción) | 1 (cubierta) | 0 | El más fiel de los tres. La caja exterior es exacta |
| `trinatracker-buildex-e` | 3* (largo, ancho, masa) | 2 (tracción, cubierta) | 0 | \*Leídos por el índice del buscador. Masa en disputa (8 t o 9 t) |
| `aes-maximo` | 1 (tracción) | 0 | 4 | Solo proporciones. Un clon con medidas absolutas sería inventado |

## 7. Specs del catálogo que las fuentes contradicen

| Archivo | Campo actual | Lo que dicen las fuentes |
|---|---|---|
| `trinatracker-buildex-e` | `velocidad_base_m_s: 1.53` (5,5 km/h) | La ficha da 5,5 km/h al modelo S. El E va a menos de 5 km/h (< 1,39 m/s) |
| `trinatracker-buildex-e` | `carga_util_kg: 35` (estimado) | La ficha dice "2 t + 100 kg". Si los 100 kg son del brazo, la carga útil es 100 kg |
| `trinatracker-buildex-e` | `estimados.alcance_m` cita "borde entre 0,5 y 2,2 m en trackers" | La ficha da ese rango al S. El E llega a 0,5–1,5 m |
| `trinatracker-buildex-e` | README: "9 t" | La ficha dice 8 t para el E. pv magazine 2025 dice 9 t |
| `relu-bison` | `estimados.efector` dice que se asume | Las fotos de Relu muestran ventosas. Sigue sin texto, pero ya no es solo un supuesto |
| `aes-maximo` | `velocidad_base_m_s: 0.5` (estimado) | AES dice que un minicargador lo remolca entre filas. La velocidad depende del remolcador, no del robot |

## 8. Páginas que no cargaron (2026-11-21)

| URL | Error |
|---|---|
| `https://www.pv-bot.com` | `getaddrinfo ENOTFOUND` |
| `https://www.trinarobot.com/auxiliary-module-installation-robot/auxiliary-module-installation-robot.html` (con y sin `www`) | `TLSV1_ALERT_INTERNAL_ERROR` |
| `https://www.trinabot.com` | `getaddrinfo ENOTFOUND` |
| Nota de prensa de Relu en accessnewswire | HTTP 403 |
| Fast Company (Maximo) | HTTP 403 |

## 9. Fuentes (consultadas el 2026-11-21)

- pv magazine, "AI-powered 9-ton tracked robot for large-scale PV construction", 2026-07-17. <https://www.pv-magazine.com/2026/07/17/ai-powered-9-ton-tracked-robot-for-large-scale-pv-construction/>
- Fotos de Relu en ese artículo: [1](https://www.pv-magazine.com/wp-content/uploads/2026/07/Screenshot-2026-07-17-081157-1024x762.png), [2](https://www.pv-magazine.com/wp-content/uploads/2026/07/Screenshot-2026-07-17-082757.png), [3](https://www.pv-magazine.com/wp-content/uploads/2026/07/Screenshot-2026-07-17-082832.png)
- pv magazine, "Trinabot offers installation robots for large PV projects", 2025-08-26. <https://www.pv-magazine.com/2025/08/26/trinabot-offers-installation-robots-for-large-pv-projects/>
- Render de Trinabot en ese artículo. <https://www.pv-magazine.com/wp-content/uploads/2025/08/TRINABOT-INSTALLER-1024x547.png>
- Trinabot, ficha Buildex (leída solo por el índice del buscador). <https://www.trinarobot.com/auxiliary-module-installation-robot/auxiliary-module-installation-robot.html>
- Robotics & Automation News, "TrinaTracker launches robots…", 2026-10-08. <https://roboticsandautomationnews.com/2026/10/08/trinatracker-launches-robots-to-automate-solar-farm-construction-and-maintenance/105710/>
- AES, página de Maximo, con la foto lateral y la foto con una persona. <https://www.aes.com/about-us/innovation/maximo>
- The Robot Report, "Transforming solar farms: AI, robotics, and industry partnerships at AES". <https://www.therobotreport.com/transforming-solar-farms-ai-robotics-and-industry-partnerships-at-aes/>
- Fuseproject, caso Maximo. <https://fuseproject.com/case-studies/maximo/>
- Electrek, "This friendly robot just installed 100 MW of solar power", 2026-03-29. <https://electrek.co/2026/03/29/this-friendly-robot-just-installed-100-mw-of-solar-power/>
