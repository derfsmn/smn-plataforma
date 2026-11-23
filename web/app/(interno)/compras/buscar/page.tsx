"use client";
// Compras · Buscar productos (pedido de Diego, 22 nov 2026): una sola caja para encontrar cualquier artículo por
// nombre, SKU, código de barras, marca o proveedor, sin importar acentos. Cada resultado abre su ficha completa.
// También salen las ideas y propuestas del radar de productos con su semáforo.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { ChevronRight, Lightbulb, Loader2, PackageSearch, Search, X } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { CabeceraCompras } from "@/componentes/cabecera-compras";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Esqueleto, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { PERMISOS_BUSCADOR, RUTA_BUSCADOR, hrefDe, type Busqueda, type Resultado } from "@/lib/buscador";
import { Miniatura, precio } from "../precios/piezas";

const EJEMPLOS = ["magnesio", "colágeno", "creatina 300 g", "7501"];

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-72" />}>
      <Buscar />
    </Suspense>
  );
}

function Buscar() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const ruta = usePathname();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [datos, setDatos] = useState<Busqueda | null>(null);
  const [buscando, setBuscando] = useState(false);
  const caja = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = q.trim();
    // La búsqueda queda en la dirección para poder regresar o compartirla
    router.replace(t ? `${ruta}?q=${encodeURIComponent(t)}` : ruta, { scroll: false });
    if (t.length < 2) {
      setDatos(null);
      setBuscando(false);
      return;
    }
    let vigente = true;
    setBuscando(true);
    const espera = setTimeout(() => {
      api<Busqueda>(`${RUTA_BUSCADOR}?q=${encodeURIComponent(t)}&limite=50`)
        .then((r) => vigente && setDatos(r))
        .catch((e) => vigente && avisar(mensajeDe(e), "info"))
        .finally(() => vigente && setBuscando(false));
    }, 250);
    return () => {
      vigente = false;
      clearTimeout(espera);
    };
  }, [q, router, ruta, avisar]);

  if (!PERMISOS_BUSCADOR.some((p) => puede(p))) return <p className="text-smn-gris-500">No tienes acceso al buscador de productos.</p>;

  const nada = datos && datos.catalogo.length === 0 && datos.nuevos.length === 0;

  return (
    <>
      <CabeceraCompras id="buscar" titulo="Buscar productos" descripcion="Escribe el nombre, el SKU, el código de barras, la marca o el proveedor. Cada producto abre su ficha con precio, venta, inventario, costo, proveedor y mercado." />

      <label className="relative block">
        <Search className="pointer-events-none absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-smn-gris-500" />
        <input
          ref={caja}
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Por ejemplo: magnesio 60 cápsulas"
          aria-label="Buscar productos"
          enterKeyHint="search"
          className="h-14 w-full rounded-2xl border border-smn-gris-300 bg-superficie pr-12 pl-12 text-[17px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
        />
        {buscando ? (
          <Loader2 className="absolute top-1/2 right-4 h-5 w-5 -translate-y-1/2 animate-spin text-smn-gris-500" aria-label="Buscando" />
        ) : (
          q && (
            <button type="button" onClick={() => { setQ(""); caja.current?.focus(); }} aria-label="Borrar" className="absolute top-1/2 right-3 -translate-y-1/2 rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta">
              <X className="h-4 w-4" />
            </button>
          )
        )}
      </label>
      <p className="mt-2 hidden text-[13px] text-smn-gris-500 sm:block">
        También desde cualquier pantalla con <kbd className="rounded border border-smn-gris-100 px-1">Ctrl K</kbd> o <kbd className="rounded border border-smn-gris-100 px-1">/</kbd>.
      </p>

      {q.trim().length < 2 ? (
        <div className="mt-10 rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          <PackageSearch className="mx-auto mb-3 h-8 w-8" aria-hidden />
          <p>Prueba con</p>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {EJEMPLOS.map((e) => (
              <button key={e} onClick={() => setQ(e)} className="rounded-full bg-smn-gris-100 px-3 py-1 text-sm font-medium text-smn-gris-700 hover:text-tinta">
                {e}
              </button>
            ))}
          </div>
        </div>
      ) : !datos ? (
        <div className="mt-6 space-y-2">
          <Esqueleto className="h-[72px]" />
          <Esqueleto className="h-[72px]" />
          <Esqueleto className="h-[72px]" />
        </div>
      ) : nada ? (
        <p className="mt-10 rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          No encontré productos con «{datos.q}». Revisa la ortografía o busca con menos palabras.
        </p>
      ) : (
        <div className="mt-6 space-y-8">
          {datos.catalogo.length > 0 && (
            <section>
              <h2 className="mb-2 text-[13px] font-semibold tracking-wide text-smn-gris-500 uppercase">
                Catálogo <span className="tabular-nums">({datos.catalogo_total.toLocaleString("es-MX")})</span>
              </h2>
              <ul className="divide-y divide-smn-gris-100 overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
                {datos.catalogo.map((r, i) => (
                  <Renglon key={r.id} r={r} i={i} />
                ))}
              </ul>
              {datos.catalogo_total > datos.catalogo.length && (
                <p className="mt-2 text-[13px] text-smn-gris-500">
                  Se muestran {datos.catalogo.length} de {datos.catalogo_total.toLocaleString("es-MX")}. Agrega otra palabra para acotar.
                </p>
              )}
            </section>
          )}
          {datos.nuevos.length > 0 && (
            <section>
              <h2 className="mb-2 text-[13px] font-semibold tracking-wide text-smn-gris-500 uppercase">Productos nuevos e ideas ({datos.nuevos.length})</h2>
              <ul className="divide-y divide-smn-gris-100 overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
                {datos.nuevos.map((r, i) => (
                  <Renglon key={`${r.tipo}-${r.id}`} r={r} i={i} />
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </>
  );
}

function Renglon({ r, i }: { r: Resultado; i: number }) {
  return (
    <motion.li initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.2) }}>
      <Link href={hrefDe(r)} className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-smn-gris-50">
        {r.tipo === "catalogo" ? (
          <Miniatura liga={r.imagen} />
        ) : (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-smn-gris-100/60 text-smn-gris-500">
            <Lightbulb className="h-4 w-4" aria-hidden />
          </span>
        )}
        <div className="min-w-0 flex-1">
          {/* En el celular el nombre usa dos renglones y el precio va abajo, para que no se corte */}
          <p className="line-clamp-2 font-medium sm:truncate">
            {r.titulo}
            {!r.activo && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">Inactivo</Insignia>}
          </p>
          <p className="truncate text-[13px] text-smn-gris-500">{r.detalle}</p>
          {r.tipo === "catalogo" && r.precio && <p className="mt-0.5 text-sm font-semibold tabular-nums sm:hidden">{precio(r.precio)}</p>}
        </div>
        {r.tipo === "catalogo" ? (
          r.precio && <span className="hidden shrink-0 text-[15px] font-semibold tabular-nums sm:block">{precio(r.precio)}</span>
        ) : (
          <span className="shrink-0"><InsigniaColor color={r.color} /></span>
        )}
        <ChevronRight className="h-5 w-5 shrink-0 text-smn-gris-300 transition group-hover:translate-x-0.5 group-hover:text-tinta" aria-hidden />
      </Link>
    </motion.li>
  );
}
