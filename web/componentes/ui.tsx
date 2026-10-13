"use client";
// Piezas visuales básicas del cascarón. Cualquier módulo las reutiliza.

import { motion, type HTMLMotionProps } from "motion/react";
import { Loader2 } from "lucide-react";

type BotonProps = HTMLMotionProps<"button"> & {
  variante?: "primario" | "secundario" | "fantasma";
  cargando?: boolean;
};

export function Boton({ variante = "primario", cargando, className = "", children, disabled, ...resto }: BotonProps) {
  const estilos = {
    primario: "bg-smn-naranja text-smn-negro hover:brightness-105 shadow-sm shadow-smn-naranja/30",
    secundario: "bg-superficie text-tinta border border-smn-gris-300 hover:border-tinta",
    fantasma: "text-smn-gris-700 hover:bg-smn-gris-100",
  }[variante];
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      disabled={disabled || cargando}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-colors disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja ${estilos} ${className}`}
      {...resto}
    >
      {cargando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children as React.ReactNode}
    </motion.button>
  );
}

export function Insignia({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${className}`}>{children}</span>;
}

export function Campo({
  etiqueta,
  error,
  ...resto
}: React.InputHTMLAttributes<HTMLInputElement> & { etiqueta: string; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">{etiqueta}</span>
      <input
        className={`w-full rounded-xl border bg-superficie px-3.5 py-2.5 text-base outline-none transition-shadow placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20 ${
          error ? "border-red-400" : "border-smn-gris-300"
        }`}
        {...resto}
      />
      {error && <span className="mt-1 block text-sm text-red-600">{error}</span>}
    </label>
  );
}

export function Esqueleto({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-smn-gris-100 ${className}`} />;
}

// Aparición suave al entrar a una página o sección
export function Entrada({ children, retraso = 0, className = "" }: { children: React.ReactNode; retraso?: number; className?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: retraso, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function Encabezado({ titulo, descripcion, accion }: { titulo: string; descripcion?: string; accion?: React.ReactNode }) {
  return (
    <Entrada className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{titulo}</h1>
        {descripcion && <p className="mt-1 text-smn-gris-500">{descripcion}</p>}
      </div>
      {accion}
    </Entrada>
  );
}
