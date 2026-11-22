"use client";

// El demo lee web/public/demo: no depende de la API ni del pod (RF-WEB-08).
import dynamic from "next/dynamic";
import Image from "next/image";
import Link from "next/link";
import { preload } from "react-dom";
import { useCallback, useEffect, useRef, useState } from "react";

import { RespaldoLienzo } from "@/components/Portada";
import LineasPortada from "@/components/LineasPortada";
import QrSala from "@/components/QrSala";
import VideoDemoSolar, { type FuenteVideoDemoSolar } from "@/components/VideoDemoSolar";
import { cargarDemo, type Datos } from "@/lib/datos";
import { numero } from "@/lib/formato";
import { modeloPortadaUrl } from "@/lib/modelo-portada";

const ModeloPortada = dynamic(() => import("@/components/BrazoPortada"));

const ResultadosDemo = dynamic(() => import("@/components/Resultados"));

const Visor = dynamic(() => import("@/components/Visor"), {
  ssr: false,
  loading: () => <div className="visor-cargando">Cargando la planta en 3D…</div>,
});

export default function Inicio() {
  const presentacion = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const pagina = presentacion.current;
    if (!pagina) return;
    const pantallas = Array.from(pagina.querySelectorAll<HTMLElement>("[data-diapositiva]"));
    const mapas = pantallas.filter((pantalla) => pantalla.classList.contains("pitch-parada"));

    function pantallaSiguiente(haciaAbajo: boolean) {
      return haciaAbajo
        ? pantallas.find((pantalla) => pantalla.getBoundingClientRect().top > 8)
        : pantallas.findLast((pantalla) => pantalla.getBoundingClientRect().top < -8);
    }

    function avanzar(evento: KeyboardEvent) {
      if (evento.defaultPrevented || evento.altKey || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
      const haciaAbajo = evento.key === "ArrowDown" || evento.key === "PageDown";
      if (!haciaAbajo && evento.key !== "ArrowUp" && evento.key !== "PageUp") return;
      if (getComputedStyle(document.documentElement).scrollSnapType === "none") return;
      if (evento.target instanceof HTMLElement && evento.target.closest("input, textarea, select, [contenteditable]")) return;

      const destino = pantallaSiguiente(haciaAbajo);
      evento.preventDefault();
      destino?.focus({ preventScroll: true });
      destino?.scrollIntoView({ behavior: "instant", block: "start" });
    }

    let ultimoGiro = 0;
    let sentidoGiro = 0;
    let distanciaGiro = 0;
    let avanzoConGiro = false;

    function avanzarMapasConRueda(evento: WheelEvent) {
      if (evento.defaultPrevented || !evento.cancelable || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
      const { deltaMode, deltaX, deltaY } = evento;
      if (!deltaY || Math.abs(deltaX) > Math.abs(deltaY)) return;

      const tiempo = performance.now();
      const sentido = Math.sign(deltaY);
      if (sentido !== sentidoGiro || tiempo - ultimoGiro > 200) {
        distanciaGiro = 0;
        avanzoConGiro = false;
      }

      if (!avanzoConGiro && !mapas.some((mapa) => Math.abs(mapa.getBoundingClientRect().top) <= 8)) return;
      if (getComputedStyle(document.documentElement).scrollSnapType === "none") return;

      evento.preventDefault();
      ultimoGiro = tiempo;
      sentidoGiro = sentido;
      if (avanzoConGiro) return;

      const escala = deltaMode === WheelEvent.DOM_DELTA_LINE ? 16
        : deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1;
      distanciaGiro += Math.abs(deltaY) * escala;
      if (distanciaGiro < 112) return;

      // El resto del gesto pertenece al mismo avance, incluida la inercia del trackpad.
      avanzoConGiro = true;
      pantallaSiguiente(sentido > 0)?.scrollIntoView({ behavior: "instant", block: "start" });
    }

    window.addEventListener("keydown", avanzar);
    window.addEventListener("wheel", avanzarMapasConRueda, { passive: false });
    return () => {
      window.removeEventListener("keydown", avanzar);
      window.removeEventListener("wheel", avanzarMapasConRueda);
    };
  }, []);

  return (
    <div ref={presentacion} className="inicio-viaz">
      <Apertura />
      <PortadaIndustrial />
      <DesafioYSolucion />
      <CasoSolar />
      <Cierre />
    </div>
  );
}

