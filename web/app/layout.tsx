import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { scriptTema } from "@/lib/tema";

// Letra única del diseño sobrio en todo el sitio (se quitó Nunito el 1 nov 2026)
const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "SMN - Transformación digital",
  description: "Plataforma de iniciativas de Transformación Digital de Súper Naturista",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX" className={geist.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: scriptTema }} />
      </head>
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
