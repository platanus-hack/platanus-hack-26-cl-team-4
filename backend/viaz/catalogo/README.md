# Catálogo de robots

Un JSON por robot en `robots/`. El agente Robot elige **solo** entre estos archivos: no inventa robots.
Los archivos que empiezan con `_` no se cargan.

- Formato: `robot.schema.json` sin `justificacion` ni `alternativas`. Copia `_plantilla.json`.
- Cada dato sale de una fuente con URL y fecha (`fuente`). Si un dato no aparece en la fuente, déjalo fuera del pitch.
- `viaz-instalador-ficticio` existe solo para desarrollar el flujo. Tiene `"ficticio": true` y la web lo muestra así.

Candidatos por cargar (investigación del 2026-09-28, reverificar): Maximo (AES), Gritt, Charge Robotics,
Luminous, Cosmic Robotics y robots chinos de instalación de paneles.
