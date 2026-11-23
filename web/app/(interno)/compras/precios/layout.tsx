"use client";
// Radar de precios (Compras · TD001): cabecera y pestañas comunes a todas sus pantallas.

import { useSesion } from "@/componentes/sesion";
import { CabeceraCompras } from "@/componentes/cabecera-compras";

const PESTANAS = [
  { href: "/compras/precios", texto: "Resumen" },
  { href: "/compras/precios/todos", texto: "Todos los productos", tambien: /^\/compras\/precios\/producto\// },
  { href: "/compras/precios/reporte", texto: "Reporte a Excel" },
  { href: "/compras/precios/productos", texto: "Productos vigilados", permiso: "compras.precios.administrar", ajuste: true },
  { href: "/compras/precios/corridas", texto: "Corridas y gasto", permiso: "compras.precios.administrar", ajuste: true },
];

export default function LayoutPrecios({ children }: { children: React.ReactNode }) {
  const { puede } = useSesion();
  if (!puede("compras.precios.ver")) return <p className="text-smn-gris-500">No tienes acceso al Radar de precios.</p>;
  return (
    <>
      <CabeceraCompras id="precios" titulo="Radar de precios" descripcion="Nuestro precio contra el de la competencia en internet, producto por producto." pestanas={PESTANAS} />
      {children}
    </>
  );
}
