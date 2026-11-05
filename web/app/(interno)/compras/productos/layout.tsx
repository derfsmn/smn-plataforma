"use client";
// Radar de productos (Compras): semáforo con explicación para cada producto nuevo, sea propuesta de proveedor o idea de Compras.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Plus, Sparkles } from "lucide-react";
import { Boton } from "@/componentes/ui";
import { EVENTO_CAPTURAR } from "@/lib/productos";
import { useSesion } from "@/componentes/sesion";

export default function LayoutProductos({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede } = useSesion();
  if (!puede("compras.productos.ver")) return <p className="text-smn-gris-500">No tienes acceso al radar de productos.</p>;
  const enDetalle = /^\/compras\/productos\/(\d+|oportunidades)/.test(ruta);

  return (
    <>
      <Link href={enDetalle ? "/compras/productos" : "/modulos/compras"} className="mb-5 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> {enDetalle ? "Radar de productos" : "Inteligencia de Compras"}
      </Link>
      {!enDetalle && (
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-[15px] text-smn-gris-500"><span className="font-mono">TD001</span> · Compras</p>
            <h1 className="mt-1 text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">Radar de productos</h1>
            <p className="mt-2 max-w-2xl text-[16px] text-smn-gris-700">Semáforo con explicación para cada producto nuevo. El color final lo decide Compras.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/compras/productos/oportunidades"
              className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-smn-gris-100 bg-superficie px-4 text-[15px] font-medium hover:border-smn-gris-300"
            >
              <Sparkles className="h-4 w-4" /> Buscar oportunidades
            </Link>
            {puede("compras.productos.evaluar") && (
              <Boton onClick={() => window.dispatchEvent(new Event(EVENTO_CAPTURAR))}>
                <Plus className="h-4 w-4" /> Capturar producto
              </Boton>
            )}
          </div>
        </div>
      )}
      {children}
    </>
  );
}
