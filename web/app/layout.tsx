import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import Link from "next/link";
import "./globals.css";

// Una sola familia con contraste de ancho (web/DISENO.md): expandida en títulos, normal en texto.
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--fuente", display: "swap" });

export const metadata: Metadata = {
  title: "VIAZ: la inteligencia de un robot real para tu planta",
  description: "VIAZ es una cadena de agentes de IA que convierte los videos de una planta en un robot real entrenado en Isaac Lab, antes de comprarlo.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={archivo.variable}>
      <body>
        <a href="#contenido" className="saltar">Saltar al contenido</a>
        <header className="cabecera">
          <Link href="/" className="marca" aria-label="VIAZ, inicio">VIAZ</Link>
          <nav aria-label="Principal">
            <Link href="/probar" className="nav-accion">Probar con tu planta</Link>
          </nav>
        </header>
        <main id="contenido">{children}</main>
        <footer className="pie">
          Hecho en Platanus Hack 26 Santiago por el team-4.
        </footer>
      </body>
    </html>
  );
}