function useSeccionVisible(umbral = 0) {
  const seccion = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const elemento = seccion.current;
    if (!elemento) return;
    const observador = new IntersectionObserver(([entrada]) => {
      setVisible(entrada.isIntersecting && entrada.intersectionRatio >= umbral);
    }, { threshold: umbral });
    observador.observe(elemento);
    return () => observador.disconnect();
  }, [umbral]);

  return { seccion, visible };
}

function Apertura() {
  const { seccion, visible } = useSeccionVisible();

  return (
    <section ref={seccion} className="apertura-viaz" data-diapositiva tabIndex={-1} aria-labelledby="t-apertura">
      <LineasPortada visible={visible} />
      <p id="t-apertura" className="apertura-viaz-nombre">
        <span className="sr">VIAZ</span>
        <span className="apertura-viaz-letras" aria-hidden="true">
          {Array.from("VIAZ", (letra, indice) => (
            <span key={letra} className="apertura-viaz-letra">
              <span style={{ animationDelay: (80 * indice) + "ms" }}>{letra}</span>
            </span>
          ))}
        </span>
      </p>
      <a href="#inicio" className="apertura-viaz-avanzar" aria-label="Ir a la portada">
        <span aria-hidden="true">↓</span>
      </a>
    </section>
  );
}

function PortadaIndustrial() {
  preload(modeloPortadaUrl, { as: "fetch", crossOrigin: "anonymous" });
  const { seccion, visible } = useSeccionVisible();
  const [listo, setListo] = useState(false);
  const mostrarModelo = useCallback(() => setListo(true), []);
  const [girar, setGirar] = useState(false);

  useEffect(() => {
    const movimiento = window.matchMedia("(prefers-reduced-motion: reduce)");
    const adaptarMovimiento = () => setGirar(!movimiento.matches);
    adaptarMovimiento();
    movimiento.addEventListener("change", adaptarMovimiento);
    return () => movimiento.removeEventListener("change", adaptarMovimiento);
  }, []);

  return (
    <section ref={seccion} id="inicio" className="portada-industrial" data-diapositiva tabIndex={-1} aria-labelledby="t-hero" data-modelo-3d={listo}>
      <LineasPortada visible={visible && listo} />
      <div className="portada-industrial-modelo" role={listo ? "img" : undefined} aria-label={listo ? "Brazo robótico KUKA KR 210 con una mitad metálica y otra en dígitos ámbar" : undefined}>
        <RespaldoLienzo>
          <ModeloPortada girar={girar && visible} listo={mostrarModelo} />
        </RespaldoLienzo>
      </div>
      <div className="portada-industrial-contenido">
        <h1 id="t-hero">El puente entre la industria y la <span lang="en">physical AI</span></h1>
        <p className="portada-bajada">
          Convierte los videos de tu planta en un entorno 3D para elegir un robot, entrenarlo en
          simulación y evaluar cómo haría el trabajo.
        </p>
      </div>
    </section>
  );
}

