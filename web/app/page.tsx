"use client";

// Portada = corrida del demo precalculada (RF-WEB-08). Lee web/public/demo: no depende de la API ni del pod.
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import Resultados from "@/components/Resultados";
import { cargarDemo, type Datos } from "@/lib/datos";
import { numero } from "@/lib/formato";

const Visor = dynamic(() => import("@/components/Visor"), {
  ssr: false,
  loading: () => <div className="visor-cargando">Cargando la planta en 3D…</div>,
});

export default function Inicio() {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cargarDemo().then(setDatos).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <>
      <section className="hero" aria-labelledby="t-hero">
        <div className="hero-texto">
          <h1 id="t-hero">Un robot real instalando paneles en tu planta, antes de comprarlo.</h1>
          {datos && <p className="hero-bajada">{bajada(datos)}</p>}
        </div>
        <div className="hero-visor">
          {datos ? (
            <Visor entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} descripcion={bajada(datos)} />
          ) : error ? (
            <div className="visor-cargando" role="alert">
              No se pudo cargar la planta de demostración ({error}). Genérala con <code>python -m viaz.demo</code>.
            </div>
          ) : (
            <div className="visor-cargando">Cargando la planta en 3D…</div>
          )}
        </div>
      </section>

      {datos && <Resultados datos={datos} />}

      <section className="bloque" aria-labelledby="t-pasos">
        <h2 id="t-pasos" className="titulo-seccion">Cómo se arma este demo</h2>
        <ol className="pasos">
          <li>
            <h3>Virtualizar la planta</h3>
            <p>Un agente mide la planta en los videos: filas, estructuras y paneles. Con eso genera la escena 3D con física.</p>
          </li>
          <li>
            <h3>Elegir el robot</h3>
            <p>Otro agente compara la tarea con un catálogo de robots que ya se venden y justifica cuál calza mejor.</p>
          </li>
          <li>
            <h3>Clonar el robot</h3>
            <p>Se arma un modelo simulado con el alcance, la carga útil y las masas del robot real.</p>
          </li>
          <li>
            <h3>Entrenar en Isaac Lab</h3>
            <p>El manipulador aprende a dejar el panel sobre el tubo, con miles de intentos en paralelo en una GPU.</p>
          </li>
          <li>
            <h3>Medir y mostrar</h3>
            <p>Se mide cuántos paneles quedan bien puestos y se graba el resultado que ves en esta página.</p>
          </li>
        </ol>
      </section>
    </>
  );
}

function bajada(d: Datos) {
  const f = d.entorno.filas;
  const p = d.entorno.panel;
  const n = d.tray.paneles.length;
  return `Parque solar de demostración: ${f.cantidad} filas de trackers de ${numero(f.largo_m, 0)} m. ` +
    `El robot lleva ${n} paneles de ${numero(p.peso_kg, 0)} kg y los deja sobre el tubo de la primera fila.`;
}
