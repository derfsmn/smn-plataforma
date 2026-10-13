import type { Metadata } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";

// Sustituta de la tipografía del logotipo hasta tener la oficial
const nunito = Nunito({ subsets: ["latin"], variable: "--font-nunito" });

export const metadata: Metadata = {
  title: "SMN - Transformación digital",
  description: "Plataforma de iniciativas de Transformación Digital de Súper Naturista",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-MX" className={nunito.variable}>
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
