"use client";
// Radar · Tendencias: todas las señales con su estado y decisión.

import Link from "next/link";
import { Search, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_ESTADO, fechaCorta, type EstadoSenal, type Senal } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { Entrada, Esqueleto } from "@/componentes/ui";
import { Etiquetas, UltimaAccion, Vacio } from "../piezas";

const FILTROS: { id: "todas" | EstadoSenal | "tendencia"; texto: string }[] = [
  { id: "todas", texto: "Todas" },
  { id: "tendencia", texto: "Solo tendencias" },
  { id: "nueva", texto: TEXTO_ESTADO.nueva },
  { id: "vigilar", texto: TEXTO_ESTADO.vigilar },
  { id: "iniciativa", texto: TEXTO_ESTADO.iniciativa },
  { id: "descartada", texto: "Descartadas" },
];

export default function Tendencias() {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Senal[] | null>(null);
  const [filtro, setFiltro] = useState<(typeof FILTROS)[number]["id"]>("todas");
  const [texto, setTexto] = useState("");

  useEffect(() => {
    api<Senal[]>("/api/compras/radar/senales").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const visibles = useMemo(
    () =>
      (lista ?? []).filter(
        (s) =>
          (filtro === "todas" || (filtro === "tendencia" ? s.tipo === "tendencia" : s.estado === filtro)) &&
          [s.titulo, s.descripcion, s.area, s.categoria].join(" ").toLowerCase().includes(texto.toLowerCase()),
      ),
    [lista, filtro, texto],
  );

  if (!lista) return <Esqueleto className="h-64" />;
  if (!lista.length) return <Vacio icono={<TrendingUp className="h-10 w-10" />} titulo="Aún no hay señales" texto="Aparecen cuando el radar arma su primer reporte con hallazgos." />;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-60 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            type="search"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Buscar señal, ingrediente, área…"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <div className="flex flex-wrap gap-1">
          {FILTROS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFiltro(f.id)}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold transition-colors ${filtro === f.id ? "bg-tinta text-superficie" : "text-smn-gris-500 hover:bg-smn-gris-100"}`}
            >
              {f.texto}
            </button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-sm text-smn-gris-500">
        {visibles.length} de {lista.length} señales
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        {visibles.map((s, i) => (
          <Entrada key={s.id} retraso={Math.min(i, 10) * 0.03}>
            <li className="h-full">
              <Link href={`/compras/radar/senal/${s.id}`} className="block h-full rounded-2xl border border-smn-gris-100 bg-superficie p-4 transition-colors hover:border-smn-naranja">
                <Etiquetas nivel={s.nivel} tipo={s.tipo} estado={s.estado} area={s.area} />
                <p className="mt-2 font-semibold">{s.titulo}</p>
                <p className="mt-1 text-[13px] text-smn-gris-500">
                  {s.articulos} nota{s.articulos === 1 ? "" : "s"} · {s.sitios_distintos} sitio{s.sitios_distintos === 1 ? "" : "s"}
                  {s.paises ? ` · ${s.paises}` : ""} · desde {fechaCorta(s.primera_vez)} · última {fechaCorta(s.ultima_vez)}
                </p>
                <div className="mt-2">
                  <UltimaAccion a={s.ultima_accion} />
                </div>
              </Link>
            </li>
          </Entrada>
        ))}
      </ul>
    </div>
  );
}
