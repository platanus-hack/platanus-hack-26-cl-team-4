# Cómo decide la etapa de robot

> Explicación del contrato [`seleccion-robot.md`](seleccion-robot.md) (v3). El contrato dice qué entra y qué sale. Esta página dice por qué el flujo tiene esa forma.
> **Estado:** los diagramas 2, 3 y 4 existen en el código (la búsqueda del diagrama 3 solo se probó contra modelos falsos). El diagrama 1 es el flujo anterior. Los diagramas 5 y 6 describen el diseño acordado. Cada uno nombra el PR que lo implementa.

Cada diagrama repite el anterior y agrega una parte. Lo nuevo va en verde.

## 1. Hoy: un robot, un catálogo cerrado

```mermaid
flowchart LR
  E[entorno.json] --> A["Agente de selección"]
  T[tarea.json] --> A
  CAT[("Catálogo<br/>5 fichas")] --> A
  A --> R["robot.json<br/>1 robot"]
  R --> C["Constructor<br/>Isaac Lab"]
  C --> RL["Entrenar y evaluar"]
  RL --> RES[resultado.json]
```

- El agente elige un robot entre las fichas del catálogo. Una ficha es el JSON de un robot real, con su fuente.
- Los criterios del prompt hablan de paneles, ventosas y tubos. Por eso el agente solo sirve para un parque solar.
- La simulación prueba un solo robot. No hay con qué compararlo.

## 2. Los requisitos separan el rubro del agente

```mermaid
flowchart LR
  E[entorno.json] --> P["Perfil de dominio<br/>código, sin LLM"]
  T[tarea.json] --> P
  P --> Q[requisitos.json]
  Q --> A["Agente de selección"]
  CAT[("Catálogo")] --> A
  A --> R["robot.json"]
  classDef nuevo fill:#d9f2d9,stroke:#2e7d32,color:#000
  class P,Q nuevo
```

- Un perfil de dominio es código que traduce el lugar y la tarea a números: carga mínima, alcance mínimo por robot, efectores aceptados, movilidad y pendiente.
- El agente lee `requisitos.json`. Ya no lee "panel" ni "tubo".
- Las reglas solares de hoy pasan al perfil `solar`. Otro rubro agrega su perfil y no toca el agente.
- **Límite:** el agente queda general, pero la simulación sigue siendo solar. Otro rubro todavía no corre de punta a punta.
- **Llega en:** PR 2.

## 3. La búsqueda agrega robots que no estaban

```mermaid
flowchart LR
  Q[requisitos.json] --> B["Agente de búsqueda<br/>con búsqueda web"]
  B --> F["Borradores<br/>dato, URL y cita"]
  F --> V{"¿El código arma<br/>una ficha válida?"}
  V -->|no| X["busqueda.invalidas<br/>con el motivo"]
  V -->|sí| CAND["Candidatos"]
  CAT[("Catálogo del repo")] --> CAND
  COM[("Catálogo compartido<br/>en el almacén")] --> CAND
  COM -.->|"conocidas: no las<br/>busca otra vez"| B
  CAND --> A["Agente de selección"]
  Q --> A
  V -->|sí| COM
  COM -.->|"una persona la revisa<br/>y abre un PR"| CAT
  classDef nuevo fill:#d9f2d9,stroke:#2e7d32,color:#000
  class B,F,V,X,CAND,COM nuevo
```

- El agente de búsqueda parte de los requisitos y busca robots reales que hagan la tarea. Recibe la lista de fichas conocidas para buscar otras.
- El modelo devuelve borradores. El código arma la ficha: `origen: "busqueda"`, fuente con URL y fecha, y un `id` propio.
- Cada spec de selección lleva su `evidencia` (URL y la oración exacta de la fuente) o un `estimado` con su motivo. Sin eso, la ficha es inválida.
- El código valida cada ficha. Una ficha inválida no llega al agente de selección y queda registrada con su motivo.
- Las fichas válidas quedan en el catálogo compartido del almacén. Las corridas siguientes las usan como fichas conocidas.
- Una persona las pasa al catálogo del repo con un PR, porque un modelo escribió esas specs y alguien debe revisarlas.
- Si la búsqueda falla, la corrida sigue con las fichas conocidas.
- **Llega en:** PR 3.

## 4. Qué le pasa a cada candidato

```mermaid
flowchart TD
  C["Candidato"] --> O{"¿Cumple los requisitos<br/>obligatorios?"}
  O -->|no| D["Descartado<br/>con la lista de fallas"]
  O -->|sí| N{"¿Tiene el núcleo<br/>de fisica?"}
  N -->|no| ALT["Alternativa<br/>con su motivo"]
  N -->|sí| ORD["El agente lo ordena<br/>contra los demás"]
  ORD --> TOP{"¿Queda entre<br/>los 3 primeros?"}
  TOP -->|no| ALT
  TOP -->|sí| FIN["Finalista"]
```

| Decisión | Quién decide | Por qué |
|---|---|---|
| ¿Cumple los requisitos obligatorios? | Código | Es una comparación de números. Se puede probar |
| ¿Tiene el núcleo de `fisica`? | Código | Sin largo, ancho, masa, altura de cubierta y tracción, el clon usa la base genérica. Por eso un candidato con núcleo va antes que uno sin núcleo |
| Orden entre los que pasan | Agente | Pesa margen, ritmo y datos estimados. Es un juicio |
| Tope de 3 | Código | Cada finalista cuesta un entrenamiento completo |

