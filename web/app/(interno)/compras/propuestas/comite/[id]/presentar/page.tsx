"use client";
// Modo presentación del comité: pantalla completa, un producto por pantalla para proyectar, con su semáforo y por qué
// se eligió. Primero se registra quién asiste; en cada producto se decide ahí mismo y se anotan las peticiones.
// Se avanza con las flechas del teclado; al final sale el resumen. En cada producto: el porqué del semáforo resumido,
// «Ver a fondo» con cada factor y un asistente de IA local para las preguntas del comité.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowDownRight, ArrowUpRight, Check, FileDown, MonitorPlay, TriangleAlert, ChevronLeft, ChevronRight, Layers, Minus, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { DECISION, descargarActa, fechaReunion, pesos, RUTA, VALOR, type Item, type Parecidos, type Reunion } from "@/lib/comite";
import { SEMAFORO } from "@/lib/precios";
import { Miniatura } from "../../../../precios/piezas";
import { AgregarAsistente, FormDecision, Foto, ListaPeticiones, NuevaPeticion } from "../../piezas";
import { AFondo, Asistente, BotonAsistente, Panel, type Modo, type Turno } from "./asistente";

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
  const [panel, setPanel] = useState<Modo | null>(null);
  const [platicas, setPlaticas] = useState<Record<number, Turno[]>>({});
  const [rojoAbierto, setRojoAbierto] = useState<number | null>(null);
  const [proyector, setProyector] = useState(false);
  useEffect(() => {
    try {
      setProyector(localStorage.getItem("comite.proyector") === "1");
    } catch {}
  }, []);
  const cambiarProyector = () =>
    setProyector((v) => {
      try {
        localStorage.setItem("comite.proyector", v ? "0" : "1");
      } catch {}
      return !v;
    });

  useEffect(() => {
    api<Reunion>(`${RUTA}/reuniones/${id}`).then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);

  // Orden (Diego, 2026-11-06): de la calificación más alta a la más baja; los rojos van juntos en una sola diapositiva
  const elegidos = r?.productos.filter((i) => i.prefiltro === "pasa") ?? [];
  const { ordenados, rojos } = ordenar(elegidos);
  const posRojos = rojos.length ? ordenados.length + 1 : -1;
  const total = ordenados.length + (rojos.length ? 1 : 0) + 2; // portada + productos + rojos + resumen
  const ir = useCallback((n: number) => {
    setDir(n > pos ? 1 : -1);
    setPos(Math.max(0, Math.min(total - 1, n)));
    setRojoAbierto(null);
  }, [pos, total]);
  const abrirProducto = (i: Item) => {
    if (esRojo(i)) {
      ir(posRojos);
      setRojoAbierto(i.id);
    } else ir(ordenados.indexOf(i) + 1);
  };
  const salir = useCallback(() => router.push(`/compras/propuestas/comite/${id}`), [router, id]);
  const cerrarPanel = useCallback(() => setPanel(null), []);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (asistentes || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") ir(pos + 1);
      else if (e.key === "ArrowLeft" || e.key === "PageUp") ir(pos - 1);
      else if (e.key === "Escape" && !panel) {
        if (rojoAbierto) setRojoAbierto(null);
        else salir();
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [ir, pos, salir, asistentes, panel, rojoAbierto]);

  if (!r) return <div className="fixed inset-0 z-[60] bg-superficie" />;


  const decidir = r.estado === "comite" && puede("compras.comite.decidir");
  const anotar = r.estado === "comite" && (puede("compras.comite.decidir") || puede("compras.comite.prefiltrar"));
  const actual =
    pos > 0 && pos <= ordenados.length ? ordenados[pos - 1] : pos === posRojos ? (rojos.find((i) => i.id === rojoAbierto) ?? null) : null;

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-superficie text-tinta">
      <header className="flex items-center gap-3 border-b border-smn-gris-100 px-4 py-2.5 sm:px-6">
        <p className="min-w-0 flex-1 truncate text-sm text-smn-gris-500">
          Comité de producto nuevo · <span className="first-letter:uppercase">{fechaReunion(r.fecha, { day: "numeric", month: "long", year: "numeric" })}</span>
        </p>
        <span className="text-sm tabular-nums text-smn-gris-500">
          {pos > 0 && pos <= ordenados.length ? `${pos} de ${ordenados.length}` : pos === posRojos ? `Rojos · ${rojos.length}` : ""}
        </span>
        <button
          type="button"
          onClick={cambiarProyector}
          aria-pressed={proyector}
          title="En modo proyector la diapositiva solo muestra lo ejecutivo; la decisión se registra en la barra de abajo"
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm ${proyector ? "bg-tinta text-superficie" : "text-smn-gris-500 hover:bg-smn-gris-100"}`}
        >
          <MonitorPlay className="h-4 w-4" /> <span className="hidden sm:inline">Modo proyector</span>
        </button>
        <button type="button" onClick={salir} aria-label="Salir de la presentación" className="rounded-full p-1.5 hover:bg-smn-gris-100">
          <X className="h-5 w-5" />
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
      <main className="relative flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={`${pos}-${pos === posRojos ? (rojoAbierto ?? "todos") : ""}`}
            custom={dir}
            initial={quieto ? { opacity: 0 } : { opacity: 0, x: 40 * dir }}
            animate={{ opacity: 1, x: 0 }}
            exit={quieto ? { opacity: 0 } : { opacity: 0, x: -40 * dir }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="@container mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-10"
          >
            {pos === 0 ? (
              <Portada r={r} ordenados={ordenados} rojos={rojos} registrar={() => setAsistentes(true)} puedeRegistrar={puede("compras.comite.decidir") || puede("compras.comite.prefiltrar")} abrirProducto={abrirProducto} />
            ) : actual ? (
              <>
                {pos === posRojos && (
                  <button type="button" onClick={() => setRojoAbierto(null)} className="mb-4 inline-flex items-center gap-1.5 text-[15px] font-semibold text-smn-gris-700 hover:text-tinta">
                    <ChevronLeft className="h-4 w-4" /> Volver a los productos en rojo
                  </button>
                )}
                <Diapositiva i={actual} r={r} decidir={decidir} anotar={anotar} listo={setR} abrir={setPanel} proyector={proyector} />
              </>
            ) : pos === posRojos ? (
              <Rojos rojos={rojos} decidir={decidir} listo={setR} abrir={(i) => setRojoAbierto(i.id)} />
            ) : (
              <Resumen r={r} elegidos={[...ordenados, ...rojos]} abrirProducto={abrirProducto} />
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      {proyector && actual && (decidir || anotar || actual.decision) && <BarraDecision key={actual.id} i={actual} r={r} decidir={decidir} anotar={anotar} listo={setR} />}
      <footer className="flex items-center gap-3 border-t border-smn-gris-100 px-4 py-2.5 sm:px-6">
        <Boton variante="secundario" onClick={() => ir(pos - 1)} disabled={pos === 0} aria-label="Anterior">
          <ChevronLeft className="h-4 w-4" /> <span className="hidden sm:inline">Anterior</span>
        </Boton>
        <div className="flex flex-1 flex-wrap justify-center gap-1.5" aria-hidden>
          {Array.from({ length: total }, (_, k) => {
            const i = k > 0 && k <= ordenados.length ? ordenados[k - 1] : null;
            const rojosListos = k === posRojos && rojos.every((x) => x.decision);
            return (
              <button
                key={k}
                type="button"
                tabIndex={-1}
                onClick={() => ir(k)}
                className={`h-2 rounded-full transition-all ${k === pos ? "w-6 bg-smn-naranja" : k === posRojos ? (rojosListos ? "w-2 bg-red-600/60" : "w-2 bg-red-600") : i?.decision || rojosListos ? "w-2 bg-tinta/60" : "w-2 bg-smn-gris-300"}`}
              />
            );
          })}
        </div>
        <Boton onClick={() => ir(pos + 1)} disabled={pos === total - 1} aria-label="Siguiente">
          <span className="hidden sm:inline">Siguiente</span> <ChevronRight className="h-4 w-4" />
        </Boton>
      </footer>
      </div>
      <AnimatePresence>
        {panel && actual && (
          <Panel key="panel" i={actual} modo={actual.evaluacion ? panel : "ia"} cambiar={setPanel} cerrar={cerrarPanel}>
            {panel === "fondo" && actual.evaluacion ? (
              <AFondo evaluacionId={actual.evaluacion.id} />
            ) : (
              <Asistente
                key={actual.id}
                i={actual}
                r={r}
                turnos={platicas[actual.id] ?? []}
                guardar={(t) => setPlaticas((p) => ({ ...p, [actual.id]: t }))}
                anotar={anotar}
                listo={setR}
              />
            )}
          </Panel>
        )}
      </AnimatePresence>
      </div>

      <AnimatePresence>{asistentes && <AgregarAsistente reunion={r} cerrar={() => setAsistentes(false)} listo={setR} />}</AnimatePresence>
    </div>
  );
}

/** Portada: la fecha, cuántos productos llegan y el orden del día, para que el comité vea de un vistazo qué se va a decidir. */
function Portada({ r, ordenados, rojos, registrar, puedeRegistrar, abrirProducto }: { r: Reunion; ordenados: Item[]; rojos: Item[]; registrar: () => void; puedeRegistrar: boolean; abrirProducto: (i: Item) => void }) {
  const elegidos = [...ordenados, ...rojos];
  const incompletos = elegidos.filter((i) => i.faltantes.length && !i.decision);
  const fecha = fechaReunion(r.fecha);
  const coma = fecha.indexOf(", ");
  const [dia, resto] = coma > 0 ? [fecha.slice(0, coma), fecha.slice(coma + 2)] : ["", fecha];
  const anio = resto.match(/ de (\d{4})$/);
  const fechaCorta = anio ? resto.slice(0, anio.index) : resto;
  const colores = (["verde", "amarillo", "rojo"] as const)
    .map((c) => ({ c, n: elegidos.filter((i) => i.evaluacion?.estado === "lista" && i.evaluacion.color === c).length }))
    .filter((x) => x.n);
  const decididos = elegidos.filter((i) => i.decision).length;
  const cifras = [
    { n: r.embudo.subidos, t: r.embudo.subidos === 1 ? "producto se subió" : "productos se subieron" },
    { n: elegidos.length, t: elegidos.length === 1 ? "pasó el pre-filtro de Compras" : "pasaron el pre-filtro de Compras" },
    { n: elegidos.length - decididos, t: "por decidir hoy" },
  ];
  return (
    <div className="grid gap-10 py-2 @4xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] @4xl:gap-14 @4xl:py-8">
      <div className="flex flex-col">
        <p className="text-sm font-semibold tracking-[0.14em] text-smn-naranja uppercase">Comité de producto nuevo</p>
        <h1 className="mt-4 text-5xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-7xl">{fechaCorta}</h1>
        <p className="mt-2 text-2xl text-smn-gris-500 first-letter:uppercase">{[dia, anio?.[1]].filter(Boolean).join(" · ")}</p>

        <dl className="mt-10 grid grid-cols-3 gap-3">
          {cifras.map((x) => (
            <div key={x.t} className="rounded-2xl bg-smn-gris-50 px-4 py-3.5">
              <dt className="sr-only">{x.t}</dt>
              <dd className="text-4xl font-semibold tabular-nums">{x.n}</dd>
              <dd className="mt-1 text-sm leading-snug text-smn-gris-700">{x.t}</dd>
            </div>
          ))}
        </dl>
        {colores.length > 0 && (
          <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[15px] text-smn-gris-700">
            <span className="text-smn-gris-500">Semáforo:</span>
            {colores.map(({ c, n }) => (
              <span key={c} className="inline-flex items-center gap-1.5">
                <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[c].punto}`} /> {n} {SEMAFORO[c].texto.toLowerCase()}{n > 1 ? "s" : ""}
              </span>
            ))}
          </p>
        )}

        <section className="mt-10">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">Asisten</h2>
            {puedeRegistrar && r.estado !== "cerrada" && (
              <button type="button" onClick={registrar} className="inline-flex items-center gap-1.5 text-sm font-semibold underline-offset-2 hover:underline">
                <UserPlus className="h-4 w-4" /> Registrar asistentes
              </button>
            )}
          </div>
          {r.asistentes.length === 0 ? (
            <p className="mt-2 text-smn-gris-500">Todavía no se registra a nadie.</p>
          ) : (
            <ul className="mt-2 flex flex-wrap gap-2">
              {r.asistentes.map((a) => (
                <li key={a.id} className="flex items-center gap-2 rounded-full border border-smn-gris-100 py-1 pr-3 pl-1">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-smn-naranja/15 text-xs font-semibold text-smn-naranja" aria-hidden>
                    {[a.nombre.split(" ")[0], a.nombre.split(" ").length > 1 ? a.nombre.split(" ").at(-1) : ""].map((x) => x?.[0] ?? "").join("").toUpperCase()}
                  </span>
                  <span>
                    {a.nombre}
                    {a.puesto && <span className="text-smn-gris-500"> · {a.puesto}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="self-start rounded-3xl border border-smn-gris-100 p-5 sm:p-6">
        <h2 className="text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">Orden del día</h2>
        {incompletos.length > 0 && (
          <p className="mt-2 rounded-xl bg-aviso-fondo px-3 py-2 text-sm text-aviso-texto">
            {incompletos.length === 1 ? "1 producto no está listo" : `${incompletos.length} productos no están listos`} para presentar. Están marcados abajo con lo que les falta.
          </p>
        )}
        {elegidos.length === 0 ? (
          <p className="mt-3 text-lg text-smn-gris-700">Ningún producto pasó el pre-filtro de Compras para esta reunión.</p>
        ) : (
          <ol className="mt-3 divide-y divide-smn-gris-100">
            {elegidos.map((i, k) => {
              const primerRojo = rojos.length > 0 && k === ordenados.length;
              const e = i.evaluacion?.estado === "lista" ? i.evaluacion : null;
              return (
                <li key={i.id}>
                  {primerRojo && (
                    <p className="pt-4 pb-1 text-sm font-semibold text-red-700 dark:text-red-400">
                      En rojo · {rojos.length === 1 ? "se ve" : `se ven los ${rojos.length} juntos`} en una diapositiva
                    </p>
                  )}
                  <button type="button" onClick={() => abrirProducto(i)} className="group flex w-full items-center gap-4 py-3 text-left">
                    <span className="w-5 shrink-0 text-right text-sm tabular-nums text-smn-gris-500">{k + 1}</span>
                    <Foto i={i} className="h-14 w-14 shrink-0 rounded-xl" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-lg font-semibold group-hover:underline">{i.nombre}</span>
                      {i.faltantes.length > 0 && !i.decision && (
                        <span className="flex items-center gap-1 text-[13px] text-aviso-texto">
                          <TriangleAlert className="h-3.5 w-3.5 shrink-0" /> Falta {i.faltantes.join(", ")}
                        </span>
                      )}
                      <span className="block truncate text-sm text-smn-gris-500">
                        {[i.marca, i.departamento, i.proveedor ? (i.proveedor_actual ? "Proveedor actual" : "Proveedor nuevo") : "Sin proveedor"].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    {i.decision ? (
                      <Insignia className={DECISION[i.decision].clase}>{DECISION[i.decision].texto}</Insignia>
                    ) : e?.puntaje != null ? (
                      <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-semibold tabular-nums ${e.color ? SEMAFORO[e.color].insignia : "bg-smn-gris-100"}`}>
                        <span className={`h-2 w-2 rounded-full ${e.color ? SEMAFORO[e.color].punto : "bg-smn-gris-300"}`} />
                        {e.puntaje}
                      </span>
                    ) : (
                      <span className="shrink-0 text-sm text-smn-gris-500">Sin semáforo</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
        {elegidos.length > 0 && (
          <Boton className="mt-6 w-full justify-center py-3 text-lg" onClick={() => abrirProducto(elegidos[0])}>
            Empezar con {elegidos[0].nombre.length > 28 ? "el primero" : elegidos[0].nombre} <ChevronRight className="h-5 w-5" />
          </Boton>
        )}
      </section>
    </div>
  );
}

function Diapositiva({ i, r, decidir, anotar, listo, abrir, proyector = false }: { i: Item; r: Reunion; decidir: boolean; anotar: boolean; listo: (r: Reunion) => void; abrir: (modo: "fondo" | "ia") => void; proyector?: boolean }) {
  const [foto, setFoto] = useState(0);
  const e = i.evaluacion?.estado === "lista" ? i.evaluacion : null;
  const peticiones = r.peticiones.filter((p) => p.item_id === i.id);

  return (
    <div className="grid gap-8 @4xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] @4xl:gap-12">
      <div className="space-y-5">
        <Foto i={i} n={foto} className="aspect-square w-full rounded-3xl" />
        {i.fotos > 1 && (
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: i.fotos }, (_, n) => (
              <button key={n} type="button" onClick={() => setFoto(n)} aria-label={`Foto ${n + 1}`} className={`overflow-hidden rounded-xl border-2 ${n === foto ? "border-smn-naranja" : "border-transparent"}`}>
                <Foto i={i} n={n} className="h-16 w-16" />
              </button>
            ))}
          </div>
        )}
        {i.prefiltro_motivo && (
          <section className="rounded-3xl bg-smn-gris-50 p-5">
            <h2 className="text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">Compras lo propone porque</h2>
            <p className="mt-1 text-xl leading-snug">{i.prefiltro_motivo}</p>
            {i.criterios.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {i.criterios.map((c) => (
                  <Insignia key={c.criterio} className={`text-sm ${VALOR[c.valor].clase}`}>{c.criterio}: {VALOR[c.valor].texto.toLowerCase()}{c.nota && ` (${c.nota})`}</Insignia>
                ))}
              </div>
            )}
          </section>
        )}
        {e && <ContraParecidos i={i} />}
      </div>

      <div className="min-w-0 space-y-6">
        <div>
          <h1 className="text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">{i.nombre}</h1>
          <p className="mt-2 text-lg text-smn-gris-700">{[i.marca, i.presentacion, i.departamento].filter(Boolean).join(" · ")}</p>
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

        <Numeros i={i} minimo={e?.ejecutivo?.margen_minimo ?? null} />

        {e ? <Veredicto e={e} abrir={abrir} /> : (
          <section className="rounded-3xl border border-smn-gris-100 p-5">
            <p className="text-lg text-smn-gris-500">Este producto no tiene semáforo.</p>
            <div className="mt-3"><BotonAsistente onClick={() => abrir("ia")} /></div>
          </section>
        )}

        {proyector ? (
          i.decision && (
            <p className="text-lg">
              <Insignia className={`text-base ${DECISION[i.decision].clase}`}>{DECISION[i.decision].texto}</Insignia> {i.decision_motivo}
            </p>
          )
        ) : (
        <section className="rounded-3xl bg-smn-gris-50 p-5">
          <h2 className="mb-3 text-lg font-semibold">Decisión del comité</h2>
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
        )}
      </div>
    </div>
  );
}

/** Precio, costo y margen en grande; el margen dice si pasa o no el mínimo de Compras. */
function Numeros({ i, minimo }: { i: Item; minimo: string | null }) {
  const margen = i.margen != null ? Number(i.margen) : null;
  const bajo = margen != null && minimo != null && margen < Number(minimo);
  const datos = [
    { t: "Precio al público", v: pesos(i.precio), nota: null as React.ReactNode },
    { t: "Costo sin IVA", v: pesos(i.costo), nota: null },
    {
      t: "Margen",
      v: margen != null ? `${margen.toFixed(0)} %` : null,
      nota: minimo != null && margen != null ? <span className={bajo ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400"}>{bajo ? "abajo" : "arriba"} del mínimo de {Number(minimo).toFixed(0)} %</span> : null,
    },
  ].filter((d) => d.v);
  if (datos.length === 0) return null;
  return (
    <dl className="grid grid-cols-3 gap-3">
      {datos.map((d) => (
        <div key={d.t} className={`rounded-2xl px-4 py-3 ${d.t === "Margen" && bajo ? "bg-red-600/10" : "bg-smn-gris-50"}`}>
          <dt className="text-sm text-smn-gris-500">{d.t}</dt>
          <dd className={`text-3xl font-semibold tabular-nums ${d.t === "Margen" && bajo ? "text-red-700 dark:text-red-400" : ""}`}>{d.v}</dd>
          {d.nota && <dd className="mt-0.5 text-sm">{d.nota}</dd>}
        </div>
      ))}
    </dl>
  );
}

const TONO = (p: number | null) => (p == null ? "bg-smn-gris-300" : p > 80 ? "bg-green-600" : p >= 60 ? "bg-yellow-500" : "bg-red-600");

/** El semáforo para un comité: color y calificación, una frase, a favor y en contra, y qué lo subiría. */
function Veredicto({ e, abrir }: { e: NonNullable<Item["evaluacion"]>; abrir: (modo: "fondo" | "ia") => void }) {
  const color = e.color;
  const x = e.ejecutivo;
  const factores = e.factores.filter((f) => !(e.modelo === "sin_proveedor" && f.factor === "proveedor" && f.puntaje == null));
  return (
    <section className="rounded-3xl border border-smn-gris-100 p-5 sm:p-6">
      <div className="flex items-start gap-5">
        <div className={`flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-2xl ${color ? SEMAFORO[color].punto : "bg-smn-gris-300"} text-white`}>
          <span className="text-3xl leading-none font-semibold tabular-nums">{e.puntaje ?? "—"}</span>
          <span className="mt-1 text-[11px] font-medium tracking-wide uppercase opacity-90">de 100</span>
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">
            {color ? SEMAFORO[color].texto : "Sin color"}
            {x?.faltan_puntos != null && <span className="font-normal normal-case"> · {x.faltan_puntos === 1 ? "le falta 1 punto" : `le faltan ${x.faltan_puntos} puntos`} para verde</span>}
          </p>
          <p className="mt-1 text-2xl leading-snug font-semibold">{x?.titular ?? "Semáforo listo."}</p>
          {e.motivo_cambio && <p className="mt-1 text-sm text-smn-gris-700">Compras cambió el color: {e.motivo_cambio}</p>}
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-smn-gris-700">
            {factores.map((f) => (
              <li key={f.factor} className="inline-flex items-center gap-1.5" title={f.valor ?? undefined}>
                <span className={`h-2 w-2 rounded-full ${TONO(f.puntaje)}`} />
                {f.nombre} <b className="tabular-nums text-tinta">{f.puntaje ?? "s/d"}</b>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {x && (x.a_favor.length > 0 || x.en_contra.length > 0) && (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Lista titulo="A favor" puntos={x.a_favor} bien />
          <Lista titulo="En contra" puntos={x.en_contra} bien={false} />
        </div>
      )}

      {x?.para_verde && (
        <p className="mt-4 rounded-2xl bg-smn-gris-50 px-4 py-3 text-[17px] leading-snug">
          <span className="font-semibold">Lo que más lo subiría: </span>
          {x.para_verde}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-smn-gris-100 pt-4">
        <p className="mr-auto text-sm text-smn-gris-500">¿Preguntan el porqué de algo?</p>
        <div className="flex gap-2">
          <Boton variante="secundario" onClick={() => abrir("fondo")}>
            <Layers className="h-4 w-4" /> Ver a fondo
          </Boton>
          <BotonAsistente onClick={() => abrir("ia")} />
        </div>
      </div>
    </section>
  );
}

function Lista({ titulo, puntos, bien }: { titulo: string; puntos: { factor: string; nombre: string; puntaje: number; texto: string }[]; bien: boolean }) {
  const Icono = bien ? Check : Minus;
  return (
    <div>
      <h3 className={`mb-2 text-sm font-semibold tracking-wide uppercase ${bien ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>{titulo}</h3>
      {puntos.length === 0 ? (
        <p className="text-[15px] text-smn-gris-500">{bien ? "Ningún factor destaca a favor." : "Nada en contra."}</p>
      ) : (
        <ul className="space-y-2.5">
          {puntos.map((p) => (
            <li key={p.factor} className="flex gap-2.5">
              <Icono className={`mt-1 h-4 w-4 shrink-0 ${bien ? "text-green-600" : "text-red-600"}`} />
              <span className="text-[17px] leading-snug">
                <b>{p.nombre}</b> <span className="text-smn-gris-500 tabular-nums">({p.puntaje})</span>
                <span className="block text-[15px] text-smn-gris-700">{p.texto}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Resumen({ r, elegidos, abrirProducto }: { r: Reunion; elegidos: Item[]; abrirProducto: (i: Item) => void }) {
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
            <button key={i.id} type="button" onClick={() => abrirProducto(i)} className="mr-2 font-semibold underline underline-offset-2">{i.nombre}</button>
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
      <div className="mt-6 flex flex-wrap gap-2">
        <Link href={`/compras/propuestas/comite/${r.id}`} className="inline-flex min-h-10 items-center rounded-lg bg-[var(--resalte)] px-4 py-2 text-[15px] font-medium text-[var(--resalte-tinta)]">
          Volver al ciclo
        </Link>
        <BotonActa r={r} />
      </div>
    </div>
  );
}

/** El producto nuevo contra los 3 parecidos más cercanos que ya vendemos: precio y cómo se venden de verdad (SMNBI). */
function ContraParecidos({ i }: { i: Item }) {
  const [d, setD] = useState<Parecidos | null>(null);
  useEffect(() => {
    let vivo = true;
    api<Parecidos>(`${RUTA}/productos/${i.id}/parecidos`).then((x) => vivo && setD(x)).catch(() => vivo && setD({ ventana: null, productos: [] }));
    return () => {
      vivo = false;
    };
  }, [i.id]);
  if (!d || d.productos.length === 0) return null;
  const nuevo = i.precio ? Number(i.precio) : null;
  return (
    <section className="rounded-3xl border border-smn-gris-100 p-5">
      <h2 className="text-sm font-semibold tracking-wide text-smn-gris-500 uppercase">Contra lo que ya vendemos</h2>
      <div className="mt-3 flex items-center gap-3 rounded-2xl bg-smn-naranja/10 px-3 py-2.5">
        <Foto i={i} className="h-11 w-11 shrink-0 rounded-xl" />
        <p className="min-w-0 flex-1 truncate font-semibold">Este producto</p>
        <p className="shrink-0 text-right tabular-nums">
          <span className="block text-lg font-semibold">{i.precio ? pesos(i.precio) : "—"}</span>
          <span className="block text-xs text-smn-gris-500">todavía sin venta</span>
        </p>
      </div>
      <ul className="mt-1 divide-y divide-smn-gris-100">
        {d.productos.map((p) => {
          const dif = nuevo && p.precio ? Math.round((nuevo / Number(p.precio) - 1) * 100) : null;
          return (
            <li key={p.producto_id} className="flex items-center gap-3 px-3 py-2.5">
              <Miniatura liga={p.imagen} />
              <div className="min-w-0 flex-1">
                <p className="line-clamp-2 leading-snug font-medium">{p.descripcion || p.sku}</p>
                <p className="mt-0.5 text-[13px] text-smn-gris-500">
                  {p.por_tienda_mes !== null ? (
                    <>
                      <b className="font-semibold text-tinta tabular-nums">{p.por_tienda_mes.toLocaleString("es-MX", { maximumFractionDigits: 1 })}</b> pzas/tienda al mes · {p.tiendas} {p.tiendas === 1 ? "tienda" : "tiendas"}
                      {p.cambio !== null && Math.abs(p.cambio) >= 5 && (
                        <span className={`ml-1 inline-flex items-center ${p.cambio > 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
                          {p.cambio > 0 ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
                          {Math.abs(Math.round(p.cambio))} %
                        </span>
                      )}
                    </>
                  ) : d.ventana ? (
                    "Sin venta en el periodo"
                  ) : (
                    "Sin ventas cargadas"
                  )}
                </p>
              </div>
              <p className="shrink-0 text-right tabular-nums">
                <span className="block font-semibold">{p.precio ? pesos(p.precio) : "—"}</span>
                {dif !== null && dif !== 0 && (
                  <span className={`block text-xs ${dif > 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400"}`}>nuevo {Math.abs(dif)} % {dif > 0 ? "más caro" : "más barato"}</span>
                )}
              </p>
            </li>
          );
        })}
      </ul>
      {d.ventana && <p className="mt-2 text-xs text-smn-gris-500 first-letter:uppercase">{d.ventana}. Flecha: últimas 13 semanas contra las 13 anteriores.</p>}
    </section>
  );
}

function BotonActa({ r }: { r: Reunion }) {
  const avisar = useAvisos();
  const [bajando, setBajando] = useState(false);
  return (
    <Boton
      variante="secundario"
      cargando={bajando}
      onClick={async () => {
        setBajando(true);
        try {
          await descargarActa(r);
        } catch (e) {
          avisar(mensajeDe(e), "info");
        } finally {
          setBajando(false);
        }
      }}
    >
      <FileDown className="h-4 w-4" /> {r.estado === "cerrada" ? "Descargar acta" : "Descargar acta (borrador)"}
    </Boton>
  );
}

const esRojo = (i: Item) => i.evaluacion?.estado === "lista" && i.evaluacion.color === "rojo";

/** De la calificación más alta a la más baja; los que no tienen semáforo al final; los rojos aparte. */
function ordenar(elegidos: Item[]) {
  const puntos = (i: Item) => (i.evaluacion?.estado === "lista" && i.evaluacion.puntaje != null ? i.evaluacion.puntaje : -1);
  const orden = [...elegidos].sort((a, b) => puntos(b) - puntos(a));
  return { ordenados: orden.filter((i) => !esRojo(i)), rojos: orden.filter(esRojo) };
}

/** Los productos en rojo que llegaron al comité, en una sola diapositiva de tarjetas: se abre el que quieran ver y
 * se puede decidir ahí; los que nadie pidió ver se pueden denegar juntos con un mismo motivo. */
function Rojos({ rojos, decidir, listo, abrir }: { rojos: Item[]; decidir: boolean; listo: (r: Reunion) => void; abrir: (i: Item) => void }) {
  const avisar = useAvisos();
  const pendientes = rojos.filter((i) => !i.decision);
  const [juntos, setJuntos] = useState(false);
  const [motivo, setMotivo] = useState("Salió en rojo en el semáforo y el comité no pidió revisarlo a detalle.");
  const [guardando, setGuardando] = useState(false);
  const denegarJuntos = async () => {
    setGuardando(true);
    try {
      let ultima: Reunion | null = null;
      for (const i of pendientes) ultima = await api<Reunion>(`${RUTA}/productos/${i.id}/decision`, { metodo: "PUT", cuerpo: { decision: "denegado", motivo } });
      if (ultima) listo(ultima);
      setJuntos(false);
      avisar(pendientes.length === 1 ? "Producto denegado" : `${pendientes.length} productos denegados`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  return (
    <div>
      <p className="text-sm font-semibold tracking-[0.14em] text-red-700 uppercase dark:text-red-400">Semáforo en rojo</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">
        {rojos.length === 1 ? "1 producto llegó en rojo" : `${rojos.length} productos llegaron en rojo`}
      </h1>
      <p className="mt-2 max-w-3xl text-xl text-smn-gris-700">Compras los pasó al comité aunque salieron en rojo. Abran el que quieran ver a detalle; ahí se decide.</p>

      <div className="mt-8 grid gap-4 @2xl:grid-cols-2 @5xl:grid-cols-3">
        {rojos.map((i) => {
          const e = i.evaluacion!;
          const contra = e.ejecutivo?.en_contra[0];
          return (
            <button key={i.id} type="button" onClick={() => abrir(i)} className="group flex flex-col rounded-3xl border border-smn-gris-100 p-4 text-left transition-colors hover:border-red-600/50 hover:bg-red-600/5">
              <div className="flex gap-4">
                <Foto i={i} className="h-24 w-24 shrink-0 rounded-2xl" />
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-lg leading-snug font-semibold group-hover:underline">{i.nombre}</p>
                  <p className="mt-0.5 truncate text-sm text-smn-gris-500">{i.proveedor ?? "Sin proveedor"}{i.precio && ` · ${pesos(i.precio)}`}</p>
                  <span className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold tabular-nums ${SEMAFORO.rojo.insignia}`}>
                    <span className={`h-2 w-2 rounded-full ${SEMAFORO.rojo.punto}`} /> {e.puntaje ?? "—"} de 100
                  </span>
                </div>
              </div>
              {e.motivo_cambio ? (
                <p className="mt-3 text-[15px] leading-snug">Compras lo puso en rojo: {e.motivo_cambio}</p>
              ) : (
                e.ejecutivo?.titular && <p className="mt-3 text-[15px] leading-snug">{e.ejecutivo.titular}</p>
              )}
              {contra && <p className="mt-1 text-sm text-smn-gris-500">{contra.nombre} ({contra.puntaje}): {contra.texto}</p>}
              <div className="mt-auto pt-3">
                {i.decision ? (
                  <Insignia className={DECISION[i.decision].clase}>{DECISION[i.decision].texto}</Insignia>
                ) : (
                  <span className="text-sm font-semibold text-smn-gris-700">Ver a detalle y decidir →</span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {decidir && pendientes.length > 0 && (
        <div className="mt-8 rounded-3xl bg-smn-gris-50 p-5">
          {!juntos ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-[15px] text-smn-gris-700">
                {pendientes.length === 1 ? "Falta decidir 1." : `Faltan ${pendientes.length} por decidir.`} Si el comité no quiere ver ninguno a detalle, se pueden denegar juntos.
              </p>
              <Boton variante="secundario" onClick={() => setJuntos(true)}>Denegar los {pendientes.length} que faltan</Boton>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="font-semibold">Denegar {pendientes.map((i) => i.nombre).join(", ")}</p>
              <textarea
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                rows={2}
                maxLength={1000}
                aria-label="Motivo"
                className="w-full rounded-xl border border-smn-gris-100 bg-superficie px-3 py-2 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
              />
              <div className="flex justify-end gap-2">
                <Boton variante="fantasma" onClick={() => setJuntos(false)}>Cancelar</Boton>
                <Boton onClick={denegarJuntos} cargando={guardando} disabled={!motivo.trim()}>Denegar</Boton>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Modo proyector: la decisión y las peticiones se registran en esta barra, abajo, y la diapositiva queda limpia. */
function BarraDecision({ i, r, decidir, anotar, listo }: { i: Item; r: Reunion; decidir: boolean; anotar: boolean; listo: (r: Reunion) => void }) {
  const [abierta, setAbierta] = useState(false);
  const peticiones = r.peticiones.filter((p) => p.item_id === i.id);
  return (
    <div className="border-t border-smn-gris-100 bg-smn-gris-50">
      <div className="flex flex-wrap items-center gap-3 px-4 py-2 sm:px-6">
        <p className="min-w-0 flex-1 truncate text-sm">
          <span className="text-smn-gris-500">Decisión: </span>
          {i.decision ? <Insignia className={DECISION[i.decision].clase}>{DECISION[i.decision].texto}</Insignia> : <span className="font-semibold">sin decisión</span>}
          {peticiones.length > 0 && <span className="text-smn-gris-500"> · {peticiones.length === 1 ? "1 petición" : `${peticiones.length} peticiones`}</span>}
        </p>
        {(decidir || anotar) && (
          <Boton variante="secundario" className="min-h-9 py-1.5" onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}>
            {abierta ? "Ocultar" : i.decision ? "Cambiar decisión o anotar" : "Registrar decisión"}
          </Boton>
        )}
      </div>
      {abierta && (
        <div className="max-h-[45vh] overflow-y-auto border-t border-smn-gris-100 px-4 py-3 sm:px-6">
          <div className="mx-auto grid max-w-6xl gap-5 @container lg:grid-cols-2">
            {decidir && <FormDecision i={i} listo={listo} />}
            {anotar && (
              <div>
                <h3 className="mb-2 text-sm font-semibold">Peticiones sobre este producto</h3>
                {peticiones.length > 0 && <ListaPeticiones peticiones={peticiones} />}
                <div className="mt-2">
                  <NuevaPeticion reunion={r} item={i} listo={listo} compacta />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
