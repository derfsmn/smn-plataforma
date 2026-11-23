"use client";
// Productos nuevos (TD001): propuestas que mandan los proveedores desde su portal (entrada del radar de productos) y el Comité de producto nuevo.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useSesion } from "@/componentes/sesion";
import { CabeceraCompras } from "@/componentes/cabecera-compras";

const PESTANAS = [
  { href: "/compras/propuestas", texto: "Propuestas", permiso: "compras.propuestas.ver" },
  { href: "/compras/propuestas/comite", texto: "Comité", permiso: "compras.comite.ver" },
  { href: "/compras/propuestas/busquedas", texto: "Búsqueda de proveedores", permiso: "compras.busquedas.ver" },
  { href: "/compras/propuestas/proveedores", texto: "Proveedores invitados", permiso: "compras.proveedores.invitar", ajuste: true },
];

export default function LayoutPropuestas({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede } = useSesion();
  if (!puede("compras.propuestas.ver") && !puede("compras.comite.ver") && !puede("compras.busquedas.ver"))
    return <p className="text-smn-gris-500">No tienes acceso a Productos nuevos.</p>;
  const enComite = /^\/compras\/propuestas\/comite\/\d+/.test(ruta);
  const enBusqueda = /^\/compras\/propuestas\/busquedas\/\d+/.test(ruta);
  const enDetalle = enComite || enBusqueda || /^\/compras\/propuestas\/(captura\/)?\d+/.test(ruta);
  if (/\/presentar$/.test(ruta)) return <>{children}</>; // el modo presentación ocupa toda la pantalla

  if (enDetalle)
    return (
      <>
        <Link
          href={enComite ? "/compras/propuestas/comite" : enBusqueda ? "/compras/propuestas/busquedas" : "/compras/propuestas"}
          className="mb-4 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta"
        >
          <ArrowLeft className="h-4 w-4" /> {enComite ? "Comité" : enBusqueda ? "Búsqueda de proveedores" : "Propuestas"}
        </Link>
        {children}
      </>
    );
  return (
    <>
      <CabeceraCompras id="propuestas" titulo="Productos nuevos" descripcion="Lo que proponen los proveedores, el comité que decide y la búsqueda de proveedor para las buenas ideas." pestanas={PESTANAS} />
      {children}
    </>
  );
}
