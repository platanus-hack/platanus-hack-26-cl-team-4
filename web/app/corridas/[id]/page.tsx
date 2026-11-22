"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import ComparacionDeCorrida from "@/components/Comparacion";
import Etapas from "@/components/Etapas";
import SeleccionDeCorrida from "@/components/Seleccion";
import { bajarJson, bajarTexto, verCorrida } from "@/lib/api";
import type { Clon, Corrida, Entorno, Resultado, Robot, Tarea, Trayectoria, VideoInfo } from "@/lib/tipos";
import { vocabulario, type Vocabulario } from "@/lib/vocabulario";

const Visor = dynamic(() => import("@/components/Visor"), { ssr: false, loading: () => <p>Cargando visor…</p> });

interface Datos {
  entorno: Entorno;
  tarea: Tarea | null;
  robot: Robot;
  clon: Clon;
  resultado: Resultado;
  tray: Trayectoria | null;
  urdf: string | null;
  construccion: string | null;   // el agente construyendo el robot (RF-WEB-20)
  video: string | null;          // muestra del robot entrenado (RF-WEB-06)
  rapido: string | null;         // entrenamiento en cámara rápida (RF-WEB-13)
  info: VideoInfo | null;
}

async function opcional<T>(f: () => Promise<T>): Promise<T | null> {
  try {
    return await f();
  } catch {
    return null;
  }
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
          const [entorno, robot, clon, resultado] = await Promise.all([
            bajarJson<Entorno>(a["entorno.json"]), bajarJson<Robot>(a["robot.json"]), bajarJson<Clon>(a["clon.json"]),
            bajarJson<Resultado>(a["resultado.json"]),
          ]);
          const [tarea, tray, urdf, info] = await Promise.all([
            a["tarea.json"] ? opcional(() => bajarJson<Tarea>(a["tarea.json"])) : null,
            a["trayectoria.json"] ? opcional(() => bajarJson<Trayectoria>(a["trayectoria.json"])) : null,
            a["robot.urdf"] ? opcional(() => bajarTexto(a["robot.urdf"])) : null,
            a["video_info.json"] ? opcional(() => bajarJson<VideoInfo>(a["video_info.json"])) : null,
          ]);
          if (vivo) setDatos({ entorno, robot, clon, resultado, tray, urdf, info, tarea,
            construccion: a["construccion.mp4"] ?? null, video: a["video.mp4"] ?? null,
            rapido: a["entrenamiento_rapido.mp4"] ?? null });
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
        <h2>{id === "demo" ? "Demo: lugar de referencia" : `Corrida ${corrida.id}`}</h2>
        <Etapas etapas={corrida.etapas} />
        {corrida.error && <p className="error" role="alert">{corrida.error}</p>}
        {datos && <Panel datos={datos} />}
        <SeleccionDeCorrida corrida={corrida} />
      </aside>
      <div className="principal">
        <ComparacionDeCorrida corrida={corrida} />
        {datos ? <Videos datos={datos} /> : (
          <div className="espera">{corrida.estado === "error" ? "La corrida falló." : "Los agentes están trabajando…"}</div>
        )}
      </div>
    </section>
  );
}

function entornoAMano(e: Entorno) {
  const v = Object.values(e.confianza ?? {});
  return v.length > 0 && v.every((x) => x === 1);
}

function Videos({ datos }: { datos: Datos }) {
  const { resultado, info, entorno } = datos;
  const sim = resultado.fuente === "simulado";
  const ent = resultado.entrenamiento;
  return (
    <>
      {entornoAMano(entorno) ? (
        <p className="aviso">
          <strong>Lugar de referencia.</strong> Su entorno lo escribimos a mano. En producción, VIAZ lo extrae de los videos
          que sube el cliente.
        </p>
      ) : (
        <p className="aviso">
          <strong>Medidas estimadas.</strong> El entorno sale de los frames del video, sin medición 3D: cada medida tiene
          su confianza (menor a 1).
        </p>
      )}
      {datos.construccion && (
        <figure className="figura">
          <figcaption>
            <strong>1 · El agente construye el robot</strong> <span className="etiqueta">simulación</span>
            <span className="tenue">
              {" "}{datos.clon.modelo
                ? "modelo publicado del robot para Isaac Lab, validado en la escena de esta corrida"
                : datos.clon.construccion?.metodo === "agente"
                  ? `${datos.clon.construccion.intentos} intento(s) hasta un robot válido en Isaac Lab`
                  : "el agente no lo logró: se usó el ensamblaje por defecto"}
            </span>
          </figcaption>
          <video className="video" src={datos.construccion} controls muted playsInline />
        </figure>
      )}
      {datos.rapido && (
        <figure className="figura">
          <figcaption>
            <strong>2 · El robot aprendiendo</strong> <span className="etiqueta">simulación</span>
            <span className="etiqueta etiqueta-tenue">cámara rápida</span>
            <span className="tenue">
              {" "}{info ? `${info.duracion_s.toFixed(0)} s de video = ${info.horas_representadas.toLocaleString("es-CL")} h de entrenamiento` : ""}
              {ent ? ` · ${ent.iteraciones.toLocaleString("es-CL")} iteraciones · ${ent.pasos.toLocaleString("es-CL")} pasos de simulación` : ""}
              {ent?.factor_video ? ` · ×${ent.factor_video.toLocaleString("es-CL")} más rápido` : ""}
            </span>
          </figcaption>
          <video className="video" src={datos.rapido} controls muted playsInline />
        </figure>
      )}
      {datos.video && (
        <figure className="figura">
          <figcaption>
            <strong>{resultado.metodo === "rl" ? "3 · El robot ya entrenado" : "El robot haciendo la tarea"}</strong>
            <span className="etiqueta">simulación</span>
            {resultado.metodo !== "rl" && <span className="etiqueta etiqueta-tenue">planificador, sin RL</span>}
          </figcaption>
          <video className="video" src={datos.video} controls muted playsInline />
        </figure>
      )}
      {datos.tray && datos.urdf && <Visor entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} />}
      {sim && <p className="tenue">Resultado del entorno simulado de desarrollo: no es una corrida de Isaac.</p>}
    </>
  );
}

