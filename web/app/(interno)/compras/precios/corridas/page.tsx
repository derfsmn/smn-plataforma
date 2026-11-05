"use client";
// Radar de precios · Corridas y gasto: cada corrida, qué encontró y cuánto costó en DataForSEO.

import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Clock, Download, FileSpreadsheet, FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { api, dolares, mensajeDe } from "@/lib/api";
import { CLASE_CORRIDA, ORIGEN, dia, excelCorrida, hora, textoCorrida, type Corrida, type CorridaDetalle } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";

const ESTADO_ENVIO: Record<string, string> = { reservado: "Reservado", confirmado: "Cobrado", incierto: "Incierto", rechazado: "Rechazado" };

export default function Corridas() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const administra = puede("compras.precios.administrar");
  const [corridas, setCorridas] = useState<Corrida[] | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<Record<number, CorridaDetalle>>({});

  useEffect(() => {
    api<Corrida[]>("/api/compras/precios/corridas").then(setCorridas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const abrir = (id: number) => {
    setAbierta(abierta === id ? null : id);
    if (!detalle[id])
      api<CorridaDetalle>(`/api/compras/precios/corridas/${id}`)
        .then((d) => setDetalle((x) => ({ ...x, [id]: d })))
        .catch((e) => avisar(mensajeDe(e), "info"));
  };

  // Todo lo que hizo la corrida en un archivo, para revisar casos fuera de este equipo (sin claves de DataForSEO).
  const diagnostico = (c: Corrida) =>
    api<unknown>(`/api/compras/precios/corridas/${c.id}/diagnostico`)
      .then((d) => {
        const liga = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }));
        const a = document.createElement("a");
        a.href = liga;
        a.download = `diagnostico-precios-${c.fecha}-${c.id}.json`;
        a.click();
        URL.revokeObjectURL(liga);
      })
      .catch((e) => avisar(mensajeDe(e), "info"));

  if (!corridas) return <Esqueleto className="h-60" />;
  if (!corridas.length)
    return <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">Todavía no hay corridas.</p>;

  return (
    <>
      <p className="mb-4 max-w-2xl text-sm text-smn-gris-500">
        Antes de cada envío a DataForSEO se calcula lo más que puede costar y se revisan los topes. Un envío sin respuesta clara nunca se repite (para no pagar dos veces) y
        cuenta con su máximo en el gasto del mes.
      </p>
      <ul className="space-y-2">
        {corridas.map((c) => (
          <li key={c.id} className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
            <button onClick={() => abrir(c.id)} aria-expanded={abierta === c.id} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 p-4 text-left text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {dia(c.fecha)}, {hora(c.iniciado_en)}
                  {c.terminado_en && ` a ${hora(c.terminado_en)}`} <Insignia className={`ml-1 ${CLASE_CORRIDA[c.estado]}`}>{textoCorrida(c)}</Insignia>
                </p>
                <p className="text-smn-gris-500">
                  {c.origen === "prueba" ? <FlaskConical className="mr-1 inline h-3.5 w-3.5 text-smn-naranja" /> : <Clock className="mr-1 inline h-3.5 w-3.5" />}
                  {ORIGEN[c.origen]}
                  {c.archivo && ` (${c.archivo})`}
                  {c.usuario && ` por ${c.usuario}`}
                  {c.intentos > 1 && ` · intento ${c.intentos}`}
                </p>
              </div>
              <p className="text-smn-gris-700 tabular-nums">
                {c.productos} productos · {c.con_precios} con precios · {c.sin_coincidencia} sin coincidencia
                {c.fallidos > 0 && ` · ${c.fallidos} sin terminar`} · <b className="text-tinta">{dolares(c.costo_usd, 3)}</b>
              </p>
              <ChevronDown className={`h-4 w-4 text-smn-gris-500 transition-transform ${abierta === c.id ? "rotate-180" : ""}`} />
            </button>
            <AnimatePresence>
              {abierta === c.id && (
                <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
                  <div className="border-t border-smn-gris-100 px-4 py-3 text-sm">
                    {c.error && <p className="mb-2 text-red-700 dark:text-red-400">{c.error}</p>}
                    {c.avisos.map((a) => (
                      <p key={a} className="mb-2 text-aviso-texto">
                        {a}
                      </p>
                    ))}
                    <p className="mb-2 text-smn-gris-500">
                      {c.alertas > 0 ? `${c.alertas} productos quedaron en rojo (más caros que el mercado por arriba del límite).` : "Ningún producto quedó en rojo."}
                      {c.tope_usd && ` Tope de la corrida: ${dolares(c.tope_usd)}.`}
                    </p>
                    {!detalle[c.id] ? (
                      <Esqueleto className="h-16" />
                    ) : !detalle[c.id].envios.length ? (
                      <p className="text-smn-gris-500">No se envió nada a DataForSEO.</p>
                    ) : (
                      <table className="w-full text-[13px]">
                        <thead className="text-left text-smn-gris-500">
                          <tr>
                            <th className="py-1">Envío</th>
                            <th className="py-1 pr-4 text-right">Tareas</th>
                            <th className="py-1">Estado</th>
                            <th className="py-1 text-right">Máximo</th>
                            <th className="py-1 text-right">Cobrado</th>
                          </tr>
                        </thead>
                        <tbody className="tabular-nums">
                          {detalle[c.id].envios.map((e, i) => (
                            <tr key={i} className="border-t border-smn-gris-100">
                              <td className="py-1.5">{e.tipo === "productos" ? "Búsqueda de productos" : "Precios de vendedores"}</td>
                              <td className="py-1.5 pr-4 text-right">{e.tareas}</td>
                              <td className="py-1.5">{ESTADO_ENVIO[e.estado] ?? e.estado}</td>
                              <td className="py-1.5 text-right">{dolares(e.estimado_usd, 3)}</td>
                              <td className="py-1.5 text-right">{e.costo_usd === null ? "—" : dolares(e.costo_usd, 3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {c.estado !== "en_curso" && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Boton variante="secundario" onClick={() => excelCorrida(c).catch((e) => avisar(mensajeDe(e), "info"))} className="px-3 py-2">
                          <FileSpreadsheet className="h-4 w-4" /> Descargar Excel
                        </Boton>
                        {administra && (
                          <Boton variante="secundario" onClick={() => diagnostico(c)} className="px-3 py-2">
                            <Download className="h-4 w-4" /> Descargar diagnóstico
                          </Boton>
                        )}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </li>
        ))}
      </ul>
    </>
  );
}
