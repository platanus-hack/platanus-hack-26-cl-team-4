// Palabras de cada tarea para la web (RF-GEN-04, RF-WEB-21). Una tarea nueva agrega su fila; sin fila, se usan
// las genéricas. Los datos siguen saliendo de resultado.json: aquí solo cambian los nombres.
export interface Vocabulario {
  logrados: string;        // fila de éxitos sobre intentos
  ciclo: string;           // tiempo promedio de un éxito
  episodios: string;       // cómo se evaluó
  usaAngulo: boolean;      // la tolerancia angular aplica a esta tarea
}

const TAREAS: Record<string, Vocabulario> = {
  instalar_panel: {
    logrados: "Paneles instalados", ciclo: "Ciclo por panel", usaAngulo: true,
    episodios: "episodios de evaluación, con la base detenida con ruido de ±15 cm y ±5°.",
  },
  animar_evento: {
    logrados: "Recorridos completos", ciclo: "Tiempo del recorrido", usaAngulo: false,
    episodios: "recorridos completos en la sala, cada uno con su coreografía, sin caerse ni chocar.",
  },
};

const GENERICO: Vocabulario = {
  logrados: "Repeticiones logradas", ciclo: "Ciclo por repetición", usaAngulo: true,
  episodios: "episodios de evaluación.",
};

export function vocabulario(tarea: string | undefined): Vocabulario {
  return (tarea && TAREAS[tarea]) || GENERICO;
}
