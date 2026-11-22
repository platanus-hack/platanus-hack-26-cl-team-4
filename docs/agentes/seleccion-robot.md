# Contrato: agente de selección de robot

> Etapa 3. **Contrato v3** (2026-11-21). **Implementado:** pasos 1, 3 y 4 de la v3 (requisitos, descarte por reglas, 1 a 3 finalistas). Sin búsqueda web ni corridas hijas: la corrida sigue con el finalista 1.
> Requerimientos: RF-ROB-01..12, RF-CLO-10..11, RF-ORQ-07..08, RNF-02, RNF-03.
> Código: [`agentes/__init__.py`](../../backend/viaz/agentes/__init__.py) → `seleccionar()`, con el paso 1 en [`agentes/perfiles.py`](../../backend/viaz/agentes/perfiles.py) y los pasos 3 y 4 en [`agentes/seleccion.py`](../../backend/viaz/agentes/seleccion.py). Prompt: [`prompts/robot.md`](../../backend/viaz/agentes/prompts/robot.md). Catálogo: [`catalogo/robots/`](../../backend/viaz/catalogo/robots/). Tests: [`test_seleccion.py`](../../backend/tests/test_seleccion.py).
> Explicación paso a paso, con un diagrama por parte: [`seleccion-robot-flujo.md`](seleccion-robot-flujo.md).
> Esquemas v3: [`requisitos`](../../backend/viaz/esquemas/requisitos.schema.json), [`seleccion`](../../backend/viaz/esquemas/seleccion.schema.json), [`comparacion`](../../backend/viaz/esquemas/comparacion.schema.json). Ejemplos en [`fixtures/`](../../backend/viaz/fixtures/).

## Estado de cada paso

| Paso | Real y probado | Sin probar | Falso o de relleno | No existe |
|---|---|---|---|---|
| 1. Requisitos (perfil de dominio) | Perfil `solar` (`perfiles.py`). Su salida es igual a `fixtures/requisitos.json`. Un dominio sin perfil da `ErrorAgente` | — | — | Perfiles de otros dominios |
| 2. Búsqueda web | — | — | — | Todo el paso |
| 3. Descarte por reglas | `fallas()` genérico: lee solo `requisitos.json`. Un test por requisito | — | — | — |
| 4. Selección | Modo `fijo`: 1 a 3 finalistas y `seleccion.json`, con tests. Modo `claude`: las reglas de §4 sobre la respuesta, con tests contra un modelo falso | Modo `claude` contra la API del backend, con salida estructurada | — | — |
| 5. Corridas hijas | `procesar_rl` con el finalista 1 | — | — | Una corrida hija por finalista |
| 6. Modelo comprobado | — | — | — | Registro y reuso de recetas de clon |
| 7. Comparación | — | — | Métricas de `fixtures/comparacion.json` (ilustrativas) | Regla, `comparacion.json`, `fidelidad` en el código |

- **Esquemas y fixtures v3:** existen y validan (`test_esquemas.py`). La etapa robot de los dos flujos escribe `requisitos.json`, `seleccion.json` y `robot.json` (finalista 1). `fixtures/seleccion.json` sale del modo `fijo`. Nadie escribe `comparacion.json` todavía.
- **Otro dominio:** con este contrato el agente puede **elegir** para otro dominio. La **simulación** de ese dominio no corre todavía: `entorno.json`, `tarea.json` y `sim/rl` son solo solares.

## Flujo v3

```mermaid
flowchart TD
  E[entorno.json] --> P["1. Perfil de dominio<br/>código, sin LLM"]
  T[tarea.json] --> P
  P --> RQ[requisitos.json]
  RQ --> B["2. Búsqueda web<br/>LLM, acotada"]
  B -->|fichas válidas<br/>origen: busqueda| CAND[(Candidatos)]
  CAT[(Catálogo)] --> CAND
  CAND --> D["3. Descarte por reglas<br/>código"]
  RQ --> D
  D -->|pasan| S["4. Selección<br/>LLM"]
  D -->|fallas| SEL
  S --> SEL["seleccion.json<br/>1 a 3 finalistas"]
  SEL --> H["5. Corrida hija por finalista<br/>robot.json + procesar_rl"]
  REG[("6. Modelos comprobados")] -.reuso.-> H
  H --> EV[evaluacion.json × N]
  EV --> C["7. Comparación<br/>código decide, LLM explica"]
  C --> CO[comparacion.json]
```

## 1. Propósito

- **Decide:** qué robots reales sirven para la tarea en ese lugar, y cuáles 1 a 3 vale la pena entrenar.
- **Explica:** el cliente lee cada justificación en la web. Debe ser verificable con números.
- **No decide:** las specs ni el ganador. Las specs salen de la ficha (RNF-02). El ganador sale de una regla sobre `evaluacion.json`.
- **Por qué cambia:** la v2 solo sirve para paneles y solo elige del catálogo. VIAZ virtualiza cualquier industria.

