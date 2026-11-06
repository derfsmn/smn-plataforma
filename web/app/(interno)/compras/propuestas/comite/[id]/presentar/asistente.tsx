"use client";
// Piezas de la presentación del comité (pedido de Diego, 2026-11-05): el detalle «a fondo» de cada factor y un asistente de IA local al que el comité le pregunta sobre el producto. El asistente solo contesta con
// la ficha del producto y dice de qué parte sale cada dato.

import { motion, useReducedMotion } from "motion/react";
import { Bot, Boxes, CircleHelp, ExternalLink, Layers, Loader2, NotebookPen, Send, Tag, TrendingUp, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Insignia } from "@/componentes/ui";
import { api, mensajeDe, pesos } from "@/lib/api";
import { RUTA, type Item, type Reunion } from "@/lib/comite";
import { SEMAFORO } from "@/lib/precios";
import { aportes, QUE_MIDE, RUTA as RUTA_PRODUCTOS, type Evaluacion } from "@/lib/productos";

export type Turno = { pregunta: string; respuesta: string; encontrada: boolean; fuentes: { numero: number; titulo: string }[]; aviso?: string | null };

const SUGERENCIAS: { texto: string; icono: typeof Bot }[] = [
  { texto: "¿Por qué salió de este color?", icono: CircleHelp },
  { texto: "¿Qué lo haría subir de calificación?", icono: TrendingUp },
  { texto: "¿Cómo está su precio contra internet?", icono: Tag },
  { texto: "¿Qué productos parecidos ya vendemos?", icono: Boxes },
];

export type Modo = "ia" | "fondo";

/** Panel junto a la diapositiva: en pantalla grande se acomoda a la derecha y deja ver el producto; en celular ocupa todo. */
export function Panel({ i, modo, cambiar, cerrar, children }: { i: Item; modo: Modo; cambiar: (m: Modo) => void; cerrar: () => void; children: React.ReactNode }) {
  const quieto = useReducedMotion();
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && cerrar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [cerrar]);
  const e = i.evaluacion;
  const color = e?.color ?? null;
  const pestanas: { m: Modo; texto: string; icono: typeof Bot }[] = [
    { m: "ia", texto: "Pregúntale a la IA", icono: Bot },
    ...(e ? [{ m: "fondo" as const, texto: "La evaluación a fondo", icono: Layers }] : []),
  ];
  return (
    <motion.aside
      aria-label={`${modo === "ia" ? "Pregúntale a la IA" : "La evaluación a fondo"} · ${i.nombre}`}
      initial={quieto ? { opacity: 0 } : { opacity: 0, x: 48 }}
      animate={{ opacity: 1, x: 0 }}
      exit={quieto ? { opacity: 0 } : { opacity: 0, x: 48 }}
      transition={{ type: "spring", stiffness: 420, damping: 40 }}
      className="fixed inset-0 z-[70] flex flex-col bg-superficie lg:static lg:z-auto lg:w-[40%] lg:min-w-[30rem] lg:max-w-[42rem] lg:shrink-0 lg:border-l lg:border-smn-gris-100"
    >
      <header className="border-b border-smn-gris-100 px-5 pt-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] text-smn-gris-500">Sobre este producto</p>
            <h2 className="truncate text-xl font-semibold leading-tight">{i.nombre}</h2>
          </div>
          {e?.puntaje != null && (
            <span className={`mt-1 inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-semibold tabular-nums ${color ? SEMAFORO[color].insignia : "bg-smn-gris-100"}`}>
              <span className={`h-2 w-2 rounded-full ${color ? SEMAFORO[color].punto : "bg-smn-gris-300"}`} />
              {e.puntaje} de 100
            </span>
          )}
          <button type="button" onClick={cerrar} aria-label="Cerrar" title="Cerrar (Esc)" className="-mr-1.5 rounded-full p-1.5 hover:bg-smn-gris-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div role="tablist" className="mt-3 flex gap-5">
          {pestanas.map(({ m, texto, icono: Icono }) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={modo === m}
              onClick={() => cambiar(m)}
              className={`-mb-px flex items-center gap-2 border-b-2 pb-2.5 text-[15px] font-semibold transition-colors ${
                modo === m ? "border-smn-naranja text-tinta" : "border-transparent text-smn-gris-500 hover:text-tinta"
              }`}
            >
              <Icono className="h-4 w-4" /> {texto}
            </button>
          ))}
        </div>
      </header>
      {children}
    </motion.aside>
  );
}


