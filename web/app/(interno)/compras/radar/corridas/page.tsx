"use client";
// Radar · Corridas: cada ejecución diaria, cómo le fue, cuánto costó y si salió el correo.

import Link from "next/link";
import { CalendarClock } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_ORIGEN, fechaCorta, fechaHora, pesos, type ReporteResumen } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { Esqueleto, Insignia } from "@/componentes/ui";
import { Vacio } from "../piezas";

const ESTADO = {
  listo: { texto: "Lista", clase: "bg-tinta text-superficie" },
  en_curso: { texto: "Corriendo", clase: "bg-aviso-fondo text-aviso-texto" },
  error: { texto: "Error", clase: "bg-red-500/10 text-red-700 dark:text-red-400" },
};

export default function Corridas() {
  const avisar = useAvisos();
  const [lista, setLista] = useState<ReporteResumen[] | null>(null);
  useEffect(() => {
    api<ReporteResumen[]>("/api/compras/radar/reportes").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  if (!lista) return <Esqueleto className="h-64" />;
  if (!lista.length) return <Vacio icono={<CalendarClock className="h-10 w-10" />} titulo="Sin corridas" texto="El radar corre solo todos los días a la hora configurada." />;

  const columnas = ["Día", "Estado", "Corrió", "Fuentes", "Búsquedas", "Notas nuevas", "Relevantes", "Hallazgos", "Correos", "Costo IA"];
  return (
    <>
      <div className="hidden overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie md:block">
        <table className="w-full text-sm">
          <thead className="bg-smn-gris-50 text-left text-[13px] text-smn-gris-500">
            <tr>
              {columnas.map((c) => (
                <th key={c} className="px-3 py-2.5 font-semibold whitespace-nowrap">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-smn-gris-100">
            {lista.map((r) => (
              <tr key={r.fecha} className="hover:bg-smn-gris-50">
                <td className="px-3 py-2.5 font-semibold whitespace-nowrap">
                  <Link href={`/compras/radar?fecha=${r.fecha}`} className="hover:underline">
                    {fechaCorta(r.fecha)}
                  </Link>
                </td>
                <td className="px-3 py-2.5">
                  <Insignia className={ESTADO[r.estado].clase}>{ESTADO[r.estado].texto}</Insignia>
                  {r.error && <p className="mt-1 max-w-56 text-[13px] text-red-700 dark:text-red-400">{r.error}</p>}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap text-smn-gris-700">
                  {fechaHora(r.iniciado_en)}
                  <span className="block text-[13px] text-smn-gris-500">
                    {TEXTO_ORIGEN[r.origen]}
                    {r.intentos > 1 ? ` · intento ${r.intentos}` : ""}
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  {r.fuentes_leidas}
                  {r.fuentes_con_error > 0 && <span className="text-[13px] text-red-700 dark:text-red-400"> ({r.fuentes_con_error} con error)</span>}
                </td>
                <td className="px-3 py-2.5 tabular-nums">{r.busquedas}</td>
                <td className="px-3 py-2.5 tabular-nums">{r.articulos_nuevos}</td>
                <td className="px-3 py-2.5 tabular-nums">{r.articulos_relevantes}</td>
                <td className="px-3 py-2.5 tabular-nums">{r.hallazgos}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  {r.correos_enviados}
                  {r.correos_fallidos > 0 && <span className="text-[13px] text-red-700 dark:text-red-400"> ({r.correos_fallidos} fallaron)</span>}
                </td>
                <td className="px-3 py-2.5 tabular-nums whitespace-nowrap">{pesos(r.costo_mxn)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {lista.map((r) => (
          <li key={r.fecha}>
            <Link href={`/compras/radar?fecha=${r.fecha}`} className="block rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <div className="flex items-center justify-between">
                <span className="font-semibold">{fechaCorta(r.fecha)}</span>
                <Insignia className={ESTADO[r.estado].clase}>{ESTADO[r.estado].texto}</Insignia>
              </div>
              <p className="mt-1 text-sm text-smn-gris-500">
                {TEXTO_ORIGEN[r.origen]} · {r.articulos_nuevos} notas · {r.hallazgos} hallazgos · {r.correos_enviados} correos · {pesos(r.costo_mxn)}
              </p>
              {r.error && <p className="mt-1 text-[13px] text-red-700 dark:text-red-400">{r.error}</p>}
            </Link>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[13px] text-smn-gris-500">El costo es el estimado de la puerta de IA con los precios y el tipo de cambio de Configuración.</p>
    </>
  );
}
