"use client";
// Radar de precios · la tabla de productos (nuestro precio, mercado, diferencia, qué conviene y dinero en juego). La usan
// «Precios contra el mercado» y el resumen de cada corrida. En celular cada producto es una tarjeta.

import { SEMAFORO, pct, type Color, type FilaTablero } from "@/lib/precios";
import { Miniatura, monto } from "./piezas";

const CLASE_ACCION: Record<string, string> = {
  bajar: "text-red-700 dark:text-red-400",
  bajar_y_negociar: "text-red-700 dark:text-red-400",
  negociar: "text-naranja-tinta",
  subir: "text-green-700 dark:text-green-400",
  mantener: "text-smn-gris-700",
  sin_referencia: "text-smn-gris-500",
};
export const dinero = (v: string | number) => Number(v).toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

export function TablaPrecios({ filas, abierto, abrir }: { filas: FilaTablero[]; abierto: number | null; abrir: (id: number) => void }) {
  return (
    <>
      <table className="hidden w-full text-[14px] lg:table">
        <thead className="text-left text-[13px] text-smn-gris-500">
          <tr className="border-b border-smn-gris-100">
            <th className="w-[32%] px-4 py-2.5 font-medium">Producto</th>
            <th className="px-2 py-2.5 text-right font-medium">Nuestro <span className="font-normal">(MXN)</span></th>
            <th className="px-2 py-2.5 text-right font-medium">Mercado <span className="font-normal">(MXN)</span></th>
            <th className="px-3 py-2.5 font-medium">Diferencia</th>
            <th className="px-2 py-2.5 font-medium">Qué conviene</th>
            <th className="px-4 py-2.5 text-right font-medium">En juego al mes</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-smn-gris-100">
          {filas.map((f) => (
            <tr
              key={f.producto_id}
              onClick={() => abrir(f.producto_id)}
              className={`cursor-pointer align-top hover:bg-smn-gris-100/40 ${abierto === f.producto_id ? "bg-smn-gris-100/60" : ""}`}
            >
              <td className="px-4 py-3">
                <Producto f={f} />
              </td>
              <td className="px-2 py-3 text-right whitespace-nowrap tabular-nums">
                <span className="block font-semibold">{monto(f.nuestro)}</span>
                {f.membresia && <span className="block text-[13px] text-smn-gris-500">Memb. {monto(f.membresia)}</span>}
              </td>
              <td className="px-2 py-3 text-right tabular-nums">
                <span className="block whitespace-nowrap font-semibold">{monto(f.mercado)}</span>
                <DeTiendas f={f} />
              </td>
              <td className="px-3 py-3">
                <Difs f={f} />
              </td>
              <td className="max-w-[260px] px-2 py-3">
                <Accion f={f} />
              </td>
              <td className="px-4 py-3 text-right font-semibold whitespace-nowrap tabular-nums">{Number(f.en_juego) > 0 ? dinero(f.en_juego) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="divide-y divide-smn-gris-100 lg:hidden">
        {filas.map((f) => (
          <li key={f.producto_id}>
            <button type="button" onClick={() => abrir(f.producto_id)} className="block w-full space-y-2 p-4 text-left">
              <Producto f={f} />
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px]">
                <span>Nuestro <b className="tabular-nums">{monto(f.nuestro)}</b></span>
                <span>Mercado <b className="tabular-nums">{monto(f.mercado)}</b> <DeTiendas f={f} enLinea /></span>
                <Difs f={f} />
              </div>
              <div className="flex items-start justify-between gap-3">
                <Accion f={f} />
                {Number(f.en_juego) > 0 && <span className="shrink-0 text-[14px] font-semibold tabular-nums">{dinero(f.en_juego)}/mes</span>}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function Producto({ f }: { f: FilaTablero }) {
  return (
    <span className="flex min-w-0 items-start gap-3">
      <Miniatura liga={f.imagen} />
      <span className="min-w-0">
        <span className="block font-medium">{f.descripcion ?? f.sku}</span>
        <span className="block text-[13px] text-smn-gris-500">
          {f.sku}
          {f.marca && ` · ${f.marca}`}
          {f.clase && ` · clase ${f.clase}`}
          {f.agente && ` · agente ${f.agente}`}
        </span>
      </span>
    </span>
  );
}

function DeTiendas({ f, enLinea }: { f: FilaTablero; enLinea?: boolean }) {
  const cuantas = Object.keys(f.tiendas).length + f.otras;
  if (!f.mercado || !cuantas) return null;
  const texto = `de ${cuantas} ${cuantas === 1 ? "tienda" : "tiendas"}`;
  return enLinea ? <span className="text-[13px] text-smn-gris-500">{texto}</span> : <span className="block text-[13px] text-smn-gris-500">{texto}</span>;
}

function Difs({ f }: { f: FilaTablero }) {
  if (!f.color || f.dif_pct === null) return <span className="text-[13px] text-smn-gris-500">Sin comparar</span>;
  return (
    <span className="inline-flex flex-wrap gap-x-3 gap-y-1 lg:flex-col">
      <Dif color={f.color} valor={f.dif_pct} etiqueta="Lista" />
      {f.color_membresia && f.dif_membresia_pct !== null && <Dif color={f.color_membresia} valor={f.dif_membresia_pct} etiqueta="Memb." />}
    </span>
  );
}

function Dif({ color, valor, etiqueta }: { color: Color; valor: string; etiqueta: string }) {
  const s = SEMAFORO[color];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap tabular-nums">
      <span className={`h-2.5 w-2.5 rounded-full ${s.punto}`} aria-hidden />
      <span className="sr-only">{s.texto}: </span>
      <span className="text-[13px] text-smn-gris-500">{etiqueta}</span> <b className="font-semibold">{pct(valor)}</b>
    </span>
  );
}

function Accion({ f }: { f: FilaTablero }) {
  const texto = f.accion === "sin_referencia" ? "Sin comparar" : f.accion_texto;
  return <b className={`font-semibold ${CLASE_ACCION[f.accion] ?? ""}`}>{texto}</b>;
}
