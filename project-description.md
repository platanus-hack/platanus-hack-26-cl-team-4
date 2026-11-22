# VIAZ

**De videos de tu lugar de trabajo a un robot real trabajando ahí, antes de comprarlo.**

Muchas industrias todavía no usan robots. No saben qué robot sirve ni cómo trabajaría en su lugar de trabajo.
VIAZ responde esas dos preguntas con un demo en simulación, para cualquier rubro y cualquier tarea de manipulación.

## Cómo funciona

1. **Virtualizar el entorno.** Un agente analiza los videos del lugar y genera una copia 3D para la simulación.
2. **Elegir el robot.** Un agente compara el lugar y la tarea con un catálogo de robots reales. Después elige el que mejor calza y explica por qué.
3. **Clonar el robot.** Se arma un modelo simulado con las medidas, el alcance y la carga útil del robot real.
4. **Clonar su inteligencia.** El robot ejecuta la tarea en NVIDIA Isaac Lab, dentro del entorno virtual, en una GPU en la nube.
5. **Resultado.** El cliente ve en la web un visor 3D del robot trabajando en su lugar de trabajo, con métricas: tareas hechas, tasa de éxito y tiempo por ciclo.

## Ejemplos

- **Parque solar:** una empresa de energía verde instala paneles a mano. VIAZ toma videos del parque, elige un robot de instalación de paneles y simula cómo los instalaría en esas estructuras.
- **Oficina o bodega:** VIAZ toma videos del lugar, elige un robot móvil con brazo y simula cómo ordenaría cajas en un estante.

El mismo sistema sirve para los dos. Así cualquier empresa ve el resultado antes de comprar o importar un robot.

## Tecnología

- **Agentes:** Claude con salidas validadas contra un contrato de datos (JSON Schema).
- **Simulación:** NVIDIA Isaac Sim e Isaac Lab en una RTX 5090 en la nube.
- **Web:** Next.js en Vercel, con un visor 3D en three.js que reproduce la simulación.
- **Backend:** API y orquestador de agentes en Render, con Postgres y Cloudflare R2.

Equipo: Nicolás Jara Castillo, Francisco Martinez y Joaquín Vila Ormazabal.
