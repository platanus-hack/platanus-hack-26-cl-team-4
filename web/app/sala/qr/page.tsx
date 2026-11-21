"use client";

// QR para imprimir: apunta a /sala en el mismo dominio donde está publicada la web.
import QRCode from "qrcode";
import { useEffect, useState } from "react";

export default function PaginaQR() {
  const [url, setUrl] = useState("");
  const [svg, setSvg] = useState("");
  useEffect(() => {
    const destino = `${window.location.origin}/sala`;
    setUrl(destino);
    QRCode.toString(destino, { type: "svg", margin: 1, width: 520, errorCorrectionLevel: "M" }).then(setSvg);
  }, []);
  return (
    <section className="qr">
      <h2>Experimenten el cambio</h2>
      <p>Escaneen para ver esta sala virtualizada, con un robot trayéndoles café.</p>
      <div className="qr-codigo" dangerouslySetInnerHTML={{ __html: svg }} />
      <p className="tenue">{url}</p>
    </section>
  );
}
