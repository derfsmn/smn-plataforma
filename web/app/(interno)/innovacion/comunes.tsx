"use client";
// Piezas compartidas de Innovación Vidanat: menú del módulo, tarjetas, campos de texto y chips de estado.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft, Lock } from "lucide-react";
import { useSesion } from "@/componentes/sesion";
import { Insignia } from "@/componentes/ui";
import { CLASIFICACION, ESTADO_FUENTE, P, RESULTADO } from "@/lib/innovacion";

export const TARJETA = "rounded-2xl border border-smn-gris-100 bg-superficie p-5";
export const AREA =
  "w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 py-2.5 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15";
export const ETIQUETA = "mb-1.5 block text-sm font-medium text-smn-gris-700";

const SECCIONES = [
  { href: "/innovacion", texto: "Inicio", permiso: P.ver, exacto: true },
  { href: "/innovacion/fuentes", texto: "Fuentes", permiso: P.ver },
  { href: "/innovacion/consultar", texto: "Consultar", permiso: P.consultar },
  { href: "/innovacion/investigar", texto: "Investigar en internet", permiso: P.investigar },
  { href: "/innovacion/expedientes", texto: "Expedientes", permiso: P.expVer },
  { href: "/innovacion/reglas", texto: "Reglas", permiso: P.ver },
  { href: "/innovacion/ingredientes", texto: "Ingredientes", permiso: P.ver },
];

export function MenuModulo() {
  const ruta = usePathname();
  const { puede } = useSesion();
  return (
    <nav aria-label="Secciones de Innovación Vidanat" className="mb-6 -mx-1 flex gap-1 overflow-x-auto pb-1">
      {SECCIONES.filter((s) => puede(s.permiso)).map((s) => {
        const activa = s.exacto ? ruta === s.href : ruta.startsWith(s.href);
        return (
          <Link
            key={s.href}
            href={s.href}
            aria-current={activa ? "page" : undefined}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition ${activa ? "bg-tinta text-superficie" : "text-smn-gris-700 hover:bg-smn-gris-100"}`}
          >
            {s.texto}
          </Link>
        );
      })}
    </nav>
  );
}

export function Volver({ href, texto }: { href: string; texto: string }) {
  return (
    <Link href={href} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
      <ArrowLeft className="h-4 w-4" /> {texto}
    </Link>
  );
}

export function SinAcceso({ texto = "No tienes acceso a esta parte de Innovación Vidanat." }: { texto?: string }) {
  return <p className="text-smn-gris-500">{texto}</p>;
}

export function ChipClasificacion({ valor }: { valor: string }) {
  const c = CLASIFICACION[valor] ?? CLASIFICACION.general;
  if (valor === "general") return null;
  return (
    <Insignia className={c.clase}>
      <Lock className="mr-1 h-3 w-3" aria-hidden /> {c.texto}
    </Insignia>
  );
}

export function ChipFuente({ estado }: { estado: string }) {
  const c = ESTADO_FUENTE[estado] ?? { texto: estado, clase: "bg-smn-gris-100 text-smn-gris-700" };
  return <Insignia className={c.clase}>{c.texto}</Insignia>;
}

export function ChipResultado({ valor }: { valor: string }) {
  const c = RESULTADO[valor] ?? { texto: valor, clase: "bg-smn-gris-100 text-smn-gris-700" };
  return <Insignia className={c.clase}>{c.texto}</Insignia>;
}

export function Texto({
  etiqueta,
  valor,
  cambiar,
  filas = 3,
  ayuda,
  ...resto
}: { etiqueta: string; valor: string; cambiar: (v: string) => void; filas?: number; ayuda?: string } & Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value">) {
  return (
    <label className="block">
      <span className={ETIQUETA}>{etiqueta}</span>
      <textarea rows={filas} value={valor} onChange={(e) => cambiar(e.target.value)} className={`${AREA} resize-y`} {...resto} />
      {ayuda && <span className="mt-1 block text-[13px] text-smn-gris-500">{ayuda}</span>}
    </label>
  );
}

// Resumen de una evaluación: cuántas reglas cumplen, fallan o están pendientes.
export function BarraResumen({ resumen }: { resumen: Record<string, number> | null | undefined }) {
  if (!resumen) return <span className="text-sm text-smn-gris-500">Sin evaluar</span>;
  const orden = ["incumple", "pendiente", "cumple", "no_aplica"] as const;
  const total = orden.reduce((s, k) => s + (resumen[k] ?? 0), 0);
  if (!total) return <span className="text-sm text-smn-gris-500">Sin reglas publicadas que apliquen</span>;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-smn-gris-700">
      {orden.filter((k) => resumen[k]).map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${RESULTADO[k].punto}`} aria-hidden /> {resumen[k]} {RESULTADO[k].texto.toLowerCase()}
        </span>
      ))}
    </div>
  );
}

export function Vacio({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl border border-dashed border-smn-gris-300 p-5 text-center text-sm text-smn-gris-500">{children}</p>;
}
