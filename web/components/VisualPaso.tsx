import type { CSSProperties } from "react";

const capturas = ["Contexto", "Brazo", "Pinza"];
const criterios = ["Alcance", "Carga útil", "Entorno"];
const entregables = ["Trayectoria", "Video", "Métricas"];

function Captura() {
  return (
    <>
      <div className="visual-capturas">
        {capturas.map((nombre, i) => (
          <div key={nombre} style={{ "--orden": i } as CSSProperties}>
            <i />
            <span>{nombre}</span>
          </div>
        ))}
      </div>
      <div className="visual-linea"><i /></div>
    </>
  );
}

function Mapa() {
  return (
    <div className="visual-mapa">
      <i className="visual-mapa-zona zona-a" />
      <i className="visual-mapa-zona zona-b" />
      <i className="visual-mapa-zona zona-c" />
      <i className="visual-mapa-paso" />
      <i className="visual-mapa-scan" />
    </div>
  );
}

function Seleccion() {
  return (
    <div className="visual-criterios">
      {criterios.map((criterio, i) => (
        <div key={criterio} style={{ "--orden": i } as CSSProperties}>
          <span>{criterio}</span>
          <i /><i /><i />
        </div>
      ))}
    </div>
  );
}

function Gemelo() {
  return (
    <div className="visual-gemelo">
      <div className="visual-gemelo-brazo" />
      <i className="visual-gemelo-reticula" />
      <i className="visual-gemelo-medida medida-a" />
      <i className="visual-gemelo-medida medida-b" />
    </div>
  );
}

function Entrenamiento() {
  return (
    <div className="visual-ensayos">
      {Array.from({ length: 20 }, (_, i) => (
        <span key={i} style={{ "--orden": (i % 5) * 2 + Math.floor(i / 5) } as CSSProperties}><i /></span>
      ))}
    </div>
  );
}

function Evaluacion() {
  return (
    <>
      <div className="visual-trayectoria"><i /><i /><i /></div>
      <div className="visual-entregables">
        {entregables.map((nombre, i) => (
          <div key={nombre} style={{ "--orden": i } as CSSProperties}><i /><span>{nombre}</span></div>
        ))}
      </div>
    </>
  );
}

const visuales = [
  { titulo: "A partir de video", Contenido: Captura },
  { titulo: "Reconstrucción del entorno", Contenido: Mapa },
  { titulo: "Criterios de selección", Contenido: Seleccion },
  { titulo: "Modelo del robot", Contenido: Gemelo },
  { titulo: "Ensayos en paralelo", Contenido: Entrenamiento },
  { titulo: "Evidencia para revisar", Contenido: Evaluacion },
];

export default function VisualPaso({ indice }: { indice: number }) {
  const visual = visuales[indice];
  if (!visual) return null;
  const { Contenido } = visual;

  return (
    <figure className="visual-paso" aria-hidden="true">
      <figcaption>{visual.titulo}</figcaption>
      <div className="visual-lienzo"><Contenido /></div>
    </figure>
  );
}
