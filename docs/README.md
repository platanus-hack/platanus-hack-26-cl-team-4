# Índice de `docs/`

Orden de lectura para quien evalúa VIAZ. Empieza por el estado: es la única fuente de verdad de qué está probado.

## Lo esencial

1. [`estado.md`](estado.md): qué es real y probado, qué no. Cómo correr los tests y dónde está la evidencia del RL.
2. [`arquitectura.md`](arquitectura.md): agentes, flujo `rl` por defecto, infraestructura y decisiones clave.
3. [`contrato-datos.md`](contrato-datos.md): los archivos que pasan entre etapas. Explica los JSON Schema de `backend/viaz/esquemas/`.
4. [`contrato-entorno-rl.md`](contrato-entorno-rl.md): los 4 comandos que cumple todo entorno RL de Isaac Lab para que el sistema lo lance sin cambios.
5. [`requerimientos.md`](requerimientos.md): requerimientos con prioridad MoSCoW (ISO/IEC/IEEE 29148).
6. [`agentes/`](agentes/README.md): contrato e instrucciones de cada agente (Mapeo de entorno, Tarea, Selección de robot, Constructor, Monitor).
7. [`agregar-dominio.md`](agregar-dominio.md): cómo sumar un rubro nuevo con un perfil, sin tocar los agentes. Ejemplo: `animar_evento`.

## Operación

- [`desarrollo.md`](desarrollo.md): correr todo en local sin GPU y el plan de deploy.
- [`infraestructura.md`](infraestructura.md): GPU en la nube, versiones del pod y prueba de humo.
- [`ciclo-desarrollo.md`](ciclo-desarrollo.md): cómo el equipo pasó de requerimientos a demo durante el hack.
- [`escena-isaac.md`](escena-isaac.md): cómo se arma la escena en Isaac Lab para que la física sea creíble.
- [`calidad-virtualizacion.md`](calidad-virtualizacion.md): estándar de calidad para escenas, objetos y robots.

## Investigación

- [`investigacion-datasets.md`](investigacion-datasets.md): datos públicos sobre el montaje de paneles solares, con fuentes.
- [`investigacion-fisica-robots.md`](investigacion-fisica-robots.md): medidas físicas de Bison, BUILDEX E y Maximo (publicado o estimado).
- [`investigacion-isaac-gpu.md`](investigacion-isaac-gpu.md): elección de GPU y proveedor para Isaac Lab.
- [`plan-entrenamiento.md`](plan-entrenamiento.md): plan para entrenar con pocas horas de GPU. Las horas son estimaciones.
- [`diagnostico-entrenamiento-corto.md`](diagnostico-entrenamiento-corto.md): por qué una prueba de 12 minutos dio 0 % de éxito.

## Pendientes

- [`pendientes-corrida-real.md`](pendientes-corrida-real.md): los 13 problemas para correr con Claude real y su arreglo.

[`referencias/`](referencias/README.md) guarda capturas aprobadas y rechazadas de escenas y robots, y la especificación perceptual.
