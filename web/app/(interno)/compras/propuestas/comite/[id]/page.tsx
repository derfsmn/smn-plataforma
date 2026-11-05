"use client";
// El ciclo de una reunión del comité: cuatro columnas que se llenan conforme avanza (subidos → evaluados → pre-filtro →
// comité), los asistentes, las peticiones, «Qué aprendimos» y el semáforo contra las decisiones.

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowLeft, ArrowRight, Check, Filter, Lightbulb, Loader2, PackagePlus, PenLine, Presentation, RefreshCw, Search, Trash2,
  UserPlus, Users, X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { CapturarIdea } from "@/componentes/capturar-idea";
import { Modal } from "@/componentes/modal";
import { InsigniaColor, Semaforo } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import {
  columna, DECISION, fechaReunion, MODELO, PASOS, RESULTADO_REVISION, RUTA, VALOR, type EstadoReunion, type Item, type Peticion,
  type Reunion, type Revision,
} from "@/lib/comite";
import { Capturar } from "../../capturar";
import { AgregarAsistente, AgregarExistente, Atender, FormDecision, Foto, ListaPeticiones, NuevaPeticion, Prefiltrar } from "../piezas";

const COLUMNAS = [
  { titulo: "Subidos", vacio: "Sube los productos de este ciclo." },
  { titulo: "Evaluados", vacio: "Aquí aparecen con su semáforo." },
  { titulo: "Pre-filtro", vacio: "Lo que Compras pre-filtra." },
  { titulo: "Comité", vacio: "Lo que pasó el pre-filtro, con su decisión." },
];

const SIGUIENTE: Partial<Record<EstadoReunion, { estado: EstadoReunion; texto: string; pregunta: string }>> = {
  abierta: { estado: "prefiltro", texto: "Empezar pre-filtro", pregunta: "Al empezar el pre-filtro ya no se pueden subir productos a esta reunión." },
  prefiltro: { estado: "comite", texto: "Pasar al comité", pregunta: "Al comité llega solo lo que pasó el pre-filtro. Después de la primera decisión ya no se regresa al pre-filtro." },
  comite: { estado: "cerrada", texto: "Cerrar reunión", pregunta: "El ciclo queda de solo lectura. Los aceptados quedan listos para el proceso de alta y lo que quedó «En espera» entra a la siguiente reunión." },
};
const ANTERIOR: Partial<Record<EstadoReunion, { estado: EstadoReunion; texto: string }>> = {
  prefiltro: { estado: "abierta", texto: "Regresar a subir productos" },
  comite: { estado: "prefiltro", texto: "Regresar al pre-filtro" },
};

