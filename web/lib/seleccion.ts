// These files carry text found on the web: render it as plain text.

import { bajarJson } from "./api";
import type { Corrida } from "./tipos";

export type BusquedaEstado = "completa" | "cortada" | "fallida" | "omitida";
export type Fidelidad = "generico" | "medido" | "verificado";

export interface Requisitos {
  tarea: string;
  carga_min_kg: number;
  efectores_aceptados: string[];
  movilidad: "fija" | "movil" | "cualquiera";
  por_robot: { id: string; alcance_min_m: number | null }[];
  advertencias: string[];
}

export interface Seleccion {
  busqueda: { estado: BusquedaEstado; detalle: string; invalidas: { nombre: string; motivo: string }[] };
  encontrados: string[];
  descartados: { id: string; nombre?: string; fallas: string[] }[];
  finalistas: { id: string; nombre?: string; puesto: number; justificacion: string }[];
  alternativas: { id: string; nombre?: string; por_que_no: string }[];
}

export interface Evidencia {
  url: string;
  cita: string;
}

export interface FichaRobot {
  id: string;
  nombre: string;
  fabricante: string;
  tipo: string;
  carga_util_kg: number;
  alcance_m: number;
  velocidad_base_m_s: number;
  efector: string;
  fuente: { url: string | null; consultado: string | null };
  origen?: "catalogo" | "busqueda";
  evidencia?: Record<string, Evidencia>;
  estimados?: Record<string, string>;
  fisica?: Record<string, number | string>;
}

export interface FilaRanking {
  id: string;
  nombre?: string;
  corrida_id: string;
  puesto: number;
  tasa_exito: number;
  ciclo_s: number | null;
  fidelidad: Fidelidad;
}

export interface Comparacion {
  ganador: string;
  regla: string;
  condiciones: {
    escena: string;
    horas_entrenamiento: number;
    semillas: number[] | null;
    tolerancia_pos_m: number;
    tolerancia_ang_grados: number;
  };
  ranking: FilaRanking[];
  advertencias: string[];
  que_compara: string[];
  que_no_compara: string[];
  explicacion: string;
}

export interface DatosSeleccion {
  seleccion: Seleccion;
  requisitos: Requisitos | null;
  encontrados: FichaRobot[];
  fichas: Record<string, FichaRobot>;
}

export interface DatosComparacion {
  comparacion: Comparacion;
  fichas: Record<string, FichaRobot>;
}

export interface Hija {
  id: string;
  robot_id: string | null;
  estado: string;
}

// Not in tipos.ts: another open pull request rewrites that file.
export interface CorridaConFamilia extends Corrida {
  padre_id?: string | null;
  hijas?: Hija[];
}

export function artefactosDe(corrida: Corrida): Record<string, string> {
  return Object.assign({}, ...corrida.etapas.map((e) => e.artefactos)) as Record<string, string>;
}

export function esUrlWeb(url: string | null | undefined): url is string {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}

export function numero(valor: number, decimales = 2): string {
  return valor.toLocaleString("es-CL", { maximumFractionDigits: decimales });
}

export function porcentaje(fraccion: number): string {
  return `${numero(fraccion * 100, 1)} %`;
}

function esSeleccion(x: unknown): x is Seleccion {
  const s = x as Seleccion | null;
  return !!s && Array.isArray(s.finalistas) && Array.isArray(s.alternativas) && Array.isArray(s.descartados)
    && Array.isArray(s.encontrados) && !!s.busqueda && Array.isArray(s.busqueda.invalidas);
}

function esComparacion(x: unknown): x is Comparacion {
  const c = x as Comparacion | null;
  return !!c && Array.isArray(c.ranking) && Array.isArray(c.advertencias) && Array.isArray(c.que_compara)
    && Array.isArray(c.que_no_compara) && !!c.condiciones;
}

async function opcional<T>(url: string | undefined): Promise<T | null> {
  if (!url) return null;
  try {
    return await bajarJson<T>(url);
  } catch {
    return null;
  }
}

export function indexarFichas(
  encontrados: FichaRobot[], primerFinalista: FichaRobot | null,
): Record<string, FichaRobot> {
  const todas = primerFinalista ? [...encontrados, primerFinalista] : encontrados;
  return Object.fromEntries(todas.filter((f) => typeof f?.id === "string").map((f) => [f.id, f]));
}

async function cargarFichas(artefactos: Record<string, string>) {
  const [encontrados, robot] = await Promise.all([
    opcional<unknown>(artefactos["encontrados.json"]),
    opcional<FichaRobot>(artefactos["robot.json"]),
  ]);
  const lista = Array.isArray(encontrados) ? (encontrados as FichaRobot[]) : [];
  return { encontrados: lista, fichas: indexarFichas(lista, robot) };
}

export async function cargarSeleccion(artefactos: Record<string, string>): Promise<DatosSeleccion | null> {
  const seleccion = await opcional<unknown>(artefactos["seleccion.json"]);
  if (!esSeleccion(seleccion)) return null;
  const [requisitos, fichas] = await Promise.all([
    opcional<Requisitos>(artefactos["requisitos.json"]),
    cargarFichas(artefactos),
  ]);
  return { seleccion, requisitos, ...fichas };
}

export async function cargarComparacion(artefactos: Record<string, string>): Promise<DatosComparacion | null> {
  const comparacion = await opcional<unknown>(artefactos["comparacion.json"]);
  if (!esComparacion(comparacion)) return null;
  const { fichas } = await cargarFichas(artefactos);
  return { comparacion, fichas };
}

export function nombreDe(fichas: Record<string, FichaRobot>, fila: { id: string; nombre?: string }): string {
  return fila.nombre ?? fichas[fila.id]?.nombre ?? fila.id;
}
