# VIAZ: reglas para agentes

VIAZ virtualiza lugares de trabajo reales (cualquier industria) y pone robots reales a trabajar en ellos en simulación. El demo usa un parque solar, pero **el producto no es solo para paneles**.

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
