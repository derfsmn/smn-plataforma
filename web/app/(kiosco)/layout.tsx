"use client";
// Kiosco Digital: pantalla completa, sin el menú de la plataforma. Usa la misma sesión que el portal
// interno (cookie + /api/auth/yo; sin sesión manda a /login) y exige el permiso kiosco.naturi.usar.

import Image from "next/image";
import Link from "next/link";
import { MotionConfig } from "motion/react";
import { LogOut, Lock } from "lucide-react";
import { ProveedorAvisos } from "@/componentes/avisos";
import { ProveedorSesion, useSesion } from "@/componentes/sesion";
import { Boton } from "@/componentes/ui";
import { PERMISO_KIOSCO } from "@/lib/kiosco";

function ConPermiso({ children }: { children: React.ReactNode }) {
  const { puede, salir } = useSesion();
  if (puede(PERMISO_KIOSCO)) return <>{children}</>;
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-16 items-center bg-smn-negro px-4 sm:px-6">
        <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-40" priority />
      </header>
      <main className="grid flex-1 place-items-center p-6">
        <div className="w-full max-w-md rounded-2xl border border-smn-gris-100 bg-superficie p-8 text-center shadow-sm">
          <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-smn-gris-100 bg-superficie text-smn-naranja">
            <Lock className="h-7 w-7" aria-hidden />
          </span>
          <h1 className="mt-5 text-xl font-semibold">No tienes acceso al Kiosco Digital</h1>
          <p className="mt-2 text-sm text-smn-gris-500">
            Tu cuenta no tiene el permiso para usar a Naturi en el kiosco. Pide a un administrador que te asigne un rol con ese permiso.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Link
              href="/inicio"
              className="inline-flex items-center justify-center rounded-xl border border-smn-gris-300 px-4 py-2.5 text-sm font-semibold hover:border-tinta"
            >
              Ir al inicio
            </Link>
            <Boton onClick={salir}>
              <LogOut className="h-4 w-4" aria-hidden /> Salir
            </Boton>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function LayoutKiosco({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorAvisos>
        <ProveedorSesion tipo="interno">
          <ConPermiso>{children}</ConPermiso>
        </ProveedorSesion>
      </ProveedorAvisos>
    </MotionConfig>
  );
}
