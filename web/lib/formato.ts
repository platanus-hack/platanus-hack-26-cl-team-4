// Formato de números y unidades en español de Chile.
const nf = (opts?: Intl.NumberFormatOptions) => new Intl.NumberFormat("es-CL", opts);

export const porcentaje = (x: number) => `${nf({ maximumFractionDigits: 0 }).format(x * 100)} %`;

export const numero = (x: number, decimales = 1) => nf({ maximumFractionDigits: decimales }).format(x);

/** 48 000 000 → "48 millones"; 950 000 → "950 mil". */
export function cantidadGrande(x: number) {
  if (x >= 1e6) return `${nf({ maximumFractionDigits: 1 }).format(x / 1e6)} millones`;
  if (x >= 1e3) return `${nf({ maximumFractionDigits: 0 }).format(x / 1e3)} mil`;
  return nf().format(x);
}

/** 2700 → "45 min"; 5400 → "1 h 30 min". */
export function duracion(s: number) {
  const min = Math.round(s / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const resto = min % 60;
  return resto ? `${h} h ${resto} min` : `${h} h`;
}

/** 0.05 m → "5 cm". */
export const centimetros = (m: number) => `${nf({ maximumFractionDigits: 1 }).format(m * 100)} cm`;
