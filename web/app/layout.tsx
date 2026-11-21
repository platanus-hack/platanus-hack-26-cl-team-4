import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "VIAZ",
  description: "De videos de tu planta a un robot real trabajando en ella, antes de comprarlo.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="cabecera">
          <Link href="/" className="marca">VIAZ</Link>
          <nav><Link href="/corridas/demo">Ver demo</Link></nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
