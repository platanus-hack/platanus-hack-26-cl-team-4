# Catálogo de robots

Un JSON por robot en `robots/`. El agente Robot elige **solo** entre estos archivos: no inventa robots.
Los archivos que empiezan con `_` no se cargan.

- Formato: `robot.schema.json` sin `justificacion` ni `alternativas`. Copia `_plantilla.json`.
- Cada dato sale de una fuente con URL y fecha (`fuente`). Si un dato no aparece en la fuente, déjalo fuera del pitch.
- `viaz-instalador-ficticio` existe solo para desarrollar el flujo. Tiene `"ficticio": true` y la web lo muestra así.

## Física propia del robot (`fisica`)

- **Opcional.** Un robot con el bloque `fisica` usa sus propias medidas en el clon: largo, ancho y masa del vehículo, altura de la cubierta, orugas, gabinete, grosor del brazo, marco de ventosas y remolque de paneles. `urdf.py` las lee de aquí.
- **Sin el bloque,** el clon usa la base genérica de 1,6 × 1,0 m sobre ruedas.
- **Lo que el fabricante no publica** va también en `estimados`, con la clave `fisica.<dato>`. Esas claves no cuentan como specs estimadas en la selección.
- **Hoy lo tiene:** `leapting-mmr` (3,145 × 1,8 m y 4 500 kg publicados; remolque de 2,35 m y 2 300 kg publicado; altura de cubierta, posición del brazo, gabinete, grosor del brazo y marco de ventosas medidos en fotos y videos).

## Robots cargados (consultados el 2026-11-21)

| id | Fuente | Specs publicadas | Estimadas (`estimados`) |
|---|---|---|---|
| `leapting-mmr` | Página del fabricante | Carga 100 kg, alcance 3,1 m, 1,5 km/h, 8 ventosas | — |
| `relu-bison` | Nota de prensa del fabricante | Carga 50 kg, alcance "más de 5 m", 4 km/h, orugas, 9 t | Efector |
| `trinatracker-buildex-e` | pv magazine (2025) | 9 t, 5,5 km/h, módulos con borde entre 0,5 y 2,2 m | Carga, alcance, efector |
| `aes-maximo` | Página de AES | Orugas, brazo con ventosas (imágenes) | Carga, alcance, velocidad, efector |

- **Regla:** un dato que el fabricante no publica va en `estimados` con su motivo. El agente lo dice en la justificación.
- **Por verificar:** las páginas de Relu (pv-bot.com) y Trinabot no cargaron el 2026-11-21 (DNS y TLS). Reintentar antes del pitch.
- **Pendientes:** Gritt, Charge Robotics, Luminous y Cosmic Robotics (investigación del 2026-09-28).
