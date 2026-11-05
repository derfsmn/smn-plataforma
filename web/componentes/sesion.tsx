"use client";
// Sesión real: se pide a la API (/api/auth/yo). La cookie la maneja el navegador.

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ErrorApi, mensajeDe, type Yo } from "@/lib/api";
import { Boton } from "./ui";

type ContextoSesion = { yo: Yo; recargar: () => Promise<void>; salir: () => Promise<void>; puede: (permiso: string) => boolean };
const Contexto = createContext<ContextoSesion | null>(null);

export function useSesion() {
  const c = useContext(Contexto);
  if (!c) throw new Error("useSesion fuera de ProveedorSesion");
  return c;
}

export const destinoDe = (yo: Yo) => (yo.usuario.tipo === "externo" ? "/proveedores" : "/inicio");

export function ProveedorSesion({ tipo, children }: { tipo: "interno" | "externo"; children: React.ReactNode }) {
  const router = useRouter();
  const ruta = usePathname();
  const [yo, setYo] = useState<Yo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recargar = useCallback(async () => {
    try {
      setError(null);
      const datos = await api<Yo>("/api/auth/yo");
      if (datos.usuario.tipo !== tipo) return router.replace(destinoDe(datos));
      setYo(datos);
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 401) router.replace(`/login?volver=${encodeURIComponent(ruta)}`);
      else setError(mensajeDe(e));
    }
  }, [router, ruta, tipo]);

  useEffect(() => {
    recargar();
    // solo al montar; las páginas llaman recargar() cuando cambian permisos
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const salir = useCallback(async () => {
    await api("/api/auth/salir", { metodo: "POST" }).catch(() => {});
    router.replace("/login");
  }, [router]);

  if (error)
    return (
      <div className="grid min-h-screen place-items-center p-6 text-center">
        <div>
          <p className="font-semibold">{error}</p>
          <Boton className="mt-4" onClick={recargar}>Reintentar</Boton>
        </div>
      </div>
    );
  if (!yo) return <div className="min-h-screen" />;

  return (
    <Contexto.Provider value={{ yo, recargar, salir, puede: (p) => yo.permisos.includes(p) }}>
      {children}
    </Contexto.Provider>
  );
}
