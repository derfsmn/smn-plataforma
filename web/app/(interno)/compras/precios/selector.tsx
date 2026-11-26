"use client";
// Radar de precios · elegir productos (Diego, 26 nov 2026: «por marca, clasificación, categoría, skus y mezclados»).
// Lo usan el Reporte a Excel y la Nueva corrida. Se mezclan productos sueltos, marcas, clasificaciones, categorías y una
// lista de SKU (pegada o en Excel); ninguno sale repetido. La clasificación acota lo elegido por marca o categoría.

import { FileSpreadsheet, Search, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { leerSkus, type ListaSkus, type ModoReporte, type OpcionReporte } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Esqueleto } from "@/componentes/ui";

export type Modo = ModoReporte | "skus";
export type Elegido = { modo: ModoReporte; clave: string; nombre: string };

const MODOS: { valor: Modo; texto: string; buscar?: string }[] = [
  { valor: "producto", texto: "Productos", buscar: "Buscar por SKU, código de barras, nombre o marca" },
  { valor: "marca", texto: "Marca", buscar: "Buscar marca" },
  { valor: "clasificacion", texto: "Clasificación" },
  { valor: "categoria", texto: "Categoría", buscar: "Buscar categoría" },
  { valor: "skus", texto: "Lista de SKU" },
];

const ETIQUETA: Record<ModoReporte, string> = { producto: "Producto", marca: "Marca", categoria: "Categoría", clasificacion: "Clase" };

export function aSeleccion(elegidos: Elegido[]) {
  return {
    producto_ids: elegidos.filter((e) => e.modo === "producto").map((e) => Number(e.clave)),
    marcas: elegidos.filter((e) => e.modo === "marca").map((e) => e.clave),
    categorias: elegidos.filter((e) => e.modo === "categoria").map((e) => e.clave),
    clasificaciones: elegidos.filter((e) => e.modo === "clasificacion").map((e) => e.clave),
  };
}

/** Lo que trajo la última lista de SKU (para que la corrida guarde el nombre del archivo y los no encontrados). */
export type UltimaLista = { archivo: string | null; no_encontrados: string[] };

