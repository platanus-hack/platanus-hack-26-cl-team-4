# Estado de VIAZ

> **Única fuente de verdad del estado.** Otros docs enlazan aquí y no repiten cifras.
> Fecha: 2026-11-22. Commit base: `08094bd` (`origin/main`).
> Categorías (las de [`CLAUDE.md`](../CLAUDE.md)): **Real y probado**, **Sin probar**, **Falso o de relleno**, **No existe**.

## 1. Cómo verificar en 5 minutos

```bash
cd backend
pip install -e ".[dev]" && pip install usd-core
python -m pytest -q -rs
```

- Es el mismo comando de la CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml), job `backend`).
- Resultado medido con este comando: **365 passed, 1 skipped, 1 xfailed en 5 min 14 s** (Mac, Python 3.12, 2026-11-22, commit `08094bd`).
- El único skip necesita `torch` (`test_entorno_rl.py:421`). Tampoco corre en la CI. Sin `usd-core` se saltan 6 más.
- El tiempo se va en 11 tests de punta a punta. Levantan la API y el runner simulado como procesos.
- Los más lentos: `test_rl.py::test_segunda_corrida_reusa_el_modelo_comprobado` (50 s) y `test_flujo.py::test_flujo_completo` (33 s). Lista completa con `pytest --durations=15`.
- El xfail es a propósito y estricto: `trinatracker-buildex-e` en `test_fisica_robot.py:172`.
- Todos los tests corren en modo `fijo` o con Claude reemplazado por `monkeypatch`. Prueban el cableado, no la calidad de los agentes.
- Corridas de la CI: <https://github.com/platanus-hack/platanus-hack-26-cl-team-4/actions/workflows/ci.yml>. La CI de `main` está verde con el tope de 20 min del job `backend` (`timeout-minutes` en `ci.yml`). Las corridas canceladas viejas son del tope anterior de 10 min.

## 2. Estado por componente

