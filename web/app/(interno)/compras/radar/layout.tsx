"use client";
// Radar de tendencias (Compras · TD001): cabecera y pestañas comunes a todas sus pantallas.

import { useSesion } from "@/componentes/sesion";
import { CabeceraCompras } from "@/componentes/cabecera-compras";

const PESTANAS = [
  { href: "/compras/radar", texto: "Hoy", tambien: /^\/compras\/radar\/senal/ },
  { href: "/compras/radar/tendencias", texto: "Tendencias" },
  { href: "/compras/radar/historico", texto: "Histórico" },
  { href: "/compras/radar/conocimiento", texto: "Documentos de apoyo" },
  { href: "/compras/radar/origen", texto: "De dónde sale" },
  { href: "/compras/radar/fuentes", texto: "Fuentes y temas", permiso: "compras.radar.administrar", ajuste: true },
  { href: "/compras/radar/destinatarios", texto: "Destinatarios", permiso: "compras.radar.administrar", ajuste: true },
  { href: "/compras/radar/corridas", texto: "Corridas", permiso: "compras.radar.administrar", ajuste: true },
];

export default function LayoutRadar({ children }: { children: React.ReactNode }) {
  const { puede } = useSesion();
  if (!puede("compras.radar.ver")) return <p className="text-smn-gris-500">No tienes acceso al Radar de tendencias.</p>;
  return (
    <>
      <CabeceraCompras id="radar" titulo="Radar de tendencias" descripcion="Lo que se mueve en suplementos y naturistas, con su fuente, cada mañana." pestanas={PESTANAS} />
      {children}
    </>
  );
}
