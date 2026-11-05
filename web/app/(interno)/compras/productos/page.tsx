"use client";
// Lista del radar de productos: evaluaciones vigentes (propuestas «listas para evaluar» e ideas de Compras) y captura de ideas.

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { CapturarIdea } from "@/componentes/capturar-idea";
import { useAvisos } from "@/componentes/avisos";
import { SEMAFORO } from "@/lib/precios";
import { Boton, Esqueleto } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { colorVigente, CONFIANZA, ESTADOS_IDEA, EVENTO_CAPTURAR, RUTA, type Color, type EvaluacionResumen } from "@/lib/productos";

const TIPOS = [
  { valor: "", texto: "Todos" },
  { valor: "propuesta", texto: "De proveedores" },
  { valor: "idea", texto: "Ideas de Compras" },
] as const;

const ORDEN_COLOR: Color[] = ["verde", "amarillo", "rojo"];

export default function RadarProductos() {
  const avisar = useAvisos();
  const [filas, setFilas] = useState<EvaluacionResumen[] | null>(null);
  const [tipo, setTipo] = useState<"" | "propuesta" | "idea">("");
  const [color, setColor] = useState<Color | "">("");
  const [capturando, setCapturando] = useState(false);

  // El color se filtra aquí para poder contar cuántos hay de cada uno
  const cargar = useCallback(() => {
    const params = new URLSearchParams();
    if (tipo) params.set("tipo", tipo);
    return api<EvaluacionResumen[]>(`${RUTA}/evaluaciones?${params}`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info"));
  }, [tipo, avisar]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  useEffect(() => {
    const abrir = () => setCapturando(true);
    window.addEventListener(EVENTO_CAPTURAR, abrir);
    return () => window.removeEventListener(EVENTO_CAPTURAR, abrir);
  }, []);

  // Mientras alguna esté en curso, se vuelve a preguntar
  const enCurso = filas?.some((f) => f.estado === "en_curso");
  useEffect(() => {
    if (!enCurso) return;
    const t = setInterval(cargar, 3000);
    return () => clearInterval(t);
  }, [enCurso, cargar]);

  const cuenta = (c: Color) => filas?.filter((f) => f.estado === "lista" && colorVigente(f) === c).length ?? 0;
  const visibles = filas?.filter((f) => !color || (f.estado === "lista" && colorVigente(f) === color)) ?? null;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div role="radiogroup" aria-label="Origen" className="flex max-w-full gap-1 overflow-x-auto rounded-xl bg-smn-gris-100 p-1">
          {TIPOS.map((t) => (
            <button
              key={t.valor}
              role="radio"
              aria-checked={tipo === t.valor}
              onClick={() => setTipo(t.valor)}
              className={`h-9 shrink-0 rounded-lg px-3.5 text-[15px] font-medium whitespace-nowrap transition-colors ${tipo === t.valor ? "bg-superficie text-tinta shadow-sm" : "text-smn-gris-500 hover:text-tinta"}`}
            >
              {t.texto}
            </button>
          ))}
        </div>
        <div role="group" aria-label="Filtrar por color" className="flex flex-wrap gap-2">
          {ORDEN_COLOR.map((c) => {
            const activo = color === c;
            return (
              <button
                key={c}
                aria-pressed={activo}
                onClick={() => setColor(activo ? "" : c)}
                className={`inline-flex h-10 items-center gap-2 rounded-lg border px-3.5 text-[15px] transition-colors ${
                  activo ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 bg-superficie hover:border-smn-gris-300"
                }`}
              >
                <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[c].punto}`} aria-hidden />
                {SEMAFORO[c].texto}
                <span className={`font-semibold tabular-nums ${activo ? "" : "text-smn-gris-700"}`}>{filas ? cuenta(c) : "–"}</span>
              </button>
            );
          })}
        </div>
      </div>

      {visibles === null ? (
        <div className="space-y-2">
          <Esqueleto className="h-14" />
          <Esqueleto className="h-14" />
          <Esqueleto className="h-14" />
        </div>
      ) : visibles.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          {tipo || color ? "No hay productos con este filtro." : "Todavía no hay productos evaluados. Marca una propuesta como «Lista para evaluar» o captura un producto."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
          <div className="hidden grid-cols-[minmax(0,1fr)_200px_150px_130px_24px] gap-4 border-b border-smn-gris-100 px-5 py-2.5 text-[13px] text-smn-gris-500 md:grid">
            <span>Producto</span>
            <span>Departamento</span>
            <span>Evaluado</span>
            <span className="text-right">Puntaje</span>
            <span />
          </div>
          <ul className="divide-y divide-smn-gris-100">
            {visibles.map((f, i) => {
              const c = f.estado === "lista" ? colorVigente(f) : null;
              return (
                <motion.li key={f.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.015, 0.2) }}>
                  <Link
                    href={`/compras/productos/${f.id}`}
                    className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3.5 transition-colors hover:bg-smn-gris-50 md:grid-cols-[minmax(0,1fr)_200px_150px_130px_24px]"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[15px] font-medium">{f.sujeto.nombre}</p>
                      {(f.sujeto.tipo === "propuesta" || !tipo) && (
                        <p className="mt-0.5 truncate text-[13px] text-smn-gris-500">
                          {f.sujeto.tipo === "propuesta" ? `${f.sujeto.folio} · ${f.sujeto.proveedor}` : `Idea de Compras · ${ESTADOS_IDEA[f.sujeto.estado ?? "nueva"]}`}
                          <span className="md:hidden"> · {f.sujeto.departamento ?? "Sin departamento"}</span>
                        </p>
                      )}
                    </div>
                    <span className="hidden truncate text-sm text-smn-gris-700 md:block">{f.sujeto.departamento ?? "Sin departamento"}</span>
                    <span className="hidden text-sm text-smn-gris-500 tabular-nums md:block">{fechaLocal(f.creada_en)}</span>
                    {f.estado === "en_curso" ? (
                      <span className="flex items-center justify-end gap-1.5 text-sm text-smn-gris-500">
                        <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" /> Evaluando
                      </span>
                    ) : f.estado === "fallida" ? (
                      <span className="text-right text-sm text-aviso-texto">No se pudo evaluar</span>
                    ) : (
                      <div className="text-right">
                        <p className="flex items-center justify-end gap-2">
                          <span className="text-[13px] text-smn-gris-700">{c ? SEMAFORO[c].texto : "Sin color"}</span>
                          <span className={`h-2.5 w-2.5 rounded-full ${c ? SEMAFORO[c].punto : "bg-smn-gris-300"}`} aria-hidden />
                          <span className="w-8 text-lg font-semibold tabular-nums">{f.puntaje ?? "—"}</span>
                        </p>
                        {f.confianza && <p className="text-[12px] text-smn-gris-500">Confianza {CONFIANZA[f.confianza].replace(/^Confianza /i, "").toLowerCase()}</p>}
                      </div>
                    )}
                    <ChevronRight className="hidden h-5 w-5 text-smn-gris-300 transition group-hover:translate-x-0.5 group-hover:text-tinta md:block" />
                  </Link>
                </motion.li>
              );
            })}
          </ul>
        </div>
      )}

      <AnimatePresence>{capturando && <CapturarIdea cerrar={() => { setCapturando(false); cargar(); }} />}</AnimatePresence>
    </>
  );
}
