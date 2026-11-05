"use client";
// Cascarón del portal de proveedores (externos) con el diseño sobrio: barra clara con logo, tema, campana y salir.
// El portal no usa el tema «Con color»: si el navegador lo trae guardado, aquí se ve en claro sin cambiar lo guardado.

import Image from "next/image";
import Link from "next/link";
import { MotionConfig } from "motion/react";
import { LogOut } from "lucide-react";
import { useEffect } from "react";
import { FranjaEntorno, ProveedorAvisos } from "./avisos";
import { ProveedorSesion, useSesion } from "./sesion";
import { SelectorTema } from "./selector-tema";
import { Campana } from "./campana";

export function MarcoProveedor({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorAvisos>
        <ProveedorSesion tipo="externo">
          <Marco>{children}</Marco>
        </ProveedorSesion>
      </ProveedorAvisos>
    </MotionConfig>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  const { salir } = useSesion();
  useEffect(() => {
    const raiz = document.documentElement;
    const quitarColor = () => raiz.dataset.tema === "marca" && (raiz.dataset.tema = "claro");
    quitarColor();
    const o = new MutationObserver(quitarColor);
    o.observe(raiz, { attributes: true, attributeFilter: ["data-tema"] });
    return () => o.disconnect();
  }, []);
  return (
    <div className="min-h-screen font-sobria">
      <header className="sticky top-0 z-20 border-b border-smn-gris-100 bg-superficie/90 backdrop-blur">
        <FranjaEntorno />
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6">
          <Link href="/proveedores" aria-label="Inicio del portal" className="flex items-center gap-3">
            <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-36 sm:w-40 dark:hidden" priority />
            <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-36 sm:w-40 dark:block" priority />
            <span className="hidden border-l border-smn-gris-100 pl-3 text-[15px] text-smn-gris-500 md:block">Portal de proveedores</span>
          </Link>
          <div className="flex items-center gap-1.5 sm:gap-3">
            <SelectorTema sinColor />
            <Campana />
            <button onClick={salir} className="flex h-10 items-center gap-1.5 rounded-lg px-3 text-[15px] text-smn-gris-700 hover:bg-smn-gris-50 hover:text-tinta">
              <LogOut className="h-4 w-4" /> Salir
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">{children}</main>
    </div>
  );
}
