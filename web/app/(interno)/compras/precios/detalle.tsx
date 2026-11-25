"use client";
// Radar de precios · detalle de un producto en un panel a la derecha, sin salir de la lista (plan del 25 nov, pantalla 2).
// De arriba abajo: qué conviene, nuestro precio contra el mercado (lista y membresía), su historial de precios, cada tienda
// que cuenta con su liga, los precios que no cuentan con su motivo y «Algo está mal».

import { motion } from "motion/react";
import { ExternalLink, Flag, Maximize2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { SEMAFORO, pct, type DetalleProducto, type FilaTablero, type ValidacionProducto } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto } from "@/componentes/ui";
import { EstaMal } from "./esta-mal";
import { Grafica, Miniatura, monto, precio } from "./piezas";

const CAJA_ACCION: Record<string, string> = {
  bajar: "border-red-600/30 bg-red-600/[0.06]",
  bajar_y_negociar: "border-red-600/30 bg-red-600/[0.06]",
  negociar: "border-smn-naranja/40 bg-smn-naranja/[0.07]",
  subir: "border-green-600/30 bg-green-600/[0.06]",
  mantener: "border-smn-gris-100 bg-smn-gris-100/40",
  sin_referencia: "border-smn-gris-100 bg-smn-gris-100/40",
};

