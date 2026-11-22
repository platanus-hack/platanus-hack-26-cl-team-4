"use client";

import { useEffect, useState } from "react";

import { artefactosDe } from "./seleccion";
import type { Corrida } from "./tipos";

interface Visto {
  corridaId: string;
  artefactos: Record<string, string>;
}

// Signed URLs change on every poll, so the load uses the artefact list seen when the file first appears.
export function useArtefacto<T>(
  corrida: Corrida,
  archivo: string,
  cargar: (artefactos: Record<string, string>) => Promise<T | null>,
): T | null {
  const [datos, setDatos] = useState<T | null>(null);
  const [visto, setVisto] = useState<Visto | null>(null);
  const artefactos = artefactosDe(corrida);
  if (archivo in artefactos && visto?.corridaId !== corrida.id) {
    setVisto({ corridaId: corrida.id, artefactos });
  }
  useEffect(() => {
    if (!visto) return;
    let vivo = true;
    cargar(visto.artefactos).then((d) => { if (vivo) setDatos(d); });
    return () => { vivo = false; };
  }, [visto, cargar]);
  return datos;
}
