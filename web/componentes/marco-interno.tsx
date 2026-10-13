"use client";
// Cascarón para usuarios internos: menú lateral (escritorio), barra inferior (celular)
// y barra superior con tema y perfil. El menú se arma con los permisos del usuario.

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { Home, LayoutGrid, Shield, UserRound, LogOut, Users, KeyRound, Boxes, Activity, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { IconoModulo } from "./icono-modulo";
import { FranjaEntorno, ProveedorAvisos } from "./avisos";
import { SelectorTema } from "./selector-tema";
import { ProveedorSesion, useSesion } from "./sesion";

export const iniciales = (nombre: string) =>
  nombre.replace(/\(.*\)/, "").trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

function EnlaceMenu({ href, activo, children }: { href: string; activo: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className={`relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
        activo ? "text-smn-negro" : "text-white/70 hover:bg-white/5 hover:text-white"
      }`}
    >
      {activo && (
        <motion.span layoutId="menu-activo" className="absolute inset-0 rounded-xl bg-smn-naranja" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
      )}
      <span className="relative flex items-center gap-3">{children}</span>
    </Link>
  );
}

export function MarcoInterno({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorAvisos>
        <ProveedorSesion tipo="interno">
          <Marco>{children}</Marco>
        </ProveedorSesion>
      </ProveedorAvisos>
    </MotionConfig>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { yo, salir, puede } = useSesion();
  const [menuPerfil, setMenuPerfil] = useState(false);
  const refPerfil = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cerrar = (e: MouseEvent) => {
      if (refPerfil.current && !refPerfil.current.contains(e.target as Node)) setMenuPerfil(false);
    };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  const admin = [
    puede("nucleo.usuarios.administrar") && { href: "/admin/usuarios", texto: "Usuarios", icono: Users },
    puede("nucleo.roles.administrar") && { href: "/admin/roles", texto: "Roles y permisos", icono: KeyRound },
    puede("nucleo.modulos.administrar") && { href: "/admin/modulos", texto: "Módulos", icono: Boxes },
    puede("nucleo.modulos.administrar") && { href: "/admin/sistema", texto: "Estado del sistema", icono: Activity },
  ].filter(Boolean) as { href: string; texto: string; icono: typeof Users }[];

  const inferior = [
    { href: "/inicio", texto: "Inicio", icono: Home },
    ...(yo.modulos[0] ? [{ href: `/modulos/${yo.modulos[0].codigo}`, texto: "Módulos", icono: LayoutGrid, prefijo: "/modulos" }] : []),
    ...(admin[0] ? [{ href: admin[0].href, texto: "Admin", icono: Shield, prefijo: "/admin" }] : []),
    { href: "/perfil", texto: "Perfil", icono: UserRound },
  ];
  const { usuario } = yo;

  return (
    <div className="min-h-screen lg:pl-64">
      {/* Menú lateral */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-white/5 bg-smn-negro px-4 py-6 lg:flex">
        <Link href="/inicio" className="mb-8 px-2">
          <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-44" priority />
          <span className="mt-2 block text-xs font-semibold tracking-wide text-white/50">Transformación digital</span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto">
          <EnlaceMenu href="/inicio" activo={ruta === "/inicio"}>
            <Home className="h-4 w-4" /> Inicio
          </EnlaceMenu>
          {yo.modulos.length > 0 && <p className="mt-5 mb-1 px-3 text-[11px] font-bold tracking-widest text-white/40 uppercase">Iniciativas</p>}
          {yo.modulos.map((m) => (
            <EnlaceMenu key={m.codigo} href={`/modulos/${m.codigo}`} activo={ruta === `/modulos/${m.codigo}`}>
              <IconoModulo icono={m.icono} className="h-4 w-4" /> {m.area}
            </EnlaceMenu>
          ))}
          {admin.length > 0 && (
            <>
              <p className="mt-5 mb-1 px-3 text-[11px] font-bold tracking-widest text-white/40 uppercase">Administración</p>
              {admin.map(({ href, texto, icono: Icono }) => (
                <EnlaceMenu key={href} href={href} activo={ruta === href}>
                  <Icono className="h-4 w-4" /> {texto}
                </EnlaceMenu>
              ))}
            </>
          )}
        </nav>
      </aside>

      {/* Barra superior */}
      <header className="sticky top-0 z-20 border-b border-smn-gris-100 bg-superficie/85 backdrop-blur-md">
        <FranjaEntorno />
        <div className="flex h-14 items-center justify-between px-4 sm:px-6">
          <Link href="/inicio" className="lg:hidden">
            <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-36 dark:hidden" priority />
            <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-36 dark:block" priority />
          </Link>
          <span className="hidden text-sm font-semibold text-smn-gris-500 lg:block">SMN - Transformación digital</span>
          <div className="flex items-center gap-2 sm:gap-3">
            <SelectorTema />
            <div className="relative" ref={refPerfil}>
              <button
                onClick={() => setMenuPerfil((v) => !v)}
                className="flex items-center gap-2 rounded-full p-1 pr-2 transition-colors hover:bg-smn-gris-100"
                aria-expanded={menuPerfil}
                aria-label="Menú de perfil"
              >
                <span className="grid h-8 w-8 place-items-center rounded-full bg-smn-naranja text-xs font-extrabold text-smn-negro">{iniciales(usuario.nombre)}</span>
                <span className="hidden text-sm font-semibold sm:block">{usuario.nombre}</span>
                <ChevronDown className={`h-4 w-4 text-smn-gris-500 transition-transform ${menuPerfil ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {menuPerfil && (
                  <motion.div
                    initial={{ opacity: 0, y: -6, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -6, scale: 0.97 }}
                    transition={{ duration: 0.15 }}
                    className="absolute right-0 mt-2 w-56 origin-top-right overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie shadow-xl"
                  >
                    <div className="border-b border-smn-gris-100 px-4 py-3">
                      <p className="text-sm font-bold">{usuario.nombre}</p>
                      <p className="truncate text-xs text-smn-gris-500">{usuario.correo}</p>
                    </div>
                    <Link href="/perfil" onClick={() => setMenuPerfil(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm hover:bg-smn-gris-50">
                      <UserRound className="h-4 w-4" /> Mi perfil
                    </Link>
                    <button onClick={salir} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-smn-gris-50">
                      <LogOut className="h-4 w-4" /> Cerrar sesión
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pt-6 pb-28 sm:px-6 lg:pb-12">
        <AnimatePresence mode="wait">
          <motion.div key={ruta} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
            {children}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Barra inferior en celular */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-smn-gris-100 bg-superficie/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${inferior.length}, 1fr)` }}>
          {inferior.map(({ href, texto, icono: Icono, prefijo }) => {
            const activo = prefijo ? ruta.startsWith(prefijo) : ruta === href;
            return (
              <li key={href}>
                <Link href={href} className={`relative flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-bold ${activo ? "text-tinta" : "text-smn-gris-500"}`}>
                  {activo && <motion.span layoutId="inferior-activo" className="absolute top-0 h-1 w-10 rounded-b-full bg-smn-naranja" />}
                  <Icono className={`h-5 w-5 ${activo ? "text-smn-naranja" : ""}`} />
                  {texto}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
