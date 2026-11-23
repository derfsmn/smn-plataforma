"use client";
// Cabecera común de las pantallas de Compras (propuesta de diseño 22 nov 2026).
// Una sola forma de título, descripción, acciones y pestañas en los cinco apartados: antes cada layout la repetía
// con diferencias. Las pestañas de configuración (fuentes, corridas, vigilados…) van al final, separadas, y solo
// las ve quien tiene el permiso: Compras consulta, no configura.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { ArrowLeft, Settings2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSesion } from "@/componentes/sesion";

export type Pestana = { href: string; texto: string; permiso?: string; ajuste?: boolean; tambien?: RegExp };

export function CabeceraCompras({
  id,
  titulo,
  descripcion,
  acciones,
  pestanas,
  volver = { href: "/modulos/compras", texto: "Compras" },
}: {
  id: string;
  titulo: string;
  descripcion?: string;
  acciones?: React.ReactNode;
  pestanas?: Pestana[];
  volver?: { href: string; texto: string };
}) {
  const ruta = usePathname();
  const { puede } = useSesion();
  const visibles = (pestanas ?? []).filter((p) => !p.permiso || puede(p.permiso));
  const raiz = visibles[0]?.href;
  const activa = (p: Pestana) => (p.href === raiz ? ruta === p.href : ruta.startsWith(p.href)) || !!p.tambien?.test(ruta);
  const consulta = visibles.filter((p) => !p.ajuste);
  const ajustes = visibles.filter((p) => p.ajuste);

  return (
    <header className="mb-6">
      {/* En escritorio la ruta ya está arriba (Compras › …); el regreso solo hace falta en el celular */}
      <Link href={volver.href} className="mb-4 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta lg:hidden">
        <ArrowLeft className="h-4 w-4" /> {volver.texto}
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-tight font-semibold tracking-tight sm:text-[32px]">{titulo}</h1>
          {descripcion && <p className="mt-1.5 max-w-2xl text-[15px] leading-relaxed text-smn-gris-700">{descripcion}</p>}
        </div>
        {acciones && <div className="flex flex-wrap gap-2">{acciones}</div>}
      </div>
      {visibles.length > 1 && (
        <Pestanas id={id} consulta={consulta} ajustes={ajustes} activa={activa} />
      )}
    </header>
  );
}

function Pestanas({ id, consulta, ajustes, activa }: { id: string; consulta: Pestana[]; ajustes: Pestana[]; activa: (p: Pestana) => boolean }) {
  const caja = useRef<HTMLDivElement>(null);
  const [orillas, setOrillas] = useState({ izq: false, der: false });
  useEffect(() => {
    const el = caja.current;
    if (!el) return;
    const medir = () => setOrillas({ izq: el.scrollLeft > 4, der: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    medir();
    // En el celular la pestaña activa se acerca al centro; en escritorio caben todas
    if (window.innerWidth < 1024) el.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ block: "nearest", inline: "center" });
    el.addEventListener("scroll", medir, { passive: true });
    window.addEventListener("resize", medir);
    return () => {
      el.removeEventListener("scroll", medir);
      window.removeEventListener("resize", medir);
    };
  }, []);

  const liga = (p: Pestana) => {
    const si = activa(p);
    return (
      <li key={p.href}>
        <Link
          href={p.href}
          aria-current={si ? "page" : undefined}
          className={`relative flex h-11 items-center gap-1.5 px-1 text-[15px] font-medium whitespace-nowrap transition-colors ${si ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
        >
          {p.ajuste && <Settings2 className="h-4 w-4" aria-hidden />}
          {p.texto}
          {si && <motion.span layoutId={`pestana-${id}`} className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-[var(--resalte)]" transition={{ duration: 0.25 }} />}
        </Link>
      </li>
    );
  };

  return (
    <nav className="relative mt-5 border-b border-smn-gris-100" aria-label={`Secciones`}>
      <div ref={caja} className="-mx-4 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0">
        <ul className="flex w-max items-center gap-5">
          {consulta.map(liga)}
          {ajustes.length > 0 && (
            <>
              <li aria-hidden className="h-5 w-px bg-smn-gris-100" />
              {ajustes.map(liga)}
            </>
          )}
        </ul>
      </div>
      {orillas.izq && <span aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-smn-gris-50 to-transparent" />}
      {orillas.der && <span aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-smn-gris-50 to-transparent" />}
    </nav>
  );
}
