"use client";

// Diagnóstico de la AR: 3 versiones que agregan funciones de a una, abiertas directo en el visor del celular
// (AR Quick Look en iPhone, Scene Viewer en Android), sin model-viewer. Sirve para aislar qué rompe la AR.
import { useEffect, useState } from "react";

const VERSION = 4;
const PRUEBAS = [
  { n: 1, archivo: "prueba_base", titulo: "Base", que: "El robot solo, la versión que funcionó. Si esta falla, el problema no es el modelo (red, navegador o celular)." },
  { n: 2, archivo: "prueba_sin_escaneo", titulo: "5 robots", que: "Agrega los 5 robots y que aparezcan y desaparezcan (escala animada). Sin el muro de números." },
  { n: 3, archivo: "robot", titulo: "Completo", que: "Agrega el muro de números estilo Matrix (transparencia y brillo). Es la versión actual." },
];

export default function PaginaPrueba() {
  const [origen, setOrigen] = useState("");
  const [android, setAndroid] = useState(false);
  useEffect(() => {
    setOrigen(window.location.origin);
    setAndroid(/android/i.test(navigator.userAgent));
  }, []);

  const sceneViewer = (glb: string) =>
    `intent://arvr.google.com/scene-viewer/1.0?file=${encodeURIComponent(`${origen}/ar/${glb}.glb?v=${VERSION}`)}&mode=ar_only` +
    `#Intent;scheme=https;package=com.google.ar.core;action=android.intent.action.VIEW;end;`;

  return (
    <section className="ar">
      <h2>Diagnóstico de la realidad aumentada</h2>
      <p className="tenue">
        Prueben las 3 en orden y anoten qué pasa en cada una. La primera que falle nos dice qué la rompe.
      </p>
      {PRUEBAS.map((p) => (
        <div key={p.n} className="tarjeta">
          <h3>{p.n} · {p.titulo}</h3>
          <p className="tenue">{p.que}</p>
          {android ? (
            <a className="ar-camara" href={sceneViewer(p.archivo)}>📷 Abrir en AR (Android)</a>
          ) : (
            // iPhone: un enlace rel="ar" con una imagen adentro abre AR Quick Look directo.
            <a rel="ar" href={`/ar/${p.archivo}.usdz?v=${VERSION}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/ar/prueba_${p.n}.png`} alt={`Abrir la prueba ${p.n} en AR`} width={240} height={135} />
            </a>
          )}
        </div>
      ))}
      <div className="aviso">
        <strong>Para cada prueba, cuéntennos:</strong>
        <ol>
          <li>¿Se abrió la cámara?</li>
          <li>¿Aparecieron los robots apoyados en el piso, o flotando, hundidos o lejos?</li>
          <li>¿Se movían (la animación)?</li>
          <li>¿Se podían mover, girar o agrandar con los dedos?</li>
          <li>¿Se vio algo raro (un rectángulo negro o blanco, parpadeos)?</li>
        </ol>
      </div>
    </section>
  );
}
