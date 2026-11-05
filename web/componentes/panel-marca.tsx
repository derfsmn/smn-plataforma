"use client";
// Panel oscuro de marca del inicio de sesión (aprobado el 1 nov 2026). Lo usan también las pantallas sin sesión
// (invitación, crear y restablecer contraseña) para que se vean igual que el inicio de sesión.

import Image from "next/image";
import { motion, useMotionTemplate, useMotionValue, useSpring } from "motion/react";
import { BookOpenCheck, Database, FileSpreadsheet, ShoppingBasket } from "lucide-react";
import { useEffect, useState } from "react";

// Áreas que ya viven en la plataforma (se iluminan una por una en el panel de marca)
const areas = [
  { nombre: "Compras", detalle: "Radar de precios, productos nuevos y proveedores", icono: ShoppingBasket },
  { nombre: "Datos", detalle: "Tiendas, salud de inventario y ventas", icono: Database },
  { nombre: "Contraloría", detalle: "DIOT con revisión paso a paso", icono: FileSpreadsheet },
  { nombre: "Métodos", detalle: "Manuales, diagramas de flujo y respuestas con cita", icono: BookOpenCheck },
];

export function PanelMarca() {
  const [activa, setActiva] = useState(0);
  const x = useMotionValue(-400);
  const y = useMotionValue(-400);
  const sx = useSpring(x, { stiffness: 120, damping: 20 });
  const sy = useSpring(y, { stiffness: 120, damping: 20 });
  const luz = useMotionTemplate`radial-gradient(520px circle at ${sx}px ${sy}px, rgba(222,149,27,0.16), transparent 60%)`;

  useEffect(() => {
    const t = setInterval(() => setActiva((a) => (a + 1) % areas.length), 2800);
    return () => clearInterval(t);
  }, []);

  return (
    <section
      className="relative hidden overflow-hidden bg-[#0d0d0c] p-12 text-white lg:flex lg:flex-col lg:justify-between xl:p-16"
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        x.set(e.clientX - r.left);
        y.set(e.clientY - r.top);
      }}
    >
      <Reticula className="text-white/[0.06] [mask-image:radial-gradient(ellipse_at_30%_40%,black,transparent_75%)]" />
      <motion.div aria-hidden className="pointer-events-none absolute inset-0" style={{ background: luz }} />
      <div aria-hidden className="pointer-events-none absolute -top-48 -left-40 h-[34rem] w-[34rem] rounded-full bg-smn-naranja/20 blur-[120px]" />
      {/* línea de luz que recorre el borde derecho */}
      <div aria-hidden className="absolute inset-y-0 right-0 w-px bg-white/10">
        <motion.div
          className="absolute left-0 h-40 w-px bg-gradient-to-b from-transparent via-smn-naranja to-transparent"
          animate={{ top: ["-20%", "110%"] }}
          transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
        />
      </div>

      <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="relative h-auto w-56" priority />

      <div className="relative max-w-lg">
        <motion.p
          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[13px] font-medium text-white/70"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.05 }}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-smn-naranja opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-smn-naranja" />
          </span>
          Transformación Digital
        </motion.p>
        <motion.h2
          className="mt-5 text-[44px] leading-[1.05] font-semibold tracking-[-0.035em] xl:text-5xl"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
        >
          Todas las iniciativas de SMN{" "}
          <span className="bg-gradient-to-r from-[#f3c06a] via-smn-naranja to-[#b8730c] bg-clip-text text-transparent">en un solo lugar.</span>
        </motion.h2>

        <motion.ul
          className="mt-10 space-y-1"
          initial="oculto"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.07, delayChildren: 0.3 } } }}
        >
          {areas.map(({ nombre, detalle, icono: Icono }, i) => (
            <motion.li
              key={nombre}
              variants={{ oculto: { opacity: 0, x: -8 }, visible: { opacity: 1, x: 0 } }}
              onMouseEnter={() => setActiva(i)}
              className="relative flex items-center gap-3.5 rounded-lg px-3 py-2.5"
            >
              {activa === i && (
                <motion.span
                  layoutId="area-activa"
                  className="absolute inset-0 rounded-lg border border-white/10 bg-white/[0.05]"
                  transition={{ type: "spring", stiffness: 300, damping: 32 }}
                />
              )}
              <span
                className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-md border transition-colors duration-500 ${
                  activa === i ? "border-smn-naranja/50 bg-smn-naranja/15 text-smn-naranja" : "border-white/10 text-white/50"
                }`}
              >
                <Icono className="h-4 w-4" />
              </span>
              <span className="relative min-w-0">
                <span className={`block text-sm font-medium transition-colors duration-500 ${activa === i ? "text-white" : "text-white/70"}`}>{nombre}</span>
                <span className="block truncate text-[13px] text-white/45">{detalle}</span>
              </span>
            </motion.li>
          ))}
        </motion.ul>
      </div>

      <p className="relative text-[13px] text-white/35">Plataforma interna · Súper Mayoreo Naturista</p>
    </section>
  );
}

export function Reticula({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 ${className}`}
      style={{
        backgroundImage: "linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)",
        backgroundSize: "44px 44px",
      }}
    />
  );
}