## 2. Entradas

| Entrada | Origen |
|---|---|
| `entorno.json`, `tarea.json` | Escritos a mano por el equipo (demo) o agentes de mapeo y tarea |
| `requisitos.json` | Perfil de dominio (código), desde `entorno.json` y `tarea.json` |
| Catálogo | `catalogo/robots/*.json`, validado contra `robot.schema.json` al cargar |
| Fichas encontradas | Paso de búsqueda, validadas contra `robot.schema.json`. Se guardan en el almacén de la corrida |
| Modelos comprobados | `sim/assets_aprobados/<id>/` (receta) + `robot.usd` en el almacén |

### Paso 1: perfil de dominio

- **Qué hace:** traduce el dominio a requisitos neutros. La selección lee `requisitos.json`. No lee "panel" ni "tubo".
- **Perfil `solar`:** contiene las reglas solares (`perfil_solar()`, `alcance_necesario()`). Otro dominio agrega su propio perfil al registro `PERFILES` y su tipo de entorno a `DOMINIO_POR_TIPO_DE_ENTORNO`.

| Campo de `requisitos.json` | Perfil `solar` |
|---|---|
| `objeto` | `entorno.panel` (largo, ancho, peso) |
| `carga_min_kg` | `panel.peso_kg` |
| `efectores_aceptados` | `["ventosa"]` |
| `movilidad`, `tipos_aceptados` | `movil`. Con pendiente mayor a 10°, solo `vehiculo_con_brazo`. Nunca `brazo_fijo` |
| `por_robot[].alcance_min_m` | `alcance_necesario(entorno, ficha)` |
| `preferencias` | En este orden: `real_sobre_ficticio`, `menos_specs_estimadas`, `mayor_margen_carga_alcance`, `mayor_velocidad_base`. Un dato publicado pesa más que la velocidad. Cada criterio es una clave de orden en `seleccion.PREFERENCIAS`. Un criterio desconocido da `ErrorAgente` |
| `advertencias` | Cada dato de `entorno.confianza` menor a 1 |

#### Cálculo de `alcance_min_m` (perfil `solar`)

```mermaid
flowchart LR
  B["Hombro del clon<br/>cubierta + 0,30 m"] -->|"d = largo_panel/2 + ancho_robot/2 + 0,06 m"| T["Tubo de la fila 0<br/>z = altura + 0,09 m"]
```

- **Fórmula:** `√(d² + dz²) + muñeca + 0,05 m de margen`, con `dz = altura + 0,09 + muñeca − hombro_z`. La muñeca mide 0,30 m.
- **Depende del robot:** un vehículo más ancho queda más lejos del tubo. Uno más alto sube el hombro. Por eso hay una fila por robot.
- **Ejemplo (fixture):** tracker de 1,5 m y panel de 2,38 m dan **2,28 m** con la base genérica, **2,53 m** para `leapting-mmr` (1,8 m de ancho), **2,86 m** para `relu-bison` (2,1 m) y **2,95 m** para `trinatracker-buildex-e` (2,47 m).
- **Verificado:** para alturas de 0,8 a 4 m y paneles de 1,7 a 2,8 m, un clon con ese alcance pasa `plan.validar()`.

### Paso 2: búsqueda web

- **Qué hace:** busca robots reales que hagan la tarea y no estén en el catálogo. Devuelve fichas con el formato del catálogo.
- **Cada ficha encontrada:** `origen: "busqueda"`, `fuente.url`, `fuente.consultado`. Cada valor que la fuente no publica va en `estimados` con su motivo.
- **Validación:** el código valida cada ficha contra el esquema. Las inválidas van a `seleccion.busqueda.invalidas` y al log. Cada ficha rechazada queda registrada.
- **Límites:** máximo de robots y de tiempo, por configuración. Al llegar al límite, `busqueda.estado` es `cortada`.
- **Falla:** no hace fallar la corrida. `busqueda.estado` queda `fallida` y la selección sigue con el catálogo.
- **Promoción:** una persona pasa una ficha encontrada a `catalogo/robots/` con un PR.

### Paso 3: descarte por reglas

- Cada candidato (catálogo + encontrados) se compara con los requisitos obligatorios. Las fallas son objetivas y se listan por robot en `descartados`.

## 3. Salida

### `seleccion.json`

