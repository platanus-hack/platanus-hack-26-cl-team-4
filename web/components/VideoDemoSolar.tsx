"use client";

import { useEffect, useRef, useState } from "react";

export type FuenteVideoDemoSolar = {
  src: string;
  etiqueta: string;
  poster?: string;
  original?: string;
  rotulos?: readonly [string, string, string, string];
};

function prepararVideo(video: HTMLVideoElement, src: string) {
  if (!video.getAttribute("src")) video.src = src;
}

function reproducirVideo(video: HTMLVideoElement, src: string) {
  prepararVideo(video, src);
  video.muted = true;
  void video.play().catch(() => {
    // Si el navegador exige una interacción, el botón queda disponible.
  });
}

export default function VideoDemoSolar({ src, etiqueta, poster, original, rotulos }: FuenteVideoDemoSolar) {
  const video = useRef<HTMLVideoElement>(null);
  const pausaManual = useRef(false);
  const [reproduciendo, setReproduciendo] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const elemento = video.current;
    if (!elemento) return;

    const movimiento = window.matchMedia("(prefers-reduced-motion: reduce)");
    let enPantalla = false;

    const actualizar = () => {
      if (!enPantalla || movimiento.matches || pausaManual.current) {
        elemento.pause();
      } else {
        reproducirVideo(elemento, src);
      }
    };

    const precarga = new IntersectionObserver(([entrada]) => {
      if (!entrada.isIntersecting || movimiento.matches) return;
      prepararVideo(elemento, src);
      precarga.disconnect();
    }, { rootMargin: "600px" });

    const visibilidad = new IntersectionObserver(([entrada]) => {
      enPantalla = entrada.intersectionRatio >= 0.25;
      actualizar();
    }, { threshold: 0.25 });

    precarga.observe(elemento);
    visibilidad.observe(elemento);
    movimiento.addEventListener("change", actualizar);
    return () => {
      precarga.disconnect();
      visibilidad.disconnect();
      movimiento.removeEventListener("change", actualizar);
      elemento.pause();
    };
  }, [src]);

  function alternar() {
    const elemento = video.current;
    if (!elemento) return;

    pausaManual.current = !elemento.paused;
    if (pausaManual.current) elemento.pause();
    else reproducirVideo(elemento, src);
  }

  return (
    <div className="pitch-demo-video">
      <video
        ref={video}
        loop
        muted
        playsInline
        preload="auto"
        poster={poster}
        aria-label={`Video de ${etiqueta}`}
        onPlay={() => setReproduciendo(true)}
        onPause={() => setReproduciendo(false)}
        onError={() => setError(true)}
      />
      {rotulos && (
        <ol className="pitch-demo-video-rotulos" aria-label="Etapas del entrenamiento">
          {rotulos.map((rotulo) => <li key={rotulo}>{rotulo}</li>)}
        </ol>
      )}
      {error ? (
        <a className="pitch-demo-video-control" href={original ?? src}>{original ? "Abrir video original" : "Abrir video"}</a>
      ) : (
        <button
          className="pitch-demo-video-control"
          type="button"
          onClick={alternar}
          aria-label={`${reproduciendo ? "Pausar" : "Reproducir"} video de ${etiqueta}`}
        >
          <span aria-hidden="true">{reproduciendo ? "Ⅱ" : "▶"}</span>
        </button>
      )}
    </div>
  );
}
