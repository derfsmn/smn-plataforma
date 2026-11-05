"use client";
// Tarjetas de productos de Naturi. Solo con datos de la herramienta de catálogo; 3 visibles y hasta 10 al desplegar.

import { Check, ImageOff, MessageCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { fotoProducto, importe, type Catalogo, type ProductoKiosco } from "@/lib/kiosco";

export type AlVerProductos = (productos: ProductoKiosco[], busqueda?: { consulta: string; filtros: Record<string, string> }) => void;

function Tarjeta({
  producto,
  posicion,
  seleccionado,
  inactivo,
  elegir,
}: {
  producto: ProductoKiosco;
  posicion: number;
  seleccionado: boolean;
  inactivo: boolean;
  elegir: (p: ProductoKiosco) => void;
}) {
  const [sinFoto, setSinFoto] = useState(false);
  return (
    <li
      className={`flex gap-3 rounded-2xl border bg-superficie p-3 transition-colors sm:gap-4 ${
        seleccionado ? "border-smn-naranja ring-2 ring-smn-naranja/25" : "border-smn-gris-100"
      }`}
    >
      <div className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-xl bg-white sm:h-28 sm:w-28">
        {sinFoto ? (
          <span className="flex flex-col items-center gap-1 px-2 text-center text-[13px] font-semibold text-smn-gris-500">
            <ImageOff className="h-5 w-5" aria-hidden />
            Imagen no disponible
          </span>
        ) : (
          // Foto solo del CDN fijo de la tienda, nunca de una URL del modelo
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={fotoProducto(producto.sku)}
            alt={producto.nombre}
            width={112}
            height={112}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setSinFoto(true)}
            className="h-full w-full object-contain"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-[13px] font-medium text-smn-gris-500">
          Opción {posicion}
          {producto.marca && <span className="text-smn-naranja"> · {producto.marca}</span>}
        </span>
        <h4 className="mt-0.5 font-semibold leading-snug break-words">{producto.nombre}</h4>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-smn-gris-700">
          {producto.precio_lista ? (
            <span>
              Lista <strong className="text-tinta">{importe(producto.precio_lista)}</strong>
            </span>
          ) : (
            <span className="text-smn-gris-500">Precio de lista no disponible</span>
          )}
          {producto.precio_membresia && (
            <span>
              Membresía <strong className="text-tinta">{importe(producto.precio_membresia)}</strong>
            </span>
          )}
        </div>
        <span className="mt-1 text-[13px] text-smn-gris-500 tabular-nums">SKU {producto.sku}</span>
        <button
          type="button"
          aria-pressed={seleccionado}
          disabled={inactivo || seleccionado}
          onClick={() => elegir(producto)}
          className={`mt-2 inline-flex min-h-10 items-center justify-center gap-1.5 self-start rounded-xl px-3.5 py-2 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja ${
            seleccionado
              ? "bg-smn-naranja text-smn-negro"
              : "border border-smn-gris-300 text-tinta hover:border-tinta disabled:opacity-50 disabled:hover:border-smn-gris-300"
          }`}
        >
          {seleccionado ? <Check className="h-4 w-4" aria-hidden /> : <MessageCircle className="h-4 w-4" aria-hidden />}
          {seleccionado ? "Seleccionado" : "Hablar de este producto"}
        </button>
      </div>
    </li>
  );
}

const nota = "rounded-2xl border border-dashed border-smn-gris-300 px-4 py-3 text-sm text-smn-gris-700";

export function ProductosNaturi({
  catalogo,
  elegir,
  skuSeleccionado,
  inactivo,
  alVer,
}: {
  catalogo: Catalogo;
  elegir: (p: ProductoKiosco) => void;
  skuSeleccionado?: string;
  inactivo: boolean;
  alVer?: AlVerProductos;
}) {
  const [desplegado, setDesplegado] = useState(false);
  useEffect(() => {
    if (catalogo.estado === "listo" && alVer)
      alVer(catalogo.productos.slice(0, desplegado ? 10 : 3), { consulta: catalogo.consulta, filtros: catalogo.filtros });
  }, [catalogo, desplegado, alVer]);

  if (catalogo.estado === "no_disponible") return <div className={nota}>No pude mostrar los productos de esta consulta. Puedes pedirle a Naturi que vuelva a buscar.</div>;
  if (catalogo.estado === "agotado") return <div className={nota}>Ya no hay más opciones para estos filtros. Podemos cambiar la búsqueda.</div>;
  if (catalogo.estado === "vacio") return <div className={nota}>Sin coincidencias para «{catalogo.consulta}». Prueba otro nombre, marca o SKU.</div>;

  const visibles = desplegado ? catalogo.productos : catalogo.productos.slice(0, 3);
  return (
    <section aria-label="Productos consultados" className="w-full">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
        <strong className="text-sm font-semibold">Productos encontrados</strong>
        <span className="text-[13px] text-smn-gris-500">
          {catalogo.consulta} · {catalogo.total === 1 ? "1 coincidencia" : `${catalogo.total} coincidencias`}
        </span>
      </div>
      <ul className="grid gap-2.5">
        {visibles.map((p, i) => (
          <Tarjeta key={p.sku} producto={p} posicion={i + 1} elegir={elegir} seleccionado={skuSeleccionado === p.sku} inactivo={inactivo} />
        ))}
      </ul>
      {catalogo.productos.length > 3 && (
        <button
          type="button"
          aria-expanded={desplegado}
          onClick={() => setDesplegado((v) => !v)}
          className="mt-2 rounded-xl px-3 py-2 text-sm font-semibold text-tinta underline decoration-smn-naranja decoration-2 underline-offset-4 hover:bg-smn-gris-100"
        >
          {desplegado ? "Mostrar menos" : `Ver los ${catalogo.productos.length} productos consultados`}
        </button>
      )}
      <small className="mt-2 block text-[13px] text-smn-gris-500">
        Importes del catálogo; impuestos no confirmados. Fotos de referencia. Disponibilidad en sucursal por confirmar.
      </small>
    </section>
  );
}
