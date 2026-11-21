// Contenido del pitch: el flujo de VIAZ (RF-WEB-19) y el problema con datos verificados.
// Los hechos salen de docs/investigacion-datasets.md (verificado el 2026-11-21). No agregar cifras sin fuente.

export interface Paso {
  nombre: string;
  quien: string;
  agente: boolean; // true = lo hace un agente de IA (se marca en amarillo)
  hace: string;
  produce: string;
}

export const FLUJO: Paso[] = [
  {
    nombre: "Subir videos",
    quien: "El cliente",
    agente: false,
    hace: "Graba su planta con un celular o un dron y sube los videos.",
    produce: "Videos de la planta",
  },
  {
    nombre: "Extraer el entorno",
    quien: "Agente de mapeo",
    agente: true,
    hace: "Mide en los videos las filas, las estructuras y los paneles, y arma la escena 3D con física.",
    produce: "Escena de la planta",
  },
  {
    nombre: "Elegir el robot",
    quien: "Agente de selección",
    agente: true,
    hace: "Compara la tarea con un catálogo de robots que ya se venden y justifica cuál calza, con la fuente de cada dato.",
    produce: "Robot elegido",
  },
  {
    nombre: "Construir el robot",
    quien: "Agente constructor",
    agente: true,
    hace: "Arma el robot en Isaac Lab con el alcance, la carga útil y las masas del real, y lo prueba en la escena.",
    produce: "Clon del robot",
  },
  {
    nombre: "Entrenar su inteligencia",
    quien: "Isaac Lab y agente monitor",
    agente: true,
    hace: "El robot aprende la tarea con miles de intentos en paralelo en una GPU. El agente monitor vigila el entrenamiento y avisa al equipo.",
    produce: "Inteligencia entrenada",
  },
  {
    nombre: "Mostrar el resultado",
    quien: "VIAZ",
    agente: false,
    hace: "Mide cuántas veces el robot hace bien la tarea y graba cómo trabajaría en esa planta.",
    produce: "Videos y métricas",
  },
];

export interface Hecho {
  texto: string;
  fuente: string;
  url: string | null;
}

export const PROBLEMA: Hecho[] = [
  {
    texto: "Los robots que instalan paneles ya existen. Maximo, de AES, instaló 100 MW con 4 robots y superó un módulo por minuto.",
    fuente: "Solar Power World, 25 de marzo de 2026",
    url: "https://www.solarpowerworldonline.com/2026/03/robots-install-100-mw-of-solar-panels-on-1-gw-aes-project/",
  },
  {
    texto: "También los venden fabricantes chinos: Trina Solar declara que su BUILDEX instala hasta 90 módulos por hora.",
    fuente: "Comunicado de Trina Solar (cifra del fabricante), 24 de septiembre de 2026",
    url: "https://www.webull.com/news/15632505306743808",
  },
  {
    texto: "Pero nadie publica datos para entrenarlos en otra planta: no encontramos ningún dataset público de montaje de paneles.",
    fuente: "Investigación del equipo en Hugging Face, Kaggle y arXiv, 21 de noviembre de 2026",
    url: null,
  },
  {
    texto: "Y en Chile hay 761 centrales solares registradas que podrían usarlos.",
    fuente: "Infotécnica, Coordinador Eléctrico Nacional, consultada el 21 de noviembre de 2026",
    url: "https://infotecnica.coordinador.cl/instalaciones/centrales",
  },
];

export const PRINCIPIOS = [
  {
    titulo: "Robots que se pueden comprar",
    texto: "El agente elige solo dentro de un catálogo de robots a la venta. Cada especificación cita su fuente y su fecha.",
  },
  {
    titulo: "Datos que nadie publica",
    texto: "La simulación genera los miles de intentos de montaje que no existen en ningún dataset público.",
  },
  {
    titulo: "Agentes con supervisión",
    texto: "El agente monitor vigila el entrenamiento y avisa al equipo. Lo que cuesta horas de GPU lo aprueba una persona.",
  },
  {
    titulo: "Medido, no prometido",
    texto: "La tasa de éxito va con su tolerancia y su número de intentos, y lo que el clon no copia del robot real se dice. La simulación revisa alcance y carga antes de comprar; no certifica nada.",
  },
];
