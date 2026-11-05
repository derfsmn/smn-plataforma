"use client";
// Radar · Histórico: todas las notas que ha leído el radar, con buscador.

import { ChevronLeft, ChevronRight, ExternalLink, Newspaper, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { CLASE_NIVEL, fechaCorta, type ArticuloRadar } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { Esqueleto, Insignia } from "@/componentes/ui";
import { Vacio } from "../piezas";

type Pagina = { total: number; articulos: ArticuloRadar[] };

export default function Historico() {
  const avisar = useAvisos();
  const [texto, setTexto] = useState("");
  const [buscar, setBuscar] = useState("");
  const [relevantes, setRelevantes] = useState(true);
  const [origen, setOrigen] = useState("");
  const [pagina, setPagina] = useState(0);
  const [datos, setDatos] = useState<Pagina | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setBuscar(texto.trim());
      setPagina(0);
    }, 350);
    return () => clearTimeout(t);
  }, [texto]);

  useEffect(() => {
    const p = new URLSearchParams({ pagina: String(pagina), solo_relevantes: String(relevantes) });
    if (buscar) p.set("q", buscar);
    if (origen) p.set("origen", origen);
    api<Pagina>(`/api/compras/radar/articulos?${p}`).then(setDatos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [buscar, relevantes, origen, pagina, avisar]);

  const paginas = datos ? Math.max(1, Math.ceil(datos.total / 25)) : 1;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            type="search"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Buscar en títulos, resúmenes y sitios"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <select
          value={origen}
          onChange={(e) => {
            setOrigen(e.target.value);
            setPagina(0);
          }}
          aria-label="Origen"
          className="rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2.5 text-sm outline-none focus:border-smn-naranja"
        >
          <option value="">Lista y búsqueda abierta</option>
          <option value="lista">Solo lista de fuentes</option>
          <option value="busqueda">Solo búsqueda abierta</option>
        </select>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={relevantes}
            onChange={(e) => {
              setRelevantes(e.target.checked);
              setPagina(0);
            }}
            className="h-4 w-4 accent-[var(--color-smn-naranja)]"
          />
          Solo relevantes
        </label>
      </div>

      {!datos ? (
        <Esqueleto className="h-64" />
      ) : datos.total === 0 ? (
        <Vacio icono={<Newspaper className="h-10 w-10" />} titulo="Sin notas" texto={buscar ? `Nada coincide con “${buscar}”.` : "El radar todavía no guarda notas."} />
      ) : (
        <>
          <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
            {datos.articulos.map((a) => (
              <li key={a.id} className="p-4">
                <div className="flex flex-wrap items-center gap-1.5">
                  {a.nivel && <Insignia className={CLASE_NIVEL[a.nivel]}>{a.nivel}</Insignia>}
                  {a.categoria && <Insignia className="border border-smn-gris-300 text-smn-gris-700">{a.categoria}</Insignia>}
                  {a.relevante === false && <Insignia className="bg-smn-gris-100 text-smn-gris-500">No relevante</Insignia>}
                  {!a.en_ventana && <Insignia className="bg-smn-gris-100 text-smn-gris-500">Fuera de la ventana de días</Insignia>}
                  <span className="text-[13px] text-smn-gris-500">
                    {a.fuente ?? a.sitio} · publicada {fechaCorta(a.publicado_en)} · leída {fechaCorta(a.leido_en)}
                    {a.origen === "busqueda" && " · búsqueda abierta"}
                  </span>
                </div>
                <a href={a.url} target="_blank" rel="noopener noreferrer" className="mt-1.5 flex items-start gap-1.5 font-semibold hover:underline">
                  {a.titulo} <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 text-smn-naranja" />
                </a>
                {(a.por_que || a.extracto) && <p className="mt-1 line-clamp-2 text-sm text-smn-gris-700">{a.por_que ?? a.extracto}</p>}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex items-center justify-between text-sm text-smn-gris-500">
            <span className="tabular-nums">{datos.total} notas</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPagina(pagina - 1)} disabled={pagina === 0} aria-label="Página anterior" className="rounded-lg p-1.5 hover:bg-smn-gris-100 disabled:opacity-30">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="tabular-nums">
                {pagina + 1} / {paginas}
              </span>
              <button onClick={() => setPagina(pagina + 1)} disabled={pagina >= paginas - 1} aria-label="Página siguiente" className="rounded-lg p-1.5 hover:bg-smn-gris-100 disabled:opacity-30">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
