"use client";

import { useEffect, useRef, useState } from "react";

function destinoSala() {
  const configurado = process.env.NEXT_PUBLIC_SALA_URL;
  if (configurado) {
    try {
      const url = new URL(configurado);
      if (url.protocol === "https:") return url;
    } catch {
      // La sala se resuelve en el dominio de la presentación si falta una URL HTTPS válida.
    }
  }
  return new URL("/sala", window.location.origin);
}

export default function QrSala() {
  const figura = useRef<HTMLElement>(null);
  const [imagen, setImagen] = useState<string | null>(null);
  const [destino, setDestino] = useState<URL | null>(null);

  useEffect(() => {
    const elemento = figura.current;
    if (!elemento) return;

    let activo = true;
    const observador = new IntersectionObserver(([entrada]) => {
      if (!entrada.isIntersecting) return;
      observador.disconnect();
      const url = destinoSala();
      setDestino(url);
      void import("qrcode")
        .then(({ default: QRCode }) => QRCode.toDataURL(url.href, { width: 720, margin: 4, errorCorrectionLevel: "M" }))
        .then((codigo) => { if (activo) setImagen(codigo); })
        .catch(() => undefined);
    }, { rootMargin: "400px" });
    observador.observe(elemento);

    return () => {
      activo = false;
      observador.disconnect();
    };
  }, []);

  return (
    <figure className="pitch-qr" ref={figura}>
      <div className="pitch-qr-cuadro">
        {imagen && <img src={imagen} width={360} height={360} alt="Código QR de la sala virtual del evento" />}
      </div>
      <figcaption>
        {destino?.protocol === "https:" ? (
          <a href={destino.href}>Escanea para abrir la sala virtual</a>
        ) : (
          <>Sala virtual{destino && <small>Vista previa local</small>}</>
        )}
      </figcaption>
    </figure>
  );
}
