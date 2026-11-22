# Pendientes para una corrida real con `VIAZ_AGENTES=claude`

- **Fecha:** 2026-11-22.
- **Commit base:** `dc7a26b` (`main`).
- **Objetivo:** correr todos los agentes con Claude real, de punta a punta, con clave de API (A) o con suscripción (B).

**Resumen**
1. Hoy ningún flujo corre todos los agentes juntos: `rl` salta Tarea (y Entorno sin `VIAZ_MEDIR`), y `planificador` salta Constructor, RL, Monitor y Comparación.
2. Con clave de API (A), el código ya usa la API documentada. Falta probarla con el modelo real, manejar sus errores y desplegarla.
3. Con suscripción (B), el backend no tiene cómo autenticarse. Hace falta un adaptador a `claude -p` o al Agent SDK.
4. Los términos permiten B solo como uso personal de Claude Code. B no sirve para Render ni para un producto.
5. Tres agentes (Búsqueda, Monitor, Comparación) caen a reglas sin avisar. Una corrida puede terminar "lista" sin que Claude haya respondido.

## Estado honesto

| Estado | Qué |
|---|---|
| Real y probado | `pytest` del backend: 323 passed, 1 skipped (falta torch), 1 xfailed. Todo en modo `fijo` o con `pedir_json` reemplazado por `monkeypatch`. El pod responde por `ssh viaz-pod`. |
| Sin probar | Cualquier llamada real a Claude: los 8 prompts de `backend/viaz/agentes/prompts/` y los esquemas que manda `para_api`. |
| Sin probar | La web en esta sesión. Una corrida con `runner.py --modo isaac` lanzada por el orquestador. |
| De relleno | `sim/rl_simulado.py` inventa la curva de entrenamiento y los videos (`sim/rl_simulado.py:8-9`). |
| No existe | Una corrida de punta a punta con `VIAZ_AGENTES=claude`. La autenticación con suscripción en el backend. `ANTHROPIC_API_KEY` o `ANTHROPIC_AUTH_TOKEN` en la sesión de trabajo. |

## Índice

| # | Problema | Afecta a | Gravedad |
|---|---|---|---|
| 1 | Ningún flujo corre todos los agentes | Ambas | bloquea |
| 2 | El backend solo se autentica con clave de API | Suscripción | bloquea |
| 3 | Los términos no permiten la suscripción en Render ni en un producto | Suscripción | bloquea |
| 4 | La búsqueda web depende de citas que el CLI no entrega | Suscripción | degrada |
| 5 | Los errores de la API botan la corrida entera | Ambas | bloquea |
| 6 | Búsqueda, Monitor y Comparación fallan en silencio | Ambas | riesgo |
| 7 | Los esquemas nunca pasaron por la API real | Ambas | riesgo |
| 8 | `max_tokens` fijo con pensamiento siempre activo en Opus 5.5 | Ambas | riesgo |
| 9 | `render.yaml` despliega en modo `fijo` | API key | bloquea |
| 10 | El pod no alcanza el almacén local | Ambas | bloquea |
| 11 | El worker Isaac no está listo para el orquestador | Ambas | bloquea |
| 12 | La corrida dura más de 12 h y gasta sin tope | Ambas | riesgo |
| 13 | El Monitor puede trabar la espera del entrenamiento | Ambas | riesgo |

## 1. Ningún flujo corre todos los agentes

**Qué pasa**
- Flujo `rl` (por defecto, `config.py:68`): el agente Entorno corre solo con `VIAZ_MEDIR`, videos y sin `VIAZ_ENTORNO_MANUAL` (`orquestador.py:333`). Si no, lee el entorno a mano (`orquestador.py:336`).
- Flujo `rl`: la tarea siempre se lee a mano. Nunca llama al agente Tarea (`orquestador.py:344`).
- Flujo `planificador`: llama a Entorno y Tarea (`orquestador.py:150`, `:155`), pero usa el clon determinista (`:165`) y `ejecutar_tarea`. No llama a Constructor, RL, Monitor ni Comparación.
- Con `VIAZ_MEDIR`, Entorno necesita el trabajo de GPU `medir_entorno` y el Python de medición del pod (`runner.py:316`). En modo simulado escribe `"disponible": false` (`runner.py:309-312`).

