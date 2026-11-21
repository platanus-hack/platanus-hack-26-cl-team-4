// Tipos del contrato (docs/contrato-datos.md). Si cambias el contrato, cambia esto también.

export type EstadoCorrida =
  | "en_cola" | "analizando_entorno" | "eligiendo_robot" | "clonando" | "simulando" | "listo" | "error";

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
  filas: { cantidad: number; largo_m: number; separacion_m: number };
  estructura: { tipo: string; altura_m: number; inclinacion_grados: number };
  panel: { largo_m: number; ancho_m: number; peso_kg: number };
  terreno: { pendiente_grados: number; suelo: string };
}

export interface Robot {
  id: string;
  nombre: string;
  fabricante: string;
  ficticio: boolean;
  tipo: "base_movil_brazo" | "brazo_fijo" | "vehiculo_con_brazo";
  carga_util_kg: number;
  alcance_m: number;
  velocidad_base_m_s: number;
  efector: "ventosa" | "pinza";
  justificacion: string;
  alternativas: { id: string; por_que_no: string }[];
  fuente: { url: string | null; consultado: string | null };
}

export interface Clon {
  diferencias_con_real: string[];
  validado_en_escena: boolean;
}

export interface Resultado {
  fuente: "isaac" | "simulado";
  metricas: { paneles_instalados: number; intentos: number; tasa_exito: number; ciclo_promedio_s: number };
  video: string | null;
  notas: string;
  evaluacion?: {
    episodios: number;
    exitos: number;
    tasa_exito: number;
    tolerancia: { pos_m: number; ang_grados: number };
  };
  entrenamiento?: {
    pasos_sim: number;
    tiempo_real_s: number;
    num_entornos: number;
    video_rapido: string | null;
    curva: { paso: number; tasa_exito: number }[];
    hitos: { paso: number; texto: string }[];
  };
}

export interface Tarea {
  descripcion: string;
  objetivo: { paneles: number; ciclo_s: number };
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
