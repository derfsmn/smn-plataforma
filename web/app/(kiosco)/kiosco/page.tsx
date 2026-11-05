import type { Metadata } from "next";
import { KioscoNaturi } from "./naturi";

// Kiosco Digital (Tiendas · TD002): Naturi a pantalla completa, sin el menú de la plataforma.
export const metadata: Metadata = {
  title: "Kiosco Digital · Naturi",
  description: "Asistente virtual Naturi para tiendas Súper Naturista, por voz o por escrito.",
  robots: { index: false, follow: false },
};

export default function Pagina() {
  return <KioscoNaturi />;
}
