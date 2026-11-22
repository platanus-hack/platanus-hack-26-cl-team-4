import type { Etapa } from "@/lib/tipos";

const NOMBRES: Record<Etapa["nombre"], string> = {
  entorno: "Entorno del lugar",
  tarea: "Definir la tarea",
  robot: "Elegir el robot real",
  clon: "Construir el robot (Isaac Lab)",
  inteligencia: "Entrenar con RL (Isaac Lab)",
};

const ICONOS: Record<Etapa["estado"], string> = { pendiente: "○", en_curso: "◐", listo: "●", error: "✕" };

export default function Etapas({ etapas }: { etapas: Etapa[] }) {
  return (
    <ol className="etapas">
      {etapas.map((e) => (
        <li key={e.nombre} className={`etapa etapa-${e.estado}`}>
          <span className="icono" aria-hidden>{ICONOS[e.estado]}</span>
          <span>{NOMBRES[e.nombre]}</span>
          <span className="estado">{e.estado.replace("_", " ")}</span>
        </li>
      ))}
    </ol>
  );
}