- **Por qué importa:** no hay forma de ejecutar los 6 agentes del README en una sola corrida. Tarea nunca corre junto con el entrenamiento.
- **Afecta a:** ambas.

**Soluciones**
- **A. Opción en `rl` para pedir la tarea al agente** (variable nueva, por ejemplo `VIAZ_TAREA_AGENTE=1`; nombre a decidir).
  - Pro: cambio chico en `procesar_rl`; reutiliza `agentes.tarea`.
  - Contra: Tarea necesita frames; hay que sacarlos aunque no haya medición.
- **B. Dos corridas:** una con `planificador` (Entorno + Tarea) y otra con `rl` que lea esos JSON como "manuales".
  - Pro: cero código.
  - Contra: no es una corrida de punta a punta; los archivos se copian a mano.

- **Recomendada:** A, porque es la única que cumple "punta a punta". `exigir_pipeline` ya corta las tareas sin simulación.
- **Cómo se verifica:** un test nuevo en `test_rl.py`, en modo `fijo` con la opción encendida, confirma que `tarea.json` viene del agente y no del fixture.

## 2. El backend solo se autentica con clave de API

**Qué pasa**
- `pedir_json` crea `anthropic.Anthropic()`, que lee `ANTHROPIC_API_KEY` (`base.py:26`). La búsqueda crea su propio cliente (`busqueda.py:229`).
- Una suscripción no entrega clave de API. Los caminos oficiales desde un programa son `claude -p` y el Agent SDK, con `claude setup-token` y `CLAUDE_CODE_OAUTH_TOKEN` ([autenticación](https://code.claude.com/docs/en/authentication)).

| El backend usa | API (A) | `claude -p` / Agent SDK (B) |
|---|---|---|
| Salida JSON con esquema | `output_config.format` ([doc](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)) | `--json-schema` → campo `structured_output` ([doc](https://code.claude.com/docs/en/headless)); SDK: `output_format` ([doc](https://code.claude.com/docs/en/agent-sdk/structured-outputs)) |
| Imágenes base64 | Bloques `image` en el mensaje | SDK: bloques `image` con entrada en streaming ([doc](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)). CLI: `--input-format stream-json` existe ([doc](https://code.claude.com/docs/en/cli-reference)); la forma del bloque en el CLI: **[Sin verificar]** |
| Búsqueda web con citas | `web_search_20250305` con `cited_text` ([doc](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)) | `WebSearch` devuelve solo títulos y URLs ([doc](https://code.claude.com/docs/en/tools-reference)). Ver problema 4 |
| `effort` | `output_config.effort` ([doc](https://platform.claude.com/docs/en/build-with-claude/effort)) | `--effort` ([doc](https://code.claude.com/docs/en/cli-reference)); SDK: `effort` ([doc](https://code.claude.com/docs/en/agent-sdk/python)) |
| Tiempo tope | `timeout` del SDK `anthropic` | Sin bandera de tiempo. SDK: `API_TIMEOUT_MS` por intento, en `env` ([doc](https://code.claude.com/docs/en/agent-sdk/python)). Para el total: matar el proceso |
| Respaldo ante rechazo | beta `server-side-fallback-2026-07-01` + `fallbacks="default"` ([doc](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)) | `--betas` es solo para clave de API; `--fallback-model` cubre sobrecarga, no rechazos ([doc](https://code.claude.com/docs/en/cli-reference)) |

**Trampas del camino B**
- `ANTHROPIC_API_KEY` gana sobre `CLAUDE_CODE_OAUTH_TOKEN` si las dos existen ([precedencia](https://code.claude.com/docs/en/authentication#authentication-precedence)). Una corrida "con suscripción" puede cobrar a la API sin avisar.
- `--bare` no lee `CLAUDE_CODE_OAUTH_TOKEN` ([doc](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token)). Sin `--bare`, `claude -p` carga hooks, CLAUDE.md y MCP de la carpeta ([doc](https://code.claude.com/docs/en/headless)). Hay que correrlo en una carpeta vacía, con `--system-prompt-file` y `--tools ""`.
- El SDK valida el esquema con draft-07 ([doc](https://code.claude.com/docs/en/agent-sdk/structured-outputs)). `para_api` quita `$schema` (`esquemas.py:18`). Que el resto calce con draft-07: **[Sin verificar]**.
- El token de `setup-token` dura un año y solo sirve para pedir respuestas al modelo ([doc](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token)).

- **Por qué importa:** sin adaptador, la opción B no existe.
- **Afecta a:** solo suscripción.

**Soluciones**
- **A. Adaptador `claude -p` dentro de `pedir_json`**, elegido por una variable nueva (nombre a decidir).
  - Pro: un solo punto de cambio; todos los agentes pasan por `pedir_json` salvo `investigar`.
  - Contra: un proceso por llamada; imágenes por `stream-json` sin verificar.
- **B. Adaptador con el Agent SDK de Python** (`claude_agent_sdk`).
  - Pro: imágenes, `effort` y `output_format` documentados en Python.
  - Contra: API asíncrona dentro de un orquestador síncrono; dependencia nueva.
- **C. No soportar B; solo clave de API.**
  - Pro: cero código y sin riesgo de términos (problema 3).
  - Contra: el equipo necesita créditos de API.

- **Recomendada:** B si el equipo quiere la suscripción, porque es el único camino con imágenes documentadas en Python. Si nadie la necesita para el demo, C.
- **Cómo se verifica:** sin `ANTHROPIC_API_KEY` y con `CLAUDE_CODE_OAUTH_TOKEN`, una llamada del agente Entorno con 2 frames devuelve un JSON que pasa `validado("entorno", ...)`.

## 3. Los términos no permiten la suscripción en Render ni en un producto

**Qué pasa**
- Pro y Max se rigen por los Términos de Consumidor ([legal](https://code.claude.com/docs/en/legal-and-compliance)).
- OAuth está pensado para el uso normal de Claude Code por quien compró el plan. Quien construye un producto o servicio, también con el Agent SDK, debe usar clave de API ([legal](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use)).
- Anthropic no permite ofrecer login de Claude.ai en productos de terceros ([Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)).
- Los límites de Pro, Max y Ultra asumen uso normal e individual ([legal](https://code.claude.com/docs/en/legal-and-compliance#acceptable-use)). Las cifras de cada plan: **[Sin verificar]**.
- `render.yaml` pone el orquestador en un servicio (`render.yaml:45-57`). Un token de suscripción ahí atiende las corridas de cualquier visitante de la web.

- **Por qué importa:** Anthropic puede hacer cumplir estas reglas sin aviso previo ([legal](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use)).
- **Afecta a:** solo suscripción.

**Soluciones**
- **A. B solo en local:** una persona corre el orquestador en su máquina, con su propio token, para corridas del equipo.
  - Pro: lo más cercano al uso normal que describe la doc.
  - Contra: si eso cuenta como uso normal es **[Sin verificar]**; conviene preguntar a Anthropic.
- **B. Render siempre con clave de API.**
  - Pro: cumple los términos comerciales.
  - Contra: cuesta créditos.

- **Recomendada:** las dos juntas. Render solo con clave de API; la suscripción solo en local y con la duda declarada.
- **Cómo se verifica:** `grep -n CLAUDE_CODE_OAUTH_TOKEN render.yaml` no devuelve nada.

## 4. La búsqueda web depende de citas que el CLI no entrega

**Qué pasa**
- `investigar` lee las citas `web_search_result_location` con `cited_text` (`busqueda.py:232-241`).
- `ficha_desde_borrador` exige una cita por dato (`busqueda.py:117-127`).
- En `claude -p`, `WebSearch` devuelve títulos y URLs. Para leer una página usa `WebFetch`, donde otro modelo responde sobre la página ([doc](https://code.claude.com/docs/en/tools-reference)). La cita deja de ser texto literal de la fuente.

- **Por qué importa:** con B, las fichas encontradas pierden su evidencia literal, o la búsqueda queda `fallida`.
- **Afecta a:** solo suscripción.

**Soluciones**
- **A. Con B, apagar la búsqueda** (`VIAZ_BUSQUEDA=0`, ya existe, `config.py:86`).
  - Pro: cero código; la selección sigue con el catálogo.
  - Contra: no se prueba el agente de búsqueda.
- **B. `WebSearch` + `WebFetch` y marcar las citas como "resumidas".**
  - Pro: la búsqueda corre.
  - Contra: cambia el contrato de evidencia de `docs/agentes/seleccion-robot.md`.

- **Recomendada:** A, porque no rompe el contrato de evidencia. La búsqueda se prueba con clave de API.
- **Cómo se verifica:** con B y `VIAZ_BUSQUEDA=0`, `seleccion.json` trae `"busqueda": {"estado": "omitida", ...}`.

## 5. Los errores de la API botan la corrida entera

**Qué pasa**
- `pedir_json` no captura errores de `anthropic` ni de `json.loads` (`base.py:28-45`).
- `construir_robot` solo captura `ErrorAgente` (`orquestador.py:287`). Un 429 o un 529 en el Constructor sale de `construir_robot` y bota la corrida hija.
- Con tiempo tope, el cliente no reintenta (`base.py:26`, `busqueda.py:229`). Sin tope, usa los reintentos por defecto del SDK: cifra **[Sin verificar]**.

- **Por qué importa:** con 3 finalistas, un error de red en el finalista 3 pierde horas de trabajo hecho. El respaldo determinista (`orquestador.py:277`) nunca se alcanza.
- **Afecta a:** ambas (con B, el proceso `claude` también puede fallar).

**Soluciones**
- **A. `pedir_json` convierte todo error de la API y del JSON en `ErrorAgente`.**
  - Pro: un cambio; el Constructor ya pasa al respaldo con `ErrorAgente`.
  - Contra: Entorno, Tarea y Selección siguen cortando la corrida; ahí es correcto.
- **B. A más reintentos con espera para 429 y 529.**
  - Pro: aguanta sobrecargas cortas.
  - Contra: alarga la corrida; hay que respetar el tope de la búsqueda.

- **Recomendada:** B, porque los dos errores son pasajeros y la corrida es larga.
- **Cómo se verifica:** un test hace lanzar `anthropic.APIStatusError` a `pedir_json` y confirma que `construir_robot` termina con el método `determinista`.

## 6. Búsqueda, Monitor y Comparación fallan en silencio

**Qué pasa**
- La búsqueda nunca lanza: queda `fallida` y sigue (`busqueda.py:338-340`).
- El Monitor usa las reglas si Claude falla (`monitor.py:163-165`).
- La Comparación deja la plantilla si Claude falla (`comparacion.py:116-118`). No hay un chequeo de credenciales antes de la corrida.

- **Por qué importa:** con una clave mala o sin cupo, la corrida llega a `listo`. Nadie sabe que esos 3 agentes no usaron Claude, así que la corrida parece real sin serlo.
- **Afecta a:** ambas.

**Soluciones**
- **A. Chequeo previo:** al arrancar en modo `claude`, el orquestador hace una llamada mínima y se detiene si falla.
  - Pro: corta antes de gastar GPU.
  - Contra: no detecta fallas a mitad de la corrida.
- **B. Fuente por artefacto:** cada artefacto anota si salió de Claude o de las reglas.
  - Pro: la web y el equipo ven qué parte usó Claude.
  - Contra: toca 3 esquemas (`monitoreo`, `comparacion`, `seleccion`).

- **Recomendada:** las dos. A evita la corrida perdida y B hace honesto el resultado.
- **Cómo se verifica:** con `ANTHROPIC_API_KEY=invalida`, el orquestador sale antes de tomar una corrida. Con una clave válida, cada línea de `monitoreo.jsonl` dice que salió de Claude.

## 7. Los esquemas nunca pasaron por la API real

**Qué pasa**
- Ningún test llama a Claude. Todos reemplazan `pedir_json`, `investigar`, `fichar` o `_cliente` con `monkeypatch` (`test_agente_entorno.py:85`, `test_busqueda.py:193`, `test_seleccion.py:244`, `test_comparacion.py:138`).
- El Constructor y el Monitor en modo `claude` no tienen ningún test.
- La API limita los esquemas a 24 parámetros opcionales y 16 con tipos de unión, y responde 400 si los pasan ([doc](https://platform.claude.com/docs/en/build-with-claude/structured-outputs#schema-complexity-limits)).
- `esquema_agente_entorno` agrega un `anyOf` con `null` por bloque (`agentes/__init__.py:50-53`). `esquema_borradores` usa `["number", "null"]` (`busqueda.py:270`). Si algún esquema pasa los límites: **[Sin verificar]**.

- **Por qué importa:** un 400 en Entorno, Tarea o Selección bota la corrida en el primer minuto.
- **Afecta a:** ambas.

**Soluciones**
- **A. Script de humo:** manda una vez el esquema de cada agente con un caso real y guarda la respuesta.
  - Pro: prueba prompts y esquemas juntos por pocos dólares.
  - Contra: necesita la clave; no entra en CI.
- **B. Test sin red que cuente uniones y opcionales** de cada esquema contra los límites.
  - Pro: corre en CI.
  - Contra: no cubre los límites internos de la gramática.

- **Recomendada:** A primero, porque es la única que prueba el modelo. B después, para que el error no vuelva.
- **Cómo se verifica:** el script termina con 7 de 7 respuestas válidas contra el esquema local (Entorno, Tarea, Selección, Fichas, Constructor, Monitor, Comparación).

## 8. `max_tokens` fijo con pensamiento siempre activo en Opus 5.5

**Qué pasa**
- `pedir_json` usa `max_tokens=16000` y `effort="high"` por defecto (`base.py:21`, `:31`).
- En Opus 5.5 el pensamiento adaptativo siempre está activo y cuenta dentro de `max_tokens` ([doc](https://platform.claude.com/docs/en/build-with-claude/effort)).
- Si la respuesta se corta, `pedir_json` lanza `ErrorAgente` (`base.py:40-41`).

- **Por qué importa:** Entorno, con 8 imágenes y un esquema grande, puede gastar el tope pensando y cortar el JSON.
- **Afecta a:** ambas.

**Soluciones**
- **A. Subir `max_tokens` y usar streaming.**
  - Pro: margen para pensar.
  - Contra: más tiempo por llamada; el umbral de streaming del SDK es **[Sin verificar]**.
- **B. Bajar `effort` a `medium` (el valor por defecto de Opus 5.5) salvo en Entorno.**
  - Pro: menos tokens y menos costo.
  - Contra: puede bajar la calidad; hay que medir.

- **Recomendada:** medir con el script del problema 7 antes de elegir. Si un agente corta, A para ese agente.
- **Cómo se verifica:** el script de humo registra `usage.output_tokens` por agente; ninguno pasa el 80 % del tope.

## 9. `render.yaml` despliega en modo `fijo`

**Qué pasa**
- `VIAZ_AGENTES: fijo` (`render.yaml:8-9`). Solo declara `ANTHROPIC_API_KEY` para el orquestador (`render.yaml:56-57`).
- No declara `VIAZ_MAX_FINALISTAS`, `VIAZ_BUSQUEDA` ni `VIAZ_MONITOR_S`. Rigen los valores por defecto: 3 finalistas, búsqueda encendida, monitor cada 600 s (`config.py:83-94`).

- **Por qué importa:** un deploy sin cambios no llama a Claude. Un cambio a `claude` sin más corre 3 finalistas.
- **Afecta a:** solo API key (la suscripción no va en Render, problema 3).

**Soluciones**
- **A. Variables del demo en `render.yaml`:** `VIAZ_AGENTES=claude`, `VIAZ_MAX_FINALISTAS=1` y `VIAZ_HORAS_ENTRENAMIENTO` explícito.
  - Pro: el deploy queda declarado en el repo.
  - Contra: cambiar el modo exige un commit.
- **B. Dejar `fijo` en el repo y cambiarlo en el panel de Render.**
  - Pro: sin commit.
  - Contra: el estado real no queda escrito.

- **Recomendada:** A, porque el estado del deploy queda escrito en el repo.
- **Cómo se verifica:** el log del orquestador al arrancar dice `agentes=claude` (`orquestador.py:423`).

## 10. El pod no alcanza el almacén local

**Qué pasa**
- Con `VIAZ_ALMACEN=local`, las URLs salen de `VIAZ_URL_PUBLICA`, que vale `http://localhost:8000` por defecto (`config.py:53-55`).
- El runner baja cada entrada por URL (`runner.py:392-395`). El pod no ve el `localhost` de un Mac.

- **Por qué importa:** una corrida local con el worker Isaac en el pod no pasa de `generar_escena`.
- **Afecta a:** ambas.

**Soluciones**
- **A. API en Render con R2.** El orquestador corre en Render (A) o en local (B).
  - Pro: el pod ya está pensado para eso (`docs/infraestructura.md`).
  - Contra: con B, el orquestador local necesita la `DATABASE_URL` de Render.
- **B. Todo en local con `runner.py --modo simulado`.**
  - Pro: sin red.
  - Contra: las métricas son de relleno (problema 11).

- **Recomendada:** A para la corrida real. B solo para probar los agentes antes.
- **Cómo se verifica:** el trabajo `generar_escena` pasa a `ok` y `escena.usd` existe en R2.

## 11. El worker Isaac no está listo para el orquestador

**Qué pasa**
- Sin `--modo isaac`, el runner usa `sim/rl_simulado.py`, que inventa métricas (`runner.py:84`).
- En `--modo isaac`, el runner exige `VIAZ_CMD_ENTRENAR`, `VIAZ_CMD_EVALUAR`, `VIAZ_CMD_GRABAR_CLIP` y `VIAZ_CMD_VALIDAR_ROBOT` (`runner.py:38`, `:80-82`).
- La doc dice `VIAZ_CMD_CLIP` (`docs/contrato-entorno-rl.md:34`, `docs/desarrollo.md:94`). El archivo del pod usa `VIAZ_CMD_GRABAR_CLIP` (`worker-gpu/pod/entorno_rl.env:9`).
- Hoy no hay un `runner.py` corriendo en el pod, y otra persona lo usa para entrenar.

- **Por qué importa:** sin Isaac, la corrida no es real. Quien siga la doc del clip ve fallar `grabar_clips` después de horas de entrenamiento.
- **Afecta a:** ambas.

**Soluciones**
- **A. Corregir la doc a `VIAZ_CMD_GRABAR_CLIP`** y reservar una ventana del pod.
  - Pro: el código y el pod ya calzan; solo cambia la doc.
  - Contra: depende de que el pod quede libre.
- **B. Aceptar las dos variables en el runner.**
  - Pro: no falla con ninguna doc.
  - Contra: dos nombres para lo mismo.

- **Recomendada:** A, porque deja un solo nombre.
- **Cómo se verifica:** en el pod, `source worker-gpu/pod/entorno_rl.env && python worker-gpu/runner.py --modo isaac --una-vez` arranca sin el aviso `faltan [...]` (`runner.py:426-428`).

## 12. La corrida dura más de 12 h y gasta sin tope

**Qué pasa**
- Por defecto: 3 finalistas (`config.py:83-84`) y 4 h por entrenamiento (`config.py:80`).
- Las hijas corren una tras otra (`hijas.py:128-130`). `grabar_clips` y `evaluar` esperan hasta 3 h cada uno (`orquestador.py:385`, `:389`). El orquestador procesa una corrida a la vez (`orquestador.py:424-426`).
- El Monitor llama a Opus cada 600 s (`config.py:94`): unas 24 llamadas por finalista de 4 h. No hay tope de gasto por corrida.

- **Por qué importa:** una corrida bloquea la cola más de medio día. Con B, choca con los límites de uso del plan (problema 3).
- **Afecta a:** ambas.

**Soluciones**
- **A. Primera corrida con `VIAZ_MAX_FINALISTAS=1`, `VIAZ_HORAS_ENTRENAMIENTO=1` y `VIAZ_MONITOR_S=1800`.**
  - Pro: sin código; menos de 3 h y pocas llamadas.
  - Contra: no prueba Comparación (necesita 2 o más finalistas).
- **B. Segunda corrida con 2 finalistas y 1 h cada uno.**
  - Pro: prueba hijas y Comparación.
  - Contra: dobla el tiempo de GPU.

- **Recomendada:** A y después B, para que cada corrida pruebe algo nuevo.
- **Cómo se verifica:** el log dice `2 finalistas en corridas hijas, 1.0 h de entrenamiento cada uno (2.0 h en total)` (`hijas.py:125-126`).

## 13. El Monitor puede trabar la espera del entrenamiento

**Qué pasa**
- `Vigia.chequear` corre dentro del bucle de espera del trabajo (`corrida.py:71-73`).
- El Monitor llama a `pedir_json` sin tiempo tope (`monitor.py:156-157`). Con B y un proceso `claude` sin tope, la espera queda colgada.
- El prompt del Monitor fija "5 cm y 5°" (`monitor.py:151`), aunque las tolerancias salen de `tarea.json` (`orquestador.py:133-137`).

- **Por qué importa:** si el Monitor se cuelga, nadie marca `detener` y la corrida no ve el fin del trabajo.
- **Afecta a:** ambas.

**Soluciones**
- **A. Tiempo tope al Monitor** (por ejemplo, la mitad de `VIAZ_MONITOR_S`) y las tolerancias reales en el texto.
  - Pro: cambio chico; el respaldo por reglas ya existe.
  - Contra: un chequeo lento cae a reglas.
- **B. Monitor en un hilo aparte.**
  - Pro: nunca bloquea la espera.
  - Contra: estado compartido entre hilos en `Vigia`.

- **Recomendada:** A, porque usa el respaldo que ya existe.
- **Cómo se verifica:** un test donde `pedir_json` duerme más que el tope confirma que `chequear` devuelve el chequeo por reglas a tiempo.

## Orden de trabajo sugerido

1. Problemas 6A y 5B: chequeo previo y errores de la API como `ErrorAgente`. Son cambios chicos que protegen todo lo demás.
2. Problema 7A con clave de API: script de humo de los 7 agentes. Ajustar prompts, esquemas y `max_tokens` (problema 8).
3. Problema 1A: opción para que `rl` llame al agente Tarea.
4. Problemas 11A y 10A: doc del clip, ventana del pod, API en Render con R2.
5. Problemas 9A y 12A: primera corrida real con clave de API, 1 finalista y 1 h.
6. Problema 12B: segunda corrida con 2 finalistas, para probar Comparación.
7. Problemas 2, 3 y 4: adaptador de suscripción, solo si el equipo lo pide, solo en local y con `VIAZ_BUSQUEDA=0`.
8. Problemas 6B y 13A: fuente por artefacto y tope del Monitor.

## Fuera de alcance

- **Dominio:** solo `parque_solar` tiene perfil de entorno y solo `instalar_panel` tiene perfil de tarea, los dos con simulación (`perfiles.py:94-110`). Si el agente Entorno devuelve otro `tipo`, `exigir_pipeline` corta la corrida después de `tarea.json` (`orquestador.py:119-130`).
- El aviso de Discord dice siempre `instalar_panel` (`monitor.py:192`). El clon del flujo `planificador` solo existe para `base_movil_brazo` (`agentes/__init__.py:384-385`).
