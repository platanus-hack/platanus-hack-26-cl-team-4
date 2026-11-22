// Secciones de resultados de una corrida: métrica, ficha del robot, entrenamiento y diferencias.
// Requerimientos: RF-WEB-06, 07, 13, 14, 15, 16 y vocabulario ISO 8373 (RF-WEB-11).
import Curva from "@/components/Curva";
import type { Datos } from "@/lib/datos";
import { cantidadGrande, centimetros, duracion, numero, porcentaje } from "@/lib/formato";

const META_EXITO = 0.9; // docs/requerimientos.md: 90 % a 5 cm y 5°

const TIPO: Record<Datos["robot"]["tipo"], string> = {
  base_movil_brazo: "Robot móvil con manipulador",
  brazo_fijo: "Manipulador fijo",
  vehiculo_con_brazo: "Vehículo con manipulador",
};

export default function Resultados({ datos }: { datos: Datos }) {
  return (
    <>
      <section className="bloque bloque-doble" aria-labelledby="t-resultado">
        <Resultado datos={datos} />
        <FichaRobot datos={datos} />
      </section>
      <Entrenamiento datos={datos} />
      <section className="bloque" aria-labelledby="t-diferencias">
        <h2 id="t-diferencias" className="titulo-seccion">En qué se diferencia el clon del robot real</h2>
        <ul className="diferencias">
          {datos.clon.diferencias_con_real.map((d) => <li key={d}>{d}</li>)}
        </ul>
      </section>
    </>
  );
}

function Resultado({ datos }: { datos: Datos }) {
  const { resultado: r, tarea } = datos;
  const ev = r.evaluacion;
  const m = r.metricas;
  return (
    <div className="resultado">
      <h2 id="t-resultado" className="titulo-seccion">Resultado</h2>
      {ev ? (
        <p className="frase-metrica">
          {porcentaje(ev.tasa_exito)} de los paneles quedan en su lugar, a {centimetros(ev.tolerancia.pos_m)} y{" "}
          {numero(ev.tolerancia.ang_grados, 0)}° de tolerancia, en {ev.episodios} episodios.
        </p>
      ) : (
        <p className="frase-metrica">
          El plan instala {m.paneles_instalados} de {m.intentos} paneles, a {numero(m.ciclo_promedio_s)} s por panel.
        </p>
      )}
      <p className="nota-estado">
        {r.fuente === "simulado"
          ? "Sin física: es la trayectoria planificada. Todavía no se simula en Isaac Lab, así que no mide si el panel resbala o choca."
          : `Simulado con física en Isaac Lab. Meta de la tarea: ${tarea.objetivo.paneles} paneles a ${tarea.objetivo.ciclo_s} s por panel.`}
      </p>
      {datos.video ? (
        <video className="video" src={datos.video} controls muted playsInline preload="metadata"
          aria-label="El robot entrenado instalando paneles" />
      ) : (
        <p className="pendiente">
          El video del robot entrenado aparece aquí cuando el entrenamiento en Isaac Lab entregue <code>video.mp4</code>.
        </p>
      )}
    </div>
  );
}

function FichaRobot({ datos }: { datos: Datos }) {
  const r = datos.robot;
  return (
    <div className="ficha">
      <h2 className="titulo-seccion">Robot elegido</h2>
      <p className="ficha-nombre">
        {r.nombre}
        {r.ficticio && <span className="marca-ficticio">Robot de referencia ficticio</span>}
      </p>
      <p className="tenue">{r.fabricante}</p>
      <dl className="ficha-datos">
        <dt>Tipo</dt><dd>{TIPO[r.tipo]}</dd>
        <dt>Carga útil</dt><dd>{numero(r.carga_util_kg, 0)} kg</dd>
        <dt>Alcance del manipulador</dt><dd>{numero(r.alcance_m)} m</dd>
        <dt>Efector final</dt><dd>{r.efector === "ventosa" ? "Ventosa" : "Pinza"}</dd>
        <dt>Velocidad de la base</dt><dd>{numero(r.velocidad_base_m_s)} m/s</dd>
        <dt>Panel a instalar</dt><dd>{numero(datos.entorno.panel.peso_kg, 0)} kg</dd>
      </dl>
      <p className="justificacion">{r.justificacion}</p>
      {r.fuente.url ? (
        <a className="enlace" href={r.fuente.url} target="_blank" rel="noreferrer">
          Ficha del fabricante, consultada el {r.fuente.consultado}
        </a>
      ) : (
        <p className="tenue">Sin fuente externa: sus specs no salen de un fabricante.</p>
      )}
    </div>
  );
}

function Entrenamiento({ datos }: { datos: Datos }) {
  const e = datos.resultado.entrenamiento;
  return (
    <section className="bloque" aria-labelledby="t-entrenamiento">
      <h2 id="t-entrenamiento" className="titulo-seccion">Cómo aprendió: entrenamiento con RL en Isaac Lab</h2>
      {e ? (
        <div className="entrenamiento">
          <div>
            {datos.videoRapido ? (
              <video className="video" src={datos.videoRapido} controls muted playsInline preload="metadata"
                aria-label="Entrenamiento en cámara rápida" />
            ) : (
              <p className="pendiente">Falta el video acelerado del entrenamiento.</p>
            )}
            <p className="escala-video">
              Este video resume {duracion(e.tiempo_real_s)} de entrenamiento en una GPU:{" "}
              {cantidadGrande(e.pasos_sim)} pasos de simulación en {numero(e.num_entornos, 0)} entornos en paralelo.
            </p>
          </div>
          <Curva curva={e.curva} hitos={e.hitos} meta={META_EXITO} />
        </div>
      ) : (
        <p className="pendiente pendiente-grande">
          El entrenamiento todavía no corre en la GPU. Cuando termine, aquí aparecen el video en cámara rápida, la curva
          de aprendizaje con los avisos del agente monitor y la tasa de éxito.
        </p>
      )}
    </section>
  );
}
