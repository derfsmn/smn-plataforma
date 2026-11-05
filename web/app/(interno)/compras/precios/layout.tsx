"use client";
// Radar de precios (Compras · TD001): pestañas comunes a todas sus pantallas.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { ArrowLeft } from "lucide-react";
import { useSesion } from "@/componentes/sesion";

const PESTANAS = [
  { href: "/compras/precios", texto: "Productos" },
  { href: "/compras/precios/productos", texto: "Productos vigilados" },
  { href: "/compras/precios/corridas", texto: "Corridas y gasto" },
];

export default function LayoutPrecios({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede } = useSesion();
  if (!puede("compras.precios.ver")) return <p className="text-smn-gris-500">No tienes acceso al Radar de precios.</p>;
  const activa = (href: string) => (href === "/compras/precios" ? ruta === href || ruta.startsWith("/compras/precios/producto/") : ruta.startsWith(href));

  return (
    <>
      <Link href="/modulos/compras" className="mb-5 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Inteligencia de Compras
      </Link>
      <div className="mb-7 flex items-center gap-3">
        <div>
          <p className="text-[15px] text-smn-gris-500"><span className="font-mono">TD001</span> · Compras</p>
          <h1 className="mt-1 text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">Radar de precios</h1>
        </div>
      </div>
      <nav className="-mx-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Secciones del radar de precios">
        <ul className="flex w-max gap-1 rounded-xl bg-smn-gris-100 p-1">
          {PESTANAS.map((p) => (
            <li key={p.href}>
              <Link
                href={p.href}
                className={`relative block rounded-lg px-3.5 py-2 text-[15px] font-medium whitespace-nowrap transition-colors ${activa(p.href) ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
              >
                {activa(p.href) && <motion.span layoutId="pestana-precios" className="absolute inset-0 rounded-lg bg-superficie shadow-sm" transition={{ duration: 0.25 }} />}
                <span className="relative">{p.texto}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {children}
    </>
  );
}
