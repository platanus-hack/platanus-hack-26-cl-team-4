// La cadena de agentes del hero: una línea con 6 nodos. El amarillo marca los pasos que hace un agente de IA.
// Movimiento: la línea se dibuja una vez al cargar (CSS). Con prefers-reduced-motion aparece entera.
import { FLUJO } from "@/lib/flujo";

export default function Cadena() {
  return (
    <figure className="cadena" aria-labelledby="cadena-leyenda">
      <ol className="cadena-pasos">
        {FLUJO.map((p, i) => (
          <li key={p.nombre} className={p.agente ? "nodo nodo-agente" : "nodo"} style={{ "--i": i } as React.CSSProperties}>
            <span className="nodo-punto" aria-hidden />
            <span className="nodo-nombre">{p.nombre}</span>
            <span className="nodo-quien">{p.quien}</span>
          </li>
        ))}
      </ol>
      <figcaption id="cadena-leyenda" className="cadena-leyenda">
        <span className="leyenda-item"><span className="leyenda-punto leyenda-agente" aria-hidden /> Lo hace un agente de IA</span>
        <span className="leyenda-item"><span className="leyenda-punto" aria-hidden /> Lo hace una persona o la web</span>
      </figcaption>
    </figure>
  );
}
