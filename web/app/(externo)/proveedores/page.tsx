"use client";
// Portal de proveedores (externo). Solo ve sus propias solicitudes.

import Image from "next/image";
import { motion, MotionConfig } from "motion/react";
import { FilePlus2, LogOut, PackageSearch } from "lucide-react";
import { FranjaEntorno, ProveedorAvisos, useAvisos } from "@/componentes/avisos";
import { ProveedorSesion, useSesion } from "@/componentes/sesion";
import { SelectorTema } from "@/componentes/selector-tema";
import { Entrada } from "@/componentes/ui";

export default function PortalProveedores() {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorAvisos>
        <ProveedorSesion tipo="externo">
          <Portal />
        </ProveedorSesion>
      </ProveedorAvisos>
    </MotionConfig>
  );
}

function Portal() {
  const { yo, salir } = useSesion();
  const avisar = useAvisos();
  const u = yo.usuario;
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 bg-smn-negro">
        <FranjaEntorno />
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-36 sm:w-44" priority />
          <div className="flex items-center gap-3">
            <span className="hidden text-sm font-semibold text-white/70 md:block">Portal de proveedores</span>
            <SelectorTema sobreOscuro />
            <button onClick={salir} className="flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold text-white hover:bg-white/10">
              <LogOut className="h-4 w-4" /> Salir
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <Entrada>
          <p className="text-sm font-bold tracking-widest text-smn-naranja uppercase">Bienvenido</p>
          <h1 className="mt-1 text-2xl font-extrabold sm:text-3xl">{u.empresa ?? u.nombre}</h1>
          <p className="mt-1 text-sm text-smn-gris-500">{u.nombre} · {u.correo}</p>
          <p className="mt-3 text-smn-gris-500">Desde aquí propones productos nuevos a Súper Naturista y das seguimiento a tus solicitudes.</p>
        </Entrada>
        <Entrada retraso={0.1} className="mt-8 grid gap-4 sm:grid-cols-2">
          <motion.button
            whileHover={{ y: -4 }}
            onClick={() => avisar("El formulario de producto nuevo llega con el módulo de Compras.", "info")}
            className="group flex flex-col items-start rounded-3xl bg-smn-naranja p-6 text-left text-smn-negro shadow-lg shadow-smn-naranja/20"
          >
            <FilePlus2 className="h-8 w-8 transition-transform group-hover:scale-110" />
            <span className="mt-6 text-xl font-extrabold">Proponer producto nuevo</span>
            <span className="mt-1 text-sm text-smn-negro/70">Llena la ficha y adjunta tus documentos.</span>
          </motion.button>
          <div className="flex flex-col items-start rounded-3xl border border-smn-gris-100 bg-superficie p-6">
            <PackageSearch className="h-8 w-8 text-smn-gris-500" />
            <span className="mt-6 text-xl font-extrabold">Mis solicitudes</span>
            <span className="mt-1 text-sm text-smn-gris-500">Aún no tienes solicitudes enviadas.</span>
          </div>
        </Entrada>
      </main>
    </div>
  );
}