| Componente | Estado | Evidencia |
|---|---|---|
| API (FastAPI): proyectos, corridas, cola GPU | Real y probado | `backend/viaz/api.py:53` (`create_app`); `test_flujo.py`, `test_rl.py` |
| Orquestador, flujo `rl` en modo `fijo` | Real y probado | `backend/viaz/orquestador.py:403-412`; `test_rl.py:90` (`test_flujo_rl_completo`) |
| Agentes con Claude real (8 prompts de `agentes/prompts/`) | Sin probar | [`pendientes-corrida-real.md`](pendientes-corrida-real.md), sección "Estado honesto" |
| Cliente de Claude (`pedir_json`, reintentos, structured outputs) | Real y probado con mocks | `backend/viaz/agentes/base.py:68`; `pendientes-corrida-real.md:15` (errores reales del SDK) |
| Adaptador de suscripción (Agent SDK) | Sin probar | `pendientes-corrida-real.md:12`: probado con un SDK falso |
| Esquemas JSON del contrato (16) | Real y probado | `backend/viaz/esquemas/`; `test_esquemas.py` |
| Selección por reglas (requisitos, descarte, orden) | Real y probado | `backend/viaz/agentes/seleccion.py`; `test_seleccion.py` |
| Búsqueda web de robots fuera del catálogo | Real y probado con mocks; sin corrida real | `backend/viaz/agentes/busqueda.py`; `test_busqueda.py`. Solo corre con `VIAZ_AGENTES=claude` (`config.py:85`) |
| Clon paramétrico (URDF) y reglas del robot | Real y probado | `backend/viaz/urdf.py`, `robot_cfg.py`; `test_fisica_robot.py` |
| Corridas hijas por finalista y comparación | Real y probado (runner simulado) | `backend/viaz/hijas.py:123`, `comparacion.py:1-5`; `test_hijas.py:120`, `test_comparacion.py` |
| Monitor (Claude con respaldo por reglas) | Reglas: real y probado. Claude: sin probar | `backend/viaz/monitor.py:69,158` |
| Perfiles de dominio | Real y probado | `backend/viaz/agentes/perfiles.py:206-226`; `test_tareas_sim.py` |
| Escena USD desde `entorno.json` | Real y probado | `sim/generar_escena.py`; `test_escena.py` |
| Entorno RL `instalar_panel` (`sim/rl/`), lógica sin GPU | Real y probado | `test_entorno_rl.py` |
| Entrenamiento RL en Isaac (`sim/rl/`) | Real, con evidencia fuera de `main` | §3. Archivos en la rama `feat/fisica-real` (PR #36) |
| Humanoide `animar_evento` (`sim/animar/`) | Lógica: real y probado. Isaac: sin prueba en el repo | `test_animar.py`. No hay resultados versionados (§3.4) |
| `sim/rl_simulado.py` | Falso o de relleno | §4 |
| Worker GPU (`worker-gpu/runner.py`) | Modo `simulado`: real y probado. Modo `isaac` lanzado por el orquestador: sin probar | `test_hijas.py`, `test_rl.py`; `pendientes-corrida-real.md`, problema 11 |
| Instalador del pod (`worker-gpu/pod/`) | Real, sin test automático | `worker-gpu/pod/instalar.sh`, `humo.sh` |
| Web (Next.js 15) | Compila en la CI. En navegador contra la API: sin probar | `ci.yml` job `web` (`npm run build`). No hay test en navegador |
| Deploy (Vercel + Render + R2) | No existe | §5 |

## 3. Resultados de RL y dónde está la prueba

> **Aviso:** la evidencia está en el PR #36 (<https://github.com/platanus-hack/platanus-hack-26-cl-team-4/pull/36>), rama `feat/fisica-real`. **Todavía no está en `main`.**

### 3.1 Cifras con archivo

Robot: clon de LEAPTING MMR. Tarea: `instalar_panel`. Todas las evaluaciones traen `"fuente": "isaac"`.
Base de los enlaces: `https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/` (commit `7e9ba0c`, punta de `feat/fisica-real`).
Los enlaces usan el commit fijo para no romperse si la rama se borra al mergear el PR #36.

| Modelo | Qué mide | Cifra exacta del JSON | Tolerancia | Archivo |
|---|---|---|---|---|
| `model_609` | 100 episodios de 1 panel | 100/100 éxitos; 97/100 a tolerancia fina; 0 colisiones | 5 cm y 5°; fina 2 cm y 2° | [`evaluacion_609.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/evaluacion_609.json) |
| `model_609` | 100 secuencias de 4 paneles, panel instalado fijado | 100/100 secuencias; 400/400 paneles; 0 choques | 5 cm y 5° | [`secuencia_609_fijando.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/secuencia_609_fijando.json) |
| `model_609` | Lo mismo, sin fijar el panel | 79/100 secuencias; 354/375 paneles; 21 choques | 5 cm y 5° | [`secuencia_609_sin_fijar.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/secuencia_609_sin_fijar.json) |
| `model_609` | Criterio de parada del entrenamiento | iteración 485; éxito medio 0,9889 en 20 iteraciones | No viene en el JSON | [`criterio_multi.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/criterio_multi.json) |
| `model_990` (rieles y grapas) | 100 episodios de 1 panel | 99/100; 84/100 a tolerancia fina; 0 colisiones | 5 cm y 5°; fina 2 cm y 2° | [`evaluacion_990_rieles.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/evaluacion_990_rieles.json) |
| `model_990` | 100 secuencias de 4 paneles con grapas | 93/100 secuencias; 379/386 paneles; 7 por tiempo agotado | 5 cm y 5° | [`secuencia_990_rieles_grapas.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/secuencia_990_rieles_grapas.json) |
| `model_990` | Ráfagas de 10 a 40 m/s sobre 93 paneles instalados | Con grapas: 0 paneles corridos. Sin grapas, desde 20 m/s: 93 corridos | Corrido = más de 1 cm | [`viento_990_grapas.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/viento_990_grapas.json), [`viento_990_sin_grapas.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/viento_990_sin_grapas.json) |
| `model_1164` (ventosa con fuerza limitada, viento 8 m/s) | 100 episodios de 1 panel | 99/100; 83/100 a tolerancia fina; 0 colisiones | 5 cm y 5°; fina 2 cm y 2° | [`evaluacion_1164_succion_viento.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/evaluacion_1164_succion_viento.json) |
| `model_1164` | 100 secuencias de 4 paneles | 98/100 secuencias; 393/395 paneles; 0 choques; 2 por tiempo agotado | 5 cm y 5° | [`secuencia_1164_succion_viento.json`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/secuencia_1164_succion_viento.json) |

Los checkpoints (`model_*.pt`) están en la misma carpeta. Los clips y las métricas por iteración están solo en un archivo del pod (`sim/rl/respaldo/README.md`, sección "Respaldo completo"). No están en el repo.

### 3.2 Límites declarados

Fuentes: [`sim/rl/respaldo/README.md`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/sim/rl/respaldo/README.md) y [`docs/fisica-real.md`](https://github.com/platanus-hack/platanus-hack-26-cl-team-4/blob/7e9ba0c1f0f92e7b54eb4af14adaa94444e44cc1/docs/fisica-real.md) de esa rama.

- `model_609`: el panel instalado se teletransporta a su slot (`fijar_instalados=True`). Sin eso, 79 de 100 secuencias salen bien.
- `model_609`: la ventosa es una unión fija y el panel se apoya en una caja de 10 × 10 cm, sin rieles.
- `model_990` y `model_1164`: el panel queda donde lo deja la política, unido por una grapa rígida. La grapa no modela la carga de rotura (`fisica-real.md:41`).
- Todos: la base se mueve por código, sin tracción ni orugas (`fisica-real.md:91`).
- El robot entrenado sale de `robot.urdf` (clon de `backend/viaz/urdf.py`), no de `robot_cfg.py`.

### 3.3 Corrida corta de `main`

[`diagnostico-entrenamiento-corto.md`](diagnostico-entrenamiento-corto.md): corrida `178ab8fee014`, 12 minutos, 170 iteraciones, **0 % de éxito**. La política sella el panel el 98 % del tiempo, pero no lo lleva al tubo. Causa más probable: la ayuda del currículo se acaba a los 7 minutos. El `metricas.jsonl` citado está en el pod, no en el repo.

### 3.4 Sin prueba en el repo

| Cifra o afirmación | Dónde aparece | Estado |
|---|---|---|
| Humanoide `animar_evento`: resultados de entrenamiento | Notas del equipo | Sin prueba en el repo. No hay resultados versionados en `main` ni en `feat/humanoide-unitree-h1` (PR #34) |
| "99,8 %" y "94 %" de éxito de LEAPTING | Notas del equipo | Sin prueba en el repo. Ningún archivo tiene esas cifras. Usa las de §3.1 |
| Cartpole ~150 000 pasos/s | `infraestructura.md:104` | Sin prueba en el repo. No hay log |
| "92 % a 5 cm y 5°" | `requerimientos.md:292` | Es un ejemplo de formato, no una medida |

## 4. Falso o de relleno

| Qué | Evidencia |
|---|---|
| `sim/rl_simulado.py`: imita los 4 comandos del entorno RL sin Isaac. Métricas de curva sintética y videos 2D | `sim/rl_simulado.py:8-9`. El runner lo rotula "simulado" (`worker-gpu/runner.py:228-229`) |
| Modo `fijo`: los agentes devuelven fixtures | `backend/viaz/fixtures/*.json`; `config.py:61` (`VIAZ_AGENTES`, por defecto `fijo`) |
| Robot ficticio en el catálogo | `backend/viaz/catalogo/robots/viaz-instalador-ficticio.json:7` (`"ficticio": true`) |
| Medidas estimadas desde fotos o videos del fabricante | Campo `estimados` en 5 fichas: `aes-maximo`, `leapting-mmr` (`:32`), `relu-bison`, `trinatracker-buildex-e`, `unitree-h1` |
| Página de desarrollo de la selección | `web/app/dev/seleccion/page.tsx` (solo fixtures) |

## 5. No existe todavía

| Qué | Referencia |
|---|---|
| Deploy público (web en Vercel, API en Render, R2) | `platanus-hack-project.jsonc:15-16` ("TEMPORAL", apunta al repo); `pendientes-corrida-real.md:20` (Render + R2 pendiente) |
| Corrida de punta a punta con Claude real (`VIAZ_AGENTES=claude`) | `pendientes-corrida-real.md`, sección "Estado honesto" |
| Corrida de respaldo `/corridas/demo` (RF-WEB-08, Must) | `requerimientos.md:287`; necesita `VIAZ_CORRIDA_DEMO` (`render.yaml`) y una API viva |
| Caso 3 (oficina, caja al estante) con entorno RL | Solo fixtures `entorno_sala.json` y `tarea_sala.json`; `sim/tareas.py:19` conoce solo `instalar_panel` y `animar_evento` |

## 6. Qué se hizo en la hackathon

- Todo el repo se hizo en la hackathon. El primer commit es la plantilla de Platanus (`769fa97`, 2026-11-21 01:01).
- **128 commits** en `main` hasta `8fdc540` (2026-11-22 05:15): 113 el 21-nov y 15 el 22-nov. 40 son merges de PR (`git log`).
- Orden: arquitectura y contrato → esqueleto de API, web y sim → pod con Isaac Lab → entorno RL de paneles → selección con corridas hijas → perfiles de dominio → humanoide para la sala → preparación para Claude real.
- Fuera de `main`: PR #36 (física real y evidencia de RL) y PR #34 (humanoide Unitree H1), ambos abiertos.
