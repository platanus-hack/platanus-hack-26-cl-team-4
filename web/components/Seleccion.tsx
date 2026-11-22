"use client";

import Link from "next/link";
import { useId } from "react";

import {
  cargarSeleccion, esUrlWeb, nombreDe, numero,
  type BusquedaEstado, type CorridaConFamilia, type DatosSeleccion, type FichaRobot, type Requisitos,
} from "@/lib/seleccion";
import { useArtefacto } from "@/lib/useArtefacto";

const ESTADO_BUSQUEDA: Record<BusquedaEstado, string> = {
  omitida: "No buscamos robots en la web en esta corrida. Los candidatos son los del catálogo.",
  completa: "Buscamos robots en la web y la búsqueda terminó.",
  cortada: "Buscamos robots en la web, pero la búsqueda se cortó por tiempo o por tope. Pueden faltar robots.",
  fallida: "La búsqueda web falló. Seguimos solo con los robots del catálogo.",
};

const TIPOS: Record<string, string> = {
  base_movil_brazo: "robot móvil con manipulador",
  brazo_fijo: "manipulador fijo",
  vehiculo_con_brazo: "vehículo con manipulador",
};

const MOVILIDAD: Record<Requisitos["movilidad"], string> = {
  movil: "un robot móvil",
  fija: "un manipulador fijo",
  cualquiera: "un robot móvil o fijo",
};

interface Spec {
  clave: string;
  nombre: string;
  valor: (f: FichaRobot) => string;
}

const SPECS: Spec[] = [
  { clave: "carga_util_kg", nombre: "Carga útil", valor: (f) => `${numero(f.carga_util_kg)} kg` },
  { clave: "alcance_m", nombre: "Alcance", valor: (f) => `${numero(f.alcance_m)} m` },
  { clave: "velocidad_base_m_s", nombre: "Velocidad de la base", valor: (f) => `${numero(f.velocidad_base_m_s)} m/s` },
  { clave: "efector", nombre: "Efector final", valor: (f) => f.efector },
  { clave: "tipo", nombre: "Tipo", valor: (f) => TIPOS[f.tipo] ?? f.tipo },
];

function specFisica(clave: string): Spec {
  const campo = clave.slice("fisica.".length);
  return {
    clave,
    nombre: `Medida física: ${campo.replaceAll("_", " ")}`,
    valor: (f) => {
      const v = f.fisica?.[campo];
      return typeof v === "number" ? numero(v) : (v ?? "sin valor");
    },
  };
}

function specsDe(ficha: FichaRobot): Spec[] {
  const conocidas = new Set(SPECS.map((s) => s.clave));
  const extra = [...Object.keys(ficha.evidencia ?? {}), ...Object.keys(ficha.estimados ?? {})]
    .filter((k) => !conocidas.has(k) && k.startsWith("fisica."));
  return [...SPECS, ...[...new Set(extra)].map(specFisica)];
}

function cantidadEstimados(ficha: FichaRobot | undefined): number {
  return Object.keys(ficha?.estimados ?? {}).filter((k) => !k.startsWith("fisica.")).length;
}

function EtiquetaEstimados({ cantidad }: { cantidad: number }) {
  if (cantidad === 0) return null;
  return (
    <span className="etiqueta etiqueta-tenue">{cantidad === 1 ? "1 dato estimado" : `${cantidad} datos estimados`}</span>
  );
}

function Enlace({ url, children }: { url: string | null | undefined; children: React.ReactNode }) {
  if (!esUrlWeb(url)) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer">{children}</a>;
}

export default function SeleccionDeCorrida({ corrida }: { corrida: CorridaConFamilia }) {
  const datos = useArtefacto(corrida, "seleccion.json", cargarSeleccion);
  return (
    <>
      {corrida.padre_id && <AvisoHija padreId={corrida.padre_id} />}
      {datos && <Seleccion datos={datos} />}
    </>
  );
}

function AvisoHija({ padreId }: { padreId: string }) {
  return (
    <p className="aviso">
      Esta corrida es una de las finalistas de <Link href={`/corridas/${padreId}`}>la corrida {padreId}</Link>.
    </p>
  );
}

