// Reglas de la escena: las mismas que sim/generar_escena.py. Si cambias una, cambia la otra.
// Z arriba, metros. Fila i: tubo en y = -i * separacion, a altura_m, de x = 0 a x = largo; postes cada 7 m.
import type { Entorno } from "./tipos";

export const POSTE_CADA_M = 7;

export interface Caja {
  nombre: string;
  centro: [number, number, number];
  tam: [number, number, number];
  color: string;
}

export function cajasEscena(e: Entorno): Caja[] {
  const { cantidad, largo_m: largo, separacion_m: sep } = e.filas;
  const alto = e.estructura.altura_m;
  const cajas: Caja[] = [
    { nombre: "suelo", centro: [largo / 2, (-sep * (cantidad - 1)) / 2, -0.05], tam: [largo + 20, sep * cantidad + 20, 0.1], color: "#9e8566" },
  ];
  for (let i = 0; i < cantidad; i++) {
    const y = -i * sep;
    cajas.push({ nombre: `fila${i}-tubo`, centro: [largo / 2, y, alto], tam: [largo, 0.1, 0.1], color: "#8c9199" });
    const postes = Math.floor(largo / POSTE_CADA_M) + 1;
    for (let j = 0; j < postes; j++) {
      const x = Math.min(j * POSTE_CADA_M, largo);
      // El poste termina en la cara de abajo del tubo (lado 0,1 m), igual que en sim/generar_escena.py.
      const h = alto - 0.05;
      cajas.push({ nombre: `fila${i}-poste${j}`, centro: [x, y, h / 2], tam: [0.15, 0.15, h], color: "#737880" });
    }
  }
  return cajas;
}
