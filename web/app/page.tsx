"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { crearCorrida, crearProyecto } from "@/lib/api";

export default function Inicio() {
  const router = useRouter();
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
      setError(e instanceof Error ? e.message : String(e));
      setEnviando(false);
    }
  }

  return (
    <section className="inicio">
      <h1>De videos de tu planta a un robot real trabajando en ella</h1>
      <p className="bajada">
        Sube videos de tu planta. Agentes de IA la virtualizan, eligen un robot real, lo clonan y lo
        ponen a trabajar en una simulación con NVIDIA Isaac.
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
        <label>
          Videos de la planta
          <input type="file" accept="video/*" multiple onChange={(e) => setVideos(Array.from(e.target.files ?? []))} />
        </label>
        <button type="submit" disabled={enviando || !nombre}>{enviando ? "Subiendo…" : "Virtualizar mi planta"}</button>
        {error && <p className="error" role="alert">{error}</p>}
      </form>
    </section>
  );
}
