"use client";
// Campana de notificaciones de la barra superior. Revisa cada minuto y al volver a la pestaña.

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { Bell, CheckCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, haceCuanto, type Bandeja } from "@/lib/api";

const CADA_MS = 60_000;

export function Campana({ sobreOscuro = false }: { sobreOscuro?: boolean }) {
  const [bandeja, setBandeja] = useState<Bandeja | null>(null);
  const [abierta, setAbierta] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const cargar = useCallback(() => {
    api<Bandeja>("/api/notificaciones").then(setBandeja).catch(() => {});
  }, []);

  useEffect(() => {
    cargar();
    const intervalo = setInterval(() => document.visibilityState === "visible" && cargar(), CADA_MS);
    const alVolver = () => document.visibilityState === "visible" && cargar();
    document.addEventListener("visibilitychange", alVolver);
    const cerrar = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAbierta(false);
    document.addEventListener("mousedown", cerrar);
    return () => {
      clearInterval(intervalo);
      document.removeEventListener("visibilitychange", alVolver);
      document.removeEventListener("mousedown", cerrar);
    };
  }, [cargar]);

  const leer = (id: number) => {
    setBandeja((b) => b && { no_leidas: Math.max(0, b.no_leidas - 1), notificaciones: b.notificaciones.map((n) => (n.id === id ? { ...n, leida: true } : n)) });
    api(`/api/notificaciones/${id}/leer`, { metodo: "POST" }).catch(cargar);
  };
  const leerTodas = () => {
    setBandeja((b) => b && { no_leidas: 0, notificaciones: b.notificaciones.map((n) => ({ ...n, leida: true })) });
    api("/api/notificaciones/leer-todas", { metodo: "POST" }).catch(cargar);
  };

  const pendientes = bandeja?.no_leidas ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          setAbierta((v) => !v);
          if (!abierta) cargar();
        }}
        className={`relative grid h-9 w-9 place-items-center rounded-full transition-colors ${sobreOscuro ? "text-white hover:bg-white/10" : "hover:bg-smn-gris-100"}`}
        aria-label={pendientes ? `Notificaciones, ${pendientes} sin leer` : "Notificaciones"}
        aria-expanded={abierta}
      >
        <motion.span key={pendientes} animate={pendientes ? { rotate: [0, -14, 12, -8, 0] } : {}} transition={{ duration: 0.5 }}>
          <Bell className="h-5 w-5" />
        </motion.span>
        <AnimatePresence>
          {pendientes > 0 && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute -top-0.5 -right-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-smn-naranja px-1 text-[13px] leading-none font-semibold text-smn-negro"
            >
              {pendientes > 9 ? "9+" : pendientes}
            </motion.span>
          )}
        </AnimatePresence>
      </button>

      <AnimatePresence>
        {abierta && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-x-3 top-16 origin-top overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie shadow-xl sm:absolute sm:inset-x-auto sm:top-auto sm:right-0 sm:mt-2 sm:w-96 sm:origin-top-right"
          >
            <div className="flex items-center justify-between border-b border-smn-gris-100 px-4 py-3">
              <p className="text-sm font-semibold">Notificaciones</p>
              {pendientes > 0 && (
                <button onClick={leerTodas} className="flex items-center gap-1 text-[13px] font-medium text-smn-gris-500 hover:text-tinta">
                  <CheckCheck className="h-4 w-4" /> Marcar todo como leído
                </button>
              )}
            </div>
            <ul className="max-h-[60vh] overflow-y-auto">
              {!bandeja?.notificaciones.length && <li className="px-4 py-10 text-center text-sm text-smn-gris-500">No tienes notificaciones.</li>}
              {bandeja?.notificaciones.map((n, i) => {
                const contenido = (
                  <>
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.leida ? "bg-transparent" : "bg-smn-naranja"}`} />
                    <span className="min-w-0 flex-1">
                      <span className={`block text-sm ${n.leida ? "font-semibold text-smn-gris-700" : "font-semibold"}`}>{n.titulo}</span>
                      <span className="mt-0.5 block text-sm text-smn-gris-500">{n.mensaje}</span>
                      <span className="mt-1 block text-[13px] text-smn-gris-500">{haceCuanto(n.enviada_en)}</span>
                    </span>
                  </>
                );
                const clase = "flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-smn-gris-50";
                return (
                  <motion.li key={n.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }}>
                    {n.liga ? (
                      <Link
                        href={n.liga}
                        className={clase}
                        onClick={() => {
                          if (!n.leida) leer(n.id);
                          setAbierta(false);
                        }}
                      >
                        {contenido}
                      </Link>
                    ) : (
                      <button className={clase} onClick={() => !n.leida && leer(n.id)}>
                        {contenido}
                      </button>
                    )}
                  </motion.li>
                );
              })}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
