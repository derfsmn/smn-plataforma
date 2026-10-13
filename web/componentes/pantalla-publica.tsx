"use client";
// Marco de las pantallas sin sesión (invitación, restablecer contraseña)

import Image from "next/image";
import { motion, MotionConfig } from "motion/react";
import { FranjaEntorno } from "./avisos";
import { SelectorTema } from "./selector-tema";

export function PantallaPublica({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col">
        <FranjaEntorno />
        <div className="flex justify-end p-4">
          <SelectorTema />
        </div>
        <main className="flex flex-1 items-start justify-center px-5 pb-16 sm:items-center">
          <motion.div className="w-full max-w-md" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="mb-8 h-auto w-52 dark:hidden" priority />
            <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="mb-8 hidden h-auto w-52 dark:block" priority />
            {children}
          </motion.div>
        </main>
      </div>
    </MotionConfig>
  );
}
