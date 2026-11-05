"use client";
// Marco de las pantallas sin sesión (invitación, crear y restablecer contraseña): el mismo panel de marca y la misma
// columna del formulario que el inicio de sesión aprobado.

import Image from "next/image";
import { motion, MotionConfig } from "motion/react";
import { FranjaEntorno } from "./avisos";
import { SelectorTema } from "./selector-tema";
import { PanelMarca, Reticula } from "./panel-marca";

export function PantallaPublica({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col font-sobria">
        <FranjaEntorno />
        <div className="grid flex-1 lg:grid-cols-[1.05fr_1fr]">
          <PanelMarca />
          <section className="relative flex flex-col overflow-hidden bg-superficie">
            <Reticula className="text-smn-gris-100 [mask-image:radial-gradient(ellipse_at_top,black,transparent_65%)]" />
            <header className="relative flex items-center justify-between px-5 pt-5 sm:px-8">
              <span className="lg:invisible">
                <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-40 dark:hidden" priority />
                <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-40 dark:block" priority />
              </span>
              <SelectorTema />
            </header>
            <main className="relative flex flex-1 items-start justify-center px-5 py-10 sm:items-center sm:px-8">
              <motion.div className="w-full max-w-[420px]" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
                {children}
              </motion.div>
            </main>
          </section>
        </div>
      </div>
    </MotionConfig>
  );
}