function Exito({ resultado, voc }: { resultado: Resultado; voc: Vocabulario }) {
  const ev = resultado.evaluacion;
  if (!ev) {
    const m = resultado.metricas;
    return (
      <dl className="metricas">
        <dt>{voc.logrados}</dt><dd>{m.paneles_instalados} / {m.intentos}</dd>
        <dt>Tasa de éxito</dt><dd>{Math.round(m.tasa_exito * 100)} %</dd>
        <dt>{voc.ciclo}</dt><dd>{m.ciclo_promedio_s} s</dd>
      </dl>
    );
  }
  // RF-WEB-16: la tasa de éxito siempre con su tolerancia y la cantidad de episodios.
  return (
    <>
      <dl className="metricas">
        {ev.tolerancias.map((t) => (
          <FilaTolerancia key={`${t.pos_m}-${t.ang_grados}`} t={t} conAngulo={voc.usaAngulo} />
        ))}
        <dt>{voc.ciclo}</dt><dd>{resultado.metricas.ciclo_promedio_s} s</dd>
      </dl>
      <p className="tenue">{ev.episodios} {voc.episodios}</p>
    </>
  );
}

function FilaTolerancia({ t, conAngulo }: { t: { pos_m: number; ang_grados: number; tasa_exito: number; exitos: number };
  conAngulo: boolean }) {
  return (
    <>
      <dt>Éxito a {Math.round(t.pos_m * 100)} cm{conAngulo ? ` y ${t.ang_grados}°` : ""}</dt>
      <dd>{Math.round(t.tasa_exito * 100)} % <span className="tenue">({t.exitos})</span></dd>
    </>
  );
}

function Panel({ datos }: { datos: Datos }) {
  const { robot, clon, resultado } = datos;
  return (
    <>
      <div className="tarjeta">
        <h3>{robot.nombre} {robot.ficticio && <span className="etiqueta">ficticio</span>}</h3>
        <p className="tenue">{robot.fabricante} · carga útil {robot.carga_util_kg} kg · alcance {robot.alcance_m} m</p>
        <p>{robot.justificacion}</p>
        {robot.fuente.url && <a href={robot.fuente.url} target="_blank" rel="noreferrer">Fuente ({robot.fuente.consultado})</a>}
        {robot.alternativas.length > 0 && (
          <details>
            <summary className="tenue">Alternativas descartadas ({robot.alternativas.length})</summary>
            <ul>{robot.alternativas.map((a) => <li key={a.id}><strong>{a.id}:</strong> {a.por_que_no}</li>)}</ul>
          </details>
        )}
      </div>
      <div className="tarjeta">
        <h3>Resultado {resultado.metodo === "rl" ? "del aprendizaje" : ""} <span className="etiqueta">simulación</span></h3>
        <Exito resultado={resultado} voc={vocabulario(datos.tarea?.tarea)} />
        <p className="tenue">{resultado.notas}</p>
      </div>
      <div className="tarjeta">
        <h3>Diferencias del clon con el robot real</h3>
        {clon.modelo && (
          <p className="tenue">Sin ensamblaje: el clon es el modelo publicado para Isaac Lab ({clon.modelo.cfg.split(":")[1]}).</p>
        )}
        {clon.construccion && clon.piezas && (
          <p className="tenue">
            {clon.construccion.metodo === "agente"
              ? `Construido por el agente en ${clon.construccion.intentos} intento(s): ${clon.piezas.brazo} + ${clon.piezas.efector} sobre ${clon.piezas.base}.`
              : "El agente no logró un robot válido: se usó el ensamblaje por defecto."}
          </p>
        )}
        <ul>{clon.diferencias_con_real.map((d) => <li key={d}>{d}</li>)}</ul>
      </div>
    </>
  );
}
