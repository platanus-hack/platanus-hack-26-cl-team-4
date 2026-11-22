# Catálogo de robots

Un JSON por robot en `robots/`. El agente Robot elige entre estos archivos y las fichas del catálogo compartido (abajo): no inventa robots.
Los archivos que empiezan con `_` no se cargan.

- Formato: `robot.schema.json` sin `justificacion` ni `alternativas`. Copia `_plantilla.json`.
- Cada dato sale de una fuente con URL y fecha (`fuente`). Si un dato no aparece en la fuente, déjalo fuera del pitch.
- **`origen`:** es opcional. Sin el campo vale `catalogo`. Las fichas que trae la búsqueda web (contrato v3) tienen `origen: "busqueda"`.
- `viaz-instalador-ficticio` existe solo para desarrollar el flujo. Tiene `"ficticio": true` y la web lo muestra así.

## Catálogo compartido (fichas de la búsqueda web)

- **Dónde:** en el almacén, no en el repo: `catalogo/encontrados/<id>.json`, un archivo por ficha. Lo lee y lo escribe [`encontrados.py`](encontrados.py).
- **Quién escribe:** el paso 2 de la selección ([`seleccion-robot.md`](../../../docs/agentes/seleccion-robot.md) §2). Un modelo escribió esos datos: nadie los revisó todavía.
- **Evidencia:** cada spec de selección tiene una entrada en `evidencia` (`url` y `cita`, la oración exacta de la fuente) o en `estimados` (motivo).
- **Choque de id:** gana la ficha de `robots/`. Un archivo inválido se salta y queda en el log.

- **Sin revisión:** una ficha encontrada entra como candidata en todas las corridas siguientes, sin que una persona la revise. Si una ficha tiene datos malos, borra su archivo del almacén. El riesgo está descrito en [`seleccion-robot.md`](../../../docs/agentes/seleccion-robot.md).

### Cómo pasar una ficha encontrada a `robots/`

1. Copia `catalogo/encontrados/<id>.json` del almacén a `robots/<id>.json`.
2. Abre cada enlace de `evidencia`. Confirma que la página dice la `cita` y que el valor coincide. Corrige o borra lo que no coincida.
3. Revisa cada motivo de `estimados`. Un dato sin fuente ni motivo sale de la ficha.
4. Borra el campo `origen` (sin el campo vale `catalogo`). Pon la fecha de tu revisión en `fuente.consultado`.
5. Corre `uv run --no-sync -p .venv pytest -q tests/test_esquemas.py` desde `backend/` y abre un PR con lo que revisaste.

## Física propia del robot (`fisica`)

- **Opcional.** Un robot con el bloque `fisica` usa sus propias medidas en el clon. `urdf.py` las lee de aquí.
- **Sin el bloque,** el clon usa la base genérica de 1,6 × 1,0 m sobre ruedas.
- **Lo que el fabricante no publica** va también en `estimados`, con la clave `fisica.<dato>`. Esas claves no cuentan como specs estimadas en la selección.
- **Marco del clon:** x positivo hacia adelante, desde el centro del vehículo. El gabinete va siempre atrás. Si las fotos lo muestran adelante, invierte el signo de `brazo_x_m` y dilo en `estimados`.

| Campo | ¿Obligatorio? | Si falta |
|---|---|---|
| `largo_m`, `ancho_m`, `masa_kg`, `altura_cubierta_m`, `traccion` (`orugas` o `ruedas`) | Sí (núcleo) | El bloque no valida |
| `brazo_x_m` | No | Misma fracción del largo que el clon genérico (0,45 de 1,6 m) |
| `brazo_grosor_m`, `antebrazo_grosor_m` | No | Grosor del brazo genérico |
| `ventosa_largo_m` + `ventosa_ancho_m` | No, van juntos | Marco de ventosas genérico (0,6 × 1,0 m) |
| `gabinete_largo_m` + `gabinete_alto_m` | No, van juntos | Sin gabinete |
| `remolque_largo_m` + `remolque_masa_kg` | No, van juntos | Sin remolque: la pila va sobre la cubierta |
| `pila_x_m` | No, solo sin remolque | Entre el brazo y el extremo libre de la cubierta (lejos del gabinete) |

- **Hoy lo tienen:**
  - `leapting-mmr`: 3,145 × 1,8 m y 4 500 kg publicados. Remolque de 2,35 m y 2 300 kg publicado. Cubierta, brazo, gabinete, grosores y ventosas medidos en fotos y videos.
  - `relu-bison`: 5,2 × 2,1 m, 9 t y orugas publicados (pv magazine). Cubierta, brazo y gabinete medidos en fotos. Sin remolque: pallets sobre la cubierta.
  - `trinatracker-buildex-e`: 4,98 × 2,47 m y 8 t leídos por el índice del buscador (pv magazine dice 9 t). Orugas, cubierta, brazo y gabinete estimados en un render.
- **No lo tiene:** `aes-maximo`. Solo la tracción (orugas) está publicada. Ninguna foto trae una escala para medir largo, ancho ni masa ([investigación](../../../docs/investigacion-fisica-robots.md) §4). Un bloque con medidas absolutas sería inventado.

## Robots cargados (consultados el 2026-11-21)

| id | Fuente | Specs publicadas | Estimadas (`estimados`) |
|---|---|---|---|
| `leapting-mmr` | Página del fabricante | Carga 100 kg, alcance 3,1 m, 1,5 km/h, 8 ventosas | — |
| `relu-bison` | pv magazine (2026-07-17), con fotos de Relu | Carga 50 kg, alcance "más de 5 m", 4 km/h, orugas, 5,2 × 2,1 m, 9 t | Efector, alcance exacto, `fisica.*` |
| `trinatracker-buildex-e` | pv magazine (2025) | 5,5 km/h, módulos con borde entre 0,5 y 2,2 m. 4,98 × 2,47 m y 8 t leídos de la ficha por el buscador | Carga, alcance, efector, `fisica.*` |
| `aes-maximo` | Página de AES | Orugas, brazo con ventosas (imágenes) | Carga, alcance, velocidad, efector. Sin `fisica` |

- **Regla:** un dato que el fabricante no publica va en `estimados` con su motivo. El agente lo dice en la justificación.
- **Por verificar:** las páginas de Relu (pv-bot.com) y Trinabot no cargaron el 2026-11-21 (DNS y TLS). Reintentar antes del pitch.
- **Por decidir (una persona):** las specs de BUILDEX E que la ficha contradice (velocidad, carga y alcance, en la investigación §7). Con su alcance de 2,5 m, el clon no llega al tubo (necesita 2,95 m) y la selección lo descarta.
- **Pendientes:** Gritt, Charge Robotics, Luminous y Cosmic Robotics (investigación del 2026-09-28).
