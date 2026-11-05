"use client";
// Modo presentación del comité: pantalla completa, un producto por pantalla para proyectar, con su semáforo y por qué
// se eligió. Primero se registra quién asiste; en cada producto se decide ahí mismo y se anotan las peticiones.
// Se avanza con las flechas del teclado; al final sale el resumen.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronLeft, ChevronRight, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Semaforo } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { DECISION, fechaReunion, MODELO, pesos, RUTA, VALOR, type Item, type Reunion } from "@/lib/comite";
import { SEMAFORO } from "@/lib/precios";
import { AgregarAsistente, FormDecision, Foto, ListaPeticiones, NuevaPeticion } from "../../piezas";

export default function Presentar() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const quieto = useReducedMotion();
  const [r, setR] = useState<Reunion | null>(null);
  const [pos, setPos] = useState(0);
  const [dir, setDir] = useState(1);
  const [asistentes, setAsistentes] = useState(false);

  useEffect(() => {
    api<Reunion>(`${RUTA}/reuniones/${id}`).then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);

  const elegidos = r?.productos.filter((i) => i.prefiltro === "pasa") ?? [];
  const total = elegidos.length + 2; // portada + productos + resumen
  const ir = useCallback((n: number) => {
    setDir(n > pos ? 1 : -1);
    setPos(Math.max(0, Math.min(total - 1, n)));
  }, [pos, total]);
  const salir = useCallback(() => router.push(`/compras/propuestas/comite/${id}`), [router, id]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (asistentes || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") ir(pos + 1);
      else if (e.key === "ArrowLeft" || e.key === "PageUp") ir(pos - 1);
      else if (e.key === "Escape") salir();
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [ir, pos, salir, asistentes]);

  if (!r) return <div className="fixed inset-0 z-[60] bg-superficie" />;

  const decidir = r.estado === "comite" && puede("compras.comite.decidir");
  const anotar = r.estado === "comite" && (puede("compras.comite.decidir") || puede("compras.comite.prefiltrar"));
  const actual = pos > 0 && pos <= elegidos.length ? elegidos[pos - 1] : null;

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-superficie text-tinta">
      <header className="flex items-center gap-3 border-b border-smn-gris-100 px-4 py-2.5 sm:px-6">
        <p className="min-w-0 flex-1 truncate text-sm text-smn-gris-500">
          Comité de producto nuevo · <span className="first-letter:uppercase">{fechaReunion(r.fecha, { day: "numeric", month: "long", year: "numeric" })}</span>
        </p>
        <span className="text-sm tabular-nums text-smn-gris-500">{actual ? `${pos} de ${elegidos.length}` : ""}</span>
        <button type="button" onClick={salir} aria-label="Salir de la presentación" className="rounded-full p-1.5 hover:bg-smn-gris-100">
          <X className="h-5 w-5" />
        </button>
      </header>

      <main className="relative flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={pos}
            custom={dir}
            initial={quieto ? { opacity: 0 } : { opacity: 0, x: 40 * dir }}
            animate={{ opacity: 1, x: 0 }}
            exit={quieto ? { opacity: 0 } : { opacity: 0, x: -40 * dir }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-10"
          >
            {pos === 0 ? (
              <Portada r={r} elegidos={elegidos.length} registrar={() => setAsistentes(true)} puedeRegistrar={puede("compras.comite.decidir") || puede("compras.comite.prefiltrar")} empezar={() => ir(1)} />
            ) : actual ? (
              <Diapositiva i={actual} r={r} decidir={decidir} anotar={anotar} listo={setR} />
            ) : (
              <Resumen r={r} elegidos={elegidos} ir={ir} />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="flex items-center gap-3 border-t border-smn-gris-100 px-4 py-2.5 sm:px-6">
        <Boton variante="secundario" onClick={() => ir(pos - 1)} disabled={pos === 0} aria-label="Anterior">
          <ChevronLeft className="h-4 w-4" /> <span className="hidden sm:inline">Anterior</span>
        </Boton>
        <div className="flex flex-1 flex-wrap justify-center gap-1.5" aria-hidden>
          {Array.from({ length: total }, (_, k) => {
            const i = k > 0 && k <= elegidos.length ? elegidos[k - 1] : null;
            return (
              <button
                key={k}
                type="button"
                tabIndex={-1}
                onClick={() => ir(k)}
                className={`h-2 rounded-full transition-all ${k === pos ? "w-6 bg-smn-naranja" : i?.decision ? "w-2 bg-tinta/60" : "w-2 bg-smn-gris-300"}`}
              />
            );
          })}
        </div>
        <Boton onClick={() => ir(pos + 1)} disabled={pos === total - 1} aria-label="Siguiente">
          <span className="hidden sm:inline">Siguiente</span> <ChevronRight className="h-4 w-4" />
        </Boton>
      </footer>

      <AnimatePresence>{asistentes && <AgregarAsistente reunion={r} cerrar={() => setAsistentes(false)} listo={setR} />}</AnimatePresence>
    </div>
  );
}

function Portada({ r, elegidos, registrar, puedeRegistrar, empezar }: { r: Reunion; elegidos: number; registrar: () => void; puedeRegistrar: boolean; empezar: () => void }) {
  return (
    <div className="mx-auto max-w-3xl py-6 text-center sm:py-12">
      <p className="text-lg text-smn-gris-500">Comité de producto nuevo</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight first-letter:uppercase sm:text-6xl">{fechaReunion(r.fecha)}</h1>
      <p className="mt-4 text-xl text-smn-gris-700">
        {elegidos} {elegidos === 1 ? "producto pasó" : "productos pasaron"} el pre-filtro de Compras de {r.embudo.subidos} que se subieron.
      </p>
      <section className="mt-10 rounded-2xl bg-smn-gris-50 p-5 text-left">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">¿Quién asiste?</h2>
          {puedeRegistrar && r.estado !== "cerrada" && (
            <Boton variante="secundario" onClick={registrar}>
              <UserPlus className="h-4 w-4" /> Registrar asistentes
            </Boton>
          )}
        </div>
        {r.asistentes.length === 0 ? (
          <p className="text-smn-gris-500">Todavía no se registra a nadie.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {r.asistentes.map((a) => (
              <li key={a.id} className="rounded-full bg-superficie px-3 py-1.5">
                {a.nombre}{a.puesto && <span className="text-smn-gris-500"> · {a.puesto}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
      {elegidos > 0 && (
        <Boton className="mt-8 px-6 text-lg" onClick={empezar}>
          Empezar <ChevronRight className="h-5 w-5" />
        </Boton>
      )}
    </div>
  );
}

function Diapositiva({ i, r, decidir, anotar, listo }: { i: Item; r: Reunion; decidir: boolean; anotar: boolean; listo: (r: Reunion) => void }) {
  const [foto, setFoto] = useState(0);
  const e = i.evaluacion?.estado === "lista" ? i.evaluacion : null;
  const color = e?.color ?? null;
  const peticiones = r.peticiones.filter((p) => p.item_id === i.id);
  const datos = [
    ["Precio al público", pesos(i.precio)],
    ["Costo sin IVA", pesos(i.costo)],
    ["Margen", i.margen != null ? `${Number(i.margen).toFixed(0)} %` : null],
  ].filter(([, v]) => v) as [string, string][];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div>
        <Foto i={i} n={foto} className="aspect-square w-full rounded-3xl" />
        {i.fotos > 1 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {Array.from({ length: i.fotos }, (_, n) => (
              <button key={n} type="button" onClick={() => setFoto(n)} aria-label={`Foto ${n + 1}`} className={`overflow-hidden rounded-xl border-2 ${n === foto ? "border-smn-naranja" : "border-transparent"}`}>
                <Foto i={i} n={n} className="h-16 w-16" />
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="min-w-0 space-y-6">
        <div>
          <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-5xl">{i.nombre}</h1>
          <p className="mt-2 text-lg text-smn-gris-700">
            {[i.marca, i.presentacion, i.departamento].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-1 text-lg">
            {i.proveedor ? (
              <>
                <span className="text-smn-gris-500">{i.proveedor_actual ? "Proveedor actual:" : "Proveedor nuevo:"}</span> {i.proveedor}
              </>
            ) : (
              <span className="text-smn-gris-500">Sin proveedor todavía</span>
            )}
          </p>
          {i.origen === "espera" && i.viene_de_fecha && (
            <Insignia className="mt-2 bg-smn-gris-100 text-smn-gris-700">Quedó en espera el {fechaReunion(i.viene_de_fecha, { day: "numeric", month: "long" })}</Insignia>
          )}
        </div>

        {datos.length > 0 && (
          <dl className="grid grid-cols-3 gap-3">
            {datos.map(([t, v]) => (
              <div key={t} className="rounded-2xl bg-smn-gris-50 p-3">
                <dt className="text-sm text-smn-gris-500">{t}</dt>
                <dd className="text-2xl font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        )}

        <section className="flex gap-5 rounded-3xl border border-smn-gris-100 p-5">
          <Semaforo color={color} tam="lg" />
          <div className="min-w-0 flex-1">
            {e ? (
              <>
                <p className="text-sm text-smn-gris-500">{e.modelo ? MODELO[e.modelo] : "Semáforo"}</p>
                <p className="text-4xl font-semibold">
                  {e.puntaje ?? "—"}
                  <span className="text-lg font-normal text-smn-gris-500"> de 100 · {color ? SEMAFORO[color].texto.toLowerCase() : "sin color"}</span>
                </p>
                {e.motivo_cambio && <p className="mt-1 text-sm text-smn-gris-700">Compras cambió el color: {e.motivo_cambio}</p>}
                <ul className="mt-3 space-y-1.5">
                  {e.factores.map((f) => (
                    <li key={f.factor} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-sm">
                      <span className="text-smn-gris-700">{f.nombre}</span>
                      <span className="h-2 overflow-hidden rounded-full bg-smn-gris-100" title={f.valor ?? undefined}>
                        {f.puntaje != null && (
                          <motion.span
                            className={`block h-full rounded-full ${f.puntaje > 80 ? "bg-green-600" : f.puntaje >= 60 ? "bg-yellow-500" : "bg-red-600"}`}
                            initial={{ width: 0 }}
                            animate={{ width: `${f.puntaje}%` }}
                            transition={{ duration: 0.5 }}
                          />
                        )}
                      </span>
                      <span className="text-right font-semibold tabular-nums">{f.puntaje ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-smn-gris-500">Este producto no tiene semáforo.</p>
            )}
          </div>
        </section>

        <section>
          <h2 className="mb-1 text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">Por qué se eligió</h2>
          <p className="text-xl">{i.prefiltro_motivo}</p>
          {i.criterios.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {i.criterios.map((c) => (
                <Insignia key={c.criterio} className={`text-sm ${VALOR[c.valor].clase}`}>{c.criterio}: {VALOR[c.valor].texto.toLowerCase()}{c.nota && ` (${c.nota})`}</Insignia>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl bg-smn-gris-50 p-5">
          <h2 className="mb-3 font-semibold">Decisión del comité</h2>
          {decidir ? (
            <FormDecision i={i} listo={listo} grande />
          ) : i.decision ? (
            <p className="text-lg">
              <Insignia className={`text-base ${DECISION[i.decision].clase}`}>{DECISION[i.decision].texto}</Insignia> {i.decision_motivo}
            </p>
          ) : (
            <p className="text-smn-gris-500">Sin decisión.</p>
          )}
          {(anotar || peticiones.length > 0) && (
            <div className="mt-4 border-t border-smn-gris-100 pt-4">
              <h3 className="mb-2 text-sm font-semibold">Peticiones sobre este producto</h3>
              {peticiones.length > 0 && <ListaPeticiones peticiones={peticiones} />}
              {anotar && (
                <div className="mt-2">
                  <NuevaPeticion reunion={r} item={i} listo={listo} />
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Resumen({ r, elegidos, ir }: { r: Reunion; elegidos: Item[]; ir: (n: number) => void }) {
  const grupos = (["aceptado", "denegado", "en_espera"] as const).map((d) => ({ d, lista: elegidos.filter((i) => i.decision === d) }));
  const faltan = elegidos.filter((i) => !i.decision);
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-4xl font-semibold tracking-tight">Resumen</h1>
      <p className="mt-2 text-xl text-smn-gris-700">
        {grupos[0].lista.length} {grupos[0].lista.length === 1 ? "aceptado" : "aceptados"} de {elegidos.length} presentados.
      </p>
      {faltan.length > 0 && (
        <p className="mt-4 rounded-2xl bg-aviso-fondo p-3 text-aviso-texto">
          Falta decidir: {faltan.map((i) => (
            <button key={i.id} type="button" onClick={() => ir(elegidos.indexOf(i) + 1)} className="mr-2 font-semibold underline underline-offset-2">{i.nombre}</button>
          ))}
        </p>
      )}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {grupos.map(({ d, lista }) => (
          <section key={d} className="rounded-2xl border border-smn-gris-100 p-4">
            <h2 className="mb-2 flex items-center justify-between font-semibold">
              <Insignia className={`text-sm ${DECISION[d].clase}`}>{DECISION[d].texto}</Insignia>
              <span className="text-2xl tabular-nums">{lista.length}</span>
            </h2>
            <ul className="space-y-1 text-[15px]">
              {lista.map((i) => <li key={i.id}>{i.nombre}</li>)}
            </ul>
          </section>
        ))}
      </div>
      <p className="mt-6 text-smn-gris-700">
        {((n) => (n === 1 ? "1 petición por atender." : `${n} peticiones por atender.`))(r.peticiones.filter((p) => p.estado === "abierta").length)} Lo que quedó «En espera» entra a la siguiente reunión al cerrar esta.
      </p>
      <Link href={`/compras/propuestas/comite/${r.id}`} className="mt-6 inline-flex min-h-10 items-center rounded-lg bg-[var(--resalte)] px-4 py-2 text-[15px] font-medium text-[var(--resalte-tinta)]">
        Volver al ciclo
      </Link>
    </div>
  );
}
