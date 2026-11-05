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
    primario: "bg-[var(--resalte)] text-[var(--resalte-tinta)] hover:brightness-105",
    secundario: "bg-superficie text-tinta border border-smn-gris-100 hover:border-smn-gris-300",
    fantasma: "text-smn-gris-700 hover:bg-smn-gris-50 hover:text-tinta",
  }[variante];
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      disabled={disabled || cargando}
      className={`inline-flex items-center justify-center gap-2 min-h-10 rounded-lg px-4 py-2 text-[15px] font-medium transition-colors disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja ${estilos} ${className}`}
      {...resto}
    >
      {cargando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children as React.ReactNode}
    </motion.button>
  );
}

export function Insignia({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[13px] font-medium ${className}`}>{children}</span>;
}

export function Campo({
  etiqueta,
  error,
  ...resto
}: React.InputHTMLAttributes<HTMLInputElement> & { etiqueta: string; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">{etiqueta}</span>
      <input
        className={`h-11 w-full rounded-lg border bg-superficie px-3.5 text-[15px] outline-none transition-shadow placeholder:text-smn-gris-500 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15 ${
          error ? "border-red-400" : "border-smn-gris-100 hover:border-smn-gris-300"
        }`}
        {...resto}
      />
      {error && <span className="mt-1 block text-sm text-red-700">{error}</span>}
    </label>
  );
}

export function Selector({
  etiqueta,
  valor,
  cambiar,
  opciones,
  className = "",
}: {
  etiqueta: string;
  valor: string;
  cambiar: (v: string) => void;
  opciones: { valor: string; texto: string }[];
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">{etiqueta}</span>
      <select
        value={valor}
        onChange={(e) => cambiar(e.target.value)}
        className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
      >
        {opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Esqueleto({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-smn-gris-100 ${className}`} />;
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
    <Entrada className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{titulo}</h1>
        {descripcion && <p className="mt-2 max-w-2xl text-[16px] leading-relaxed text-smn-gris-700">{descripcion}</p>}
      </div>
      {accion}
    </Entrada>
  );
}
