# Contrato: agente monitor del entrenamiento

> Etapa 5 (entrenamiento RL). Requerimientos: RF-MON-01..10, RF-GPU-06, RF-API-06, RNF-17.
> **Canal de avisos:** Discord, con un webhook a un canal del equipo (ej.: `#entrenamiento`). Cada chequeo queda además en `monitoreo.jsonl`.
> Estado: **por implementar.** Prompt: [`prompts/monitor.md`](../../backend/viaz/agentes/prompts/monitor.md) (todavía no lo carga el código).

```mermaid
sequenceDiagram
  participant P as Pod 5090 (entrenar)
  participant A as API (Render)
  participant M as Agente monitor (Claude, en Render)
  participant D as Discord (#entrenamiento)
  participant E as Equipo
  loop cada 5 min
    P->>A: latido + métricas nuevas
    A-->>P: seguir | detener
  end
  loop cada 10 min
    M->>A: lee métricas desde el último chequeo
    M-->>A: chequeo → monitoreo.jsonl
    alt divergiendo, NaN o estancado 3 veces
      M-->>D: aviso con evidencia y recomendación
    else hito (primer éxito, 50 %, 90 %, fin)
      M-->>D: aviso de hito
    end
    D-->>E: notificación en el celular
  end
  E->>A: decide: seguir, ajustar o detener
```

## 1. Propósito

- **Decide:** si el entrenamiento va bien, y qué recomendar.
- **Por qué existe:** el entrenamiento dura horas. Nadie mira la curva todo el tiempo. El monitor avisa cuando hay que actuar.
- **Para el demo:** marca los hitos del video en cámara rápida y escribe el resumen final.
- **Límite:** recomienda. Solo detiene el entrenamiento por sí mismo si aparece NaN (RF-MON-08).

## 2. Entradas

| Entrada | Origen | Contenido |
|---|---|---|
| Métricas | Latidos del pod (RF-GPU-06), guardadas por la API | Una fila por iteración de PPO: `iteracion`, `pasos`, `recompensa_media`, `tasa_exito`, `largo_episodio`, `perdida_valor`, `perdida_politica`, `entropia`, `tiempo_s` |
| Chequeos anteriores | `monitoreo.jsonl` | Para detectar estancamiento sostenido |
| Contexto | `tarea.json`, meta de 90 % a 5 cm y 5° (RF-INT-11), presupuesto de tiempo (RNF-17) | Para saber qué es "bueno" |

## 3. Salida: una línea de `monitoreo.jsonl` por chequeo **[Contrato nuevo: agregar esquema]**

```json
{
  "version": 1,
  "t": "2026-11-22T01:40:00Z",
  "iteracion": 420,
  "estado": "mejorando",
  "evidencia": {
    "recompensa_media": 18.4,
    "tasa_exito": 0.35,
    "tendencia_recompensa": 0.8,
    "tiempo_usado_h": 1.2,
    "tiempo_restante_h": 2.8
  },
  "recomendacion": "seguir",
  "detalle": "La tasa de éxito subió de 0,22 a 0,35 en los últimos 10 min",
  "hito": "primer_exito",
  "checkpoint_recomendado": "model_400.pt"
}
```

| Campo | Valores |
|---|---|
| `estado` | `mejorando` \| `estancado` \| `divergiendo` \| `terminado` |
| `recomendacion` | `seguir` \| `ajustar` \| `detener` \| `revisar` |
| `hito` | `null` \| `primer_exito` \| `exito_50` \| `mejor_recompensa` \| `umbral_alcanzado` \| `fin` |
| `checkpoint_recomendado` | Nombre del mejor checkpoint hasta ahora, o `null` |

## 4. Reglas que verifica el código

1. Cada chequeo cumple su esquema.
2. `evidencia` usa solo números que vienen de las métricas. El código compara contra la fuente.
3. **NaN en una pérdida o en la recompensa:** el código responde `detener` en el siguiente latido, sin esperar al agente (RF-MON-08).
4. `ajustar` y `detener` por otras causas solo se aplican con aprobación de una persona del equipo.
5. Como máximo 1 aviso de Discord por tipo cada 30 min. NaN siempre avisa (RF-MON-10).
6. Si Discord falla, el chequeo igual se guarda en `monitoreo.jsonl`. El entrenamiento no se detiene por eso.

## 5. Instrucciones (resumen del prompt)

| Estado | Cuándo |
|---|---|
| `mejorando` | La recompensa media o la tasa de éxito suben en la ventana |
| `estancado` | Cambian menos de 2 % en la ventana y la tasa de éxito está bajo 0,9 |
| `divergiendo` | La recompensa cae más de 20 %, o las pérdidas crecen sin parar |
| `terminado` | La tasa de éxito superó 90 % en 3 chequeos seguidos, o se acabó el tiempo |

- **Ajustes que puede sugerir:** bajar la tasa de aprendizaje, cambiar el peso de un término de recompensa, volver al mejor checkpoint. Siempre uno por vez.
- **Avisos de problema:** con `divergiendo`, con NaN o con `estancado` por 3 chequeos seguidos (RF-MON-04).
- **Avisos de hito:** primer éxito, 50 %, 90 % y fin del entrenamiento (RF-MON-09).
- **Estimación de tiempo:** tras la primera hora, estima con la pendiente de la curva si 90 % llega dentro del presupuesto (RNF-17).
- **Resumen final (RF-MON-07):** horas, pasos, mejor tasa de éxito, hitos y checkpoint elegido, en 4 a 6 oraciones.

## 5.1 Formato del aviso en Discord

```text
🔴 VIAZ · entrenamiento instalar_panel · DIVERGIENDO
Iteración 420 · 1,2 h de 4 h
Recompensa media: 18,4 → 11,9 (−35 % en 20 min)
Tasa de éxito (5 cm, 5°): 0,35 → 0,21
Recomendación: volver al checkpoint model_400.pt y bajar la tasa de aprendizaje
Responde en el canal antes de aplicar el cambio.
```

| Emoji | Tipo |
|---|---|
| 🔴 | `divergiendo` o NaN |
| 🟡 | `estancado` por 3 chequeos |
| 🟢 | Hito |
| 🏁 | Fin del entrenamiento, con el resumen final |

- **Envío:** el código manda el mensaje al webhook. El agente solo escribe el texto de `detalle`.
- **Secreto:** la URL del webhook vive en Render como `VIAZ_DISCORD_WEBHOOK`. No va al repo ni al pod (RNF-08).

## 6. Errores

| Caso | Resultado |
|---|---|
| Sin métricas nuevas en 15 min | `revisar`: el pod puede estar caído |
| El modelo no responde | El chequeo se salta; el entrenamiento sigue. La regla de NaN no depende del agente |
| Discord no responde | El aviso se reintenta 1 vez y queda en `monitoreo.jsonl` |

## 7. Pruebas

- **Curvas sintéticas:** una creciente, una plana y una que cae. El monitor debe dar `mejorando`, `estancado` y `divergiendo`.
- **NaN:** una métrica NaN hace que el siguiente latido reciba `detener`.
- **Hitos:** el primer `tasa_exito ≥ 0,05` produce `primer_exito`. Los hitos los calcula el código (`monitor.hitos()`), no el LLM: los clips dependen de ellos.

## 8. Pendiente

- [x] Canal de avisos: Discord, con webhook.
- [ ] Crear el canal `#entrenamiento` y su webhook; guardar la URL en Render (`VIAZ_DISCORD_WEBHOOK`).
- [ ] Definir cada cuánto chequea (10 min es una propuesta).
- [ ] Agregar el esquema de `monitoreo.jsonl` y la tabla de métricas en la API.
