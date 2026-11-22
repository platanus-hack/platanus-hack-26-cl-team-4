"use client";

import { useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";

import VisualPaso from "@/components/VisualPaso";
import { FLUJO } from "@/lib/flujo";

const ultimo = FLUJO.length - 1;
const destino = (indice: number) => `#paso-${indice + 1}`;

function pasoDelEnlace() {
  const coincidencia = /^#paso-(\d+)$/.exec(window.location.hash);
  if (!coincidencia) return null;
  const indice = Number(coincidencia[1]) - 1;
  return indice >= 0 && indice <= ultimo ? indice : null;
}

export default function FlujoHorizontal() {
  const seccion = useRef<HTMLElement>(null);
  const marco = useRef<HTMLDivElement>(null);
  const lista = useRef<HTMLOListElement>(null);
  const indiceActual = useRef(0);
  const irAPaso = useRef<((indice: number, animar: boolean) => void) | null>(null);
  const [activo, setActivo] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const elementos = [seccion.current, marco.current, lista.current] as const;
    if (!elementos[0] || !elementos[1] || !elementos[2]) return;
    const [bloque, fija, pista] = elementos;

    const anclar = window.matchMedia("(min-width: 801px) and (min-height: 600px) and (prefers-reduced-motion: no-preference)");
    const movimientoReducido = window.matchMedia("(prefers-reduced-motion: reduce)");
    let cuadro = 0;

    const recorrido = () => Math.max(1, bloque.offsetHeight - fija.offsetHeight);

    function medir() {
      cuadro = 0;
      let paso: number;
      if (anclar.matches) {
        const progreso = Math.min(1, Math.max(0, -bloque.getBoundingClientRect().top / recorrido()));
        paso = progreso * ultimo;
        const completo = Math.floor(paso);
        // Reservar parte del desplazamiento para leer cada paso sin que se mueva.
        const mezcla = Math.min(1, Math.max(0, (paso - completo - .24) / .52));
        const curva = mezcla * mezcla * (3 - 2 * mezcla);
        pista.scrollLeft = (completo + curva) * pista.clientWidth;
      } else {
        paso = pista.scrollLeft / Math.max(1, pista.clientWidth);
      }
      const indice = Math.min(ultimo, Math.max(0, Math.round(paso)));
      if (indice === indiceActual.current) return;
      indiceActual.current = indice;
      setActivo(indice);
    }

    function programar() {
      if (!cuadro) cuadro = window.requestAnimationFrame(medir);
    }

    function mover(indice: number, animar: boolean) {
      const behavior = animar && !movimientoReducido.matches ? "smooth" : "instant";
      if (anclar.matches) {
        const inicio = window.scrollY + bloque.getBoundingClientRect().top;
        window.scrollTo({ top: inicio + recorrido() * indice / ultimo, behavior });
      } else {
        pista.scrollTo({ left: pista.clientWidth * indice, behavior });
      }
      programar();
    }

    function leerEnlace() {
      const indice = pasoDelEnlace();
      if (indice !== null) mover(indice, false);
      else if (window.location.hash === "#flujo" && !anclar.matches) mover(0, false);
    }

    function adaptar() {
      bloque.dataset.anclado = String(anclar.matches);
      if (!anclar.matches) pista.scrollLeft = pista.clientWidth * indiceActual.current;
      leerEnlace();
      programar();
    }

    const observador = new IntersectionObserver(([entrada]) => setVisible(entrada.isIntersecting), { threshold: .25 });
    observador.observe(fija);
    irAPaso.current = mover;
    adaptar();
    anclar.addEventListener("change", adaptar);
    window.addEventListener("hashchange", leerEnlace);
    window.addEventListener("scroll", programar, { passive: true });
    window.addEventListener("resize", programar);
    pista.addEventListener("scroll", programar, { passive: true });

    return () => {
      irAPaso.current = null;
      observador.disconnect();
      window.cancelAnimationFrame(cuadro);
      anclar.removeEventListener("change", adaptar);
      window.removeEventListener("hashchange", leerEnlace);
      window.removeEventListener("scroll", programar);
      window.removeEventListener("resize", programar);
      pista.removeEventListener("scroll", programar);
    };
  }, []);

  function navegar(indice: number, evento?: MouseEvent<HTMLAnchorElement>) {
    if (!irAPaso.current || (evento && (evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey))) return;
    evento?.preventDefault();
    if (window.location.hash !== destino(indice)) window.history.pushState(null, "", destino(indice));
    irAPaso.current(indice, true);
  }

  const anterior = activo - 1;
  const siguiente = activo + 1;

  return (
    <section ref={seccion} className="pitch-horizontal" id="flujo" tabIndex={-1} aria-labelledby="t-flujo">
      <div className="pitch-destinos" aria-hidden="true">
        {FLUJO.map((p, i) => (
          <span key={p.nombre} id={destino(i).slice(1)} style={{ "--paso-posicion": i / ultimo } as CSSProperties} />
        ))}
      </div>
      <div
        ref={marco}
        className="pitch-horizontal-marco"
        onKeyDown={(evento) => {
          if (evento.altKey || evento.ctrlKey || evento.metaKey || evento.shiftKey) return;
          if (evento.key !== "ArrowLeft" && evento.key !== "ArrowRight") return;
          const indice = evento.key === "ArrowLeft" ? anterior : siguiente;
          if (indice < 0 || indice > ultimo) return;
          evento.preventDefault();
          navegar(indice);
        }}
      >
        <div className="bloque pitch-horizontal-cabecera">
          <h2 className="rotulo-viaz" id="t-flujo">Cómo funciona</h2>
          <nav className="pitch-indice" aria-label="Elegir paso del proceso">
            {FLUJO.map((p, i) => (
              <a
                key={p.nombre}
                href={destino(i)}
                aria-label={`Paso ${i + 1}. ${p.nombre}`}
                aria-current={activo === i ? "step" : undefined}
                onClick={(evento) => navegar(i, evento)}
              >
                {String(i + 1).padStart(2, "0")}
              </a>
            ))}
          </nav>
        </div>
        <ol className="pitch-flujo" role="list" ref={lista}>
          {FLUJO.map((p, i) => (
            <li className="pitch-paso" key={p.nombre} data-vigente={visible && activo === i}>
              <div className="bloque pitch-contenido">
                <div>
                  <h3 className="pitch-titulo">{p.nombre}</h3>
                  <p className="pitch-texto">{p.hace}</p>
                  <dl className="pitch-resumen pitch-datos-paso">
                    <div><dt>Responsable</dt><dd>{p.quien}</dd></div>
                    <div><dt>Entrega</dt><dd>{p.produce}</dd></div>
                  </dl>
                </div>
                <VisualPaso indice={i} />
              </div>
            </li>
          ))}
        </ol>
        <nav className="bloque pitch-navegacion pitch-horizontal-controles" aria-label="Avanzar o retroceder entre pasos">
          <a href={anterior >= 0 ? destino(anterior) : "#problema"} onClick={anterior >= 0 ? (e) => navegar(anterior, e) : undefined}>
            <span aria-hidden="true">{anterior >= 0 ? "←" : "↑"}</span> {anterior >= 0 ? "Anterior" : "El desafío"}
          </a>
          <a
            href={siguiente <= ultimo ? destino(siguiente) : "#evaluacion"}
            onClick={siguiente <= ultimo ? (e) => navegar(siguiente, e) : undefined}
            aria-label={siguiente <= ultimo ? `Siguiente paso. ${FLUJO[siguiente].nombre}` : undefined}
          >
            {siguiente <= ultimo ? "Siguiente" : "Ir a la evaluación"} <span aria-hidden="true">{siguiente <= ultimo ? "→" : "↓"}</span>
          </a>
        </nav>
      </div>
    </section>
  );
}