export default function CicloReunion() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [r, setR] = useState<Reunion | null>(null);
  const [modal, setModal] = useState<null | "subir" | "proveedor" | "idea" | "existente" | "asistentes">(null);
  const [prefiltrando, setPrefiltrando] = useState<Item | null>(null);
  const [decidiendo, setDecidiendo] = useState<Item | null>(null);
  const [atendiendo, setAtendiendo] = useState<Peticion | null>(null);
  const [paso, setPaso] = useState<{ estado: EstadoReunion; texto: string; pregunta?: string } | null>(null);
  const [moviendo, setMoviendo] = useState(false);

  const cargar = useCallback(() => {
    api<Reunion>(`${RUTA}/reuniones/${id}`).then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);
  useEffect(cargar, [cargar]);

  // Mientras alguna evaluación corre, se refresca para que el semáforo aparezca solo
  const evaluando = r?.productos.some((i) => i.evaluacion?.estado === "en_curso");
  useEffect(() => {
    if (!evaluando) return;
    const t = setTimeout(cargar, 3000);
    return () => clearTimeout(t);
  }, [evaluando, r, cargar]);

  if (!r)
    return (
      <div className="space-y-3">
        <Esqueleto className="h-24" />
        <Esqueleto className="h-64" />
      </div>
    );

  const subir = async (cuerpo: object) => setR(await api<Reunion>(`${RUTA}/reuniones/${r.id}/productos`, { cuerpo }));
  const organizar = puede("compras.comite.prefiltrar");
  const decidir = puede("compras.comite.decidir");
  const anotar = (organizar || decidir) && (r.estado === "prefiltro" || r.estado === "comite");
  const idx = PASOS.findIndex((p) => p.estado === r.estado);

  const mover = async () => {
    if (!paso) return;
    setMoviendo(true);
    try {
      setR(await api<Reunion>(`${RUTA}/reuniones/${r.id}/estado`, { cuerpo: { estado: paso.estado } }));
      setPaso(null);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setMoviendo(false);
    }
  };

  const quitar = async (i: Item) => {
    try {
      setR(await api<Reunion>(`${RUTA}/productos/${i.id}`, { metodo: "DELETE" }));
      avisar(`Quitaste «${i.nombre}» del ciclo; sigue en Propuestas o en el radar`);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    }
  };
  const reevaluar = async (i: Item) => {
    try {
      setR(await api<Reunion>(`${RUTA}/productos/${i.id}/evaluar`, { metodo: "POST" }));
    } catch (err) {
      avisar(mensajeDe(err), "info");
    }
  };

  const columnas: Item[][] = [[], [], [], []];
  r.productos.forEach((i) => columnas[columna(i, r.estado)].push(i));
  const decididos = r.productos.filter((i) => i.prefiltro);

  return (
    <>
      <Entrada className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[15px] text-smn-gris-500">Comité de producto nuevo</p>
            <h1 className="mt-1 text-3xl leading-tight font-semibold tracking-tight first-letter:uppercase sm:text-[34px]">{fechaReunion(r.fecha)}</h1>
            {r.notas && <p className="mt-2 max-w-2xl text-smn-gris-700">{r.notas}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            {r.estado === "abierta" && puede("compras.comite.subir") && (
              <Boton onClick={() => setModal("subir")}>
                <PackagePlus className="h-4 w-4" /> Subir producto
              </Boton>
            )}
            {(r.estado === "comite" || r.estado === "cerrada") && (
              <Link href={`/compras/propuestas/comite/${r.id}/presentar`} className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--resalte)] px-4 py-2 text-[15px] font-medium text-[var(--resalte-tinta)] hover:brightness-105">
                <Presentation className="h-4 w-4" /> {r.estado === "comite" ? "Presentar" : "Ver presentación"}
              </Link>
            )}
            {organizar && SIGUIENTE[r.estado] && (
              <Boton variante={r.estado === "abierta" ? "secundario" : r.estado === "comite" ? "secundario" : "primario"} onClick={() => setPaso(SIGUIENTE[r.estado]!)}>
                {SIGUIENTE[r.estado]!.texto} <ArrowRight className="h-4 w-4" />
              </Boton>
            )}
          </div>
        </div>

        {organizar && ANTERIOR[r.estado] && (
          <button type="button" onClick={() => setPaso(ANTERIOR[r.estado]!)} className="mt-3 inline-flex items-center gap-1 text-[13px] text-smn-gris-500 hover:text-tinta">
            <ArrowLeft className="h-3.5 w-3.5" /> {ANTERIOR[r.estado]!.texto}
          </button>
        )}
      </Entrada>

      <ol className="mb-8 grid grid-cols-2 overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie sm:grid-cols-4" aria-label="Pasos de la reunión">
        {PASOS.map((p, k) => {
          const hecho = k < idx || r.estado === "cerrada";
          const ahora = k === idx && r.estado !== "cerrada";
          const e = r.embudo;
          const detalle = [
            `${e.subidos} ${e.subidos === 1 ? "producto" : "productos"}${e.evaluados ? ` · ${e.evaluados} con semáforo` : ""}`,
            `${e.pasan} ${e.pasan === 1 ? "pasa" : "pasan"} · ${e.no_pasan} no`,
            `${e.aceptados} ${e.aceptados === 1 ? "aceptado" : "aceptados"} · ${e.denegados} ${e.denegados === 1 ? "denegado" : "denegados"} · ${e.en_espera} en espera`,
            r.cerrada_en ? `El ${new Date(r.cerrada_en).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}` : "Solo lectura",
          ][k];
          return (
            <li
              key={p.estado}
              aria-current={ahora ? "step" : undefined}
              className={`relative border-smn-gris-100 px-4 py-3.5 max-sm:[&:nth-child(-n+2)]:border-b sm:[&:not(:last-child)]:border-r max-sm:odd:border-r ${ahora ? "bg-smn-naranja/8" : ""}`}
            >
              {ahora && <span className="absolute inset-x-0 top-0 h-1 bg-smn-naranja" aria-hidden />}
              <div className="flex items-center gap-2">
                <span
                  className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[13px] font-semibold ${
                    hecho ? "bg-tinta text-superficie" : ahora ? "bg-smn-naranja text-smn-negro" : "border border-smn-gris-300 text-smn-gris-500"
                  }`}
                >
                  {hecho ? <Check className="h-3.5 w-3.5" /> : k + 1}
                </span>
                <span className={`text-[15px] ${ahora ? "font-semibold" : hecho ? "font-medium" : "text-smn-gris-500"}`}>{p.texto}</span>
              </div>
              <p className={`mt-1.5 pl-8 text-[13px] ${hecho || ahora ? "text-smn-gris-700" : "text-smn-gris-500"}`}>
                {hecho || ahora ? detalle : "Pendiente"}
              </p>
            </li>
          );
        })}
      </ol>

      {r.productos.length === 0 ? (
        <section className="flex flex-col items-center rounded-2xl border border-dashed border-smn-gris-300 px-6 py-12 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-full bg-smn-naranja/12 text-smn-naranja">
            <PackagePlus className="h-6 w-6" />
          </span>
          <h2 className="mt-4 text-lg font-semibold">Todavía no hay productos en este ciclo</h2>
          <p className="mt-1.5 max-w-lg text-[15px] text-smn-gris-700">
            {r.estado === "abierta"
              ? "Captura uno, súbelo como idea o agrega una propuesta que ya exista. Lo que manden los proveedores por el portal entra solo, y cada producto se evalúa con el semáforo."
              : "Este ciclo se quedó sin productos."}
          </p>
          {r.estado === "abierta" && puede("compras.comite.subir") && (
            <Boton className="mt-5" onClick={() => setModal("subir")}>
              <PackagePlus className="h-4 w-4" /> Subir producto
            </Boton>
          )}
        </section>
      ) : (
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
        {COLUMNAS.map((c, k) => (
          <section key={c.titulo} aria-label={c.titulo} className={`flex flex-col rounded-2xl p-2 ${k === 3 ? "bg-smn-naranja/6" : "bg-smn-gris-50"}`}>
            <h2 className="flex items-center justify-between px-2 pt-1 pb-2.5 text-[15px] font-semibold">
              {c.titulo}
              <span className="min-w-6 rounded-full bg-superficie px-2 py-0.5 text-center text-[13px] font-medium text-smn-gris-700 tabular-nums">{columnas[k].length}</span>
            </h2>
            {columnas[k].length === 0 ? (
              <p className="m-0.5 rounded-xl border border-dashed border-smn-gris-300 px-3 py-6 text-center text-[13px] text-smn-gris-500">{c.vacio}</p>
            ) : (
              <ul className="space-y-2">
                <AnimatePresence initial={false}>
                  {columnas[k].map((i) => (
                    <motion.li key={i.id} id={`producto-${i.id}`} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                      <Tarjeta
                        i={i}
                        r={r}
                        quitar={r.estado === "abierta" && puede("compras.comite.subir") ? () => quitar(i) : undefined}
                        reevaluar={(r.estado === "abierta" || r.estado === "prefiltro") && puede("compras.comite.subir") ? () => reevaluar(i) : undefined}
                        prefiltrar={r.estado === "prefiltro" && organizar ? () => setPrefiltrando(i) : undefined}
                        decidir={r.estado === "comite" && decidir && i.prefiltro === "pasa" ? () => setDecidiendo(i) : undefined}
                        verSemaforo={puede("compras.productos.ver")}
                        revisar={organizar}
                        cambio={setR}
                      />
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            )}
          </section>
        ))}
      </div>
      )}

      <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="mb-3 flex items-center justify-between gap-2 font-semibold">
            <span className="flex items-center gap-2"><Users className="h-4 w-4 text-smn-naranja" /> Asistentes</span>
            {(organizar || decidir) && r.estado !== "cerrada" && (
              <Boton variante="secundario" onClick={() => setModal("asistentes")}>
                <UserPlus className="h-4 w-4" /> Agregar
              </Boton>
            )}
          </h2>
          {r.asistentes.length === 0 ? (
            <p className="text-[15px] text-smn-gris-500">Quién asiste y su puesto. También se registran al empezar la presentación.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {r.asistentes.map((a) => (
                <li key={a.id} className="flex items-center gap-1 rounded-full bg-smn-gris-100 py-1 pr-1.5 pl-3 text-sm">
                  {a.nombre}
                  {a.puesto && <span className="text-smn-gris-500">· {a.puesto}</span>}
                  {(organizar || decidir) && r.estado !== "cerrada" && (
                    <button
                      type="button"
                      aria-label={`Quitar a ${a.nombre}`}
                      onClick={() => api<Reunion>(`${RUTA}/asistentes/${a.id}`, { metodo: "DELETE" }).then(setR).catch((e) => avisar(mensajeDe(e), "info"))}
                      className="rounded-full p-0.5 text-smn-gris-500 hover:bg-smn-gris-300/40"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="mb-3 flex min-h-10 items-center font-semibold">Peticiones</h2>
          {r.peticiones.length === 0 && r.estado === "abierta" ? (
            <p className="text-[15px] text-smn-gris-500">Lo que pida cada asistente se anota durante el pre-filtro y el comité, y se le da seguimiento.</p>
          ) : (
          <ListaPeticiones peticiones={r.peticiones} atender={organizar || decidir ? setAtendiendo : undefined} />
          )}
          {anotar && (
            <div className="mt-3">
              <NuevaPeticion reunion={r} listo={setR} />
            </div>
          )}
        </section>
      </div>

      {decididos.length > 0 && (
        <section className="mt-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="mb-1 font-semibold">Semáforo contra decisiones</h2>
          <p className="mb-3 text-sm text-smn-gris-500">Para aprender del proceso: en qué coincidieron el semáforo, el pre-filtro y el comité.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="text-left text-smn-gris-500">
                  <th className="py-1.5 pr-3 font-medium">Producto</th>
                  <th className="py-1.5 pr-3 font-medium">Semáforo</th>
                  <th className="py-1.5 pr-3 font-medium">Pre-filtro</th>
                  <th className="py-1.5 pr-3 font-medium">Comité</th>
                  <th className="py-1.5 font-medium">¿Coinciden?</th>
                </tr>
              </thead>
              <tbody>
                {decididos.map((i) => {
                  const color = i.decision_color ?? i.prefiltro_color;
                  const final = i.decision ?? (i.prefiltro === "no_pasa" ? "no_pasa" : null);
                  const coincide =
                    !color || color === "amarillo" || !final || final === "en_espera"
                      ? null
                      : (color === "verde") === (final === "aceptado");
                  return (
                    <tr key={i.id} className="border-t border-smn-gris-100">
                      <td className="py-2 pr-3">{i.nombre}</td>
                      <td className="py-2 pr-3"><InsigniaColor color={color} /></td>
                      <td className="py-2 pr-3">{i.prefiltro === "pasa" ? "Pasa" : "No pasa"}</td>
                      <td className="py-2 pr-3">{i.decision ? DECISION[i.decision].texto : "—"}</td>
                      <td className="py-2 text-smn-gris-700">{coincide === null ? "—" : coincide ? "Sí" : "No"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Aprendizajes r={r} editable={organizar} listo={setR} />

      <AnimatePresence>
        {modal === "subir" && (
          <Modal titulo="Subir producto" cerrar={() => setModal(null)} ancho="max-w-lg">
            <div className="grid gap-2">
              {[
                { m: "idea" as const, icono: Lightbulb, t: "Captura rápida", d: "Nombre, fotos y lo que sepas, con o sin proveedor. Sirve para cargar varios seguidos; cada uno entra a esta reunión." },
                { m: "proveedor" as const, icono: PenLine, t: "Cuestionario completo", d: "El mismo cuestionario del portal, con un proveedor de Intelisis o uno nuevo." },
                { m: "existente" as const, icono: Search, t: "Agregar uno que ya existe", d: "Una propuesta del portal, una captura, una idea o una oportunidad." },
              ].map(({ m, icono: Icono, t, d }) => (
                <button key={m} type="button" onClick={() => setModal(m)} className="flex gap-3 rounded-xl border border-smn-gris-100 p-3 text-left hover:border-smn-naranja">
                  <Icono className="mt-0.5 h-5 w-5 shrink-0 text-smn-naranja" />
                  <span>
                    <span className="block text-[15px] font-semibold">{t}</span>
                    <span className="block text-[13px] text-smn-gris-700">{d}</span>
                  </span>
                </button>
              ))}
            </div>
          </Modal>
        )}
        {modal === "proveedor" && (
          <Capturar
            cerrar={() => setModal(null)}
            alCrear={(p) => subir({ propuesta_id: p.id })}
            destino={(p) => `/compras/propuestas/captura/${p.id}?comite=${r.id}`}
          />
        )}
        {modal === "idea" && (
          <CapturarIdea
            cerrar={() => setModal(null)}
            alGuardar={(e) => subir({ idea_id: e.sujeto.id })}
          />
        )}
        {modal === "existente" && <AgregarExistente reunion={r.id} cerrar={() => setModal(null)} listo={setR} />}
        {modal === "asistentes" && <AgregarAsistente reunion={r} cerrar={() => setModal(null)} listo={setR} />}
        {prefiltrando && (
          <Prefiltrar i={prefiltrando} cerrar={() => setPrefiltrando(null)} listo={(x) => { setR(x); setPrefiltrando(null); }} />
        )}
        {decidiendo && (
          <Modal titulo={decidiendo.nombre} cerrar={() => setDecidiendo(null)} ancho="max-w-lg">
            <FormDecision i={decidiendo} listo={(x) => { setR(x); setDecidiendo(null); }} />
          </Modal>
        )}
        {atendiendo && <Atender p={atendiendo} cerrar={() => setAtendiendo(null)} listo={() => { setAtendiendo(null); cargar(); }} />}
        {paso && (
          <Modal titulo={`${paso.texto}?`} cerrar={() => setPaso(null)}>
            {paso.pregunta && <p className="mb-5 text-smn-gris-700">{paso.pregunta}</p>}
            <div className="flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => setPaso(null)}>Cancelar</Boton>
              <Boton onClick={mover} cargando={moviendo}>{paso.texto}</Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </>
  );
}

function Tarjeta({ i, r, quitar, reevaluar, prefiltrar, decidir, verSemaforo, revisar, cambio }: {
  i: Item;
  r: Reunion;
  quitar?: () => void;
  reevaluar?: () => void;
  prefiltrar?: () => void;
  decidir?: () => void;
  verSemaforo: boolean;
  revisar: boolean;
  cambio: (r: Reunion) => void;
}) {
  const e = i.evaluacion;
  const proveedor = i.proveedor ? `${i.proveedor_actual ? "Proveedor actual" : "Proveedor nuevo"}: ${i.proveedor}` : "Sin proveedor";
  return (
    <article className="rounded-xl border border-smn-gris-100 bg-superficie p-3 shadow-sm">
      <div className="flex gap-3">
        <Foto i={i} className="h-14 w-14 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-[15px] leading-snug font-semibold">{i.nombre}</p>
          <p className="truncate text-[13px] text-smn-gris-500" title={proveedor}>{proveedor}</p>
          {i.llego_solo && (
            <p className="text-[13px] text-smn-gris-700">Llegó del portal el {new Date(i.agregado_en).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}</p>
          )}
          {i.origen === "espera" && i.viene_de_fecha && (
            <p className="text-[13px] text-smn-gris-700">En espera desde el {fechaReunion(i.viene_de_fecha, { day: "numeric", month: "short" })}</p>
          )}
        </div>
      </div>

      <div className="mt-2.5 text-[13px]">
        {e?.estado === "lista" ? (
          <div className="flex flex-wrap items-center gap-2">
            <Semaforo color={e.color} tam="sm" horizontal />
            <span className="font-semibold">{e.puntaje ?? "—"}</span>
            <span className="text-smn-gris-500" title={e.modelo ? MODELO[e.modelo] : undefined}>
              {e.modelo === "con_proveedor" ? "con proveedor" : "sin proveedor"}
            </span>
          </div>
        ) : e?.estado === "en_curso" ? (
          <p className="flex items-center gap-1.5 text-smn-gris-700">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-smn-naranja" /> {e.avance ?? "Evaluando…"}
          </p>
        ) : e?.estado === "fallida" ? (
          <p className="text-red-700 dark:text-red-400">{e.error ?? "No se pudo evaluar."}</p>
        ) : i.falta ? (
          <p className="text-aviso-texto">
            {i.falta}{" "}
            {i.origen === "captura" && i.estado_sujeto === "Borrador" && (
              <Link href={`/compras/propuestas/captura/${i.sujeto_id}?comite=${r.id}`} className="font-semibold underline underline-offset-2">Terminar captura</Link>
            )}
          </p>
        ) : i.llego_solo && i.tipo === "propuesta" ? (
          <p className="text-aviso-texto">
            Revisa la propuesta y pulsa «Evaluar».{" "}
            <Link href={`/compras/propuestas/${i.sujeto_id}`} className="font-semibold underline underline-offset-2">Ver propuesta</Link>
          </p>
        ) : (
          <p className="text-smn-gris-500">Sin semáforo todavía.</p>
        )}
      </div>

      {i.prefiltro && (
        <div className="mt-2 border-t border-smn-gris-100 pt-2 text-[13px]">
          <p>
            <span className="font-semibold">{i.prefiltro === "pasa" ? "Pasa al comité" : "No pasa"}:</span> {i.prefiltro_motivo}
          </p>
          {i.criterios.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {i.criterios.map((c) => (
                <Insignia key={c.criterio} className={VALOR[c.valor].clase}>{c.criterio}: {VALOR[c.valor].texto.toLowerCase()}</Insignia>
              ))}
            </div>
          )}
        </div>
      )}

      {i.decision && (
        <div className="mt-2 border-t border-smn-gris-100 pt-2 text-[13px]">
          <Insignia className={DECISION[i.decision].clase}>{DECISION[i.decision].texto}</Insignia> <span>{i.decision_motivo}</span>
          {i.decision_por && <p className="mt-0.5 text-smn-gris-500">{i.decision_por}, {i.decision_en && fechaLocal(i.decision_en, { dateStyle: "medium" })}</p>}
        </div>
      )}

      {i.decision === "aceptado" && <Revisiones i={i} editable={revisar} cambio={cambio} />}

      {(prefiltrar || decidir || quitar || (verSemaforo && e?.estado === "lista") || (reevaluar && (e?.estado === "fallida" || (!e && !i.falta)))) && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {verSemaforo && e?.estado === "lista" && (
            <Link href={`/compras/productos/${e.id}`} className="mr-auto px-1 text-[13px] font-semibold text-smn-gris-700 underline-offset-2 hover:underline">
              Ver semáforo
            </Link>
          )}
          {prefiltrar && (
            <Boton variante={i.prefiltro ? "fantasma" : "secundario"} className="min-h-8 px-2.5 py-1 text-sm" onClick={prefiltrar}>
              <Filter className="h-3.5 w-3.5" /> {i.prefiltro ? "Cambiar" : "Pre-filtrar"}
            </Boton>
          )}
          {decidir && (
            <Boton variante={i.decision ? "fantasma" : "secundario"} className="min-h-8 px-2.5 py-1 text-sm" onClick={decidir}>
              <Check className="h-3.5 w-3.5" /> {i.decision ? "Cambiar decisión" : "Decidir"}
            </Boton>
          )}
          {reevaluar && (e?.estado === "fallida" || (!e && !i.falta)) && (
            <Boton variante="fantasma" className="min-h-8 px-2.5 py-1 text-sm" onClick={reevaluar}>
              <RefreshCw className="h-3.5 w-3.5" /> Evaluar
            </Boton>
          )}
          {quitar && (
            <Boton variante="fantasma" className="min-h-8 px-2 py-1 text-sm" onClick={quitar} aria-label={`Quitar ${i.nombre} del ciclo`}>
              <Trash2 className="h-3.5 w-3.5" />
            </Boton>
          )}
        </div>
      )}
    </article>
  );
}

const TIPOS_REVISION: { tipo: Revision["tipo"]; nombre: string }[] = [
  { tipo: "inventario", nombre: "Espacio en inventario" },
  { tipo: "regulacion", nombre: "Regulación" },
];

/** Después de aceptar, si aplica: espacio en inventario y después regulación. */
function Revisiones({ i, editable, cambio }: { i: Item; editable: boolean; cambio: (r: Reunion) => void }) {
  const avisar = useAvisos();
  const poner = async (tipo: Revision["tipo"], resultado: Revision["resultado"]) => {
    try {
      cambio(await api<Reunion>(`${RUTA}/productos/${i.id}/revisiones/${tipo}`, { metodo: "PUT", cuerpo: { resultado } }));
    } catch (err) {
      avisar(mensajeDe(err), "info");
    }
  };
  if (!editable && i.revisiones.length === 0) return null;
  return (
    <div className="mt-2 space-y-1 border-t border-smn-gris-100 pt-2 text-[13px]">
      <p className="font-semibold">Revisión, si aplica</p>
      {TIPOS_REVISION.map(({ tipo, nombre }) => {
        const rev = i.revisiones.find((x) => x.tipo === tipo);
        return (
          <div key={tipo} className="flex items-center justify-between gap-2">
            <span className="text-smn-gris-700">{nombre}</span>
            {editable ? (
              <select
                value={rev?.resultado ?? ""}
                onChange={(e) => e.target.value && poner(tipo, e.target.value as Revision["resultado"])}
                aria-label={nombre}
                className="h-8 rounded-lg border border-smn-gris-100 bg-superficie px-1.5 text-[13px] outline-none focus:border-smn-naranja"
              >
                <option value="">No aplica</option>
                <option value="pendiente">Pendiente</option>
                <option value="aprobada">Aprobada</option>
                <option value="rechazada">Rechazada</option>
              </select>
            ) : rev ? (
              <Insignia className={RESULTADO_REVISION[rev.resultado].clase}>{RESULTADO_REVISION[rev.resultado].texto}</Insignia>
            ) : (
              <span className="text-smn-gris-500">No aplica</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Aprendizajes({ r, editable, listo }: { r: Reunion; editable: boolean; listo: (r: Reunion) => void }) {
  const avisar = useAvisos();
  const [texto, setTexto] = useState(r.aprendizajes ?? "");
  const [guardando, setGuardando] = useState(false);
  useEffect(() => setTexto(r.aprendizajes ?? ""), [r.aprendizajes]);
  if (!r.aprendizajes && (!editable || r.estado === "abierta" || r.estado === "prefiltro")) return null; // se escribe en el comité o al cerrar
  const guardar = async () => {
    setGuardando(true);
    try {
      listo(await api<Reunion>(`${RUTA}/reuniones/${r.id}`, { metodo: "PATCH", cuerpo: { aprendizajes: texto } }));
      avisar("Guardado");
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setGuardando(false);
    }
  };
  return (
    <section className="mt-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-1 font-semibold">Qué aprendimos</h2>
      <p className="mb-3 text-sm text-smn-gris-500">Qué cambiar en el siguiente ciclo. Se puede escribir también después de cerrar.</p>
      {editable ? (
        <>
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={4}
            maxLength={20000}
            aria-label="Qué aprendimos"
            className="w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 py-2.5 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
          />
          <div className="mt-2 flex justify-end">
            <Boton variante="secundario" onClick={guardar} cargando={guardando} disabled={texto === (r.aprendizajes ?? "")}>Guardar</Boton>
          </div>
        </>
      ) : (
        <p className="whitespace-pre-line text-[15px]">{r.aprendizajes}</p>
      )}
    </section>
  );
}
