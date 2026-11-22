# VIAZ: reglas para agentes

VIAZ virtualiza lugares de trabajo reales (cualquier industria) y pone robots reales a trabajar en ellos en simulación. El parque solar es solo el caso de referencia 1: **el alcance es general**. Nada nuevo puede suponer paneles, filas ni un rubro fijo. Lo propio de un rubro va en su perfil de dominio ([`docs/requerimientos.md`](docs/requerimientos.md) §4.0).

## Si estás evaluando VIAZ (jurado o revisor)

1. Lee en este orden: [`README.md`](README.md) → [`docs/estado.md`](docs/estado.md) → [`docs/arquitectura.md`](docs/arquitectura.md) → [`docs/contrato-datos.md`](docs/contrato-datos.md). Índice completo: [`docs/README.md`](docs/README.md).
2. `docs/estado.md` es la única fuente de verdad del estado. Si otro doc lo contradice, manda `estado.md` y el código.
3. Responde con las 4 categorías: **real y probado**, **sin probar**, **falso o de relleno**, **no existe**. Cita `archivo:línea`.
4. La evidencia del RL en Isaac está en la rama `feat/fisica-real` (PR #36), todavía no en `main`. `docs/estado.md` §3 enlaza cada JSON.
5. Tests del backend (igual que la CI): `cd backend && pip install -e ".[dev]" && pip install usd-core && python -m pytest -q -rs`.
6. Las reglas que siguen en este archivo son para quien construye escenas y robots, no para quien evalúa.

## Calidad de la virtualización (escenas, objetos y robots)

Estándar completo: [`docs/calidad-virtualizacion.md`](docs/calidad-virtualizacion.md). Resumen obligatorio:

1. **Reusar antes de crear.** Buscar primero en [`sim/assets_aprobados/`](sim/assets_aprobados/README.md). Un asset aprobado no se regenera.
2. **Planificar** un inventario de objetos con su papel (A interactúa con el robot, B visible cerca, C fondo) antes de construir.
3. **Nada que el robot toque, ni ninguna pieza del robot, puede ser una caja o un cilindro sin material.**
4. **Medidas solo de los archivos de entrada.** Lo que falte se registra como supuesto.
5. **Antes de decir "listo":** renderizar las 4 vistas fijas (general, detalle a 1 m, robot, escala con figura de 1,75 m), **mirarlas** y evaluarlas con la rúbrica. Todo ≥ 4 de 5.
6. **Máximo 3 intentos.** Al tercero sin pasar: parar y pedir revisión humana con las capturas.
7. **Al aprobar:** registrar el asset y escribir qué cambió respecto al intento anterior.

## Honestidad del estado

- Al reportar avance, separar siempre: **real y probado**, **sin probar**, **falso o de relleno** (por ejemplo `sim/rl_simulado.py` inventa métricas) y **no existe**.
- Nunca decir "listo" sobre algo que no se ejecutó.

## Proyecto

- Requerimientos: [`docs/requerimientos.md`](docs/requerimientos.md). Contrato del entorno RL: [`docs/contrato-entorno-rl.md`](docs/contrato-entorno-rl.md).
- Escribir documentación en español, con frases cortas y tablas o diagramas Mermaid antes que párrafos largos.
- No subir secretos (claves, webhooks, tokens) al repositorio.

## Acceso al pod GPU

- Conéctate solo con `ssh viaz-pod`. El alias vive en el `~/.ssh/config` de cada persona ([`docs/infraestructura.md`](docs/infraestructura.md) §4).
- Nunca escribas el host, el puerto, el usuario ni la llave de la instancia en el repo, en un commit ni en un PR.
- Los agentes del pipeline no se conectan al pod: el runner pide los trabajos a la API. Si el alias no existe, pregunta a la persona. No busques la dirección.