function DesafioYSolucion() {
  const { seccion: paradaSolucion, visible: solucionVisible } = useSeccionVisible(0.55);

  return (
    <section className="pitch-secuencia" data-solucion-visible={solucionVisible} aria-label="El desafío y la solución">
      <section id="problema" className="pitch-parada" data-diapositiva tabIndex={-1} aria-label="El desafío" />
      <section ref={paradaSolucion} id="solucion" className="pitch-parada" data-diapositiva tabIndex={-1} aria-label="La solución" />
      <div className="pitch-capitulo pitch-breve">
        <div className="bloque pitch-comparacion">
          <section className="pitch-panel pitch-panel-desafio" aria-labelledby="t-problema">
            <p className="rotulo-viaz">El desafío</p>
            <h2 id="t-problema" className="pitch-titulo">Un robot probado en otro entorno</h2>
            <figure className="pitch-pais pitch-pais-china">
              <figcaption>China</figcaption>
              <Image src="/viaz/china-puntos.svg" width={430} height={272} alt="Silueta punteada de China" unoptimized />
            </figure>
          </section>
          <svg className="pitch-conexion" viewBox="0 0 160 42" fill="none" aria-hidden="true" focusable="false">
            <path className="pitch-conexion-trazo" d="M3 32C57 32 70 10 131 10h23" pathLength="1" />
            <path className="pitch-conexion-punta" d="m146 3 8 7-8 7" />
          </svg>
          <section className="pitch-panel pitch-panel-solucion" aria-labelledby="t-solucion">
            <p className="rotulo-viaz">La solución</p>
            <h2 id="t-solucion" className="pitch-titulo">Pon el robot a prueba en una réplica virtual de alta fidelidad</h2>
            <figure className="pitch-pais pitch-pais-chile">
              <figcaption>Chile</figcaption>
              <Image
                src="/viaz/chile-atacama.svg"
                width={322}
                height={292}
                alt="Silueta punteada de Chile con el desierto de Atacama destacado"
                unoptimized
              />
            </figure>
          </section>
        </div>
        <NavegacionPitch clase="pitch-nav-desafio" anterior="#inicio" siguiente="#solucion" titulo="Ver solución" />
        <NavegacionPitch clase="pitch-nav-solucion" anterior="#problema" siguiente="#demo" titulo="Ver caso solar" />
      </div>
    </section>
  );
}

function NavegacionPitch({ anterior, siguiente, titulo, clase = "" }: {
  anterior: string;
  siguiente: string;
  titulo: string;
  clase?: string;
}) {
  return (
    <nav className={`bloque pitch-navegacion ${clase}`} aria-label="Navegación de la presentación">
      <a href={anterior}><span aria-hidden="true">↑</span> Anterior</a>
      <a href={siguiente}>{titulo} <span aria-hidden="true">↓</span></a>
    </nav>
  );
}

const etapasDemo: { id: string; titulo: string; video: FuenteVideoDemoSolar }[] = [
  {
    id: "demo-seleccion",
    titulo: "Selección del robot",
    video: {
      src: "/demo/agentes-seleccion-robot-3.5s.mp4",
      poster: "/demo/agentes-seleccion-robot-poster.webp",
      etiqueta: "los agentes comparando robots y eligiendo el Leapting MMR",
    },
  },
  {
    id: "demo-armado",
    titulo: "Armado",
    video: {
      src: "/demo/armado-robot-orden-original-720p.mp4",
      poster: "/demo/armado-robot-con-entorno-poster.webp",
      etiqueta: "armado del entorno desértico y del robot",
    },
  },
  {
    id: "demo-entrenamiento",
    titulo: "Entrenamiento",
    video: {
      src: "/demo/entrenamiento_cuatro_etapas_720p.mp4",
      poster: "/demo/entrenamiento_cuatro_etapas_poster.webp",
      etiqueta: "entrenamiento del robot en cuatro etapas",
      rotulos: ["Inicio", "Primer éxito", "50 % de éxito", "Umbral alcanzado"],
    },
  },
  {
    id: "visor-solar",
    titulo: "Instalación",
    video: {
      src: "/demo/vivo_real_6_paneles_bucle_720p.mp4",
      poster: "/demo/vivo_real_6_paneles_poster.webp",
      etiqueta: "la instalación de paneles solares",
    },
  },
];

