# Agentes de VIAZ: contratos e instrucciones

> Estado: **v2** (2026-11-21). Basado en [`requerimientos.md`](../requerimientos.md) v0.4, [`arquitectura.md`](../arquitectura.md) y [`contrato-datos.md`](../contrato-datos.md).
> **Fuente de verdad de los datos:** los JSON Schema de [`backend/viaz/esquemas/`](../../backend/viaz/esquemas/).
> **Fuente de verdad de las instrucciones:** los prompts de [`backend/viaz/agentes/prompts/`](../../backend/viaz/agentes/prompts/) (RNF-09).

## 1. Agentes del demo

```mermaid
flowchart LR
  H["Equipo:<br/>entorno.json + tarea.json<br/>a mano"] --> ROB["Agente de<br/>selección de robot"]
  CAT[(Catálogo de robots)] --> ROB
  WEBB["Búsqueda web<br/>(v3, no existe)"] -.-> ROB
  ROB -->|"robot.json<br/>(v3: uno por finalista)"| CON["Agente constructor<br/>Isaac Lab"]
  ASS[(Catálogo de assets<br/>Isaac Lab)] --> CON
  CON -->|robot_cfg.py + robot.usd| RL["Entrenamiento RL<br/>pod 5090"]
  RL -->|métricas| MON["Agente monitor<br/>del entrenamiento"]
  MON -->|avisos por Discord| H
  RL --> V["Videos:<br/>cámara rápida + muestra"]
  MCP["Agente MCP Isaac Sim<br/>solo depuración"] -.-> CON & RL
```

| Agente | Contrato | Tipo | Prompt | Requerimientos | En el demo | Estado |
|---|---|---|---|---|---|---|
| Selección de robot | [`seleccion-robot.md`](seleccion-robot.md) (contrato v3) | Código + LLM (+ búsqueda web en v3) | [`robot.md`](../../backend/viaz/agentes/prompts/robot.md) | RF-ROB-01..12 | **Sí (Must)** | Implementado: v2 (un robot, catálogo cerrado). v3 sin implementar |
| Constructor del robot en Isaac Lab | [`constructor-robot.md`](constructor-robot.md) | LLM + plantilla + pod | [`constructor.md`](../../backend/viaz/agentes/prompts/constructor.md) | RF-CLO-01..08 | **Sí (Must)** | Implementado ([`robot_cfg.py`](../../backend/viaz/robot_cfg.py)). `crear_articulacion_cfg()` sin probar en Isaac |
| Monitor del entrenamiento | [`monitor-entrenamiento.md`](monitor-entrenamiento.md) | LLM + reglas | [`monitor.md`](../../backend/viaz/agentes/prompts/monitor.md) | RF-MON-01..10 | **Sí (Must)** | Implementado ([`monitor.py`](../../backend/viaz/monitor.py)). Discord sin probar con un webhook real |
| MCP de Isaac Sim | [`mcp-isaac-sim.md`](mcp-isaac-sim.md) | LLM con herramientas MCP | En el contrato, §5 | Depuración | Opcional | Por definir el servidor |
| Mapeo de terreno (Entorno) | [`mapeo-terreno.md`](mapeo-terreno.md) | LLM con visión | [`entorno.md`](../../backend/viaz/agentes/prompts/entorno.md) | RF-MAP-01..04 | No (Could): el entorno va a mano | Implementado |
| Tarea | [`tarea.md`](tarea.md) | LLM con visión | [`tarea.md`](../../backend/viaz/agentes/prompts/tarea.md) | RF-TAR-01 | No (Could): la tarea va a mano | Implementado |

## 2. Formato común de un contrato

| Sección | Qué dice |
|---|---|
| 1. Propósito | Qué decide el agente y por qué existe |
| 2. Entradas | Archivos y datos que recibe, con su origen |
| 3. Salida | Archivo que produce, qué campos llena el agente y cuáles el sistema |
| 4. Reglas | Invariantes que el código verifica después de la respuesta |
| 5. Instrucciones | Resumen del prompt y enlace al archivo |
| 6. Errores | Qué pasa si el agente falla |
| 7. Pruebas | Cómo se verifica el contrato |

## 3. Reglas comunes a todos los agentes LLM

