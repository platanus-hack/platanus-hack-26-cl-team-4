import type { Corrida } from "./tipos";

export const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function crearProyecto(nombre: string, descripcion: string, videos: File[]) {
  const r = await fetch(`${API}/proyectos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nombre, descripcion, videos: videos.map((v) => v.name) }),
  });
  const p = await json<{ id: string; subida: { archivo: string; url_firmada: string }[] }>(r);
  // Los videos van directo al almacén (R2 en producción) con la URL firmada; no pasan por la API.
  await Promise.all(
    p.subida.map(async (s, i) => {
      const put = await fetch(s.url_firmada, { method: "PUT", body: videos[i] });
      if (!put.ok) throw new Error(`no pude subir ${s.archivo}: ${put.status}`);
    }),
  );
  return p.id;
}

export async function crearCorrida(proyectoId: string) {
  const r = await fetch(`${API}/proyectos/${proyectoId}/corridas`, { method: "POST" });
  return (await json<{ corrida_id: string }>(r)).corrida_id;
}

export async function verCorrida(id: string) {
  return json<Corrida>(await fetch(`${API}/corridas/${id}`, { cache: "no-store" }));
}

export async function bajarJson<T>(url: string) {
  return json<T>(await fetch(url));
}

export async function bajarTexto(url: string) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.text();
}
