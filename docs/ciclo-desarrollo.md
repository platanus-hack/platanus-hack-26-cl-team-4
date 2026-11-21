# Ciclo de desarrollo

> Estado: **propuesta**. Cómo pasamos de los requerimientos al demo en las horas del hack.
> Normas de referencia: ISO/IEC/IEEE 12207 (ciclo) y 29119 (pruebas), ver [`requerimientos.md` §7](requerimientos.md#7-normas-iso).
> Documentos base: [`requerimientos.md`](requerimientos.md) → [`arquitectura.md`](arquitectura.md) → [`contrato-datos.md`](contrato-datos.md).

## 1. Modelo

Usamos un ciclo **incremental por checkpoint**: cada checkpoint es una iteración corta que pasa por todas las fases y termina con algo que corre de punta a punta.

```mermaid
flowchart LR
  R[1. Requerimientos] --> D[2. Diseño]
  D --> I[3. Implementación]
  I --> P[4. Pruebas]
  P --> E[5. Entrega]
  E --> V[6. Revisión]
  V -->|siguiente checkpoint| R
```

| Fase | Qué produce | Dónde vive | Estado |
|---|---|---|---|
| 1. Requerimientos | RF y RNF con ID, prioridad MoSCoW y normas ISO | `docs/requerimientos.md` | Borrador v0.3 |
| 2. Diseño | Arquitectura, contrato de datos, JSON Schemas | `docs/arquitectura.md`, `docs/contrato-datos.md`, `esquemas/` | Arquitectura y contrato propuestos; faltan esquemas |
| 3. Implementación | Código por etapa, primero el mapeo y con stubs | `web/`, `api/`, `orquestador/`, `agentes/`, `worker-gpu/`, `sim/` | Por empezar |
| 4. Pruebas | Validación de esquemas, pruebas por etapa, prueba de punta a punta | `tests/` | Por empezar |
| 5. Entrega | Web desplegada, corrida de respaldo, video, pitch | Vercel, Render, R2 | Por empezar |
| 6. Revisión | Qué cambió, qué se recorta | Sección "Bitácora" de este archivo | — |

## 2. Iteraciones

```mermaid
flowchart LR
  I0["Iteración 0<br/>Preparación"] --> I1["Iteración 1 → CP1<br/>Mapeo + flujo con stubs"]
  I1 --> I2["Iteración 2 → CP2<br/>Mapeo real + robot + clon"]
  I2 --> I3["Iteración 3 → Freeze<br/>Simulación + web + pitch"]
```

**Prioridad del equipo:** el **mapeo** (videos → entorno virtual) va primero en cada iteración. Todas las etapas leen `entorno.json`.

### Iteración 0 — Preparación (ahora → antes de CP1)
- [ ] Revisar y aprobar `requerimientos.md` (los 3 integrantes).
- [ ] Arrendar el pod RTX 5090 y pasar la prueba de humo ([`infraestructura.md`](infraestructura.md) §5).
- [ ] Conseguir un video de parque solar (bloquea RF-MAP-01..04).
- [ ] Crear `esquemas/*.schema.json` desde `contrato-datos.md`, partiendo por `entorno.schema.json`.
- [ ] Escribir un `entorno.json` de ejemplo a mano (stub del mapeo).
- [ ] Crear la estructura de carpetas del repo ([`arquitectura.md`](arquitectura.md) §7) y `render.yaml`.

### Iteración 1 — Mapeo y flujo con stubs (→ CP1, sáb 11:00)
- [ ] **Mapeo:** `generar_escena` crea `escena.usd` de 3 filas desde el `entorno.json` de ejemplo (RF-MAP-05..06).
- [ ] **Mapeo:** la web dibuja la misma escena en three.js (RF-MAP-07, RNF-16).
- [ ] API, Postgres y cola en Render (RF-API-01..05).
- [ ] Sim runner toma trabajos y sube a R2 (RF-GPU-01..04).
- [ ] Orquestador corre todas las etapas con stubs y valida cada salida (RF-ORQ-01..05).
- [ ] Web en Vercel: crear proyecto, subir videos y ver progreso (RF-WEB-01..03, RF-WEB-09).

### Iteración 2 — Mapeo real y etapas reales (→ CP2, sáb 23:00)
- [ ] **Mapeo:** frames con `ffmpeg` y agente Entorno sobre un video real (RF-MAP-01..04).
- [ ] Agente Tarea (RF-TAR-01..02).
- [ ] Catálogo de robots con fuentes y agente Robot (RF-ROB-01..04).
- [ ] Clon con `robot.usd` y `robot.urdf`, validado en el pod (RF-CLO-01..06).
- [ ] El visor 3D carga el robot y reproduce una trayectoria (RF-WEB-04..05).

### Iteración 3 — Simulación y demo (→ Freeze, dom 05:00)
- [ ] El clon instala paneles con el planificador; métricas, video y trayectoria (RF-INT-01..04).
- [ ] Panel lateral, video y corrida de respaldo en la web (RF-WEB-06..08, RNF-07).
- [ ] Verificar los criterios de aceptación ([`requerimientos.md`](requerimientos.md) §8).
- [ ] Pitch.
- [ ] Extras si sobra tiempo: RL (RF-INT-05), fondo reconstruido (RF-MAP-10).

**Regla de recorte:** si una tarea **M** está en riesgo 2 h antes del checkpoint, se deja su stub y se sigue. Un stub que funciona vale más que una etapa real a medias.

## 3. Pruebas

| Nivel | Qué prueba | Cómo | Cuándo |
|---|---|---|---|
| Esquema | Cada archivo del contrato | `jsonschema` contra `esquemas/` | En cada corrida (orquestador) y en CI |
| Etapa | Una etapa con entradas fijas | `pytest` con los stubs como fixture | Antes de cada merge que toca la etapa |
| Mapeo | `escena.usd` y la escena web salen iguales del mismo `entorno.json` | Comparar posiciones de filas y estructuras | Cada cambio en `generar_escena` o en el visor |
| API | Rutas de la web y del worker | `pytest` + cliente HTTP de FastAPI | Antes de cada merge en `api/` |
| Catálogo | Todo robot tiene `fuente.url` y `fuente.consultado` | Test que recorre `data/robots/` | En CI |
| Simulación | El clon carga y no atraviesa estructuras | Trabajo `validar_clon` del runner | En el pod RTX 5090 |
| Punta a punta | La corrida de demo cumple los 6 criterios de aceptación | Script `verificar_demo.py` | Antes del freeze |
| Web | Subida, progreso, visor, video y métricas | Revisión manual en la URL pública | Después de cada deploy |

## 4. Flujo de trabajo en git

- `main` siempre corre de punta a punta (aunque sea con stubs).
- Una rama por tarea: `feat/<etapa>-<algo>`, `docs/<algo>`, `fix/<algo>`.
- PR pequeño, una revisión de otra persona del equipo, y merge.
- Cambios en `contrato-datos.md` o `esquemas/`: se avisa a todo el equipo antes del merge (regla de la arquitectura).
- Commits citan el requerimiento cuando aplica: `feat(mapeo): escena procedural de 3 filas (RF-MAP-05)`.

## 5. Definición de "terminado"

Una tarea está terminada cuando:
1. Cumple el requerimiento que cita.
2. Su salida valida contra el esquema.
3. Tiene al menos una prueba (o un paso manual documentado si es de simulación).
4. Está en `main` y el flujo de punta a punta sigue corriendo.

## 6. Bitácora de revisiones

| Fecha | Checkpoint | Qué cambió | Decisiones |
|---|---|---|---|
| 2026-11-21 | — | Se crean requerimientos y ciclo de desarrollo | — |
| 2026-11-21 | — | Se agregan normas ISO e infraestructura | GPU: RTX 5090 en la nube; base: Ubuntu 22.04 + Isaac Sim 5.1 + Isaac Lab 2.3 (por verificar) |
| 2026-11-21 | — | Requerimientos v0.3 alineados con la arquitectura web + nube (PR #2) | El mapeo va primero; MoSCoW; normas ISO dentro de `requerimientos.md` |