| Campo | Lo llena | Regla |
|---|---|---|
| `requisitos` | Código | Nombre del archivo usado |
| `busqueda` | Código | `estado` (`completa`, `cortada`, `fallida`, `omitida`), `detalle`, `invalidas` |
| `encontrados` | Código | Ids de las fichas válidas de la búsqueda |
| `descartados` | Código | `{id, fallas}` del paso 3 |
| `finalistas` | Agente | 1 a 3 `{id, puesto, justificacion}`. El tope fijo es 3. `VIAZ_MAX_FINALISTAS` puede bajarlo y vale 3 por defecto |
| `alternativas` | Agente | Candidatos válidos no finalistas, con `por_que_no` |

### `robot.json` (uno por finalista)

- **Mismo formato que hoy.** El constructor y el flujo RL no cambian.
- Cada finalista corre en una **corrida hija** que reutiliza `procesar_rl` con el robot fijo.
- Las specs se copian de la ficha (catálogo o encontrada), nunca de la respuesta del modelo.

### `comparacion.json`

| Campo | Lo llena | Regla |
|---|---|---|
| `ganador`, `regla`, `ranking` | Código | Primero `tasa_exito` (tolerancia de entrenamiento), luego menor `ciclo_s` |
| `condiciones` | Código | Misma escena, mismas horas, mismas semillas y tolerancias para todos |
| `ranking[].fidelidad` | Código | Copia de `clon.json → fidelidad` |
| `advertencias` | Código | Niveles de fidelidad distintos y corridas hijas que fallaron |
| `que_compara`, `que_no_compara` | Código | Texto fijo (ver abajo) |
| `explicacion` | Agente | Explica la regla. No la cambia |

- **Qué compara la simulación:** alcance, tamaño, masa, carga útil y velocidad de la base.
- **Qué no compara:** los motores y el control reales. Todos los clones usan un brazo de Isaac Lab escalado (`ur10` o `franka_panda`).
- **Fixture:** `fixtures/comparacion.json` tiene **métricas ilustrativas**, no medidas. Lo dice en `advertencias` y en `explicacion`.

Ejemplo de ranking con dos finalistas de fidelidad distinta (hipotético):

```json
"ranking": [
  { "id": "leapting-mmr", "corrida_id": "hija-1", "puesto": 1, "tasa_exito": 0.92, "ciclo_s": 48, "fidelidad": "medido" },
  { "id": "otro-robot",   "corrida_id": "hija-2", "puesto": 2, "tasa_exito": 0.92, "ciclo_s": 55, "fidelidad": "generico" }
],
"advertencias": ["Los clones tienen fidelidad distinta (medido y generico): la diferencia puede venir del clon."]
```

### `clon.json → fidelidad`

| Valor | Significado |
|---|---|
| `generico` | Base genérica, sin bloque `fisica` |
| `medido` | Usa `fisica` de la ficha, con datos publicados o medidos en fotos |
| `verificado` | `medido`, sin claves `fisica.*` en `estimados`, y pasó `validar_robot` y la rúbrica de calidad |

### Paso 6: modelo comprobado

- **Cuándo se registra:** el clon pasó `validar_robot` y la rúbrica de [`calidad-virtualizacion.md`](../calidad-virtualizacion.md) §5.
- **Qué se registra:** `ensamblaje.json`, `robot_cfg.py`, `robot.urdf`, `robot.usd`, `clon.json`, las 4 vistas y la rúbrica.
- **Clave:** id del robot + hash de su ficha + versión del catálogo de assets de Isaac Lab.
- **Dónde:** la receta de texto en `sim/assets_aprobados/<id>/`, por PR. `robot.usd` en el almacén.
- **Al reusar:** se salta el agente constructor. **Siempre** corre un chequeo corto en la escena, porque el alcance y los choques dependen del lugar.
- **No se reusa:** la política entrenada, ni entre tareas ni entre lugares.

## 4. Reglas que verifica el código

1. Cada ficha (catálogo o encontrada) cumple `robot.schema.json`. Las encontradas tienen `fuente.url` y `fuente.consultado` (RF-ROB-02, RF-ROB-03).
2. Cada `finalistas[].id` y `alternativas[].id` es un candidato que pasó el descarte. Si no, `ErrorAgente`.
3. Hay 1 a `VIAZ_MAX_FINALISTAS` finalistas, nunca más de 3. Los puestos son 1..N sin repetir.
4. **Núcleo de `fisica`:** para ser finalista, la ficha tiene `largo_m`, `ancho_m`, `masa_kg`, `altura_cubierta_m` y `traccion`. Sin él, el robot queda como alternativa con el motivo.
5. **Ninguno pasa las reglas:** exactamente un finalista, el que falla menos. Su justificación lo dice en la primera oración (igual que hoy).
6. Las specs de cada `robot.json` salen de la ficha (RNF-02).
7. El ganador sale de la regla, no del LLM.
8. Cada salida cumple su esquema.

### Cambios al esquema

