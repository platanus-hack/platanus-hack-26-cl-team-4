"use client";

// Realidad aumentada: la sala modelada de forma simple + un robot de servicio ANIMADO A MANO (no entrenado),
// y un humanoide que repite la grabación del movimiento de su política entrenada en Isaac Lab.
// model-viewer abre la cámara del celular: AR Quick Look en iPhone (USDZ) y Scene Viewer / WebXR en Android (GLB).
// El paquete autónomo de model-viewer se publica junto con los modelos de la sala.
import Script from "next/script";
import "./sala.css";
import { createElement, useEffect, useRef, useState } from "react";

// Sube este número al regenerar los modelos: obliga al celular a bajar los archivos nuevos y no usar los guardados.
const VERSION = 9;

// Primero va el modo principal: los robots a tamaño real en el lugar donde está la persona.
const MODELOS = {
  robot: {
    titulo: "En tu espacio",
    detalle: "Apunta al piso: aparecen 5 robots de verdad en este lugar, VIAZ escanea el espacio, elige uno y te trae el café.",
    glb: `/ar/robot.glb?v=${VERSION}`,
    usdz: `/ar/robot.usdz?v=${VERSION}`,
    orbita: "10deg 72deg auto",
    escalaFija: true,   // 1:1 con la sala real: no se agranda ni se achica con los dedos
    animacion: "entrega_cafe",
  },
  maqueta: {
    titulo: "Maqueta de la sala",
    detalle: "La sala virtualizada en miniatura, para ver sobre una mesa: los 5 robots, el escaneo y la entrega del café.",
    glb: `/ar/maqueta.glb?v=${VERSION}`,
    usdz: `/ar/maqueta.usdz?v=${VERSION}`,
    orbita: "35deg 60deg auto",
    escalaFija: false,
    animacion: "entrega_cafe",
  },
  entrenado: {
    titulo: "Robot entrenado",
    detalle: "Apunta al piso: un robot humanoide baila a tamaño real con el movimiento que aprendió en la simulación de VIAZ.",
    glb: `/ar/robot_entrenado.glb?v=${VERSION}`,
    usdz: `/ar/robot_entrenado.usdz?v=${VERSION}`,
    orbita: "20deg 80deg 6.5m",   // lejos: el robot se desplaza al bailar y con "auto" los pies salen del cuadro
    escalaFija: true,
    animacion: "anima_la_fiesta",
  },
} as const;

type Clave = keyof typeof MODELOS;

export default function PaginaSala() {
  const [modo, setModo] = useState<Clave>("robot");
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
      <Script type="module" src="/ar/vendor/model-viewer-4.0.0.min.js" />
      <header>
        <h2>Experimenten el cambio</h2>
        <p className="tenue">Abran la cámara y miren este mismo lugar con robots trabajando en él.</p>
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
          "ar-scale": m.escalaFija ? "fixed" : "auto",
          "camera-controls": true,
          "touch-action": "pan-y",
          autoplay: true,
          "animation-name": m.animacion,
          "shadow-intensity": "1",
          "camera-orbit": m.orbita,
          exposure: "1.1",
          class: "ar-visor",
        },
        createElement("button", { slot: "ar-button", className: "ar-boton" }, "Ver en tu espacio"),
      )}

      {modo === "entrenado" ? (
        <p className="aviso">
          <strong>Grabación.</strong> El movimiento es una grabación de la política entrenada en la simulación de VIAZ, sin
          retoques. La política no corre en el celular, y en este modo la sala no aparece.
        </p>
      ) : (
        <p className="aviso">
          <strong>Concepto.</strong> La sala está modelada de forma simple a partir del video (medidas aproximadas). Los robots y la
          elección están animados a mano: no están entrenados ni salen de la simulación de VIAZ.
        </p>
      )}
      <p className="tenue">
        Funciona en iPhone (Safari) y en Android con ARCore (Chrome). En computador se ve en 3D, sin realidad aumentada.
      </p>
    </section>
  );
}
