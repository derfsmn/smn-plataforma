"use client";
// Avisos emergentes (toasts) y franja de "datos de ejemplo"

import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, FlaskConical, Info } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { urlApi } from "@/lib/api";

type Aviso = { id: number; texto: string; tipo: "exito" | "info" };
const ContextoAvisos = createContext<(texto: string, tipo?: Aviso["tipo"]) => void>(() => {});

export function ProveedorAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const avisar = useCallback((texto: string, tipo: Aviso["tipo"] = "exito") => {
    const id = Date.now() + Math.random();
    setAvisos((a) => [...a, { id, texto, tipo }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), 3500);
  }, []);

  return (
    <ContextoAvisos.Provider value={avisar}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 lg:bottom-6 lg:items-end lg:pr-6" aria-live="polite">
        <AnimatePresence>
          {avisos.map((a) => (
            <motion.div
              key={a.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.96 }}
              transition={{ duration: 0.25 }}
              className="pointer-events-auto flex max-w-sm items-center gap-3 rounded-2xl border border-white/10 bg-smn-negro px-4 py-3 text-sm text-white shadow-xl"
            >
              {a.tipo === "exito" ? <CheckCircle2 className="h-5 w-5 shrink-0 text-smn-naranja" /> : <Info className="h-5 w-5 shrink-0 text-smn-naranja" />}
              {a.texto}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ContextoAvisos.Provider>
  );
}

export const useAvisos = () => useContext(ContextoAvisos);

// Franja visible mientras la plataforma corre en el entorno de desarrollo
let entornoEnCache: string | null = null;

export function FranjaEntorno() {
  const [entorno, setEntorno] = useState(entornoEnCache);
  useEffect(() => {
    if (entornoEnCache) return;
    fetch(`${urlApi()}/api/salud`)
      .then((r) => r.json())
      .then((d) => setEntorno((entornoEnCache = d.entorno)))
      .catch(() => {});
  }, []);
  if (entorno !== "desarrollo") return null;
  return (
    <div className="flex items-center justify-center gap-2 bg-aviso-fondo px-4 py-1.5 text-center text-[13px] font-semibold text-aviso-texto">
      <FlaskConical className="h-3.5 w-3.5 shrink-0" aria-hidden />
      Entorno de desarrollo: los datos viven en la base de pruebas de tu equipo.
    </div>
  );
}
