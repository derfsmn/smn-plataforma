"use client";
// Lista del radar de productos: evaluaciones vigentes (propuestas «listas para evaluar» e ideas de Compras) y captura de ideas.

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, LayoutDashboard, Loader2, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { CapturarIdea } from "@/componentes/capturar-idea";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { SEMAFORO } from "@/lib/precios";
import { Boton, Esqueleto } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { useSondeo } from "@/lib/sondeo";
import { colorVigente, ESTADOS_IDEA, EVENTO_ALTA_FOTOS, EVENTO_CAPTURAR, RUTA, type Color, type EvaluacionResumen } from "@/lib/productos";

const TIPOS = [
  { valor: "", texto: "Todos" },
  { valor: "propuesta", texto: "De proveedores" },
  { valor: "idea", texto: "Ideas de Compras" },
] as const;

const ORDEN_COLOR: Color[] = ["verde", "amarillo", "rojo"];

/** Por qué el color no es el que daría el número solo (verde > 80, amarillo 60–80, rojo < 60). Sin esta línea un
 *  «Amarillo 90» parece un error. */
function porQueColor(f: EvaluacionResumen): string | null {
  const c = colorVigente(f);
  const p = f.puntaje;
  if (f.color_final && f.color_final !== f.color) return "Color cambiado a mano";
  if (p == null || !c) return null;
  const porNumero = p > 80 ? "verde" : p >= 60 ? "amarillo" : "rojo";
  if (c === porNumero) return null;
  if (porNumero === "verde" && c === "amarillo" && f.confianza === "baja") return "Faltan datos para darle verde";
  if (c === "rojo") return "No pasa una regla de Compras";
  return null;
}

const sinAcentos = (t: string) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

