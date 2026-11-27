"use client";
// Radar de productos (Compras): semáforo con explicación para cada producto nuevo, sea propuesta de proveedor o idea de Compras.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Camera, Plus, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Boton } from "@/componentes/ui";
import { EVENTO_CAPTURAR, EVENTO_ALTA_FOTOS, RUTA } from "@/lib/productos";
import { api } from "@/lib/api";
import { useSesion } from "@/componentes/sesion";
import { CabeceraCompras } from "@/componentes/cabecera-compras";

export default function LayoutProductos({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { puede } = useSesion();
  // «Alta con fotos» se prende en Configuración → Radar de productos; prendida, tiene su propio botón aquí
  const [altaFotos, setAltaFotos] = useState(false);
  const evalua = puede("compras.productos.evaluar");
  useEffect(() => {
    if (evalua) api<{ activo: boolean }>(`${RUTA}/alta-fotos`).then((x) => setAltaFotos(x.activo)).catch(() => setAltaFotos(false));
  }, [evalua]);
  if (!puede("compras.productos.ver")) return <p className="text-smn-gris-500">No tienes acceso al radar de productos.</p>;
  const enDetalle = /^\/compras\/productos\/(\d+|oportunidades)/.test(ruta);

  if (enDetalle)
    return (
      <>
        <Link href="/compras/productos" className="mb-4 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta">
          <ArrowLeft className="h-4 w-4" /> Radar de productos
        </Link>
        {children}
      </>
    );
  return (
    <>
      <CabeceraCompras
        id="productos"
        titulo="Radar de productos"
        descripcion="Cada producto nuevo con su semáforo y la razón, ya calculados por la máquina."
        acciones={
          <>
            <Link
              href="/compras/productos/oportunidades"
              className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-smn-gris-100 bg-superficie px-4 text-[15px] font-medium hover:border-smn-gris-300"
            >
              <Sparkles className="h-4 w-4" /> Buscar oportunidades
            </Link>
            {evalua && altaFotos && (
              <Boton onClick={() => window.dispatchEvent(new Event(EVENTO_ALTA_FOTOS))}>
                <Camera className="h-4 w-4" /> Alta con fotos
              </Boton>
            )}
            {evalua && (
              <Boton variante={altaFotos ? "secundario" : "primario"} onClick={() => window.dispatchEvent(new Event(EVENTO_CAPTURAR))}>
                <Plus className="h-4 w-4" /> Capturar producto
              </Boton>
            )}
          </>
        }
      />
      {children}
    </>
  );
}
