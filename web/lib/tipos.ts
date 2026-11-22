// Tipos del contrato (docs/contrato-datos.md). Si cambias el contrato, cambia esto también.

export type EstadoCorrida =
  | "en_cola" | "analizando_entorno" | "eligiendo_robot" | "clonando" | "simulando" | "entrenando" | "evaluando"
  | "listo" | "error";

export interface Etapa {
  nombre: "entorno" | "tarea" | "robot" | "clon" | "inteligencia";
  estado: "pendiente" | "en_curso" | "listo" | "error";
  artefactos: Record<string, string>; // archivo -> URL
}

export interface Corrida {
  id: string;
  estado: EstadoCorrida;
  etapas: Etapa[];
  error: string | null;
}

export interface Entorno {
  tipo: string;
  descripcion: string;
  confianza: Record<string, number>;
  // Perfil parque_solar: solo existen en ese tipo de entorno.
  filas: { cantidad: number; largo_m: number; separacion_m: number };
  estructura: { tipo: string; altura_m: number; inclinacion_grados: number };
  panel: { largo_m: number; ancho_m: number; peso_kg: number };
  terreno: { pendiente_grados: number; suelo: string; friccion?: number };
}

export interface Robot {
  id: string;
  nombre: string;
  fabricante: string;
  ficticio: boolean;
  carga_util_kg: number;
  alcance_m: number;
  justificacion: string;
  alternativas: { id: string; por_que_no: string }[];
  fuente: { url: string | null; consultado: string | null };
}

export interface Clon {
  diferencias_con_real: string[];
  validado_en_escena: boolean;
  piezas?: { base: string; brazo: string; efector: string };   // clon ensamblado
  modelo?: { fuente: string; cfg: string; usd: string };      // clon = modelo publicado del fabricante
  fidelidad?: "generico" | "medido" | "verificado";
  construccion?: { metodo: "agente" | "determinista" | "comprobado"; intentos: number };
}

export interface Tolerancia {
  pos_m: number;
  ang_grados: number;
  exitos: number;
  tasa_exito: number;
}

export interface Resultado {
  metodo: "planificador" | "rl" | "planificador_rl";
  fuente: "isaac" | "simulado";
  metricas: { paneles_instalados: number; intentos: number; tasa_exito: number; ciclo_promedio_s: number };
  video: string | null;
  notas: string;
  evaluacion?: { episodios: number; tolerancias: Tolerancia[]; checkpoint: string };
  entrenamiento?: { horas: number; iteraciones: number; pasos: number; factor_video: number | null };
}

export interface VideoInfo {
  duracion_s: number;
  horas_representadas: number;
  factor_video: number | null;
}

export interface Frame {
  t_s: number;
  base: { pos_m: [number, number, number]; yaw_grados: number };
  q: number[];
  agarre: number | null;
  instalados: number[];
}

export interface Trayectoria {
  fps: number;
  articulaciones: string[];
  paneles: { id: number; pos_m: [number, number, number]; quat: [number, number, number, number] }[];
  pila: { en_base: boolean; pos_m: [number, number, number]; paso_m: number };
  frames: Frame[];
}

export interface Tarea {
  tarea: string;
  descripcion: string;
  criterios_exito: { tolerancia_pos_m: number; tolerancia_ang_grados: number; sin_choques: boolean; tiempo_max_s: number | null };
}
