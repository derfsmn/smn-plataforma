"use client";

import { FileDown } from "lucide-react";
import { useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton } from "@/componentes/ui";
import { mensajeDe } from "@/lib/api";
import { descargar } from "@/lib/precios";

/** «Descargar reporte PDF» del producto: semáforo, dictamen, las 8 preguntas del comité y lo que se propone a Compras
 * (pedido de Diego, 2026-11-13). `ruta` es la de la API que lo genera. */
export function BotonReporte({ ruta, nombre, guardado = false }: { ruta: string; nombre: string; guardado?: boolean }) {
  const avisar = useAvisos();
  const [bajando, setBajando] = useState(false);
  const limpio = nombre.replace(/[^\p{L}\p{N} +.-]/gu, "").slice(0, 80).trim();
  return (
    <Boton
      variante="secundario"
      cargando={bajando}
      title={guardado ? "El reporte que se guardó cuando el comité lo aceptó" : "Con la evaluación de hoy"}
      onClick={async () => {
        setBajando(true);
        try {
          await descargar(ruta, `Radar producto nuevo - ${limpio}.pdf`);
        } catch (e) {
          avisar(mensajeDe(e), "info");
        } finally {
          setBajando(false);
        }
      }}
    >
      {!bajando && <FileDown className="h-4 w-4" aria-hidden />} {guardado ? "Reporte del comité (PDF)" : "Descargar reporte PDF"}
    </Boton>
  );
}
