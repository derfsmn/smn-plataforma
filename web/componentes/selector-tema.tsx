"use client";
// Selector Claro / Oscuro / Automático. "compacto" para barras; "tarjetas" para la página de perfil.

import { motion } from "motion/react";
import { Check, Monitor, Moon, Palette, Sun } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { cambiarColor, cambiarTema, COLORES, escucharTema, leerColor, leerPreferencia, type Preferencia } from "@/lib/tema";

const opciones: { valor: Preferencia; texto: string; icono: typeof Sun }[] = [
  { valor: "claro", texto: "Claro", icono: Sun },
  { valor: "oscuro", texto: "Oscuro", icono: Moon },
  { valor: "marca", texto: "Con color (elige el tuyo)", icono: Palette },
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

// sinColor: el portal de proveedores no ofrece el tema «Con color» (decisión del 1 nov 2026)
export function SelectorTema({ sobreOscuro = false, sinColor = false }: { sobreOscuro?: boolean; sinColor?: boolean }) {
  const pref = usePreferencia();
  const id = useId();
  const [paleta, setPaleta] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!paleta) return;
    const cerrar = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setPaleta(false);
    };
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && setPaleta(false);
    document.addEventListener("mousedown", cerrar);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", cerrar);
      document.removeEventListener("keydown", tecla);
    };
  }, [paleta]);

  return (
    <div ref={ref} className="relative">
      <div role="radiogroup" aria-label="Tema" className={`flex rounded-full p-0.5 ${sobreOscuro ? "bg-white/10" : "bg-smn-gris-100"}`}>
        {opciones.filter((o) => !(sinColor && o.valor === "marca")).map(({ valor, texto, icono: Icono }) => {
          const activo = pref === valor;
          return (
            <button
              key={valor}
              role="radio"
              aria-checked={activo}
              aria-label={texto}
              title={texto}
              onClick={(e) => {
                elegir(valor, e);
                setPaleta(valor === "marca");
              }}
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
      {paleta && <ElegirColor />}
    </div>
  );
}

function ElegirColor() {
  const [color, setColor] = useState(COLORES[0].valor);
  useEffect(() => setColor(leerColor()), []);
  const poner = (c: string) => {
    setColor(c.toLowerCase());
    cambiarColor(c);
  };
  const propio = !COLORES.some((c) => c.valor === color);
  return (
    <motion.div
      initial={{ opacity: 0, y: -4, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.12 }}
      className="absolute right-0 z-40 mt-2 w-64 origin-top-right rounded-xl border border-smn-gris-100 bg-superficie p-3 font-sobria shadow-xl shadow-black/10"
    >
      <p className="text-sm font-medium text-tinta">Color del menú</p>
      <p className="mt-0.5 text-[13px] text-smn-gris-500">Solo cambia cómo la ves tú.</p>
      <div className="mt-3 grid grid-cols-4 gap-2">
        {COLORES.map((c) => (
          <button
            key={c.valor}
            onClick={() => poner(c.valor)}
            title={c.texto}
            aria-label={c.texto}
            aria-pressed={color === c.valor}
            className="grid h-10 place-items-center rounded-lg ring-offset-2 ring-offset-superficie transition-transform hover:scale-105 aria-pressed:ring-2 aria-pressed:ring-tinta"
            style={{ background: c.valor }}
          >
            {color === c.valor && <Check className="h-4 w-4 text-white drop-shadow-[0_1px_1px_rgba(0,0,0,0.5)]" />}
          </button>
        ))}
      </div>
      <label className={`mt-3 flex cursor-pointer items-center gap-3 rounded-lg border px-2.5 py-2 text-sm transition-colors hover:border-smn-gris-300 ${propio ? "border-tinta" : "border-smn-gris-100"}`}>
        <input type="color" value={color} onChange={(e) => poner(e.target.value)} className="h-7 w-9 cursor-pointer rounded border-0 bg-transparent p-0" />
        <span className="text-tinta">Otro color</span>
        <span className="ml-auto font-mono text-[13px] text-smn-gris-500 uppercase">{color}</span>
      </label>
    </motion.div>
  );
}

export function TarjetasTema() {
  const pref = usePreferencia();
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {opciones.map(({ valor, texto, icono: Icono }) => {
        const activo = pref === valor;
        const muestra =
          valor === "claro" ? "bg-[#f6f6f5]" : valor === "oscuro" ? "bg-[#141413]" : valor === "marca" ? "bg-[linear-gradient(90deg,var(--acento)_30%,#faf8f4_30%)]" : "bg-[linear-gradient(135deg,#f6f6f5_50%,#141413_50%)]";
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
            <span className="flex items-center gap-1.5 px-3 py-2 text-[13px] font-semibold sm:text-sm">
              <Icono className="hidden h-4 w-4 shrink-0 sm:block" /> {texto}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
