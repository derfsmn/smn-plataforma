"use client";
// Productos nuevos (TD001): propuestas que mandan los proveedores desde su portal (entrada del radar de productos) y el Comité de producto nuevo.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { ArrowLeft } from "lucide-react";
import { useSesion } from "@/componentes/sesion";

const PESTANAS = [
  { href: "/compras/propuestas", texto: "Propuestas", permiso: "compras.propuestas.ver" },
  { href: "/compras/propuestas/comite", texto: "Comité", permiso: "compras.comite.ver" },
  { href: "/compras/propuestas/proveedores", texto: "Proveedores invitados", permiso: "compras.propuestas.ver" },
];

export default function LayoutPropuestas({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede } = useSesion();
  if (!puede("compras.propuestas.ver") && !puede("compras.comite.ver"))
    return <p className="text-smn-gris-500">No tienes acceso a Productos nuevos.</p>;
  const enComite = /^\/compras\/propuestas\/comite\/\d+/.test(ruta);
  const enDetalle = enComite || /^\/compras\/propuestas\/(captura\/)?\d+/.test(ruta);
  if (/\/presentar$/.test(ruta)) return <>{children}</>; // el modo presentación ocupa toda la pantalla
  const activa = (href: string) => (href === "/compras/propuestas" ? ruta === href : ruta.startsWith(href));

  return (
    <>
      <Link
        href={enComite ? "/compras/propuestas/comite" : enDetalle ? "/compras/propuestas" : "/modulos/compras"}
        className="mb-5 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta"
      >
        <ArrowLeft className="h-4 w-4" /> {enComite ? "Comité" : enDetalle ? "Propuestas" : "Inteligencia de Compras"}
      </Link>
      {!enDetalle && (
        <>
          <div className="mb-7 flex items-center gap-3">
            <div>
              <p className="text-[15px] text-smn-gris-500"><span className="font-mono">TD001</span> · Compras</p>
              <h1 className="mt-1 text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">Productos nuevos</h1>
            </div>
          </div>
          <nav className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Secciones de productos nuevos">
            <ul className="flex w-max gap-1 rounded-xl bg-smn-gris-100 p-1">
              {PESTANAS.filter((p) => puede(p.permiso)).map((p) => (
                <li key={p.href}>
                  <Link
                    href={p.href}
                    className={`relative block rounded-lg px-3.5 py-2 text-[15px] font-medium whitespace-nowrap transition-colors ${activa(p.href) ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
                  >
                    {activa(p.href) && <motion.span layoutId="pestana-propuestas" className="absolute inset-0 rounded-lg bg-superficie shadow-sm" transition={{ duration: 0.25 }} />}
                    <span className="relative">{p.texto}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </>
      )}
      {children}
    </>
  );
}