export function Detalle({ productoId, cerrar, cambio }: { productoId: number; cerrar: () => void; cambio: () => void }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [f, setF] = useState<FilaTablero | null>(null);
  const [v, setV] = useState<ValidacionProducto | null>(null);
  const [d, setD] = useState<DetalleProducto | null>(null);
  const [mal, setMal] = useState(false);

  const cargar = useCallback(() => {
    const base = `/api/compras/precios`;
    Promise.all([
      api<FilaTablero>(`${base}/tablero/producto/${productoId}`),
      api<ValidacionProducto>(`${base}/productos/${productoId}/validacion`),
      api<DetalleProducto>(`${base}/productos/${productoId}`),
    ])
      .then(([a, b, c]) => (setF(a), setV(b), setD(c)))
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [productoId, avisar]);
  useEffect(() => {
    setF(null);
    cargar();
  }, [cargar]);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !mal && cerrar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [cerrar, mal]);

  const cuentan = v?.precios.filter((p) => p.cuenta) ?? [];
  const noCuentan = v?.precios.filter((p) => !p.cuenta) ?? [];

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-smn-negro/30 lg:bg-transparent" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={cerrar} />
      <motion.aside
        role="dialog"
        aria-modal="true"
        aria-label="Detalle del producto"
        initial={{ x: 40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 380, damping: 36 }}
        className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-smn-gris-100 bg-superficie shadow-2xl sm:max-w-[560px]"
      >
        <div className="flex items-start justify-between gap-3 border-b border-smn-gris-100 p-4 sm:p-5">
          {f ? (
            <div className="flex min-w-0 items-start gap-3">
              <Miniatura liga={f.imagen} />
              <div className="min-w-0">
                <h2 className="text-lg leading-snug font-semibold">{f.descripcion ?? f.sku}</h2>
                <p className="text-[13px] text-smn-gris-500">
                  {f.sku}
                  {f.marca && ` · ${f.marca}`}
                  {f.clase && ` · clase ${f.clase}`}
                  {f.agente && ` · agente ${f.agente}`}
                </p>
              </div>
            </div>
          ) : (
            <Esqueleto className="h-12 w-64" />
          )}
          <div className="flex shrink-0 items-center gap-1">
            {puede("compras.precios.administrar") && (
              <Link href={`/compras/precios/producto/${productoId}`} className="rounded-full p-2 text-smn-gris-500 hover:bg-smn-gris-100" title="Página completa (administración)">
                <Maximize2 className="h-4 w-4" />
              </Link>
            )}
            <button type="button" onClick={cerrar} aria-label="Cerrar" className="rounded-full p-2 hover:bg-smn-gris-100">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {!f || !v || !d ? (
          <div className="space-y-3 p-5">
            <Esqueleto className="h-24" />
            <Esqueleto className="h-20" />
            <Esqueleto className="h-48" />
          </div>
        ) : (
          <div className="flex-1 space-y-6 overflow-y-auto p-4 sm:p-5">
            <section className={`rounded-xl border p-4 ${CAJA_ACCION[f.accion] ?? CAJA_ACCION.mantener}`}>
              <p className="text-[13px] text-smn-gris-700">Qué conviene</p>
              <p className="text-lg font-semibold">{f.accion === "sin_referencia" ? (f.aviso ? "Referencia débil" : "Sin comparar") : f.accion_texto}</p>
              {(f.aviso || f.detalle) && <p className="mt-1 text-[14px] leading-snug text-smn-gris-700">{f.aviso ?? f.detalle}</p>}
              {Number(f.en_juego) > 0 && (
                <p className="mt-2 text-[13px] text-smn-gris-700">
                  En juego: <b className="tabular-nums">{precio(f.en_juego)}</b> al mes (vende {precio(f.venta_mes)} al mes).
                </p>
              )}
            </section>

            <section>
              <div className="grid grid-cols-3 gap-3">
                <Cifra t="Nuestro (lista)" v={monto(f.nuestro)} />
                <Cifra t={`Mercado${cuentan.length ? ` · ${cuentan.length} ${cuentan.length === 1 ? "tienda" : "tiendas"}` : ""}`} v={monto(f.mercado)} />
                <Cifra t="Diferencia" v={f.dif_pct === null ? "—" : pct(f.dif_pct)} color={f.color} />
              </div>
              <p className="mt-1 text-[12px] text-smn-gris-500">Precios en MXN con impuestos.</p>
              {f.membresia && (
                <div className="mt-3 grid grid-cols-3 gap-3 border-t border-smn-gris-100 pt-3">
                  <Cifra t="Nuestro (membresía)" v={monto(f.membresia)} chico />
                  <span />
                  <Cifra t="Diferencia membresía" v={f.dif_membresia_pct === null ? "—" : pct(f.dif_membresia_pct)} color={f.color_membresia} chico />
                </div>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-[15px] font-semibold">Historial de precios</h3>
              <Grafica serie={d.serie} />
              {d.ultima_fecha && <p className="mt-1 text-[13px] text-smn-gris-500">Última revisión: {haceCuanto(d.ultima_iniciada ?? d.ultima_fecha).toLowerCase()}.</p>}
            </section>

            <section>
              <h3 className="mb-2 text-[15px] font-semibold">Tiendas que cuentan</h3>
              {cuentan.length === 0 ? (
                <p className="text-[14px] text-smn-gris-500">Todavía no hay un precio confirmado de otra tienda.</p>
              ) : (
                <ul className="divide-y divide-smn-gris-100 rounded-xl border border-smn-gris-100">
                  {cuentan.map((p) => (
                    <li key={p.observacion_id} className="flex items-start justify-between gap-3 px-3.5 py-2.5 text-[14px]">
                      <span className="min-w-0">
                        <b className="font-medium">{p.vendedor}</b>
                        {p.titulo && <span className="block truncate text-[13px] text-smn-gris-500">{p.titulo}</span>}
                      </span>
                      <span className="shrink-0 text-right">
                        <b className="tabular-nums">{precio(p.precio)}</b>
                        {p.liga && (
                          <a href={p.liga} target="_blank" rel="noreferrer" className="flex items-center justify-end gap-0.5 text-[13px] text-naranja-tinta underline underline-offset-2">
                            Ver <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {noCuentan.length > 0 && (
              <section>
                <h3 className="mb-2 text-[15px] font-semibold">No cuentan</h3>
                <ul className="space-y-1.5 text-[13px]">
                  {noCuentan.map((p) => (
                    <li key={p.observacion_id} className="flex items-start justify-between gap-3">
                      <span className="min-w-0 text-smn-gris-700">
                        {p.liga ? (
                          <a href={p.liga} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-2">{p.vendedor}</a>
                        ) : (
                          <b className="font-medium">{p.vendedor}</b>
                        )}{" "}
                        · {p.motivo ?? "No cuenta"}
                      </span>
                      <span className="shrink-0 text-smn-gris-500 tabular-nums">{precio(p.precio)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="border-t border-smn-gris-100 pt-4">
              <Boton variante="secundario" onClick={() => setMal(true)} disabled={!v.precios.length}>
                <Flag className="h-4 w-4" /> Algo está mal
              </Boton>
              <p className="mt-1.5 text-[13px] text-smn-gris-500">Si un precio no es de este producto o está equivocado, márcalo y deja de contar al momento.</p>
            </div>
          </div>
        )}
      </motion.aside>
      {mal && f && (
        <EstaMal
          productoId={productoId}
          nombre={f.descripcion ?? f.sku}
          cerrar={() => setMal(false)}
          listo={() => {
            cargar();
            cambio();
          }}
        />
      )}
    </>
  );
}

function Cifra({ t, v, color, chico }: { t: string; v: string; color?: FilaTablero["color"]; chico?: boolean }) {
  return (
    <div>
      <p className="text-[13px] text-smn-gris-500">{t}</p>
      <p className={`flex items-center gap-1.5 font-semibold tabular-nums ${chico ? "text-[16px]" : "text-lg sm:text-xl"}`}>
        {color && <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[color].punto}`} aria-hidden />}
        {v}
      </p>
    </div>
  );
}
