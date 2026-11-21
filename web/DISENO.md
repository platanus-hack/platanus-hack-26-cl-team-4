# Diseño de la web de VIAZ

Plan hecho con la skill `frontend-design`. Si cambias la paleta o la tipografía, actualiza este archivo.

## Brief
- **Tema:** construcción de parques solares a escala de servicio público en Chile (Atacama).
- **Audiencia:** jurado del hack y jefes de proyecto de empresas de energía.
- **Trabajo principal de la página:** mostrar, sin backend, un robot real (clonado) trabajando en la planta, con métricas honestas.

## Color: mediodía en el desierto
| Token | Hex | Uso |
|---|---|---|
| `--cielo` | `#E4EEF3` | Fondo de la página: cielo pálido de mediodía |
| `--tinta` | `#14253A` | Texto: azul profundo de las celdas del módulo |
| `--modulo` | `#22477E` | Datos y enlaces: azul del panel |
| `--acero` | `#6E7A86` | Texto secundario y reglas: acero galvanizado |
| `--tierra` | `#B98552` | Terreno del visor 3D (uso mínimo fuera de él) |
| `--senal` | `#F4B400` | Amarillo de seguridad de la maquinaria. Solo para el robot y el estado activo |

## Tipografía
- **Una sola familia: Archivo variable**, con contraste de **ancho**.
  - **Títulos:** expandida (`wdth 125`), peso 800. Evoca la rotulación de las máquinas de construcción.
  - **Texto:** ancho normal (`wdth 100`), peso 400.
- **Escala:** 14 · 16 · 20 · 28 · 44 · 72 px. Líneas de 70 caracteres como máximo.

## Layout
```
┌─────────────────────────────────────────────┐
│ VIAZ                      Probar con tu planta│
├─────────────────────────────────────────────┤
│  VISOR 3D EN VIVO, ancho completo (78vh)    │
│                                             │
│  Título expandido abajo a la izquierda      │
│  [estado: simulación sin física] [controles]│
├──────────────────────────┬──────────────────┤
│ Resultado: una frase     │ Ficha técnica    │
│ grande con la métrica    │ del robot (dl)   │
├──────────────────────────┴──────────────────┤
│ Entrenamiento: video acelerado + curva +    │
│ hitos del monitor (o estado pendiente)      │
├─────────────────────────────────────────────┤
│ Cómo se hizo: 5 pasos (sí es una secuencia) │
├─────────────────────────────────────────────┤
│ Diferencias con el robot real               │
└─────────────────────────────────────────────┘
```
- **Alineación:** todo alineado a la izquierda, en una grilla de 12 columnas.

## Principios
- **Una sola audacia:** el visor 3D en vivo es el hero. Todo lo demás es sobrio, sin sombras ni tarjetas repetidas.
- **Ficha técnica, no tarjetas:** los datos del robot van en una lista de definiciones con reglas finas, como la ficha de un fabricante. Ahí la regla marca filas de datos.
- **Honestidad visible:** "sin física", "robot ficticio" y "pendiente" se dicen en el lugar del dato, no en una nota al pie.
- **Vocabulario ISO 8373:** robot móvil, manipulador, efector final, carga útil y alcance.
- **Movimiento:** solo el del visor. Con `prefers-reduced-motion`, el visor parte pausado.

## Revisión contra lo genérico
- **Cambio 1:** primero pensé en un hero oscuro con acento amarillo. Se parecía demasiado al default "fondo casi negro con un solo acento". Lo cambié a luz de día, que es como se ve una planta en Atacama.
- **Cambio 2:** primero pensé en las métricas como números grandes con etiqueta chica. Es el tratamiento por defecto. Lo cambié a una frase completa con la tolerancia y los episodios, como pide RF-WEB-16.
- **Cambio 3:** descarté las etiquetas en MAYÚSCULAS y la fuente monoespaciada para datos chicos. Los datos van en Archivo con cifras tabulares.
