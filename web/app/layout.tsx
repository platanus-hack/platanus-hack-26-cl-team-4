import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";
import "./portada.css";
import "./pitch-visuales.css";

const inter = localFont({ src: "./InterVariable.woff2", weight: "100 900", variable: "--fuente-inter", display: "swap" });

export const metadata: Metadata = {
  title: "VIAZ | Simulación para robótica industrial",
  description: "De los videos de tu planta a un entorno 3D para seleccionar, entrenar en simulación y evaluar robots industriales.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={inter.variable}>
      <body>
        <a href="#contenido" className="saltar">Saltar al contenido</a>
        <header className="cabecera">
          <Link href="/" className="marca marca-viaz" aria-label="VIAZ, inicio">
            <svg aria-hidden="true" viewBox="20 39 216 178" fill="currentColor">
              <path fillRule="evenodd" d="M43 49H93L111 67H145L163 49H213L228 64V96L201 123H159L140 104H116L97 123H55L28 96V64ZM54 68L48 74V90L63 105H89L105 89L84 68ZM172 68L151 89L167 105H193L208 90V74L202 68Z" />
              <path d="M54 133H89L128 172L167 133H202L128 207Z" />
            </svg>
            VIAZ
          </Link>
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
