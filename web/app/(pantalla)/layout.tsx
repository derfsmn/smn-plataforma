"use client";
// Pantallas para dejar abiertas en una tele o un segundo monitor (Monitor de la plataforma, 26 nov 2026): sin el menú de
// la plataforma, con la misma sesión del portal interno.

import Link from "next/link";
import { ProveedorAvisos } from "@/componentes/avisos";
import { ProveedorSesion, useSesion } from "@/componentes/sesion";

const PERMISO = "nucleo.bitacora.ver";

function ConPermiso({ children }: { children: React.ReactNode }) {
  const { puede } = useSesion();
  if (puede(PERMISO)) return <>{children}</>;
  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-smn-gris-100 bg-superficie p-8 text-center">
        <h1 className="text-xl font-semibold">No tienes acceso al Monitor</h1>
        <p className="mt-2 text-sm text-smn-gris-500">Pide a un administrador el permiso para ver la bitácora del sistema.</p>
        <Link href="/inicio" className="mt-6 inline-flex rounded-xl border border-smn-gris-300 px-4 py-2.5 text-sm font-semibold hover:border-tinta">
          Ir al inicio
        </Link>
      </div>
    </main>
  );
}

export default function LayoutPantalla({ children }: { children: React.ReactNode }) {
  return (
    <ProveedorAvisos>
      <ProveedorSesion tipo="interno">
        <ConPermiso>{children}</ConPermiso>
      </ProveedorSesion>
    </ProveedorAvisos>
  );
}
