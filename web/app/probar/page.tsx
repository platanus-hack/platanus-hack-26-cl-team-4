"use client";

// Probar con una planta propia (RF-WEB-01/02/03, "Could"). Necesita la API (Render o local).
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { crearCorrida, crearProyecto } from "@/lib/api";

export default function Probar() {
  const router = useRouter();
  const idVideos = useId();
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [videos, setVideos] = useState<File[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar(ev: React.FormEvent) {
    ev.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const pid = await crearProyecto(nombre, descripcion, videos);
      router.push(`/corridas/${await crearCorrida(pid)}`);
    } catch (e) {
      const detalle = e instanceof Error ? e.message : String(e);
      setError(`No se pudo crear la corrida: ${detalle}. Revisa que la API esté encendida y vuelve a enviar.`);
      setEnviando(false);
    }
  }

  return (
    <section className="probar">
      <h1>Probar con tu planta</h1>
      <p className="bajada">
        Sube videos de tu planta. Los agentes la virtualizan, eligen un robot del catálogo y lo ponen a trabajar
        en la simulación. Verás el avance de cada etapa.
      </p>
      <form onSubmit={enviar} className="formulario">
        <label>
          Nombre de la planta
          <input required value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Parque solar Atacama Norte" />
        </label>
        <label>
          Qué quieres automatizar
          <textarea value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
            placeholder="Instalación de paneles en trackers de un eje" />
        </label>
        <div className="campo-archivos">
          <span className="campo-titulo">Videos de la planta</span>
          <input id={idVideos} className="sr" type="file" accept="video/*" multiple
            onChange={(e) => setVideos(Array.from(e.target.files ?? []))} />
          <label htmlFor={idVideos} className="boton-secundario">Elegir videos</label>
          <span className="tenue" aria-live="polite">
            {videos.length === 0 ? "Ningún video elegido" : videos.map((v) => v.name).join(", ")}
          </span>
        </div>
        <button type="submit" className="boton-principal" disabled={enviando || !nombre}>
          {enviando ? "Subiendo videos…" : "Virtualizar mi planta"}
        </button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </section>
  );
}