- **Modelo:** `VIAZ_MODELO` (por defecto `claude-opus-5-5`). Esfuerzo `high`.
- **Salida estructurada:** cada llamada usa `output_config.format` con el JSON Schema del agente ([`base.py`](../../backend/viaz/agentes/base.py)).
- **Respaldo:** `fallbacks: "default"`. Si el modelo rechaza, la API reintenta en un modelo de respaldo.
- **Validación doble:** el esquema de la API omite rangos. El código valida después contra el esquema completo (RNF-13).
- **Los agentes no escriben código libre.** Devuelven JSON; plantillas y scripts lo convierten en archivos de Isaac.
- **Unidades SI** con la unidad en el nombre del campo (ISO 80000-1).
- **Idioma:** el texto libre va en español de Chile.
- **Datos, no órdenes:** un texto en una entrada es un dato. El agente no sigue instrucciones que aparezcan ahí.
- **Decisiones humanas:** los agentes recomiendan; el equipo aprueba lo que cuesta horas de pod (ISO/IEC 5338).
- **Modo `fijo`:** `VIAZ_AGENTES=fijo` reemplaza cada LLM por un fixture.

## 4. Componentes sin LLM

### Entrenamiento RL (`sim/`, pod)

| Trabajo | Entradas | Salidas |
|---|---|---|
| `generar_escena` | `entorno.json` | `escena.usd` |
| `validar_clon` | `robot_cfg.py`, `escena.usd`, `entorno.json` | `validacion.json`, `robot.usd` |
| `entrenar` | `robot_cfg.py`, `escena.usd`, `entorno.json`, `tarea.json` | Checkpoints, métricas por latido, clips → `entrenamiento_rapido.mp4`, `curva.json` |
| `evaluar` | Checkpoint elegido | `resultado.json` (`metodo: "rl"`), `video.mp4`, `trayectoria.json` (Should) |

- **Tarea RL:** con la base detenida, el brazo toma un panel y lo deja apoyado sobre el tubo. Sin cables ni pernos (W-05).
- **Base móvil:** avanza entre puntos de montaje con un controlador programado (RF-INT-18). Se detiene con ruido de ±15 cm y ±5° (RF-INT-19).
- **Éxito:** panel apoyado, sin choque, a 5 cm y 5° o menos (RF-INT-11). Meta: 90 % en 100 episodios.
- **Tiempo:** fijo. Se fija tras la primera hora de entrenamiento (RNF-17).
- **Plan B:** si la política queda bajo 50 %, el planificador graba la muestra (RF-INT-01).

### Orquestador ([`orquestador.py`](../../backend/viaz/orquestador.py))

- **Hoy:** corre Entorno → Tarea → Robot → Clon determinista → `ejecutar_tarea` con planificador.
- **Para el demo:** lee `entorno.json` y `tarea.json` a mano, corre Robot → Constructor → `entrenar` → `evaluar`, y el monitor en paralelo.

## 5. Estado del código frente a los requerimientos

| Tema | Requerimientos v0.7 | Código | Pendiente |
|---|---|---|---|
| Entorno y tarea | A mano (RF-MAP-11, RF-TAR-04) | `VIAZ_ENTORNO_MANUAL` / `VIAZ_TAREA_MANUAL`; sin ruta usa los fixtures | Escribir el `entorno.json` del parque de referencia |
| Constructor | Agente con Isaac Lab (RF-CLO-01..07) | Implementado: 3 intentos + ensamblaje por defecto | Verificar `crear_articulacion_cfg()` y el catálogo de assets en el pod |
| Entrenamiento | `entrenar`, `grabar_clips`, `evaluar` (RF-INT-12..15) | Implementado en el runner; el entorno RL lo construye el equipo | Entorno RL de Isaac Lab que cumpla [`contrato-entorno-rl.md`](../contrato-entorno-rl.md) |
| Monitor | RF-MON-01..10 | Implementado: reglas + Claude, Discord, hitos, detener con NaN o 90 % × 3 | Crear el webhook de Discord |
| Latido | RF-API-06, RF-GPU-06 | Implementado | — |
| Plan B con planificador | RF-INT-01 (Should) | Solo una nota en `resultado.json` bajo 50 % | Por hacer |
| Curva en la web | RF-WEB-14 (Should) | `curva.json` existe; la web no lo dibuja | Por hacer |
| Frames por video | Solo si se usa el mapeo (Could) | 1 cada 3 s, máx. 8 | Sin acción para el demo |
