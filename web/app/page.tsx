"use client";

// Portada = pitch de VIAZ (web/DISENO.md v2): la idea primero, el demo al final.
// El demo lee web/public/demo: no depende de la API ni del pod (RF-WEB-08).
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

import Cadena from "@/components/Cadena";
import Resultados from "@/components/Resultados";
import { cargarDemo, type Datos } from "@/lib/datos";
import { FLUJO, PRINCIPIOS, PROBLEMA } from "@/lib/flujo";
import { numero } from "@/lib/formato";

const Visor = dynamic(() => import("@/components/Visor"), {
  ssr: false,
  loading: () => <div className="visor-cargando">Cargando la planta en 3D…</div>,
});

export default function Inicio() {
  return (
    <>
      <Hero />
      <Problema />
      <Flujo />
      <Principios />
      <Demo />
      <Cierre />
    </>
  );
}

function Hero() {
  return (
    <section className="hero" aria-labelledby="t-hero">
      <div className="hero-texto">
        <h1 id="t-hero">Entrenamos la inteligencia de un robot real para tu planta, antes de que lo compres.</h1>
        <p className="hero-bajada">
          VIAZ es una cadena de agentes de IA: convierte los videos de una planta en un robot entrenado en
          simulación con NVIDIA Isaac Lab, y te muestra cómo trabajaría ahí.
        </p>
        <div className="hero-acciones">
          <a href="#demo" className="boton-principal">Ver el demo</a>
          <a href="#flujo" className="boton-secundario">Cómo funciona</a>
        </div>
      </div>
      <div className="hero-cadena">
        <Cadena />
      </div>
    </section>
  );
}

function Problema() {
  return (
    <section className="bloque" aria-labelledby="t-problema">
      <h2 id="t-problema" className="titulo-seccion">Los robots existen. Falta saber cómo trabajarían en tu planta.</h2>
      <ul className="hechos">
        {PROBLEMA.map((h) => (
          <li key={h.texto}>
            <p className="hecho-texto">{h.texto}</p>
            <p className="hecho-fuente">
              {h.url ? <a href={h.url} target="_blank" rel="noreferrer">{h.fuente}</a> : h.fuente}
            </p>
          </li>
        ))}
      </ul>
      <p className="remate">
        Una planta que nunca usó robots no sabe cuál le sirve ni cómo se movería en su terreno. Hoy, para saberlo,
        hay que comprar o arrendar el robot primero. VIAZ lo responde en simulación.
      </p>
    </section>
  );
}

function Flujo() {
  return (
    <section className="bloque" id="flujo" aria-labelledby="t-flujo">
      <h2 id="t-flujo" className="titulo-seccion">Cómo funciona</h2>
      <p className="intro-seccion">
        Seis pasos, de los videos al resultado. Cuatro los hace un agente de IA; una persona aprueba lo que
        cuesta horas de GPU.
      </p>
      <ol className="flujo">
        {FLUJO.map((p) => (
          <li key={p.nombre} className={p.agente ? "flujo-paso flujo-agente" : "flujo-paso"}>
            <h3>{p.nombre}</h3>
            <p className="flujo-quien">{p.quien}</p>
            <p>{p.hace}</p>
            <p className="flujo-produce">Entrega: {p.produce}</p>
          </li>
        ))}
      </ol>
      <p className="nota-flujo">
        En el demo, el entorno del parque de referencia se escribió a mano. En producción lo extrae el agente de
        mapeo desde los videos.
      </p>
    </section>
  );
}

function Principios() {
  return (
    <section className="bloque" aria-labelledby="t-principios">
      <h2 id="t-principios" className="titulo-seccion">Por qué confiar en el resultado</h2>
      <dl className="principios">
        {PRINCIPIOS.map((p) => (
          <div key={p.titulo}>
            <dt>{p.titulo}</dt>
            <dd>{p.texto}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Demo() {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cargarDemo().then(setDatos).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="demo" id="demo">
      <section className="bloque" aria-labelledby="t-demo">
        <h2 id="t-demo" className="titulo-seccion">El demo: un parque solar de referencia</h2>
        <p className="intro-seccion">{datos ? descripcion(datos) : "Cargando el parque de referencia…"}</p>
      </section>
      <div className="demo-visor">
        {datos ? (
          <Visor entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} descripcion={descripcion(datos)} />
        ) : error ? (
          <div className="visor-cargando" role="alert">
            No se pudo cargar el parque de referencia ({error}). Genéralo con <code>python -m viaz.demo</code>.
          </div>
        ) : (
          <div className="visor-cargando">Cargando la planta en 3D…</div>
        )}
      </div>
      {datos && <Resultados datos={datos} />}
    </div>
  );
}

function Cierre() {
  return (
    <section className="bloque cierre" aria-labelledby="t-cierre">
      <h2 id="t-cierre" className="titulo-seccion">Equipo</h2>
      <p>
        Nicolás Jara Castillo, Francisco Martinez y Joaquín Vila Ormazabal. Platanus Hack 26 Santiago, track
        Physical World.
      </p>
      <p>
        <Link href="/probar" className="enlace">Ver cómo se sube una planta</Link>
      </p>
    </section>
  );
}

function descripcion(d: Datos) {
  const f = d.entorno.filas;
  const p = d.entorno.panel;
  const n = d.tray.paneles.length;
  return `${f.cantidad} filas de trackers de ${numero(f.largo_m, 0)} m. El robot lleva ${n} paneles de ` +
    `${numero(p.peso_kg, 0)} kg y los deja sobre el tubo de la primera fila.`;
}