export function Selector({
  elegidos,
  setElegidos,
  alLeerLista,
  titulo = "¿Qué productos van?",
}: {
  elegidos: Elegido[];
  setElegidos: (f: (l: Elegido[]) => Elegido[]) => void;
  alLeerLista?: (l: UltimaLista) => void;
  titulo?: string;
}) {
  const avisar = useAvisos();
  const [modo, setModo] = useState<Modo>("producto");
  const [q, setQ] = useState("");
  const [opciones, setOpciones] = useState<OpcionReporte[] | null>(null);

  useEffect(() => {
    if (modo === "skus") return;
    setOpciones(null);
    const id = setTimeout(() => {
      api<OpcionReporte[]>(`/api/compras/precios/reporte/opciones?modo=${modo}&q=${encodeURIComponent(q.trim())}`)
        .then(setOpciones)
        .catch((e) => avisar(mensajeDe(e), "info"));
    }, 250);
    return () => clearTimeout(id);
  }, [modo, q, avisar]);

  const m = modo === "skus" ? null : modo;
  const esta = (o: OpcionReporte) => elegidos.some((e) => e.modo === m && e.clave === o.clave);
  const alternar = (o: OpcionReporte) =>
    m && setElegidos((l) => (esta(o) ? l.filter((e) => !(e.modo === m && e.clave === o.clave)) : [...l, { modo: m, clave: o.clave, nombre: o.nombre }]));
  const actual = MODOS.find((x) => x.valor === modo)!;

  const sumarLista = (r: ListaSkus, archivo: string | null) => {
    setElegidos((l) => {
      const ya = new Set(l.filter((e) => e.modo === "producto").map((e) => e.clave));
      return [...l, ...r.encontrados.filter((o) => !ya.has(o.clave)).map((o) => ({ modo: "producto" as const, clave: o.clave, nombre: o.nombre }))];
    });
    alLeerLista?.({ archivo, no_encontrados: r.no_encontrados });
  };

  return (
    <section className="rounded-xl border border-smn-gris-100 bg-superficie">
      <div className="border-b border-smn-gris-100 p-4 sm:p-5">
        <h2 className="text-lg font-semibold">{titulo}</h2>
        <p className="text-[13px] text-smn-gris-500">
          Puedes mezclar productos, marcas, clasificaciones, categorías y una lista de SKU; ninguno sale repetido. La clasificación acota las marcas y categorías que elijas.
        </p>
        <div className="mt-4 flex flex-wrap gap-0.5 rounded-lg bg-smn-gris-100 p-0.5 text-[14px] sm:w-max">
          {MODOS.map((x) => (
            <button
              key={x.valor}
              type="button"
              onClick={() => (setModo(x.valor), setQ(""))}
              className={`flex-1 rounded-md px-3 py-1.5 whitespace-nowrap sm:flex-none ${modo === x.valor ? "bg-tinta text-superficie" : "text-smn-gris-700"}`}
            >
              {x.texto}
            </button>
          ))}
        </div>
        {actual.buscar && (
          <label className="relative mt-3 block">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={actual.buscar}
              aria-label={actual.buscar}
              className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
            />
          </label>
        )}
      </div>
      {modo === "skus" ? (
        <ListaDeSkus sumar={sumarLista} />
      ) : !opciones ? (
        <div className="space-y-2 p-4">
          <Esqueleto className="h-12" />
          <Esqueleto className="h-12" />
          <Esqueleto className="h-12" />
        </div>
      ) : opciones.length === 0 ? (
        <p className="px-4 py-10 text-center text-smn-gris-500">No hay resultados.</p>
      ) : (
        <ul className="max-h-[520px] divide-y divide-smn-gris-100 overflow-y-auto">
          {opciones.map((o) => (
            <li key={o.clave}>
              <label className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-smn-gris-100/30">
                <input type="checkbox" checked={esta(o)} onChange={() => alternar(o)} className="h-[18px] w-[18px] accent-smn-naranja" />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{o.nombre}</span>
                  {o.detalle && <span className="block text-[13px] text-smn-gris-500">{o.detalle}</span>}
                </span>
                <span className="shrink-0 text-[13px] text-smn-gris-500 tabular-nums">{o.cuenta}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ListaDeSkus({ sumar }: { sumar: (r: ListaSkus, archivo: string | null) => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [texto, setTexto] = useState("");
  const [leyendo, setLeyendo] = useState(false);
  const [ultima, setUltima] = useState<{ r: ListaSkus; archivo: string | null } | null>(null);

  const leer = async (archivo: File | null) => {
    setLeyendo(true);
    try {
      const r = await leerSkus(archivo, texto);
      setUltima({ r, archivo: archivo?.name ?? null });
      sumar(r, archivo?.name ?? null);
      if (!archivo) setTexto("");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLeyendo(false);
      if (entrada.current) entrada.current.value = "";
    }
  };

  return (
    <div className="space-y-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-smn-gris-300 p-4">
        <FileSpreadsheet className="h-6 w-6 shrink-0 text-smn-gris-500" />
        <p className="min-w-0 flex-1 text-[14px]">
          Sube un Excel con una columna <b>SKU</b> (también acepta códigos de barras).
        </p>
        <input ref={entrada} type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => e.target.files?.[0] && leer(e.target.files[0])} />
        <Boton variante="secundario" onClick={() => entrada.current?.click()} cargando={leyendo}>
          <Upload className="h-4 w-4" /> Subir Excel
        </Boton>
      </div>
      <label className="block">
        <span className="text-[14px] font-medium">O pégalos aquí</span>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={5}
          placeholder={"12345\n67890\n7501234567890"}
          className="mt-1 w-full rounded-lg border border-smn-gris-100 bg-superficie p-3 font-mono text-[14px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
        />
      </label>
      <Boton onClick={() => leer(null)} disabled={!texto.trim()} cargando={leyendo && !ultima}>
        Agregar a la lista
      </Boton>
      {ultima && (
        <div className="rounded-lg bg-smn-gris-100/50 p-3 text-[14px]">
          <p>
            {ultima.archivo ? `${ultima.archivo}: ` : ""}
            <b>{ultima.r.encontrados.length.toLocaleString("es-MX")}</b> de {ultima.r.skus.toLocaleString("es-MX")} SKU encontrados
            {ultima.r.no_encontrados.length > 0 && " en el catálogo"}.
          </p>
          {ultima.r.no_encontrados.length > 0 && (
            <p className="mt-1 text-[13px] text-smn-gris-700">
              No están en el catálogo: {ultima.r.no_encontrados.slice(0, 12).join(", ")}
              {ultima.r.no_encontrados.length > 12 && ` y ${ultima.r.no_encontrados.length - 12} más`}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Lo elegido como etiquetas que se quitan con un clic. Muchos productos sueltos se juntan en una sola. */
export function Elegidos({ elegidos, setElegidos }: { elegidos: Elegido[]; setElegidos: (f: (l: Elegido[]) => Elegido[]) => void }) {
  const sueltos = elegidos.filter((e) => e.modo === "producto");
  const otros = elegidos.filter((e) => e.modo !== "producto");
  const quitar = (e: Elegido) => setElegidos((l) => l.filter((x) => !(x.modo === e.modo && x.clave === e.clave)));
  const chip = (texto: string, etiqueta: string, quitarlo: () => void, llave: string) => (
    <li key={llave} className="max-w-full min-w-0">
      <button
        type="button"
        onClick={quitarlo}
        className="inline-flex max-w-full items-center gap-1 rounded-full bg-smn-gris-100 px-2.5 py-1 text-[13px] hover:bg-smn-gris-300/50"
        title="Quitar"
      >
        <span className="text-smn-gris-500">{etiqueta}:</span>
        <span className="truncate">{texto}</span>
        <X className="h-3 w-3 shrink-0" />
      </button>
    </li>
  );
  if (!elegidos.length) return null;
  return (
    <ul className="mt-3 flex flex-wrap gap-1.5">
      {otros.map((e) => chip(e.nombre, ETIQUETA[e.modo], () => quitar(e), `${e.modo}-${e.clave}`))}
      {sueltos.length > 8
        ? chip(`${sueltos.length.toLocaleString("es-MX")} productos`, "Sueltos", () => setElegidos((l) => l.filter((x) => x.modo !== "producto")), "sueltos")
        : sueltos.map((e) => chip(e.nombre, ETIQUETA.producto, () => quitar(e), `producto-${e.clave}`))}
    </ul>
  );
}
