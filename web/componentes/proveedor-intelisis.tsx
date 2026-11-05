"use client";
// Buscador de proveedores de Intelisis (solo los que tienen agente). Lo usan la captura completa y la captura rápida.

import { Check, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";

export type Intelisis = { codigo: string; nombre: string; estatus: string | null; agente: string | null; rfc: string | null };

export function ElegirIntelisis({
  elegido,
  elegir,
  enfocar = true,
  altura = "max-h-64",
}: {
  elegido: Intelisis | null;
  elegir: (p: Intelisis) => void;
  enfocar?: boolean;
  altura?: string;
}) {
  const [q, setQ] = useState("");
  const [lista, setLista] = useState<Intelisis[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<Intelisis[]>(`/api/compras/proveedores/intelisis?q=${encodeURIComponent(q.trim())}`)
        .then((l) => {
          setLista(l);
          setError(null);
        })
        .catch((e) => setError(mensajeDe(e)));
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div>
      <label className="relative block">
        <span className="sr-only">Buscar proveedor</span>
        <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input
          autoFocus={enfocar}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Nombre, clave o RFC de Intelisis"
          className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
        />
      </label>
      <p className="mt-1.5 text-[13px] text-smn-gris-700">Solo aparecen los proveedores que tienen agente en Intelisis.</p>
      {error && <p className="mt-1.5 text-sm font-medium text-red-700 dark:text-red-400">{error}</p>}
      <ul className={`mt-2 ${altura} overflow-y-auto rounded-xl border border-smn-gris-100`} role="listbox" aria-label="Proveedores de Intelisis">
        {lista === null ? (
          <li className="p-3 text-sm text-smn-gris-700">Buscando…</li>
        ) : lista.length === 0 ? (
          <li className="p-3 text-sm text-smn-gris-700">
            {q.trim() ? "No hay proveedores con ese nombre o clave. Si es nuevo, elige «Proveedor nuevo»." : "No hay proveedores con agente. Carga tblProveedores (consulta de Proveedores con Agente y RFC) en Centro de datos → ETL."}
          </li>
        ) : (
          lista.map((x) => {
            const activo = elegido?.codigo === x.codigo;
            return (
              <li key={x.codigo}>
                <button
                  type="button"
                  role="option"
                  aria-selected={activo}
                  onClick={() => elegir(x)}
                  className={`flex w-full items-center gap-3 border-b border-smn-gris-100 px-3 py-2.5 text-left last:border-b-0 ${activo ? "bg-tinta text-superficie" : "hover:bg-smn-gris-50"}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-medium">{x.nombre}</span>
                    <span className={`block text-[13px] ${activo ? "opacity-80" : "text-smn-gris-700"}`}>
                      Clave {x.codigo}
                      {x.rfc && ` · RFC ${x.rfc}`}
                      {x.agente && ` · Agente ${x.agente}`}
                      {x.estatus && x.estatus.toUpperCase() !== "ALTA" && ` · ${x.estatus.toLowerCase()}`}
                    </span>
                  </span>
                  {activo && <Check className="h-4 w-4 shrink-0" />}
                </button>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
