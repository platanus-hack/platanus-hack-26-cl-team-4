"use client";

import Link from "next/link";
import { useId } from "react";

import {
  cargarComparacion, nombreDe, numero, porcentaje,
  type Comparacion as DatosArchivo, type DatosComparacion, type Fidelidad,
} from "@/lib/seleccion";
import type { Corrida } from "@/lib/tipos";
import { useArtefacto } from "@/lib/useArtefacto";

const FIDELIDAD: Record<Fidelidad, { nombre: string; detalle: string }> = {
  generico: { nombre: "Genérica", detalle: "base genérica, sin las medidas del vehículo real" },
  medido: { nombre: "Medida", detalle: "usa las medidas publicadas del vehículo o tomadas de fotos" },
  verificado: { nombre: "Verificada", detalle: "medidas sin estimar y clon revisado en la escena" },
};

function tolerancia(c: DatosArchivo["condiciones"]): string {
  return `${numero(c.tolerancia_pos_m * 100, 1)} cm y ${numero(c.tolerancia_ang_grados, 1)}°`;
}

function lista(valores: string[]): string {
  return valores.length < 2 ? valores.join("") : `${valores.slice(0, -1).join(", ")} y ${valores[valores.length - 1]}`;
}

export default function ComparacionDeCorrida({ corrida }: { corrida: Corrida }) {
  const datos = useArtefacto(corrida, "comparacion.json", cargarComparacion);
  return datos ? <Comparacion datos={datos} /> : null;
}

export function Comparacion({ datos }: { datos: DatosComparacion }) {
  const { comparacion: c, fichas } = datos;
  const ranking = [...c.ranking].sort((a, b) => a.puesto - b.puesto);
  const tituloId = useId();
  return (
    <section className="tarjeta comparacion" aria-labelledby={tituloId}>
      <h3 id={tituloId}>
        Comparación de los finalistas <span className="etiqueta">simulación</span>
      </h3>
      <p>Gana <strong>{nombreDe(fichas, ranking.find((r) => r.id === c.ganador) ?? { id: c.ganador })}</strong>.</p>
      <p>Regla de la elección: {c.regla}</p>
      <p className="tenue">
        Todos entrenaron en la misma escena, {numero(c.condiciones.horas_entrenamiento, 1)} h cada uno
        {c.condiciones.semillas
          ? `, con las semillas ${lista(c.condiciones.semillas.map(String))}.`
          : ". El entrenamiento no fija las semillas: una diferencia chica puede venir del azar."}
        {" "}El éxito se mide a {tolerancia(c.condiciones)}.
      </p>

      <div className="tabla-envoltura">
        <table className="tabla">
          <caption className="tenue">Ranking de la simulación</caption>
          <thead>
            <tr>
              <th scope="col">Puesto</th>
              <th scope="col">Robot</th>
              <th scope="col">Éxito a {tolerancia(c.condiciones)}</th>
              <th scope="col">Tiempo de ciclo</th>
              <th scope="col">Fidelidad del clon</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((r) => (
              <tr key={r.id}>
                <td className="num">{r.puesto}</td>
                <th scope="row"><Link href={`/corridas/${r.corrida_id}`}>{nombreDe(fichas, r)}</Link></th>
                <td className="num">{porcentaje(r.tasa_exito)}</td>
                <td className="num">{r.ciclo_s === null ? "sin éxitos" : `${numero(r.ciclo_s, 1)} s`}</td>
                <td>
                  {FIDELIDAD[r.fidelidad]?.nombre ?? r.fidelidad}
                  <span className="tenue"> · {FIDELIDAD[r.fidelidad]?.detalle ?? ""}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {c.advertencias.length > 0 && (
        <ul className="aviso" aria-label="Advertencias">
          {c.advertencias.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
      {c.explicacion && <p>{c.explicacion}</p>}

      <div className="compara">
        <div>
          <h4>Qué compara la simulación</h4>
          <ul>{c.que_compara.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
        <div>
          <h4>Qué no compara</h4>
          <ul>{c.que_no_compara.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      </div>
    </section>
  );
}