function CasoSolar() {
  const [verTrayectoria, setVerTrayectoria] = useState(false);

  return (
    <section className="caso-solar demo pitch-demo" id="demo" tabIndex={-1} aria-labelledby="t-demo">
      {etapasDemo.map(({ id, titulo, video }) => (
        <section key={id} id={id} className="pitch-demo-etapa" data-diapositiva tabIndex={-1} aria-labelledby={`t-${id}`}>
          {id === "demo-seleccion" && (
            <header className="pitch-demo-cabecera">
              <p className="rotulo-viaz">Infraestructura en acción</p>
              <h2 id="t-demo" className="titulo-seccion">Instalación de paneles solares</h2>
              <p className="intro-seccion pitch-demo-resumen">
                De la selección del robot a la instalación en un megaparque solar simulado.
              </p>
            </header>
          )}
          <h3 id={`t-${id}`}>{titulo}</h3>
          <div className="pitch-demo-marco">
            <VideoDemoSolar {...video} />
          </div>
          {id === "visor-solar" && (
            <>
              <NavegacionPitch anterior="#demo-entrenamiento" siguiente="#cierre" titulo="Cierre" />
              <details className="pitch-demo-detalles" onToggle={(evento) => setVerTrayectoria(evento.currentTarget.open)}>
                <summary>Visor 3D y detalles de la trayectoria</summary>
                {verTrayectoria && <TrayectoriaSolar />}
              </details>
            </>
          )}
        </section>
      ))}
    </section>
  );
}

function TrayectoriaSolar() {
  const lienzo = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const elemento = lienzo.current;
    if (!elemento) return;
    let activa = true;
    const observador = new IntersectionObserver(([entrada]) => setVisible(entrada.isIntersecting));
    observador.observe(elemento);
    void import("@/components/Visor").catch(() => undefined);
    cargarDemo().then((d) => { if (activa) setDatos(d); }).catch((e: unknown) => {
      if (activa) setError(e instanceof Error ? e.message : String(e));
    });
    return () => {
      activa = false;
      observador.disconnect();
    };
  }, []);

  return (
    <>
      {datos?.resultado.fuente === "simulado" && (
        <p className="estado-demo-viaz">Trayectoria planificada</p>
      )}
      <div className="demo-visor" ref={lienzo}>
        {datos ? (
          <Visor
            entorno={datos.entorno}
            tray={datos.tray}
            urdf={datos.urdf}
            descripcion={descripcion(datos)}
            activo={visible}
            reproducirAlCargar={false}
            repetir={false}
            encuadrarTrayectoria
          />
        ) : error ? (
          <div className="visor-cargando" role="alert">No se pudo cargar el visor. {error}</div>
        ) : (
          <div className="visor-cargando" role="status">Preparando el visor 3D…</div>
        )}
      </div>
      {datos && <ResultadosDemo datos={datos} />}
    </>
  );
}

function Cierre() {
  return (
    <section className="bloque cierre pitch-cierre" id="cierre" data-diapositiva tabIndex={-1} aria-labelledby="t-cierre">
      <div>
        <h2 id="t-cierre" className="titulo-seccion">Pon un robot a prueba en un entorno simulado.</h2>
        <p>Nicolás Jara Castillo, Francisco Martinez y Joaquín Vila Ormazabal · Platanus Hack 26</p>
        <Link href="/probar" className="enlace" prefetch={false}>Ver cómo se sube una planta</Link>
      </div>
      <QrSala />
      <figure className="pitch-cierre-video">
        <VideoDemoSolar
          src="/demo/timelapse_baile_10s.mp4"
          poster="/demo/timelapse_baile_poster.jpg"
          etiqueta="entrenamiento del baile del robot humanoide"
        />
        <figcaption>De caerse a bailar: 13 minutos de entrenamiento en simulación</figcaption>
      </figure>
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
