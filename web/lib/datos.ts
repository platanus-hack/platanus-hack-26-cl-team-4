// Carga de la corrida solar incluida con la demo.
import { bajarJson, bajarTexto } from "./api";
import type { Clon, Entorno, Resultado, Robot, Trayectoria } from "./tipos";

type RobotDemo = Robot & {
  tipo: "base_movil_brazo" | "brazo_fijo" | "vehiculo_con_brazo";
  velocidad_base_m_s: number;
  efector: "ventosa" | "pinza";
};

type ResultadoDemo = Pick<Resultado, "fuente" | "metricas" | "video" | "notas"> & {
  evaluacion?: {
    episodios: number;
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
};

type TareaDemo = { objetivo: { paneles: number; ciclo_s: number } };

export interface Datos {
  entorno: Entorno;
  tarea: TareaDemo;
  robot: RobotDemo;
  clon: Clon;
  resultado: ResultadoDemo;
  tray: Trayectoria;
  urdf: string;
  video: string | null;       // muestra del robot entrenado (RF-WEB-06)
  videoRapido: string | null; // entrenamiento en cámara rápida (RF-WEB-13)
}

async function existe(url: string) {
  try {
    const r = await fetch(url, { method: "HEAD" });
    return r.ok;
  } catch {
    return false;
  }
}

/** Corrida del demo: archivos estáticos en web/public/demo. */
export async function cargarDemo(): Promise<Datos> {
  const u = (archivo: string) => `/demo/${archivo}`;
  const [entorno, tarea, robot, clon, resultado, tray, urdf] = await Promise.all([
    bajarJson<Entorno>(u("entorno.json")), bajarJson<TareaDemo>(u("tarea.json")), bajarJson<RobotDemo>(u("robot.json")),
    bajarJson<Clon>(u("clon.json")), bajarJson<ResultadoDemo>(u("resultado.json")),
    bajarJson<Trayectoria>(u("trayectoria.json")), bajarTexto(u("robot.urdf")),
  ]);
  const opcional = async (archivo: string | null | undefined) => {
    if (!archivo) return null;
    const v = u(archivo);
    return await existe(v) ? v : null;
  };
  const [video, videoRapido] = await Promise.all([
    opcional(resultado.video), opcional(resultado.entrenamiento?.video_rapido),
  ]);
  return { entorno, tarea, robot, clon, resultado, tray, urdf, video, videoRapido };
}
