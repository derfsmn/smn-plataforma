"use client";
// Selector Claro / Oscuro / Automático. "compacto" para barras; "tarjetas" para la página de perfil.

import { motion } from "motion/react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { cambiarTema, escucharTema, leerPreferencia, type Preferencia } from "@/lib/tema";

const opciones: { valor: Preferencia; texto: string; icono: typeof Sun }[] = [
  { valor: "claro", texto: "Claro", icono: Sun },
  { valor: "oscuro", texto: "Oscuro", icono: Moon },
  { valor: "sistema", texto: "Automático", icono: Monitor },
];

function usePreferencia() {
  const [pref, setPref] = useState<Preferencia | null>(null);
  useEffect(() => {
    setPref(leerPreferencia());
    return escucharTema(setPref);
  }, []);
  return pref;
}

const elegir = (valor: Preferencia, e: React.MouseEvent) => {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  cambiarTema(valor, { x: r.left + r.width / 2, y: r.top + r.height / 2 });
};

export function SelectorTema({ sobreOscuro = false }: { sobreOscuro?: boolean }) {
  const pref = usePreferencia();
  const id = useId();
  return (
    <div role="radiogroup" aria-label="Tema" className={`flex rounded-full p-0.5 ${sobreOscuro ? "bg-white/10" : "bg-smn-gris-100"}`}>
      {opciones.map(({ valor, texto, icono: Icono }) => {
        const activo = pref === valor;
        return (
          <button
            key={valor}
            role="radio"
            aria-checked={activo}
            aria-label={texto}
            title={texto}
            onClick={(e) => elegir(valor, e)}
            className={`relative grid h-7 w-7 place-items-center rounded-full transition-colors ${
              activo ? (sobreOscuro ? "text-smn-negro" : "text-tinta") : sobreOscuro ? "text-white/60 hover:text-white" : "text-smn-gris-500 hover:text-tinta"
            }`}
          >
            {activo && (
              <motion.span layoutId={`tema-${id}`} className={`absolute inset-0 rounded-full shadow-sm ${sobreOscuro ? "bg-smn-naranja" : "bg-superficie"}`} transition={{ type: "spring", stiffness: 500, damping: 40 }} />
            )}
            <Icono className="relative h-3.5 w-3.5" />
          </button>
        );
      })}
    </div>
  );
}

export function TarjetasTema() {
  const pref = usePreferencia();
  return (
    <div className="grid grid-cols-3 gap-3">
      {opciones.map(({ valor, texto, icono: Icono }) => {
        const activo = pref === valor;
        const muestra =
          valor === "claro" ? "bg-[#f6f6f5]" : valor === "oscuro" ? "bg-[#141413]" : "bg-[linear-gradient(135deg,#f6f6f5_50%,#141413_50%)]";
        return (
          <motion.button
            key={valor}
            whileTap={{ scale: 0.97 }}
            onClick={(e) => elegir(valor, e)}
            aria-pressed={activo}
            className={`overflow-hidden rounded-2xl border-2 text-left transition-colors ${activo ? "border-smn-naranja" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
          >
            <div className={`relative h-16 ${muestra}`}>
              <span className="absolute top-3 left-3 h-2 w-10 rounded-full bg-smn-naranja" />
              <span className="absolute top-7 left-3 h-2 w-14 rounded-full bg-[#8a8a86]/50" />
            </div>
            <span className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold sm:text-sm">
              <Icono className="hidden h-4 w-4 shrink-0 sm:block" /> {texto}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
