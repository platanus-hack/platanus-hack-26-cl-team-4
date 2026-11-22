import { notFound } from "next/navigation";

import { Comparacion } from "@/components/Comparacion";
import { Seleccion } from "@/components/Seleccion";
import comparacionEjemplo from "@/dev-fixtures/comparacion-ejemplo.json";
import comparacion from "@/dev-fixtures/comparacion.json";
import encontradosEjemplo from "@/dev-fixtures/encontrados-ejemplo.json";
import requisitos from "@/dev-fixtures/requisitos.json";
import robot from "@/dev-fixtures/robot.json";
import seleccionEjemplo from "@/dev-fixtures/seleccion-ejemplo.json";
import seleccion from "@/dev-fixtures/seleccion.json";
import {
  indexarFichas, type Comparacion as ArchivoComparacion, type FichaRobot, type Requisitos,
  type Seleccion as ArchivoSeleccion,
} from "@/lib/seleccion";

export default function PaginaDevSeleccion() {
  if (process.env.NODE_ENV === "production") notFound();

  const ficha = robot as FichaRobot;
  const encontrados = encontradosEjemplo as FichaRobot[];
  const req = requisitos as Requisitos;
  return (
    <section className="corrida">
      <aside className="lateral">
        <h2>Fixtures del backend</h2>
        <Seleccion datos={{ seleccion: seleccion as ArchivoSeleccion, requisitos: req, encontrados: [],
          fichas: indexarFichas([], ficha) }} />
        <h2>Ejemplo con un robot encontrado</h2>
        <Seleccion datos={{ seleccion: seleccionEjemplo as ArchivoSeleccion, requisitos: req, encontrados,
          fichas: indexarFichas(encontrados, ficha) }} />
      </aside>
      <div className="principal">
        <Comparacion datos={{ comparacion: comparacion as ArchivoComparacion, fichas: indexarFichas([], ficha) }} />
        <Comparacion datos={{ comparacion: comparacionEjemplo as ArchivoComparacion,
          fichas: indexarFichas(encontrados, ficha) }} />
      </div>
    </section>
  );
}
