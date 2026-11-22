"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { crearCorrida, crearProyecto } from "@/lib/api";

// RF-WEB-19: el flujo completo, paso a paso. Los pasos 1 y 2 son el flujo de producción: en el demo no se usan en vivo.
const PASOS = [
  { n: 1, titulo: "Subes videos de tu lugar de trabajo", texto: "Grabas el lugar con un celular o un dron y subes los videos: un parque solar, una bodega, una sala de eventos." },
  { n: 2, titulo: "VIAZ extrae el entorno", texto: "Un agente mide el espacio y sus objetos, y arma una copia 3D con física." },
  { n: 3, titulo: "Un agente elige el robot real", texto: "Compara lo que pide la tarea (carga, alcance, espacio libre, movilidad) contra robots que ya existen, y justifica." },
  { n: 4, titulo: "Otro agente lo construye en Isaac Lab", texto: "Arma un robot simulado con el alcance y la carga útil del real, y lo valida en la escena." },
  { n: 5, titulo: "El robot aprende la tarea", texto: "Aprendizaje por refuerzo: miles de intentos en paralelo hasta hacer la tarea. Un agente vigila el entrenamiento." },
  { n: 6, titulo: "Ves el resultado", texto: "Video del aprendizaje en cámara rápida, el robot entrenado trabajando y la tasa de éxito medida." },
];

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
      <h1>Ve a tu robot trabajar en tu lugar de trabajo, antes de comprarlo</h1>
      <p className="bajada">
        VIAZ elige un robot real para cualquier lugar y tarea, lo construye en simulación con NVIDIA Isaac Lab y le
        enseña la tarea con aprendizaje por refuerzo.
      </p>
      {/* RF-WEB-21: un botón por caso de referencia. Cada id sale de una variable de entorno de la web. */}
      <div className="casos">
        <Link href="/corridas/demo" className="boton">Caso 1: parque solar</Link>
        {process.env.NEXT_PUBLIC_CORRIDA_EVENTO && (
          <Link href={`/corridas/${process.env.NEXT_PUBLIC_CORRIDA_EVENTO}`} className="boton">Caso 2: animar un evento</Link>
        )}
      </div>

      <h2 className="subtitulo">Cómo funciona</h2>
      <ol className="pasos">
        {PASOS.map((p) => (
          <li key={p.n} className={`paso ${p.n <= 2 ? "paso-produccion" : ""}`}>
            <span className="paso-n">{p.n}</span>
            <div>
              <strong>{p.titulo}</strong>
              <p>{p.texto}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="aviso">
        <strong>Sobre los casos:</strong> el parque solar usa un entorno escrito a mano; la sala de eventos sale de un video
        del lugar, con medidas estimadas. El mismo código corre los dos: solo cambia el perfil de cada tarea.
      </p>

      <details className="formulario-plegado">
        <summary>Flujo de producción: subir videos (prueba técnica)</summary>
        <form onSubmit={enviar} className="formulario">
          <label>
            Nombre del lugar
            <input required value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Parque solar Atacama Norte" />
          </label>
          <label>
            Qué quieres automatizar
            <textarea value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={3}
              placeholder="Instalación de paneles en trackers de un eje" />
          </label>
          <label>
            Videos del lugar
            <input type="file" accept="video/*" multiple onChange={(e) => setVideos(Array.from(e.target.files ?? []))} />
          </label>
          <button type="submit" disabled={enviando || !nombre}>{enviando ? "Subiendo…" : "Crear corrida"}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </form>
      </details>
    </section>
  );
}
