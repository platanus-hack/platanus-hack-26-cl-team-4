// Carga de una corrida completa: desde los archivos estáticos del demo o desde la API.
import { bajarJson, bajarTexto } from "./api";
import type { Clon, Corrida, Entorno, Resultado, Robot, Tarea, Trayectoria } from "./tipos";

export interface Datos {
  entorno: Entorno;
  tarea: Tarea;
  robot: Robot;
  clon: Clon;
  resultado: Resultado;
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

async function cargar(url: (archivo: string) => string | undefined): Promise<Datos> {
  const u = (a: string) => {
    const v = url(a);
    if (!v) throw new Error(`falta ${a} en la corrida`);
    return v;
  };
  const [entorno, tarea, robot, clon, resultado, tray, urdf] = await Promise.all([
    bajarJson<Entorno>(u("entorno.json")), bajarJson<Tarea>(u("tarea.json")), bajarJson<Robot>(u("robot.json")),
    bajarJson<Clon>(u("clon.json")), bajarJson<Resultado>(u("resultado.json")),
    bajarJson<Trayectoria>(u("trayectoria.json")), bajarTexto(u("robot.urdf")),
  ]);
  const opcional = async (archivo: string | null | undefined) => {
    if (!archivo) return null;
    const v = url(archivo);
    return v && (await existe(v)) ? v : null;
  };
  const [video, videoRapido] = await Promise.all([
    opcional(resultado.video), opcional(resultado.entrenamiento?.video_rapido),
  ]);
  return { entorno, tarea, robot, clon, resultado, tray, urdf, video, videoRapido };
}

/** Corrida del demo: archivos estáticos en web/public/demo (los genera `python -m viaz.demo`). */
export function cargarDemo() {
  return cargar((a) => `/demo/${a}`);
}

/** Corrida de la API: los artefactos vienen como URLs firmadas. */
export function cargarCorrida(c: Corrida) {
  const a = Object.assign({}, ...c.etapas.map((e) => e.artefactos)) as Record<string, string>;
  return cargar((archivo) => a[archivo]);
}
