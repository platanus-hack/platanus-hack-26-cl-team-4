// Curva de entrenamiento (RF-WEB-14): tasa de éxito por paso, con los hitos del monitor marcados.
import { cantidadGrande, porcentaje } from "@/lib/formato";

interface Props {
  curva: { paso: number; tasa_exito: number }[];
  hitos: { paso: number; texto: string }[];
  meta?: number; // tasa de éxito objetivo, línea horizontal
}

const W = 640, H = 240, M = { izq: 44, der: 12, arr: 12, aba: 28 };

export default function Curva({ curva, hitos, meta }: Props) {
  if (curva.length < 2) return null;
  const maxPaso = Math.max(...curva.map((p) => p.paso), ...hitos.map((h) => h.paso), 1);
  const x = (paso: number) => M.izq + (paso / maxPaso) * (W - M.izq - M.der);
  const y = (t: number) => M.arr + (1 - t) * (H - M.arr - M.aba);
  const linea = curva.map((p, i) => `${i ? "L" : "M"}${x(p.paso).toFixed(1)},${y(p.tasa_exito).toFixed(1)}`).join(" ");
  const ultima = curva[curva.length - 1];

  return (
    <figure className="curva">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Tasa de éxito durante el entrenamiento: termina en ${porcentaje(ultima.tasa_exito)} a los ${cantidadGrande(ultima.paso)} pasos`}>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={M.izq} x2={W - M.der} y1={y(t)} y2={y(t)} className="curva-grilla" />
            <text x={M.izq - 8} y={y(t) + 4} textAnchor="end" className="curva-eje">{porcentaje(t)}</text>
          </g>
        ))}
        {meta !== undefined && (
          <line x1={M.izq} x2={W - M.der} y1={y(meta)} y2={y(meta)} className="curva-meta" />
        )}
        {hitos.map((h) => (
          <line key={h.paso} x1={x(h.paso)} x2={x(h.paso)} y1={M.arr} y2={H - M.aba} className="curva-hito" />
        ))}
        <path d={linea} className="curva-linea" />
        <text x={W - M.der} y={H - 8} textAnchor="end" className="curva-eje">{cantidadGrande(maxPaso)} pasos</text>
        <text x={M.izq} y={H - 8} className="curva-eje">0</text>
      </svg>
      {hitos.length > 0 && (
        <ol className="hitos">
          {hitos.map((h) => (
            <li key={h.paso}>
              <span className="hito-paso">{cantidadGrande(h.paso)} pasos</span>
              <span>{h.texto}</span>
            </li>
          ))}
        </ol>
      )}
    </figure>
  );
}
