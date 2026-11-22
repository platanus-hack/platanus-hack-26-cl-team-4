"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useRef, useState, type ReactNode } from "react";
import type { Datos } from "@/lib/datos";

const Lienzo = dynamic(() => import("@/components/Visor").then((m) => m.LienzoPortada), { ssr: false });

const pasos = ["El parque", "El entorno", "La maniobra", "El visor"];

export class RespaldoLienzo extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };

  static getDerivedStateFromError() { return { error: true }; }

  render() { return this.state.error ? null : this.props.children; }
}

export function EscenaSolar({ datos }: { datos: Datos | null }) {
  const seccion = useRef<HTMLElement>(null);
  const marco = useRef<HTMLDivElement>(null);
  const progreso = useRef(0);
  const fotogramaEscaneo = useRef(.43);
  const pasoActual = useRef(0);
  const [paso, setPaso] = useState(0);
  const [animar, setAnimar] = useState(false);
  const [visible, setVisible] = useState(false);
  const [escaneoAbierto, setEscaneoAbierto] = useState(false);

  useEffect(() => {
    const elemento = seccion.current;
    if (!elemento) return;
    const apto = window.matchMedia("(min-width: 701px) and (min-height: 561px) and (prefers-reduced-motion: no-preference)");
    let cuadro = 0;

    function medir() {
      cuadro = 0;
      if (!elemento) return;
      const rect = elemento.getBoundingClientRect();
      const recorrido = Math.max(1, rect.height - (marco.current?.offsetHeight ?? window.innerHeight));
      const valor = apto.matches ? Math.max(0, Math.min(1, -rect.top / recorrido)) : 0;
      progreso.current = valor;
      elemento.style.setProperty("--progreso", String(valor));
      elemento.style.setProperty("--revelado", String(Math.min(1, Math.max(0, (valor - .13) / .20))));
      const siguiente = valor < .25 ? 0 : valor < .55 ? 1 : valor < .9 ? 2 : 3;
      if (pasoActual.current !== siguiente) {
        pasoActual.current = siguiente;
        setPaso(siguiente);
      }
    }

    function programar() {
      if (!cuadro) cuadro = window.requestAnimationFrame(medir);
    }

    function adaptar() {
      setAnimar(apto.matches);
      programar();
    }

    function leerDestino() {
      setEscaneoAbierto(window.location.hash === "#escaneo");
    }

    leerDestino();
    window.addEventListener("hashchange", leerDestino);
    const observador = new IntersectionObserver(([entrada]) => setVisible(entrada.isIntersecting));
    observador.observe(elemento);
    adaptar();
    window.addEventListener("scroll", programar, { passive: true });
    window.addEventListener("resize", programar);
    apto.addEventListener("change", adaptar);

    return () => {
      window.cancelAnimationFrame(cuadro);
      window.removeEventListener("hashchange", leerDestino);
      observador.disconnect();
      window.removeEventListener("scroll", programar);
      window.removeEventListener("resize", programar);
      apto.removeEventListener("change", adaptar);
    };
  }, []);

  return (
    <section ref={seccion} className="portada-viaz" id="escena-solar" aria-labelledby="t-escena-solar" data-paso={paso}>
      <div ref={marco} className="portada-marco">
        <div className="portada-imagen" aria-hidden="true" />
        {animar && visible && datos && (
          <div className="portada-lienzo" aria-hidden="true">
            <RespaldoLienzo>
              <Lienzo entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} progreso={progreso} />
            </RespaldoLienzo>
          </div>
        )}
        <div className="portada-sombra" aria-hidden="true" />
        <div className="portada-barrido" aria-hidden="true" />

        <div className="portada-contenido">
          <div className="portada-capitulo" data-vigente={paso === 0}>
            <p className="rotulo-viaz">Instalación solar</p>
            <h2 id="t-escena-solar">Un robot para instalar paneles.</h2>
            <p className="portada-bajada">Recorre la escena de referencia, desde el parque hasta la primera maniobra del brazo.</p>
            <div className="portada-acciones">
              <a className="boton-viaz" href="#escaneo">Ver escaneo 3D <span aria-hidden="true">&#8595;</span></a>
              <a className="enlace-viaz" href="#visor-solar">Abrir visor <span aria-hidden="true">&#8599;</span></a>
            </div>
          </div>
          <div className="portada-capitulo portada-capitulo-secundario" data-vigente={paso === 1}>
            <p className="rotulo-viaz">Entorno 3D</p>
            <h2>Del parque al entorno de trabajo.</h2>
            <p className="portada-bajada">La trama de puntos revela la forma del brazo antes de que tome el primer panel.</p>
          </div>
          <div className="portada-capitulo portada-capitulo-secundario" data-vigente={paso === 2}>
            <p className="rotulo-viaz">Trayectoria planificada</p>
            <h2>Una maniobra, de principio a fin.</h2>
            <p className="portada-bajada">El brazo toma un panel, lo traslada y lo coloca sobre el tracker.</p>
          </div>
          <div className="portada-capitulo portada-capitulo-secundario" data-vigente={paso === 3}>
            <p className="rotulo-viaz">Demo interactiva</p>
            <h2>Toma el control del visor.</h2>
            <p className="portada-bajada">Cambia el ángulo, recorre la trayectoria y revisa los resultados.</p>
            <div className="portada-acciones">
              <a className="boton-viaz" href="#visor-solar">Abrir visor <span aria-hidden="true">↗</span></a>
            </div>
          </div>
        </div>

        <div className="portada-pie" aria-hidden="true">
          <span>{paso === 0 ? "Desplázate para explorar" : pasos[paso]}</span>
          <div className="portada-progreso"><div /></div>
          <span>0{paso + 1} / 04</span>
        </div>
      </div>
      <div id="escaneo" className="portada-destino-escaneo" tabIndex={-1} aria-label="Escaneo del robot">
        {!animar && (
          <div className="portada-escaneo-fijo">
            <h2>Escaneo del robot</h2>
            {escaneoAbierto && visible && datos && (
              <div className="portada-escaneo-visor" aria-hidden="true">
                <RespaldoLienzo>
                  <Lienzo entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf} progreso={fotogramaEscaneo} fijo />
                </RespaldoLienzo>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