- Si ningún candidato cumple los requisitos obligatorios, pasa uno solo: el que falla menos. La justificación lo dice en la primera oración.
- Si algunos cumplen pero ninguno tiene el núcleo de `fisica`, pasa uno solo: el primero por las preferencias. El clon usa la base genérica y la justificación lo dice en la primera oración. Los demás quedan como alternativas. Así un dominio nuevo, sin robots medidos, igual corre.
- **Llega en:** PR 2.

## 5. Cada finalista hace el recorrido completo

```mermaid
flowchart TD
  S["seleccion.json<br/>1 a 3 finalistas"] --> H1["Corrida hija 1"]
  S --> H2["Corrida hija 2"]
  S --> H3["Corrida hija 3"]
  H1 --> M{"¿Hay un modelo<br/>comprobado de este robot?"}
  M -->|no| CON["Agente constructor<br/>hasta 3 intentos"]
  CON --> VAL["validar_robot<br/>en la escena"]
  VAL --> REG["Registrar el modelo<br/>comprobado"]
  M -->|sí| CHK["Chequeo corto<br/>en la escena"]
  REG --> ENT["Entrenar"]
  CHK --> ENT
  ENT --> EV["Evaluar"]
  EV --> J[evaluacion.json]
  H2 -.->|"mismo recorrido"| J
  H3 -.->|"mismo recorrido"| J
```

- Una corrida hija es una corrida normal con el robot ya fijado. Reusa el flujo de hoy sin cambios.
- Un modelo comprobado es el clon de un robot que ya pasó `validar_robot` y la rúbrica de calidad. Su clave es el `id`, la huella de su ficha y la versión de las piezas de Isaac Lab.
- Con un modelo comprobado, la corrida se salta el agente constructor.
- El chequeo en la escena corre siempre, porque el alcance y los choques dependen del lugar.
- La política entrenada no se reusa entre tareas ni entre lugares.
- **Costo:** con un pod, 3 finalistas tardan 3 veces lo que tarda uno.
- **Llega en:** PR 4 para el modelo comprobado y PR 5 para las corridas hijas.

## 6. Las reglas eligen al ganador

```mermaid
flowchart LR
  J1["evaluacion.json<br/>finalista 1"] --> CMP["Comparación<br/>código"]
  J2["evaluacion.json<br/>finalista 2"] --> CMP
  J3["evaluacion.json<br/>finalista 3"] --> CMP
  CMP --> R1{"¿Mayor tasa<br/>de éxito?"}
  R1 -->|empate| R2{"¿Menor tiempo<br/>de ciclo?"}
  R1 -->|"uno gana"| G["Ganador"]
  R2 --> G
  G --> EXP["El agente redacta<br/>la explicación"]
  CMP --> ADV["Advertencias:<br/>fidelidad distinta"]
  EXP --> OUT[comparacion.json]
  ADV --> OUT
```

- Los 3 finalistas usan la misma escena, las mismas horas de entrenamiento y las mismas semillas.
- El código elige al ganador. El agente solo redacta la explicación, porque el resultado debe salir igual cada vez.
- Cada clon declara su `fidelidad`: `generico`, `medido` o `verificado`. Si los finalistas tienen niveles distintos, el resultado lo advierte.
- **Lo que la simulación compara:** alcance, tamaño, masa, carga útil y velocidad.
- **Lo que no compara:** los motores y el control de cada marca. Todos los clones usan el mismo brazo escalado.
- **Llega en:** PR 5.

## 7. La vida de una ficha

```mermaid
stateDiagram-v2
  [*] --> Encontrada: la búsqueda la devuelve
  [*] --> EnCatalogo: ya estaba en el repo
  Encontrada --> Invalida: no cumple el esquema, sin fuente o duplicada
  Encontrada --> Compartida: cumple el esquema
  Compartida --> Candidata: en esta corrida y en las siguientes
  EnCatalogo --> Candidata
  Candidata --> Descartada: falla un requisito obligatorio
  Candidata --> Alternativa: le falta el núcleo de fisica o queda bajo el tope
  Candidata --> Finalista: queda entre los 3 primeros
  Finalista --> Ganadora: mejor evaluación
  Finalista --> NoGanadora: otra evaluación fue mejor
  Compartida --> EnCatalogo: una persona la revisa y abre un PR
  Invalida --> [*]
  Descartada --> [*]
  Alternativa --> [*]
  Ganadora --> [*]
  NoGanadora --> [*]
```

- `seleccion.json` guarda a las inválidas, las descartadas, las alternativas y las finalistas, cada una con su motivo.
- Una ficha compartida vive en `catalogo/encontrados/<id>.json` del almacén hasta que un PR la pasa al repo.
- `comparacion.json` guarda el orden final de las finalistas.

## Dónde llega cada parte

| PR | Qué agrega | Diagramas |
|---|---|---|
| 1 | Contrato, esquemas y esta página | Todos, como diseño |
| 2 | Requisitos, perfil solar, finalistas | 2 y 4 |
| 3 | Agente de búsqueda | 3 |
| 4 | Registro de modelos comprobados | 5 |
| 5 | Corridas hijas y comparación | 5 y 6 |
| 6 | Web | Ninguno |
