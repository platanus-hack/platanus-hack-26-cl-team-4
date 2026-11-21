# Especificación de requerimientos de VIAZ

> Estado: **borrador v0.4** (2026-11-21). Basado en [`arquitectura.md`](arquitectura.md), [`contrato-datos.md`](contrato-datos.md), [`agentes/`](agentes/README.md) y el [README](../README.md).
> Estructura según ISO/IEC/IEEE 29148. Prioridades según el método **MoSCoW**. Calidad según ISO/IEC 25010.
> **Cambio de v0.4:** el demo usa un entorno escrito a mano y una política entrenada con RL. El mapeo desde video pasa a Could.
> Lo marcado **[Por definir]** lo decide el equipo. Cada requerimiento tiene un ID: cítalo en issues, PRs y pruebas.

## Índice

1. [Propósito y alcance](#1-propósito-y-alcance)
2. [Actores e interesados](#2-actores-e-interesados)
3. [Método de priorización MoSCoW](#3-método-de-priorización-moscow)
4. [Requerimientos funcionales](#4-requerimientos-funcionales)
5. [Requerimientos no funcionales](#5-requerimientos-no-funcionales)
6. [Fuera del alcance (Won't)](#6-fuera-del-alcance-wont)
7. [Normas ISO](#7-normas-iso)
8. [Criterios de aceptación del demo](#8-criterios-de-aceptación-del-demo)
9. [Trazabilidad con los checkpoints](#9-trazabilidad-con-los-checkpoints)
10. [Supuestos y dependencias](#10-supuestos-y-dependencias)
11. [Preguntas abiertas](#11-preguntas-abiertas)

## 1. Propósito y alcance

- **Problema:** muchas industrias no usan robots. No saben qué robot sirve ni cómo trabajaría en su planta.
- **Solución:** VIAZ elige un robot real, lo construye en simulación y le enseña la tarea con aprendizaje por refuerzo (RL).
- **Caso del demo:** un megaparque solar. El robot toma un panel y lo deja apoyado sobre la estructura.

### 1.1 Plan del demo

```mermaid
flowchart LR
  E["1. Entorno<br/>escrito a mano"] --> R["2. Agente de<br/>selección de robot"]
  CAT[("Catálogo de<br/>robots reales")] --> R
  R --> C["3. Agente constructor<br/>robot en Isaac Lab"]
  E --> C
  C --> L["4. Entrenamiento RL<br/>instalar panel"]
  M["Agente monitor<br/>del entrenamiento"] -.vigila.-> L
  L --> V1["Video en cámara rápida<br/>del entrenamiento"]
  L --> V2["Muestra del robot<br/>ya entrenado"]
  V1 & V2 --> W["Web: robot elegido,<br/>videos y métricas"]
```

| Paso | Qué hace | Quién |
|---|---|---|
| 1 | Escribe `entorno.json` y `tarea.json` del parque del demo | El equipo, a mano |
| 2 | Elige el robot real del catálogo y justifica | Agente de selección de robot |
| 3 | Construye el robot en Isaac Lab con las specs del real y lo valida | Agente constructor |
| 4 | Entrena la política de instalar el panel con RL y graba el entrenamiento | Script de Isaac Lab en el pod |
| 5 | Vigila el entrenamiento y recomienda seguir, parar o ajustar | Agente monitor |
| 6 | Muestra los videos, el robot elegido y las métricas | Web (Vercel) |

**Dentro del alcance:**
- Un tipo de planta: `parque_solar`, con su entorno escrito a mano.
- Una tarea: `instalar_panel`. El robot **solo pone el panel** sobre la estructura: sin cables, pernos ni conexión eléctrica.
- Un catálogo curado de 5 a 10 robots reales.
- Una web pública con resultados precalculados: robot elegido, video en cámara rápida del entrenamiento y muestra del robot entrenado.

## 2. Actores e interesados

| Actor | Necesidad |
|---|---|
| **Cliente industrial** | Ver qué robot real le sirve y cómo trabaja en su planta |
| **Jurado / visitante** | Entender el flujo en menos de 2 min y ver al robot aprender y trabajar |
| **Equipo (operador)** | Escribir el entorno, lanzar el entrenamiento y decidir con la ayuda del monitor |
| **Fabricantes de robots** | Ver sus specs citadas con fuente y fecha |
| **Pod RTX 5090** | Ejecutar validación, entrenamiento y grabación (actor de sistema) |

## 3. Método de priorización MoSCoW

```mermaid
flowchart LR
  M["<b>Must</b><br/>Sin esto no hay demo"] --> S["<b>Should</b><br/>Importante, tiene alternativa"]
  S --> C["<b>Could</b><br/>Solo si sobra tiempo"]
  C --> W["<b>Won't</b><br/>No entra en el hack"]
```

| Nivel | Significado | Regla en el hack |
|---|---|---|
| **Must (M)** | Sin este requerimiento, el demo falla | Si está en riesgo, se reemplaza por un stub. Nunca se elimina |
| **Should (S)** | Aporta mucho valor, pero el demo funciona sin él | Se hace después de todos los Must del checkpoint |
| **Could (C)** | Mejora el demo, el impacto es bajo | Se hace solo después del CP2 y si sobra tiempo |
| **Won't (W)** | Se excluye de forma explícita en esta versión | No se trabaja. Queda registrado para después del hack |

**Resumen actual:**

| Tipo | Must | Should | Could | Won't |
|---|---|---|---|---|
| Funcionales | 44 | 20 | 16 | — |
| No funcionales | 13 | 6 | 0 | — |
| Fuera del alcance | — | — | — | 9 |

## 4. Requerimientos funcionales

```mermaid
flowchart LR
  MAP["4.1 Entorno<br/>RF-MAP"] --> ROB["4.3 Selección<br/>RF-ROB"]
  TAR["4.2 Tarea<br/>RF-TAR"] --> ROB
  ROB --> CLO["4.4 Constructor<br/>RF-CLO"]
  CLO --> INT["4.5 Entrenamiento RL<br/>RF-INT"]
  MON["4.6 Monitor<br/>RF-MON"] -.-> INT
  INT --> WEB["4.7 Web<br/>RF-WEB"]
  API["4.8 API y orquestador"] -.soporta.-> ROB
  GPU["4.9 Sim runner"] -.soporta.-> CLO & INT
```

### 4.1 Entorno (`entorno.json`, `sim/`)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-MAP-11 | El equipo escribe a mano el `entorno.json` del parque del demo, con `confianza` 1 en cada dato y la fuente de cada medida | **M** |
| RF-MAP-05 | El script `generar_escena` crea `escena.usd` desde `entorno.json`: terreno, filas, estructuras y paneles, con colisiones | **M** |
| RF-MAP-06 | La escena de referencia tiene al menos 3 filas de estructuras | **M** |
| RF-MAP-07 | La web genera la misma escena en three.js desde `entorno.json`, con las mismas reglas que `generar_escena` | **S** |
| RF-MAP-09 | El equipo corrige `entorno.json` y vuelve a generar la escena sin repetir otras etapas | **S** |
| RF-MAP-01 | El orquestador extrae frames de cada video con `ffmpeg` | **C** |
| RF-MAP-02 | El agente Entorno (Claude con visión) analiza los frames y llena `entorno.json` | **C** |
| RF-MAP-03 | El agente asigna a cada dato inferido un valor de `confianza` entre 0 y 1 | **C** |
| RF-MAP-04 | El agente clasifica la estructura como `tracker_1_eje` o `fijo` | **C** |
| RF-MAP-08 | Si un dato tiene `confianza` menor a 0,5, el sistema usa un valor por defecto documentado | **C** |
| RF-MAP-10 | El sistema genera un fondo visual reconstruido (NuRec u OVER) sin física | **C** |

### 4.2 Tarea (`tarea.json`)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-TAR-04 | El equipo escribe a mano el `tarea.json` del demo: `instalar_panel`, sin cables ni pernos | **M** |
| RF-TAR-02 | `tarea.json` define un objetivo medible: paneles y tiempo de ciclo en segundos | **M** |
| RF-TAR-03 | `tarea.json` lista restricciones operativas (ej.: no chocar con estructuras, panel horizontal) | **S** |
| RF-TAR-01 | El agente Tarea genera `tarea.json` desde la descripción del cliente y los frames | **C** |

### 4.3 Selección de robot (`agentes/`, `catalogo/robots/`)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-ROB-01 | El catálogo tiene entre 5 y 10 robots reales de instalación solar, un JSON por robot | **M** |
| RF-ROB-02 | Cada robot del catálogo cita `fuente.url` y `fuente.consultado` (fecha ISO 8601) | **M** |
| RF-ROB-03 | El agente elige solo robots del catálogo. `robot.json.id` coincide con un archivo existente | **M** |
| RF-ROB-04 | `robot.json` justifica la elección con datos de `entorno.json` y `tarea.json` (ej.: peso del panel vs carga útil) | **M** |
| RF-ROB-05 | `robot.json` lista al menos 2 alternativas descartadas con su motivo | **S** |
| RF-ROB-06 | El catálogo incluye al menos un robot de origen chino comprable en Chile | **S** |
| RF-ROB-07 | Cada robot del catálogo lista en `normas` las normas de seguridad que declara su fabricante | **C** |

### 4.4 Agente constructor del robot en Isaac Lab (`agentes/`, `sim/`)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-CLO-01 | El agente constructor arma el robot en Isaac Lab desde `robot.json`, con assets existentes de Isaac Lab (base, brazo, efector) | **M** |
| RF-CLO-02 | El robot construido respeta el alcance, la carga útil y la velocidad de `robot.json` | **M** |
| RF-CLO-03 | El agente entrega `robot_cfg.py` (configuración de Isaac Lab), `robot.usd` y `clon.json` | **M** |
| RF-CLO-04 | `clon.json` lista las diferencias con el robot real | **M** |
| RF-CLO-05 | El agente encola `validar_clon`, lee el error del pod y corrige. Máximo 3 intentos | **M** |
| RF-CLO-06 | `validar_clon` revisa que el robot cargue, no choque al inicio y alcance el panel y la estructura | **M** |
| RF-CLO-07 | Si el agente no logra un robot válido en 3 intentos, el sistema usa el clon determinista de `urdf.py` | **S** |
| RF-CLO-08 | El agente entrega `robot.urdf` con los mismos joints, para el visor web | **C** |

### 4.5 Entrenamiento RL de instalar el panel (`sim/`, pod RTX 5090)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-INT-10 | Existe un entorno de Isaac Lab `instalar_panel`: el robot toma un panel y lo deja apoyado sobre el tubo de la estructura | **M** |
| RF-INT-11 | El episodio termina con éxito si el panel queda apoyado, sin chocar con la estructura, dentro de la tolerancia **[Propuesta: 5 cm y 5°]** | **M** |
| RF-INT-12 | El script entrena la política con PPO en Isaac Lab, con entornos en paralelo en la 5090, y guarda checkpoints | **M** |
| RF-INT-13 | El script graba clips del entrenamiento a intervalos fijos y arma `entrenamiento_rapido.mp4` en cámara rápida | **M** |
| RF-INT-14 | El script evalúa la política final en 20 episodios y escribe `resultado.json` (`metodo: "rl"`, `politica`) | **M** |
| RF-INT-15 | El script graba `video.mp4`: la muestra del robot ya entrenado instalando paneles | **M** |
| RF-INT-16 | El script guarda la curva de entrenamiento (recompensa y tasa de éxito por iteración) en `curva.json` | **S** |
| RF-INT-17 | El script guarda `trayectoria.json` de un episodio de la política, para el visor web | **S** |
| RF-INT-01 | Si el RL no converge, un planificador (cuRobo o RMPflow) hace la tarea y graba la muestra (`metodo: "planificador"`) | **S** |

### 4.6 Agente monitor del entrenamiento (`agentes/`, pod)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-MON-01 | El agente corre en Render y lee las métricas que llegan con cada latido, cada 10 min **[Por definir]**: recompensa media, tasa de éxito, largo de episodio y pérdidas | **M** |
| RF-MON-02 | En cada chequeo, el agente clasifica el estado: `mejorando`, `estancado`, `divergiendo` o `terminado` | **M** |
| RF-MON-03 | El agente escribe cada chequeo en `monitoreo.jsonl`, con evidencia numérica y una recomendación | **M** |
| RF-MON-04 | El agente avisa al equipo si detecta NaN, divergencia o estancamiento por 3 chequeos seguidos | **M** |
| RF-MON-05 | El agente recomienda el mejor checkpoint para la muestra final | **S** |
| RF-MON-06 | El agente marca hitos (primer éxito, mejor recompensa) para el video en cámara rápida | **S** |
| RF-MON-07 | El agente escribe un resumen final del entrenamiento para la web y el pitch | **S** |
| RF-MON-08 | El agente detiene el entrenamiento solo con NaN. Otras acciones las aprueba un humano | **M** |

### 4.7 Web (`web/`, Next.js en Vercel)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-WEB-13 | La web reproduce `entrenamiento_rapido.mp4`: el video en cámara rápida del entrenamiento | **M** |
| RF-WEB-06 | La web reproduce `video.mp4`: la muestra del robot ya entrenado | **M** |
| RF-WEB-07 | El panel lateral muestra el robot elegido, su justificación, su fuente, las diferencias del clon y las métricas | **M** |
| RF-WEB-08 | La web muestra la corrida del demo precalculada (`/corridas/demo`) sin depender del pod | **M** |
| RF-WEB-09 | La web funciona en una URL pública de Vercel | **M** |
| RF-WEB-15 | La web indica cuánto tiempo real y cuántos pasos de simulación representa el video acelerado | **M** |
| RF-WEB-14 | La web muestra la curva de entrenamiento y los hitos del monitor | **S** |
| RF-WEB-04 | El visor 3D muestra la escena y el robot desde `robot.urdf` | **S** |
| RF-WEB-05 | El visor reproduce `trayectoria.json` de la política entrenada | **S** |
| RF-WEB-11 | La web usa el vocabulario de ISO 8373 (manipulador, efector final, carga útil, robot móvil) | **S** |
| RF-WEB-01 | El cliente crea un proyecto con nombre y descripción | **C** |
| RF-WEB-02 | El cliente sube los videos directo a R2 con URLs firmadas | **C** |
| RF-WEB-03 | La web consulta `GET /corridas/{id}` cada 2 s y muestra el estado de cada etapa | **C** |
| RF-WEB-10 | La web marca los datos del entorno con `confianza` baja | **C** |
| RF-WEB-12 | La web muestra el fondo reconstruido si existe | **C** |

### 4.8 API y orquestador (`backend/`, en Render)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-API-03 | `GET /corridas/{id}` y `GET /corridas/demo` devuelven el estado, las etapas y los artefactos | **M** |
| RF-API-04 | `POST /worker/trabajos/tomar` entrega un trabajo con `SELECT … FOR UPDATE SKIP LOCKED`, o `204` si no hay | **M** |
| RF-API-05 | `POST /worker/trabajos/{id}/fin` registra el resultado. Un trabajo sin latido en 30 min vuelve a la cola | **M** |
| RF-API-06 | `POST /worker/trabajos/{id}/latido` mantiene vivo un trabajo largo y recibe las métricas nuevas del entrenamiento | **M** |
| RF-ORQ-01 | El orquestador corre las etapas en orden y actualiza el estado de la corrida | **M** |
| RF-ORQ-02 | El orquestador valida cada salida contra su JSON Schema de `esquemas/` | **M** |
| RF-ORQ-05 | El orquestador acepta salidas escritas a mano por etapa (`entorno.json`, `tarea.json`) | **M** |
| RF-ORQ-03 | Si una salida no valida, el orquestador reintenta la etapa 1 vez. Si falla otra vez, la corrida pasa a `error` | **S** |
| RF-ORQ-04 | El orquestador repite una sola etapa con los archivos ya guardados | **S** |
| RF-ORQ-06 | El orquestador registra cada llamada a Claude y al runner: etapa, duración, tokens y resultado | **S** |
| RF-API-01 | `POST /proyectos` crea el proyecto y devuelve las URLs firmadas de subida | **C** |
| RF-API-02 | `POST /proyectos/{id}/corridas` crea una corrida y la encola | **C** |

### 4.9 Sim runner (`worker-gpu/`, pod RTX 5090)

| ID | Requerimiento | MoSCoW |
|---|---|---|
| RF-GPU-01 | El runner toma trabajos de la API por HTTPS (pull). El pod no expone puertos | **M** |
| RF-GPU-02 | El runner ejecuta `generar_escena`, `validar_clon`, `entrenar` y `evaluar` en Isaac Lab headless | **M** |
| RF-GPU-03 | El runner ejecuta un trabajo a la vez | **M** |
| RF-GPU-04 | El runner sube los artefactos a R2 con las URLs firmadas del trabajo | **M** |
| RF-GPU-06 | Durante `entrenar`, el runner envía un latido cada 5 min con las métricas nuevas. Si la respuesta pide `detener`, guarda un checkpoint y termina | **M** |
| RF-GPU-05 | Si el pod se reinicia, el runner retoma el entrenamiento desde el último checkpoint | **S** |

## 5. Requerimientos no funcionales

Cada RNF lleva su característica de calidad según ISO/IEC 25010:2023.

```mermaid
flowchart TD
  Q[ISO/IEC 25010] --> C1[Compatibilidad] --> R01["RNF-01, RNF-12"]
  Q --> C2[Seguridad] --> R02["RNF-02, RNF-08, RNF-11, RNF-15"]
  Q --> C3[Adecuación funcional] --> R03["RNF-03, RNF-13, RNF-16, RNF-18"]
  Q --> C4[Mantenibilidad] --> R04["RNF-04, RNF-09, RNF-14"]
  Q --> C5[Eficiencia de desempeño] --> R05["RNF-05, RNF-06, RNF-17, RNF-19"]
  Q --> C6[Fiabilidad] --> R07[RNF-07]
  Q --> C7[Flexibilidad] --> R10[RNF-10]
```

| ID | Característica (ISO/IEC 25010) | Requerimiento | Norma relacionada | MoSCoW |
|---|---|---|---|---|
| RNF-01 | Compatibilidad · interoperabilidad | Toda salida cumple el contrato: unidades SI, rutas relativas, `version: 1` | ISO 80000-1 | **M** |
| RNF-02 | Seguridad · responsabilidad | Todo dato externo cita URL y fecha. Todo dato del entorno lleva `confianza` y fuente | ISO/IEC 5338 | **M** |
| RNF-03 | Adecuación funcional · corrección | La web no afirma fidelidad exacta. Muestra métricas y diferencias con el real | ISO 12100 | **M** |
| RNF-04 | Mantenibilidad · capacidad de prueba | Cada etapa se repite sin volver a correr las anteriores | ISO/IEC/IEEE 29119 | **S** |
| RNF-05 | Eficiencia de desempeño (web) | La página carga en menos de 3 s. Los videos empiezan en menos de 5 s | — | **S** |
| RNF-06 | Eficiencia de desempeño (agentes) | Selección de robot: menos de 2 min. Constructor con sus 3 intentos: menos de 30 min | — | **S** |
| RNF-07 | Fiabilidad · disponibilidad | La corrida del demo en R2 se muestra aunque fallen el pod o Claude | — | **M** |
| RNF-08 | Seguridad · confidencialidad | La clave de Claude vive solo en Render. El pod no la necesita. El repo no contiene secretos | ISO/IEC 27002 | **M** |
| RNF-09 | Mantenibilidad · modularidad | Cada agente tiene su prompt en un archivo propio y lee solo archivos del contrato | ISO/IEC/IEEE 42010 | **M** |
| RNF-10 | Flexibilidad · instalabilidad | El runner corre en un pod RTX 5090 con versiones fijadas ([`infraestructura.md`](infraestructura.md)) | — | **M** |
| RNF-11 | Seguridad · autenticidad | Las rutas `/worker/*` exigen `Authorization: Bearer <WORKER_TOKEN>` | ISO/IEC 27002 | **M** |
| RNF-12 | Compatibilidad · interoperabilidad | Los archivos del contrato son JSON UTF-8. Las fechas usan ISO 8601 (`AAAA-MM-DD`) | ISO/IEC 21778, ISO 8601 | **M** |
| RNF-13 | Adecuación funcional · corrección | El sistema trata cada salida de un agente como no confiable hasta validarla | ISO/IEC 5338 | **M** |
| RNF-14 | Mantenibilidad · analizabilidad | Cada requerimiento Must tiene al menos una prueba o un paso manual documentado | ISO/IEC/IEEE 29119 | **S** |
| RNF-15 | Seguridad · confidencialidad | Las URLs firmadas de R2 vencen en 24 h o menos | ISO/IEC 27002 | **S** |
| RNF-16 | Adecuación funcional · coherencia | La escena web y `escena.usd` salen del mismo `entorno.json` con las mismas reglas | — | **S** |
| RNF-17 | Eficiencia de desempeño (entrenamiento) | El entrenamiento cabe en el tiempo de pod disponible. **[Propuesta: 4 h como máximo]** | — | **M** |
| RNF-18 | Adecuación funcional · corrección | Los videos se rotulan como simulación. El video acelerado dice su factor de velocidad | ISO 12100 | **M** |
| RNF-19 | Eficiencia de desempeño (video) | `entrenamiento_rapido.mp4` dura entre 30 y 90 s y pesa menos de 50 MB | — | **M** |

## 6. Fuera del alcance (Won't)

| ID | Qué no hacemos en el hack | Por qué |
|---|---|---|
| W-01 | Malla física desde la reconstrucción del video | Trae agujeros y ruido. La física usa la escena procedural |
| W-02 | Búsqueda web de robots durante la corrida | Agrega riesgo en vivo. El agente usa solo el catálogo |
| W-03 | Gemelo digital exacto del robot real | El clon usa assets de Isaac Lab. La web muestra las diferencias (RNF-03) |
| W-04 | Otras industrias o tareas | Un solo caso: parque solar, `instalar_panel` |
| W-05 | Cables, pernos, conexión eléctrica y fijación del panel | La tarea es solo dejar el panel apoyado sobre la estructura |
| W-06 | Cuentas de usuario e inicio de sesión | El demo no las necesita |
| W-07 | Certificación ISO | Usamos las normas como referencia, no como certificación |
| W-08 | Entrenamiento en vivo durante el pitch | Dura horas. La web muestra el video acelerado |
| W-09 | Política en vivo en la web | La web muestra videos grabados. El pod puede estar apagado |

## 7. Normas ISO

No buscamos certificación. Usamos las normas como referencia para ordenar el trabajo y dar credibilidad al pitch.

```mermaid
flowchart LR
  subgraph P[Proceso]
    N1[12207 ciclo de vida]
    N2[29148 requerimientos]
    N3[42010 arquitectura]
    N4[29119 pruebas]
  end
  subgraph Q[Producto]
    N5[25010 calidad]
    N6[5338 sistemas con IA]
    N7[27002 seguridad]
  end
  subgraph D[Datos]
    N8[80000-1 unidades SI]
    N9[8601 fechas]
    N10[21778 JSON]
  end
  subgraph R[Robótica: referencia]
    N11[8373 vocabulario]
    N12[10218 seguridad robots]
    N13[3691-4 vehículos sin conductor]
    N14[12100 evaluación de riesgo]
  end
```

### 7.1 Normas que aplicamos

| Norma | Tema | Cómo la aplicamos | Requerimientos |
|---|---|---|---|
| ISO/IEC/IEEE 12207:2017 | Ciclo de vida del software | Ciclo incremental por checkpoint ([`ciclo-desarrollo.md`](ciclo-desarrollo.md)) | — |
| ISO/IEC/IEEE 29148:2018 | Ingeniería de requerimientos | Estructura de este documento. ID único, prioridad y verificación por requerimiento | Todos |
| ISO/IEC/IEEE 42010:2022 | Descripción de arquitectura | Vistas y decisiones con su porqué en [`arquitectura.md`](arquitectura.md). Interesados en §2 | RNF-09 |
| ISO/IEC 25010:2023 | Calidad del producto | Clasificación de los RNF (§5) | RNF-01..19 |
| ISO/IEC/IEEE 29119 | Pruebas de software | Niveles de prueba: esquema, etapa, sistema y aceptación | RNF-04, RNF-14 |
| ISO/IEC 5338:2023 | Ciclo de vida de sistemas con IA | Salidas de agentes validadas y registradas. Entrenamiento vigilado por el monitor, con decisiones humanas | RNF-02, RNF-13, RF-ORQ-06, RF-ROB-03, RF-MON-08 |
| ISO/IEC 27002:2022 | Controles de seguridad | Secretos fuera del repo, token del worker, URLs firmadas con vencimiento | RNF-08, RNF-11, RNF-15 |
| ISO 80000-1 | Magnitudes y unidades | Unidades SI con la unidad en el nombre del campo (`peso_kg`) | RNF-01 |
| ISO 8601 | Fechas y horas | Fechas `AAAA-MM-DD` en fuentes y registros | RNF-12, RF-ROB-02 |
| ISO/IEC 21778:2017 | Sintaxis JSON | Archivos del contrato en JSON UTF-8 validados con JSON Schema | RNF-12 |

### 7.2 Normas que referenciamos (robótica)

Estas normas aplican a los **robots reales**, no a nuestro software.

| Norma | Tema | Uso en el proyecto | Requerimientos |
|---|---|---|---|
| ISO 8373:2021 | Vocabulario de robótica | Términos de la web y del catálogo | RF-WEB-11 |
| ISO 10218-1/-2:2025 | Seguridad de robots industriales | Campo `normas` del catálogo y pitch | RF-ROB-07 |
| ISO 3691-4:2023 | Vehículos industriales sin conductor | Robots con base móvil del catálogo | RF-ROB-07 |
| ISO 12100:2010 | Evaluación de riesgo de máquinas | Pitch: la simulación revisa alcance y carga antes de comprar. No certifica nada | RNF-03, RNF-18 |

### 7.3 Controles de seguridad (ISO/IEC 27002, mínimo)

- **Secretos:** la clave de Claude y las credenciales de R2 viven en variables de entorno. Nunca en git.
- **Worker:** el pod se autentica con `WORKER_TOKEN` y no expone puertos.
- **Archivos:** viven en R2 sin acceso público. Se accede solo con URLs firmadas.
- **Costo y exposición:** el equipo apaga el pod cuando no lo usa.

## 8. Criterios de aceptación del demo

```mermaid
flowchart TD
  A1{"entorno.json a mano válido<br/>y escena con ≥ 3 filas"} -->|sí| A2{"Robot del catálogo con<br/>carga útil ≥ peso del panel"}
  A2 -->|sí| A3{"Robot construido por el agente<br/>y validado en Isaac Lab"}
  A3 -->|sí| A4{"Política: tasa de éxito ≥ 70 %<br/>en 20 episodios"}
  A4 -->|sí| A5{"Videos: cámara rápida del<br/>entrenamiento y muestra final"}
  A5 -->|sí| A6{"Web pública con robot,<br/>videos y métricas, sin pod"}
  A6 -->|sí| OK[Demo aceptado]
  A1 & A2 & A3 & A4 & A5 & A6 -->|no| FIX[Volver a la etapa que falla]
```

1. `entorno.json` y `tarea.json` escritos a mano validan contra su esquema, y la escena tiene al menos 3 filas.
2. El robot elegido existe en `data/robots/` y su carga útil es mayor o igual al peso del panel.
3. El agente constructor entrega un robot con `validado_en_escena: true`, en 3 intentos o menos.
4. La política entrenada deja el panel apoyado en al menos el 70 % de 20 episodios de evaluación **[Umbral por confirmar]**.
5. Existen `entrenamiento_rapido.mp4` (30 a 90 s) y `video.mp4` con la muestra del robot entrenado.
6. La web pública muestra el robot elegido, su justificación, los dos videos y las métricas, con el pod apagado.

**Plan B:** si la política no llega al umbral, el planificador hace la muestra final (RF-INT-01). La web dice qué método se usó.

## 9. Trazabilidad con los checkpoints

```mermaid
timeline
  title Requerimientos Must por checkpoint
  CP1 (sáb 11:00) : Entorno y tarea a mano (RF-MAP-11, RF-TAR-04) : Escena en Isaac (RF-MAP-05..06) : Agente de selección (RF-ROB-01..04) : Ejemplo de RL de Isaac Lab corre en el pod
  CP2 (sáb 23:00) : Agente constructor (RF-CLO-01..06) : Entorno RL instalar_panel (RF-INT-10..11) : Entrenamiento lanzado + monitor (RF-INT-12..13, RF-MON-01..04)
  Freeze (dom 05:00) : Evaluación y videos (RF-INT-14..15) : Web con videos (RF-WEB-06..09, 13, 15) : Corrida del demo (RNF-07)
```

| Checkpoint | Must | Should / Could (si hay tiempo) |
|---|---|---|
| **CP1** (sáb 11:00) | RF-MAP-11, RF-MAP-05..06, RF-TAR-02, RF-TAR-04, RF-ROB-01..04, RF-API-03..06, RF-GPU-01..04, RF-ORQ-01..02, RF-ORQ-05, RNF-01, RNF-12; ejemplo de RL de Isaac Lab en el pod | RF-MAP-07, RF-ROB-05..06, RF-ORQ-06 |
| **CP2** (sáb 23:00) | RF-CLO-01..06, RF-INT-10..13, RF-GPU-06, RF-MON-01..04, RF-MON-08 | RF-CLO-07, RF-INT-16, RF-MON-05..06 |
| **Freeze** (dom 05:00) | RF-INT-14..15, RF-WEB-06..09, RF-WEB-13, RF-WEB-15, RNF-07, RNF-18..19, criterios de §8 | RF-INT-01, RF-INT-17, RF-MON-07, RF-WEB-04..05, RF-WEB-14 |

## 10. Supuestos y dependencias

- Hay un pod RTX 5090 (RunPod o Vast.ai) que aprobó la prueba de humo de [`infraestructura.md`](infraestructura.md) §5, incluido un ejemplo de RL de Isaac Lab.
- Hay horas de pod suficientes para entrenar (RNF-17) y para repetir el entrenamiento 1 vez si falla.
- Hay crédito en Render (US$50) y una cuenta de Cloudflare R2.
- Hay acceso a la API de Claude con tool use **[Origen de los créditos por definir]**.
- El equipo tiene datos de un parque solar real para escribir `entorno.json` (ficha técnica, fotos o imagen satelital).
- El equipo reverifica las specs de robots antes del freeze (datos base del 2026-09-28).

## 11. Preguntas abiertas

- ¿RunPod o Vast.ai? ¿Quién crea la cuenta y carga el saldo?
- ¿De dónde salen los créditos de la Claude API?
- ¿Qué parque real usamos para el `entorno.json` a mano?
- ¿Qué robot es la referencia del demo?
- ¿Quién es responsable de cada área?
- **RL:** ¿la base del robot queda fija junto a la estructura durante el entrenamiento, o el robot también se desplaza? Una base fija entrena mucho más rápido.
- **RL:** ¿el umbral de éxito es 5 cm y 5°, con 70 % en 20 episodios?
- **RL:** ¿cuántas horas de pod damos al entrenamiento (RNF-17)?
- **Monitor:** ¿avisa por Discord, por consola o en un archivo?
- **Assets:** ¿qué brazo de Isaac Lab soporta la carga del panel (32 kg)? Varios brazos de catálogo cargan menos de 32 kg. Ver [`agentes/constructor-robot.md`](agentes/constructor-robot.md).
