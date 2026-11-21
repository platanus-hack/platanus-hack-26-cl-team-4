"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import Etapas from "@/components/Etapas";
import { bajarJson, bajarTexto, verCorrida } from "@/lib/api";
import type { Clon, Corrida, Entorno, Resultado, Robot, Trayectoria } from "@/lib/tipos";

const Visor = dynamic(() => import("@/components/Visor"), { ssr: false, loading: () => <p>Cargando visor…</p> });

interface Datos {
  entorno: Entorno;
  robot: Robot;
  clon: Clon;
  resultado: Resultado;
  tray: Trayectoria;
  urdf: string;
  video: string | null;
}

export default function PaginaCorrida() {
  const { id } = useParams<{ id: string }>();
  const [corrida, setCorrida] = useState<Corrida | null>(null);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    let timer: ReturnType<typeof setTimeout>;
    async function sondear() {
      try {
        const c = await verCorrida(id);
        if (!vivo) return;
        setCorrida(c);
        if (c.estado === "listo") {
          const a = Object.assign({}, ...c.etapas.map((e) => e.artefactos)) as Record<string, string>;
          const [entorno, robot, clon, resultado, tray, urdf] = await Promise.all([
            bajarJson<Entorno>(a["entorno.json"]), bajarJson<Robot>(a["robot.json"]), bajarJson<Clon>(a["clon.json"]),
            bajarJson<Resultado>(a["resultado.json"]), bajarJson<Trayectoria>(a["trayectoria.json"]), bajarTexto(a["robot.urdf"]),
          ]);
          if (vivo) setDatos({ entorno, robot, clon, resultado, tray, urdf, video: a["video.mp4"] ?? null });
          return;
        }
        if (c.estado !== "error") timer = setTimeout(sondear, 2000);
      } catch (e) {
        if (vivo) setError(e instanceof Error ? e.message : String(e));
      }
    }
    sondear();
    return () => { vivo = false; clearTimeout(timer); };
  }, [id]);

  if (error) return <p className="error" role="alert">No pude cargar la corrida: {error}</p>;
  if (!corrida) return <p>Cargando…</p>;

  return (
    <section className="corrida">
      <aside className="lateral">
        <h2>Corrida {corrida.id}</h2>
        <Etapas etapas={corrida.etapas} />
        {corrida.error && <p className="error" role="alert">{corrida.error}</p>}
        {datos && <Panel datos={datos} />}
      </aside>
      <div className="principal">
        {datos ? (
          <>
            <Visor entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} />
            {datos.video && <video className="video" src={datos.video} controls muted playsInline />}
          </>
        ) : (
          <div className="espera">{corrida.estado === "error" ? "La corrida falló." : "Los agentes están trabajando…"}</div>
        )}
      </div>
    </section>
  );
}

function Panel({ datos }: { datos: Datos }) {
  const { robot, clon, resultado } = datos;
  const m = resultado.metricas;
  return (
    <>
      <div className="tarjeta">
        <h3>{robot.nombre} {robot.ficticio && <span className="etiqueta">ficticio</span>}</h3>
        <p className="tenue">{robot.fabricante} · {robot.carga_util_kg} kg · alcance {robot.alcance_m} m</p>
        <p>{robot.justificacion}</p>
        {robot.fuente.url && <a href={robot.fuente.url} target="_blank" rel="noreferrer">Fuente ({robot.fuente.consultado})</a>}
      </div>
      <div className="tarjeta">
        <h3>Resultado {resultado.fuente === "simulado" && <span className="etiqueta">sin física</span>}</h3>
        <dl className="metricas">
          <dt>Paneles instalados</dt><dd>{m.paneles_instalados} / {m.intentos}</dd>
          <dt>Tasa de éxito</dt><dd>{Math.round(m.tasa_exito * 100)}%</dd>
          <dt>Ciclo por panel</dt><dd>{m.ciclo_promedio_s} s</dd>
        </dl>
        <p className="tenue">{resultado.notas}</p>
      </div>
      <div className="tarjeta">
        <h3>Diferencias del clon con el real</h3>
        <ul>{clon.diferencias_con_real.map((d) => <li key={d}>{d}</li>)}</ul>
      </div>
    </>
  );
}
