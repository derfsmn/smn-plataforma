"use client";

import { motion } from "motion/react";
import { X } from "lucide-react";
import { useEffect } from "react";

// Ventana: hoja inferior en celular, centrada en escritorio. Envolver en <AnimatePresence>.
export function Modal({ titulo, cerrar, children }: { titulo: string; cerrar: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [cerrar]);
  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end justify-center bg-smn-negro/50 backdrop-blur-sm sm:items-center sm:p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={cerrar}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        onClick={(e) => e.stopPropagation()}
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 40, opacity: 0 }}
        transition={{ type: "spring", stiffness: 400, damping: 35 }}
        className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-superficie p-6 shadow-2xl sm:rounded-3xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-extrabold">{titulo}</h2>
          <button type="button" onClick={cerrar} aria-label="Cerrar" className="rounded-full p-1 hover:bg-smn-gris-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </motion.div>
    </motion.div>
  );
}