export default function RadarProductos() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const ajusta = puede("compras.productos.ajustar");
  const [filas, setFilas] = useState<EvaluacionResumen[] | null>(null);
  const [tipo, setTipo] = useState<"" | "propuesta" | "idea">("");
  const [color, setColor] = useState<Color | "">("");
  const [capturando, setCapturando] = useState(false);
  const [conFotos, setConFotos] = useState(false);
  const [q, setQ] = useState("");

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
    const abrir = () => { setConFotos(false); setCapturando(true); };
    const abrirFotos = () => { setConFotos(true); setCapturando(true); };
    window.addEventListener(EVENTO_CAPTURAR, abrir);
    window.addEventListener(EVENTO_ALTA_FOTOS, abrirFotos);
    return () => {
      window.removeEventListener(EVENTO_CAPTURAR, abrir);
      window.removeEventListener(EVENTO_ALTA_FOTOS, abrirFotos);
    };
  }, []);

  // Mientras alguna esté en curso, se vuelve a preguntar
  const enCurso = filas?.some((f) => f.estado === "en_curso");
  useSondeo(cargar, 3000, !!enCurso);

  const cuenta = (c: Color) => filas?.filter((f) => f.estado === "lista" && colorVigente(f) === c).length ?? 0;
  const buscar = sinAcentos(q.trim());
  const visibles = filas?.filter((f) => (!color || (f.estado === "lista" && colorVigente(f) === color)) &&
    (!buscar || sinAcentos([f.sujeto.nombre, f.sujeto.folio, f.sujeto.proveedor, f.sujeto.departamento].filter(Boolean).join(" ")).includes(buscar))) ?? null;

  return (
    <>
      {ajusta && <Pantallas alTerminar={cargar} />}
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
        <label className="relative order-last w-full sm:order-none sm:w-72">
          <span className="sr-only">Buscar producto</span>
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Producto, folio, proveedor o depto."
            className="h-10 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-[15px] outline-none placeholder:text-smn-gris-500 hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
          />
        </label>
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
          {tipo || color || q ? "No hay productos con este filtro." : "Todavía no hay productos evaluados. Captura un producto o espera a que llegue una propuesta del portal."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
          <div className="hidden grid-cols-[minmax(0,1fr)_180px_110px_210px_24px] gap-4 border-b border-smn-gris-100 px-5 py-2.5 text-[13px] text-smn-gris-500 md:grid">
            <span>Producto</span>
            <span>Departamento</span>
            <span>Evaluado</span>
            <span className="text-right">Semáforo</span>
            <span />
          </div>
          <ul className="divide-y divide-smn-gris-100">
            {visibles.map((f, i) => {
              const c = f.estado === "lista" ? colorVigente(f) : null;
              return (
                <motion.li key={f.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.015, 0.2) }}>
                  <Link
                    href={`/compras/productos/${f.id}`}
                    className="group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3.5 transition-colors hover:bg-smn-gris-50 md:grid-cols-[minmax(0,1fr)_180px_110px_210px_24px]"
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
                    <span className="hidden text-sm text-smn-gris-500 md:block">{haceCuanto(f.terminada_en ?? f.creada_en)}</span>
                    {f.estado === "en_curso" ? (
                      <span className="flex items-center justify-end gap-1.5 text-sm text-smn-gris-500">
                        <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" /> Evaluando
                      </span>
                    ) : f.estado === "fallida" ? (
                      <span className="text-right text-sm text-aviso-texto">No se pudo evaluar</span>
                    ) : (
                      <div className="text-right">
                        <p className="flex items-center justify-end gap-2">
                          <span className={`h-2.5 w-2.5 rounded-full ${c ? SEMAFORO[c].punto : "bg-smn-gris-300"}`} aria-hidden />
                          <span className="text-[15px] font-medium">{c ? SEMAFORO[c].texto : "Sin color"}</span>
                          <span className="w-7 text-right text-[15px] text-smn-gris-500 tabular-nums">{f.puntaje ?? "—"}</span>
                        </p>
                        {porQueColor(f) ? (
                          <p className="text-[12.5px] text-aviso-texto">{porQueColor(f)}</p>
                        ) : (
                          f.confianza === "baja" && <p className="text-[12.5px] text-smn-gris-500">Con pocos datos</p>
                        )}
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

      <AnimatePresence>{capturando && <CapturarIdea fotosPrimero={conFotos} cerrar={() => { setCapturando(false); cargar(); }} />}</AnimatePresence>
    </>
  );
}

type EstadoPantallas = { evaluadas: number; sin_pantalla: number; pesos_anteriores: number; trabajo: "preparar" | "recalcular" | null; hechas: number; total: number; resultado: string | null };

/** Solo quien ajusta el radar: dejar lista la pantalla por niveles de todas y recalcular las de los pesos anteriores
 * (plan del 22 nov 2026). Se esconde cuando no hay nada que hacer. */
function Pantallas({ alTerminar }: { alTerminar: () => void }) {
  const avisar = useAvisos();
  const [d, setD] = useState<EstadoPantallas | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const leer = useCallback(() => api<EstadoPantallas>(`${RUTA}/pantallas`).then(setD).catch(() => setD(null)), []);
  useEffect(() => {
    leer();
  }, [leer]);
  const corriendo = !!d?.trabajo;
  useSondeo(leer, 3000, corriendo);
  const [antes, setAntes] = useState(false);
  useEffect(() => {
    if (antes && !corriendo) {
      alTerminar();
      if (d?.resultado) avisar(d.resultado);
    }
    setAntes(corriendo);
  }, [corriendo]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!d || (!d.trabajo && !d.sin_pantalla && !d.pesos_anteriores)) return null;
  const correr = async (que: "preparar" | "recalcular") => {
    setOcupado(true);
    try {
      setD(await api<EstadoPantallas>(`${RUTA}/pantallas/${que}`, { metodo: "POST" }));
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setOcupado(false);
    }
  };
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-smn-gris-100 bg-superficie px-5 py-3">
      {d.trabajo ? (
        <p className="flex items-center gap-2 text-[15px]">
          <Loader2 className="h-4 w-4 text-smn-naranja motion-safe:animate-spin" aria-hidden />
          {d.trabajo === "preparar" ? "Preparando las pantallas" : "Recalculando con los pesos de Dirección"} · {d.hechas} de {d.total}
        </p>
      ) : (
        <p className="text-[15px] text-smn-gris-700">
          {[
            d.sin_pantalla > 0 && `${d.sin_pantalla} de ${d.evaluadas} productos todavía no tienen lista su pantalla por niveles`,
            d.pesos_anteriores > 0 && `${d.pesos_anteriores} se calcularon con los pesos anteriores`,
          ].filter(Boolean).join(" · ")}
          .
        </p>
      )}
      {!d.trabajo && (
        <div className="flex flex-wrap gap-2">
          {d.sin_pantalla > 0 && (
            <Boton variante="secundario" cargando={ocupado} onClick={() => correr("preparar")}>
              <LayoutDashboard className="h-4 w-4" /> Preparar pantallas
            </Boton>
          )}
          {d.pesos_anteriores > 0 && (
            <Boton variante="secundario" cargando={ocupado} onClick={() => correr("recalcular")}>
              <RefreshCw className="h-4 w-4" /> Recalcular todas
            </Boton>
          )}
        </div>
      )}
    </div>
  );
}
