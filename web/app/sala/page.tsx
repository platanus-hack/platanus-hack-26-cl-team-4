"use client";

// Realidad aumentada: la sala modelada de forma simple + un robot de servicio ANIMADO A MANO (no entrenado).
// model-viewer abre la cámara del celular: AR Quick Look en iPhone (USDZ) y Scene Viewer / WebXR en Android (GLB).
// Se carga desde el CDN oficial porque trae su propia versión de three.js (la del visor 3D del proyecto es otra).
import Script from "next/script";
import { createElement, useEffect, useRef, useState } from "react";

const MODELOS = {
  maqueta: {
    titulo: "Maqueta de la sala",
    detalle: "Ponla sobre una mesa: aparecen 5 robots, VIAZ escanea la sala, elige el adecuado y este reparte café por el pasillo.",
    glb: "/ar/maqueta.glb",
    usdz: "/ar/maqueta.usdz",
    orbita: "35deg 60deg 1.1m",
  },
  robot: {
    titulo: "Robot a tamaño real",
    detalle: "Apunta al piso: aparecen 5 robots en tu espacio, VIAZ escanea el lugar, elige uno y te trae el café.",
    glb: "/ar/robot.glb",
    usdz: "/ar/robot.usdz",
    orbita: "20deg 75deg 4m",
  },
} as const;

type Clave = keyof typeof MODELOS;

export default function PaginaSala() {
  const [modo, setModo] = useState<Clave>("maqueta");
  const [puedeAR, setPuedeAR] = useState<boolean | null>(null);
  const visor = useRef<HTMLElement & { canActivateAR?: boolean; activateAR?: () => void }>(null);
  const m = MODELOS[modo];

  // model-viewer decide si este celular y navegador pueden abrir la cámara en AR.
  useEffect(() => {
    const id = setInterval(() => {
      const v = visor.current;
      if (v && customElements.get("model-viewer") && (v as unknown as { loaded?: boolean }).loaded) {
        setPuedeAR(Boolean(v.canActivateAR));
        clearInterval(id);
      }
    }, 300);
    return () => clearInterval(id);
  }, [modo]);
  return (
    <section className="ar">
      <Script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js" />
      <header>
        <h2>Experimenten el cambio</h2>
        <p className="tenue">Virtualizamos esta sala con un video de celular. Ahora véanla con un robot trabajando, en su propio espacio.</p>
      </header>

      <div className="ar-modos" role="tablist">
        {(Object.keys(MODELOS) as Clave[]).map((k) => (
          <button key={k} role="tab" aria-selected={modo === k} className={modo === k ? "activo" : ""} onClick={() => setModo(k)}>
            {MODELOS[k].titulo}
          </button>
        ))}
      </div>
      <p className="tenue">{m.detalle}</p>

      {puedeAR && (
        <button className="ar-camara" onClick={() => visor.current?.activateAR?.()}>📷 Abrir la cámara</button>
      )}
      {puedeAR === false && (
        <p className="aviso">
          Este navegador no puede abrir la cámara en AR. En Android, ábrelo en <strong>Chrome</strong> y revisa que esté instalado
          <strong> Servicios de Google Play para RA</strong> (Play Store). En iPhone, ábrelo en <strong>Safari</strong>. En computador
          solo se ve en 3D.
        </p>
      )}

      {createElement(
        "model-viewer",
        {
          key: modo,
          ref: visor,
          src: m.glb,
          "ios-src": m.usdz,
          alt: m.titulo,
          ar: true,
          "ar-modes": "webxr scene-viewer quick-look",
          "ar-placement": "floor",
          "camera-controls": true,
          "touch-action": "pan-y",
          autoplay: true,
          "animation-name": "entrega_cafe",
          "shadow-intensity": "1",
          "camera-orbit": m.orbita,
          exposure: "1.1",
          class: "ar-visor",
        },
        createElement("button", { slot: "ar-button", className: "ar-boton" }, "Ver en tu espacio"),
      )}

      <p className="aviso">
        <strong>Concepto.</strong> La sala está modelada de forma simple a partir del video (medidas aproximadas). Los robots y la
        elección están animados a mano: no están entrenados ni salen de la simulación de VIAZ.
      </p>
      <p className="tenue">
        Funciona en iPhone (Safari) y en Android con ARCore (Chrome). En computador se ve en 3D, sin realidad aumentada.
      </p>
    </section>
  );
}