| Cambio | Estado |
|---|---|
| Núcleo de `fisica` obligatorio (`largo_m`, `ancho_m`, `masa_kg`, `altura_cubierta_m`, `traccion`). El resto es opcional | **Hecho.** Los pares (`gabinete_*`, `ventosa_*`, `remolque_*`) van juntos o no van (`dependentRequired`) |
| `fisica.traccion` acepta `ruedas` además de `orugas` | **Hecho** |
| `fisica.pila_x_m` para robots sin remolque | **Hecho.** Sin el campo, la pila va sobre la cubierta, lejos del gabinete |
| [`urdf.py`](../../backend/viaz/urdf.py) arma el clon con lo que haya. El clon del Leapting no cambió | **Hecho** (comparado byte a byte) |
| Más valores en `efector` (hoy `ventosa`/`pinza`) | Planeado |
| Un campo para una pila fuera del vehículo (horquilla de BUILDEX E) | Planeado |
| `agentes.clon()` para robots `vehiculo_con_brazo` (hoy solo `base_movil_brazo`) | Planeado |

## 5. Instrucciones (resumen del prompt)

- **Hoy (v3):** el prompt lee `requisitos.json` y no nombra el dominio. Recibe solo los candidatos que pasan, ordenados por `preferencias`. Devuelve finalistas y alternativas.
- **Ninguno pasa:** el código elige el candidato y el modelo solo escribe la justificación.
- **Probado a mano el 2026-11-21:** el prompt v3 corrió 3 veces contra el modelo real por la CLI, con la entrada que arma el código. Las 2 respuestas del caso normal pasaron `comprobar()`. La del caso sin candidatos dijo en su primera oración que ninguno cumple.
- **Sin probar:** la llamada del backend con salida estructurada de la API. Los tests usan un modelo falso.
- **Búsqueda:** un prompt nuevo, con búsqueda web, que devuelve fichas del catálogo. **[Por escribir]**
- **Sigue igual:** decir si un robot es ficticio, advertir datos con confianza baja y usar vocabulario ISO 8373 (RF-WEB-11).

## 6. Errores

| Caso | Resultado |
|---|---|
| Id de finalista o alternativa fuera de los candidatos | `ErrorAgente`. La corrida pasa a `error` |
| Catálogo vacío o inválido | `ValueError` al cargar. La corrida pasa a `error` |
| Búsqueda falla o se pasa del tiempo | `busqueda.estado` queda en `fallida` o `cortada`. La selección sigue con el catálogo |
| Ficha encontrada inválida | Va a `busqueda.invalidas` y al log. No entra a los candidatos |
| Una corrida hija falla | Queda fuera del ranking, con aviso en `comparacion.advertencias` |
| Todas las corridas hijas fallan | Corrida padre en `error` |

## 7. Pruebas

- **Hoy:** cada ficha del catálogo valida y su `id` coincide con el archivo. Los 3 fixtures v3 validan contra su esquema.
- **Hoy:** `requisitos.json → por_robot` coincide con `alcance_necesario()` para cada ficha (`test_esquemas.py`).
- **Regla de alcance:** `alcance_necesario()` vs `sim/plan.py` → `validar()` (ver §2).
- **Hoy (`test_seleccion.py`):** perfil `solar` igual al fixture, una falla por requisito, finalistas del catálogo real, tope de 1 a 3, ninguno pasa, núcleo de `fisica`, `robot.json` por finalista y cada regla de §4 sobre la respuesta de un modelo falso.
- **Hoy (`test_flujo.py`, `test_rl.py`):** los dos flujos guardan `requisitos.json` y `seleccion.json`.
- **Por hacer:** regla de la comparación con empates.
- **Con Claude:** 3 corridas revisadas a mano por la CLI (ver §5). Falta repetirlas con la API del backend.

## Decisiones abiertas

| Tema | Qué decidir |
|---|---|
| Costo de 3 finalistas | Cuántos pods y cuántas horas por entrenamiento. 3 finalistas cuestan 3 veces las horas de pod |
| Prioridad MoSCoW | RF-ROB-08..12, RF-CLO-10..11 y RF-ORQ-07..08 están en **S** hasta que el equipo decida |
| Alcance de la generalización | Si generalizar `entorno.json`, `tarea.json` y `sim/rl` (hoy solo solares) entra en el hack |
| Catálogo actual | `leapting-mmr`, `relu-bison` y `trinatracker-buildex-e` tienen el núcleo de `fisica`. `aes-maximo` no lo tiene, porque ninguna foto trae una escala para medirlo. BUILDEX E falla el alcance, con 2,5 m estimados contra 2,95 m necesarios. Una persona decide su alcance real. Hoy hay 2 finalistas |
| Definición de `fidelidad` | La tabla de §3 es una propuesta |