/** Todo lo que hay detrás de la calificación, factor por factor, para quien quiera ir a fondo. */
export function AFondo({ evaluacionId }: { evaluacionId: number }) {
  const [e, setE] = useState<Evaluacion | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setE(null);
    setError(null);
    api<Evaluacion>(`${RUTA_PRODUCTOS}/evaluaciones/${evaluacionId}`).then(setE).catch((x) => setError(mensajeDe(x)));
  }, [evaluacionId]);
  if (error) return <p className="p-5 text-sm text-red-700 dark:text-red-400">{error}</p>;
  if (!e) return <p className="flex items-center gap-2 p-5 text-smn-gris-500"><Loader2 className="h-4 w-4 animate-spin" /> Cargando la evaluación…</p>;
  const puntos = aportes(e.factores);
  const total = e.factores.reduce((a, f) => a + (f.puntaje !== null ? Number(f.peso) : 0), 0);
  return (
    <div className="flex-1 space-y-5 overflow-y-auto p-5">
      <p className="text-[15px] leading-relaxed text-smn-gris-700">
        Cada factor se califica de 0 a 100 y pesa lo que Compras le dio; los que no tienen datos no cuentan. Los puntos son lo que aporta cada uno a la calificación de {e.puntaje ?? "—"}.
      </p>
      {e.factores.map((f) => (
        <section key={f.factor} className="rounded-2xl border border-smn-gris-100 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-base font-semibold">{f.nombre}</h3>
            <p className="text-sm tabular-nums text-smn-gris-700">
              {f.puntaje !== null ? (
                <>
                  <span className="text-xl font-semibold text-tinta">{f.puntaje}</span> de 100 · pesa {total ? Math.round((Number(f.peso) / total) * 100) : 0} % · aporta {(puntos[f.factor] ?? 0).toFixed(1)} pts
                </>
              ) : (
                "Sin datos: no cuenta"
              )}
            </p>
          </div>
          {f.puntaje !== null && (
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-smn-gris-100" aria-hidden>
              <div className={`h-full rounded-full ${SEMAFORO[f.puntaje > 80 ? "verde" : f.puntaje >= 60 ? "amarillo" : "rojo"].punto}`} style={{ width: `${f.puntaje}%` }} />
            </div>
          )}
          {QUE_MIDE[f.factor] && <p className="mt-2 text-[13px] text-smn-gris-500">{QUE_MIDE[f.factor]}</p>}
          <dl className="mt-2 space-y-1.5 text-[15px]">
            {(
              [
                ["Dato", f.valor],
                ["De dónde salió", f.detalle],
                ["Cómo se calculó", f.calculo],
                ["Qué lo subiría", f.mejora],
              ] as const
            )
              .filter(([, v]) => v)
              .map(([t, v]) => (
                <div key={t}>
                  <dt className="inline font-semibold">{t}: </dt>
                  <dd className="inline">{v}</dd>
                </div>
              ))}
          </dl>
          {f.provisional && <Insignia className="mt-2 bg-smn-gris-100 text-smn-gris-700">Regla provisional, falta que Compras la confirme</Insignia>}
        </section>
      ))}
      {e.mercado && e.mercado.precios.length > 0 && (
        <section>
          <h3 className="mb-1 font-semibold">Precios en internet {e.mercado.mediana && <span className="font-normal text-smn-gris-500">· mediana {pesos(e.mercado.mediana)}</span>}</h3>
          <ul className="space-y-1 text-[15px]">
            {e.mercado.precios.slice(0, 8).map((p, k) => (
              <li key={k} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">
                  {p.liga ? <a href={p.liga} target="_blank" rel="noreferrer" className="underline underline-offset-2">{p.vendedor || p.titulo}</a> : p.vendedor || p.titulo}
                </span>
                <span className="shrink-0 tabular-nums">{pesos(p.precio)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {/* Políticas y reglas de Compras: ocultas por ahora, todas siguen «por revisar» (Diego, 2026-11-05). */}
      {e.comparables.length > 0 && (
        <section>
          <h3 className="mb-1 font-semibold">Parecidos que ya vendemos</h3>
          <ul className="space-y-1 text-[15px]">
            {e.comparables.slice(0, 8).map((c) => (
              <li key={c.producto_id} className="flex justify-between gap-3">
                <span className="min-w-0 truncate">{c.sku} · {c.descripcion}</span>
                {c.precio && <span className="shrink-0 tabular-nums">{pesos(c.precio)}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <a href={`/compras/productos/${e.id}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 font-semibold underline underline-offset-2">
        Abrir la evaluación completa <ExternalLink className="h-4 w-4" />
      </a>
    </div>
  );
}

/** Conversación con la IA local sobre un producto. La plática se conserva mientras dure la presentación. */
export function Asistente({ i, r, turnos, guardar, anotar, listo }: {
  i: Item;
  r: Reunion;
  turnos: Turno[];
  guardar: (t: Turno[]) => void;
  anotar: boolean;
  listo: (r: Reunion) => void;
}) {
  const avisar = useAvisos();
  const [pregunta, setPregunta] = useState("");
  const [pensando, setPensando] = useState<string | null>(null);
  const [anotadas, setAnotadas] = useState<Set<number>>(new Set());
  const fin = useRef<HTMLDivElement>(null);
  const caja = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (turnos.length || pensando) fin.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos.length, pensando]);
  useEffect(() => caja.current?.focus(), []);

  const preguntar = async (texto: string) => {
    const q = texto.trim();
    if (q.length < 3 || pensando) return;
    setPensando(q);
    setPregunta("");
    try {
      const x = await api<Omit<Turno, "pregunta" | "respuesta"> & { texto: string }>(`${RUTA}/productos/${i.id}/preguntar`, {
        cuerpo: { pregunta: q, historial: turnos.filter((t) => t.encontrada).slice(-4).map((t) => ({ pregunta: t.pregunta, respuesta: t.respuesta })) },
      });
      guardar([...turnos, { pregunta: q, respuesta: x.texto, encontrada: x.encontrada, fuentes: x.fuentes, aviso: x.aviso }]);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setPregunta(q);
    } finally {
      setPensando(null);
    }
  };

  const comoPeticion = async (k: number, q: string) => {
    try {
      listo(await api<Reunion>(`${RUTA}/reuniones/${r.id}/peticiones`, { cuerpo: { texto: q, item_id: i.id, asistente_id: null } }));
      setAnotadas(new Set(anotadas).add(k));
      avisar("Petición anotada");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <>
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {turnos.length === 0 && !pensando ? (
          <div className="mx-auto max-w-xl">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-smn-naranja/15 text-smn-naranja">
              <Bot className="h-6 w-6" />
            </div>
            <h3 className="mt-3 text-xl font-semibold">¿Qué quieren saber de este producto?</h3>
            <p className="mt-1 text-[15px] leading-relaxed text-smn-gris-700">
              Contesta con sus datos, el semáforo, los precios en internet y los parecidos que ya vendemos, y dice de dónde sale cada dato.
            </p>
            <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
              {SUGERENCIAS.map(({ texto, icono: Icono }) => (
                <button
                  key={texto}
                  type="button"
                  onClick={() => preguntar(texto)}
                  className="group flex items-start gap-3 rounded-2xl border border-smn-gris-100 p-3.5 text-left text-[15px] leading-snug transition-colors hover:border-smn-naranja/60 hover:bg-smn-naranja/5"
                >
                  <Icono className="mt-0.5 h-4 w-4 shrink-0 text-smn-gris-500 group-hover:text-smn-naranja" />
                  {texto}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {turnos.map((t, k) => (
              <div key={k} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-tinta px-4 py-2.5 text-base text-superficie">{t.pregunta}</p>
                <div className="max-w-[94%] rounded-2xl rounded-bl-md bg-smn-gris-50 px-4 py-3 text-base leading-relaxed">
                  <p className="whitespace-pre-line"><ConCitas texto={t.respuesta} /></p>
                  {t.fuentes.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-[13px]">
                      <span className="text-smn-gris-500">Sale de</span>
                      {t.fuentes.map((f) => (
                        <span key={f.numero} className="rounded-full border border-smn-gris-100 bg-superficie px-2 py-0.5 text-smn-gris-700">
                          <span className="tabular-nums text-smn-gris-500">{f.numero}</span> {f.titulo}
                        </span>
                      ))}
                    </div>
                  )}
                  {t.aviso && <p className="mt-2 text-[13px] text-aviso-texto">{t.aviso}</p>}
                  {!t.encontrada && anotar && (
                    <Boton variante="secundario" className="mt-2.5" disabled={anotadas.has(k)} onClick={() => comoPeticion(k, t.pregunta)}>
                      <NotebookPen className="h-4 w-4" /> {anotadas.has(k) ? "Anotada como petición" : "Anotar como petición"}
                    </Boton>
                  )}
                </div>
              </div>
            ))}
            {pensando && (
              <div className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-tinta px-4 py-2.5 text-base text-superficie">{pensando}</p>
                <p className="flex w-fit items-center gap-2 rounded-2xl bg-smn-gris-50 px-4 py-3 text-base text-smn-gris-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Revisando la ficha del producto…
                </p>
              </div>
            )}
            <div ref={fin} />
          </div>
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          preguntar(pregunta);
        }}
        className="border-t border-smn-gris-100 px-4 pb-3 pt-3"
      >
        <div className="flex items-end gap-2">
        <textarea
          ref={caja}
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              preguntar(pregunta);
            }
          }}
          rows={1}
          maxLength={500}
          placeholder="Pregunta sobre este producto…"
          aria-label="Pregunta para el asistente"
          className="min-h-11 flex-1 resize-none rounded-xl border border-smn-gris-100 bg-superficie px-3 py-2 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
        />
        <Boton type="submit" disabled={pregunta.trim().length < 3 || !!pensando} aria-label="Preguntar">
          <Send className="h-4 w-4" />
        </Boton>
        </div>
        <p className="mt-1.5 text-xs text-smn-gris-500">Solo usa la ficha del producto y la IA local: nada sale a internet. Enter para preguntar.</p>
      </form>
    </>
  );
}

/** Los «[3]» de la respuesta se ven como una marca chica que dice de qué sección sale. */
function ConCitas({ texto }: { texto: string }) {
  return texto.split(/\s?\[(\d{1,2})\]/).map((x, k) =>
    k % 2 ? (
      <sup key={k} className="ml-0.5 rounded bg-superficie px-1 text-[11px] font-semibold tabular-nums text-smn-gris-500">{x}</sup>
    ) : (
      x
    ),
  );
}

export function BotonAsistente({ onClick }: { onClick: () => void }) {
  return (
    <Boton variante="secundario" onClick={onClick}>
      <Bot className="h-4 w-4" /> Pregúntale a la IA
    </Boton>
  );
}
