"use client";
// Visor de una tabla: buscador en todas las columnas, orden por columna y páginas.
// Lo usa el Centro de datos y modelos con las filas que manda el API (hasta 100 por tabla).

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useMemo, useState } from "react";

const POR_PAGINA = 15;

function Resaltar({ texto, q }: { texto: string; q: string }) {
  if (!q) return <>{texto}</>;
  const i = texto.toLowerCase().indexOf(q);
  if (i < 0) return <>{texto}</>;
  return (
    <>
      {texto.slice(0, i)}
      <mark className="rounded bg-smn-naranja/30 px-0.5 text-tinta">{texto.slice(i, i + q.length)}</mark>
      {texto.slice(i + q.length)}
    </>
  );
}

export function VisorDatos({ columnas, filas, vacio }: { columnas: string[]; filas: Record<string, string>[]; vacio: React.ReactNode }) {
  const [buscar, setBuscar] = useState("");
  const [orden, setOrden] = useState<{ col: string; asc: boolean } | null>(null);
  const [pagina, setPagina] = useState(0);
  const q = buscar.trim().toLowerCase();

  const vistas = useMemo(() => {
    let r = q ? filas.filter((f) => columnas.some((c) => (f[c] ?? "").toLowerCase().includes(q))) : filas;
    if (orden) r = [...r].sort((a, b) => (a[orden.col] ?? "").localeCompare(b[orden.col] ?? "", "es", { numeric: true }) * (orden.asc ? 1 : -1));
    return r;
  }, [filas, columnas, q, orden]);

  const paginas = Math.max(1, Math.ceil(vistas.length / POR_PAGINA));
  const actual = Math.min(pagina, paginas - 1);
  const desde = actual * POR_PAGINA;
  const visibles = vistas.slice(desde, desde + POR_PAGINA);

  if (!filas.length) return <div className="rounded-2xl bg-smn-gris-50 px-4 py-10 text-center text-sm text-smn-gris-500">{vacio}</div>;

  return (
    <div>
      <label className="relative mb-3 block">
        <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input
          id="visor-buscar"
          type="search"
          autoFocus
          value={buscar}
          onChange={(e) => {
            setBuscar(e.target.value);
            setPagina(0);
          }}
          placeholder="Buscar en todas las columnas"
          className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
        />
      </label>

      <div className="overflow-x-auto rounded-xl border border-smn-gris-100">
        <table className="w-full text-sm">
          <thead className="bg-smn-gris-50">
            <tr>
              {columnas.map((c) => (
                <th key={c} className="px-3 py-2 text-left">
                  <button
                    onClick={() => setOrden((o) => (o?.col === c ? (o.asc ? { col: c, asc: false } : null) : { col: c, asc: true }))}
                    className="flex items-center gap-1 font-mono text-[13px] font-semibold whitespace-nowrap text-smn-gris-700 hover:text-tinta"
                    title="Ordenar"
                  >
                    {c}
                    {orden?.col === c && (orden.asc ? <ArrowUp className="h-3 w-3 text-smn-naranja" /> : <ArrowDown className="h-3 w-3 text-smn-naranja" />)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-smn-gris-100">
            {visibles.map((f, i) => (
              <tr key={desde + i} className="hover:bg-smn-gris-50">
                {columnas.map((c) => (
                  <td key={c} className="px-3 py-2 whitespace-nowrap">
                    <Resaltar texto={f[c] ?? ""} q={q} />
                  </td>
                ))}
              </tr>
            ))}
            {!visibles.length && (
              <tr>
                <td colSpan={columnas.length} className="px-3 py-8 text-center text-smn-gris-500">
                  Nada coincide con “{buscar}”.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-smn-gris-500">
        <span className="tabular-nums">
          {vistas.length ? `${desde + 1}–${desde + visibles.length} de ${vistas.length}` : "0 filas"}
          {q && vistas.length !== filas.length ? ` (de ${filas.length} en total)` : ""}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPagina(actual - 1)}
            disabled={actual === 0}
            aria-label="Página anterior"
            className="rounded-lg p-1.5 hover:bg-smn-gris-100 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="tabular-nums">
            {actual + 1} / {paginas}
          </span>
          <button
            onClick={() => setPagina(actual + 1)}
            disabled={actual >= paginas - 1}
            aria-label="Página siguiente"
            className="rounded-lg p-1.5 hover:bg-smn-gris-100 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
