"use client";

import dynamic from "next/dynamic";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import Etapas from "@/components/Etapas";
import Resultados from "@/components/Resultados";
import { verCorrida } from "@/lib/api";
import { cargarCorrida, type Datos } from "@/lib/datos";
import type { Corrida } from "@/lib/tipos";

const Visor = dynamic(() => import("@/components/Visor"), {
  ssr: false,
  loading: () => <div className="visor-cargando">Cargando la planta en 3D…</div>,
});

export default function PaginaCorrida() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [corrida, setCorrida] = useState<Corrida | null>(null);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // La corrida del demo vive en la portada, sin API (RF-WEB-08).
    if (id === "demo") {
      router.replace("/");
      return;
    }
    let vivo = true;
    let timer: ReturnType<typeof setTimeout>;
    async function sondear() {
      try {
        const c = await verCorrida(id);
        if (!vivo) return;
        setCorrida(c);
        if (c.estado === "listo") {
          const d = await cargarCorrida(c);
          if (vivo) setDatos(d);
          return;
        }
        if (c.estado !== "error") timer = setTimeout(sondear, 2000);
      } catch (e) {
        if (vivo) setError(e instanceof Error ? e.message : String(e));
      }
    }
    sondear();
    return () => { vivo = false; clearTimeout(timer); };
  }, [id, router]);

  if (id === "demo") return null;
  if (error) {
    return (
      <p className="error bloque" role="alert">
        No se pudo cargar la corrida {id}: {error}. Revisa que la API esté encendida y recarga la página.
      </p>
    );
  }
  if (!corrida) return <p className="bloque tenue">Cargando la corrida…</p>;

  return (
    <>
      <section className="bloque corrida-cabecera" aria-labelledby="t-corrida">
        <h1 id="t-corrida">Corrida {corrida.id}</h1>
        <Etapas etapas={corrida.etapas} />
        {corrida.error && <p className="error" role="alert">{corrida.error}</p>}
      </section>
      {datos ? (
        <>
          <div className="corrida-visor">
            <Visor entorno={datos.entorno} tray={datos.tray} urdf={datos.urdf}
              descripcion="El robot clonado trabajando en la planta de esta corrida" />
          </div>
          <Resultados datos={datos} />
        </>
      ) : (
        <p className="bloque pendiente pendiente-grande">
          {corrida.estado === "error"
            ? "La corrida se detuvo. El motivo está arriba, junto a la etapa que falló."
            : "Los agentes están trabajando. Esta página se actualiza sola."}
        </p>
      )}
    </>
  );
}
