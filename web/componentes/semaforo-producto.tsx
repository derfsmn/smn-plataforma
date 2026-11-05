"use client";
// Semáforo del radar de productos: las tres luces, la insignia de color y la tarjeta que se muestra en el detalle de una propuesta.

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, Gauge, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Insignia } from "@/componentes/ui";
import { api } from "@/lib/api";
import { SEMAFORO } from "@/lib/precios";
import { colorVigente, CONFIANZA, RUTA, type Color, type Evaluacion } from "@/lib/productos";

const LUCES: Color[] = ["rojo", "amarillo", "verde"];

/** Tres luces; la encendida es el color vigente. Vertical en el detalle, horizontal en listas. */
export function Semaforo({ color, tam = "md", horizontal = false }: { color: Color | null; tam?: "sm" | "md" | "lg"; horizontal?: boolean }) {
  const luz = { sm: "h-2.5 w-2.5", md: "h-4 w-4", lg: "h-9 w-9" }[tam];
  return (
    <span
      role="img"
      aria-label={color ? `Semáforo ${SEMAFORO[color].texto.toLowerCase()}` : "Sin semáforo"}
      className={`inline-flex shrink-0 items-center rounded-full bg-smn-negro ${horizontal ? "flex-row gap-1 px-1.5 py-1" : "flex-col gap-1.5 px-2 py-2.5"} ${tam === "lg" ? "gap-2.5 px-3 py-3.5" : ""}`}
    >
      {LUCES.map((c) => (
        <motion.span
          key={c}
          initial={false}
          animate={{ opacity: color === c ? 1 : 0.18, scale: color === c ? 1 : 0.92 }}
          transition={{ duration: 0.3 }}
          className={`${luz} rounded-full ${SEMAFORO[c].punto} ${color === c ? "shadow-[0_0_14px_currentColor]" : ""}`}
        />
      ))}
    </span>
  );
}

export function InsigniaColor({ color }: { color: Color | null }) {
  if (!color) return <Insignia className="bg-smn-gris-100 text-smn-gris-700">Sin color</Insignia>;
  const s = SEMAFORO[color];
  return (
    <Insignia className={`gap-1.5 ${s.insignia}`}>
      <span className={`h-2 w-2 rounded-full ${s.punto}`} aria-hidden /> {s.texto}
    </Insignia>
  );
}

/** Resumen de la evaluación de una propuesta, para el detalle que ve Compras. Se refresca mientras está en curso. */
export function TarjetaEvaluacion({ propuestaId, recarga = 0 }: { propuestaId: number; recarga?: number }) {
  const [e, setE] = useState<Evaluacion | null | undefined>(undefined);

  useEffect(() => {
    let vivo = true;
    let reloj: ReturnType<typeof setTimeout>;
    const traer = () =>
      api<Evaluacion | null>(`${RUTA}/propuestas/${propuestaId}`)
        .then((x) => {
          if (!vivo) return;
          setE(x);
          if (x?.estado === "en_curso") reloj = setTimeout(traer, 3000);
        })
        .catch(() => vivo && setE(null));
    traer();
    return () => {
      vivo = false;
      clearTimeout(reloj);
    };
  }, [propuestaId, recarga]);

  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <Gauge className="h-4 w-4 text-smn-naranja" /> Radar de productos
      </h2>
      {e === undefined ? (
        <div className="h-16 animate-pulse rounded-xl bg-smn-gris-100" />
      ) : e === null ? (
        <p className="text-sm text-smn-gris-500">Se evalúa sola cuando la marcas como «Lista para evaluar».</p>
      ) : e.estado === "en_curso" ? (
        <p className="flex items-center gap-2 text-sm text-smn-gris-500">
          <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" /> Evaluando…
        </p>
      ) : (
        <Link href={`/compras/productos/${e.id}`} className="group flex items-center gap-3">
          <Semaforo color={colorVigente(e)} tam="sm" />
          <div className="min-w-0 flex-1">
            {e.estado === "fallida" ? (
              <p className="text-sm font-semibold text-aviso-texto">No se pudo evaluar</p>
            ) : (
              <>
                <p className="text-2xl font-semibold tabular-nums">
                  {e.puntaje ?? "—"} <span className="text-sm font-semibold text-smn-gris-500">de 100</span>
                </p>
                <p className="text-[13px] text-smn-gris-500">
                  {e.confianza && CONFIANZA[e.confianza]}
                  {e.color_final && " · color cambiado por Compras"}
                </p>
              </>
            )}
          </div>
          <ArrowRight className="h-4 w-4 shrink-0 text-smn-gris-500 transition group-hover:translate-x-0.5 group-hover:text-smn-naranja" />
        </Link>
      )}
    </section>
  );
}