export function Seleccion({ datos }: { datos: DatosSeleccion }) {
  const { seleccion, requisitos, encontrados, fichas } = datos;
  const deLaWeb = new Set(seleccion.encontrados);
  const finalistas = [...seleccion.finalistas].sort((a, b) => a.puesto - b.puesto);
  const hayFinalistaDeLaWeb = finalistas.some((f) => deLaWeb.has(f.id));
  const tituloId = useId();
  return (
    <section className="tarjeta seleccion" aria-labelledby={tituloId}>
      <h3 id={tituloId}>Cómo elegimos el robot</h3>
      {requisitos && <LoQuePide requisitos={requisitos} />}

      <h4>{finalistas.length === 1 ? "Finalista" : `Finalistas (${finalistas.length})`}</h4>
      <ol className="finalistas">
        {finalistas.map((f) => (
          <li key={f.id}>
            <strong>{nombreDe(fichas, f)}</strong>
            {deLaWeb.has(f.id) && <span className="etiqueta">Encontrado en la web, sin revisar</span>}
            <EtiquetaEstimados cantidad={cantidadEstimados(fichas[f.id])} />
            <p>{f.justificacion}</p>
          </li>
        ))}
      </ol>
      {hayFinalistaDeLaWeb && (
        <p className="aviso">
          Un finalista viene de una página web. Una persona todavía no revisa sus datos: compáralos con la fuente antes
          de decidir.
        </p>
      )}

      {seleccion.alternativas.length > 0 && (
        <details>
          <summary className="tenue">Alternativas que no quedaron ({seleccion.alternativas.length})</summary>
          <ul>
            {seleccion.alternativas.map((a) => (
              <li key={a.id}><strong>{nombreDe(fichas, a)}:</strong> {a.por_que_no}</li>
            ))}
          </ul>
        </details>
      )}
      {seleccion.descartados.length > 0 && (
        <details>
          <summary className="tenue">Robots descartados por no cumplir ({seleccion.descartados.length})</summary>
          <ul>
            {seleccion.descartados.map((d) => (
              <li key={d.id}><strong>{nombreDe(fichas, d)}:</strong> {d.fallas.join("; ")}</li>
            ))}
          </ul>
        </details>
      )}

      <Busqueda busqueda={seleccion.busqueda} />
      {encontrados.length > 0 && (
        <>
          <h4>Robots encontrados en la web en esta corrida ({encontrados.length})</h4>
          {encontrados.map((f) => <FichaEncontrada key={f.id} ficha={f} />)}
        </>
      )}
    </section>
  );
}

function LoQuePide({ requisitos }: { requisitos: Requisitos }) {
  const efectores = requisitos.efectores_aceptados.join(" o ");
  return (
    <>
      <p>
        La tarea pide {MOVILIDAD[requisitos.movilidad] ?? "un robot"}, con efector final {efectores}
        {requisitos.carga_min_kg > 0 ? ` y una carga útil de al menos ${numero(requisitos.carga_min_kg)} kg` : ""}.
      </p>
      {requisitos.advertencias.length > 0 && (
        <ul className="aviso">{requisitos.advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
      )}
    </>
  );
}

function Busqueda({ busqueda }: { busqueda: DatosSeleccion["seleccion"]["busqueda"] }) {
  return (
    <>
      <h4>Búsqueda en la web</h4>
      <p>{ESTADO_BUSQUEDA[busqueda.estado] ?? busqueda.estado}</p>
      {busqueda.detalle && <p className="tenue">{busqueda.detalle}</p>}
      {busqueda.invalidas.length > 0 && (
        <details>
          <summary className="tenue">Fichas rechazadas por datos incompletos o inválidos ({busqueda.invalidas.length})</summary>
          <ul>
            {busqueda.invalidas.map((i, n) => <li key={`${i.nombre}-${n}`}><strong>{i.nombre}:</strong> {i.motivo}</li>)}
          </ul>
        </details>
      )}
    </>
  );
}

function FichaEncontrada({ ficha }: { ficha: FichaRobot }) {
  return (
    <article className="ficha">
      <h5>{ficha.nombre} <span className="tenue">· {ficha.fabricante}</span></h5>
      <p className="tenue">
        <Enlace url={ficha.fuente?.url}>Fuente principal</Enlace>
        {ficha.fuente?.consultado ? ` (consultada el ${ficha.fuente.consultado})` : ""}
      </p>
      <ul className="specs">
        {specsDe(ficha).map((s) => <FilaSpec key={s.clave} spec={s} ficha={ficha} />)}
      </ul>
    </article>
  );
}

function FilaSpec({ spec, ficha }: { spec: Spec; ficha: FichaRobot }) {
  const evidencia = ficha.evidencia?.[spec.clave];
  const estimado = ficha.estimados?.[spec.clave];
  return (
    <li>
      <strong>{spec.nombre}:</strong> {spec.valor(ficha)}
      {estimado !== undefined && (
        <> <span className="etiqueta etiqueta-tenue">estimado</span> <span className="tenue">{estimado}</span></>
      )}
      {estimado === undefined && evidencia && (
        <>
          {" "}<q className="cita">{evidencia.cita}</q>{" "}
          <Enlace url={evidencia.url}>ver fuente</Enlace>
        </>
      )}
      {estimado === undefined && !evidencia && <span className="tenue"> (sin fuente para este dato)</span>}
    </li>
  );
}
