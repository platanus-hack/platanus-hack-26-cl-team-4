# Escena en Isaac Lab

Cómo se arma el mapa donde trabaja el robot, para que la física (pesos, fricción, contactos) sea creíble.

```mermaid
flowchart LR
  EJ[entorno.json<br/>medidas y pesos] --> GE[sim/generar_escena.py]
  GE --> USD[escena.usd<br/>estática: colisión + fricción]
  EJ --> VE[sim/viaz_escena.py]
  F[sim/fisica.py<br/>dt, fricción, CCD] --> GE & VE
  U[robot.urdf<br/>masas e inercias] --> VE
  USD --> VE
  VE --> IL[InteractiveSceneCfg<br/>Isaac Lab]
  BL[Blender<br/>solo apariencia] -.->|opcional| IL
```

## Decisión: el mapa se genera con código, no en Blender

- **Física en el USD:** Blender no exporta masa, fricción ni cuerpos rígidos de PhysX en forma confiable. Esas propiedades se definen en código de todas formas.
- **Colisiones simples:** una malla detallada como colisión vuelve la simulación lenta e inestable. Por eso todo choca como cajas.
- **Una escena por cliente:** la escena sale de `entorno.json`. Una escena hecha a mano sirve para una sola planta.
- **Blender, opcional:** sirve para mallas visuales (panel con marco, tracker detallado). Se montan encima de la caja de colisión y no reemplazan la física.

## Tres capas

| Capa | Qué tiene | Archivo | Masa |
|---|---|---|---|
| **Estática** | Suelo, tubos de torsión y postes | `escena.usd` (de `sim/generar_escena.py`) | No. Un colisionador sin cuerpo rígido es fijo |
| **Dinámica** | Paneles | `sim/viaz_escena.py` → `RigidObjectCfg` | Sí: `panel.peso_kg` de `entorno.json` |
| **Robot** | Base, ruedas, brazo y ventosa | `robot.urdf` (de `backend/viaz/urdf.py`) → `ArticulationCfg` | Sí: por link, con inercia calculada de su forma |

## Parámetros de física ([`sim/fisica.py`](../sim/fisica.py))

| Parámetro | Valor | Por qué |
|---|---|---|
| Paso de física | 1/120 s | Con pasos más grandes, un panel de 4 cm puede atravesar el tubo |
| CCD | Activado | Detecta choques entre pasos en objetos delgados |
| Iteraciones del solver | 16 de posición / 1 de velocidad | Hacen falta para cuerpos pesados apilados |
| Fricción suelo | 0,9 / 0,7 | Tierra compactada |
| Fricción acero | 0,6 / 0,5 | Tubo y postes galvanizados |
| Fricción panel | 0,5 / 0,4 | Marco de aluminio contra acero |
| Restitución | 0 en todo | Un panel que rebota es un error de simulación |
| Margen de contacto | 5 mm | Contactos estables en objetos delgados |

Los valores son **supuestos**: se calibran con la prueba de física.

## Masas del clon ([`backend/viaz/urdf.py`](../backend/viaz/urdf.py))

| Pieza | Masa | Origen |
|---|---|---|
| Base | 600 kg | Supuesto: chasis + baterías de una base que carga paneles |
| Ruedas | 4 × 15 kg | Supuesto |
| Brazo (hombro a muñeca) | ~54 kg | Aluminio hueco: 2700 kg/m³ × 30 % × volumen de cada pieza |
| Ventosa | 6 kg | Supuesto |
| **Total** | **~720 kg** | |

- **Inercias:** cada link tiene la inercia de una caja o un cilindro sólido de su tamaño. Antes eran 0,01, y eso hace inestable a PhysX.
- **Torque:** el hombro aguanta 3000 N·m. Con el brazo horizontal y un panel de 32 kg en la punta necesita unos 1230 N·m (ver test).
- **Pendiente:** cuando tengamos la ficha del robot real, hay que reemplazar los `MASA_*` de `urdf.py`.

## Prueba de física: lo primero en el pod

```bash
mkdir -p /tmp/viaz && cp backend/viaz/fixtures/entorno.json /tmp/viaz/
$ISAACLAB_SH -p sim/prueba_fisica.py --headless --dir /tmp/viaz --paneles 3
```

La prueba suelta 3 paneles 10 cm sobre el tubo, espera 3 s y revisa:

| Revisión | Tolerancia |
|---|---|
| Masa de cada panel | ±1 % de `peso_kg` |
| Altura final (apoyado sobre el tubo) | ±1 cm |
| Corrimiento en el plano | ±2 cm |
| Inclinación | < 2° |
| Velocidad final | < 1 cm/s |

- **Resultado:** escribe `prueba_fisica.json` y termina con código 1 si algo falla.
- **Con robot:** `--con-robot` necesita `clon.json` y `robot.urdf` en la carpeta. Revisa las 6 articulaciones y la masa total. Ambos archivos se sacan de una corrida en modo simulado.

### Qué hacer si falla
- **El panel atraviesa el tubo:** bajar `DT_S` o subir `CONTACTO_OFFSET_M`.
- **El panel rebota o vibra:** subir `ITER_POSICION` o bajar `DESPENETRACION_MAX_M_S`.
- **El panel resbala del tubo:** subir la fricción de `acero` y `panel`.
- **Error de importación o de nombre de API:** el código es para Isaac Lab 2.x y **no se ha probado en Isaac**. Hay que ajustar el nombre según la versión instalada.

## Supuestos y límites

- **Panel suelto:** el panel queda apoyado sobre la cara plana de 10 cm del tubo, sin abrazaderas. En una planta real se fija con abrazaderas, que el modelo todavía no tiene.
- **Suelo plano:** la `pendiente_grados` de `entorno.json` todavía no se modela, porque el plan supone la base en z = 0.
- **Base cinemática:** en `ejecutar_tarea.py` la base se mueve fijando su pose en cada paso, no con tracción de ruedas.
