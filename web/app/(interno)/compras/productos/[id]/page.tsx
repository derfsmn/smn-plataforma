"use client";
// Detalle de una evaluación del radar de productos: la pantalla por niveles (como en el comité), las acciones y «Más del producto».

import { Imagen } from "@/componentes/imagen";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Bot, Check, ChevronDown, CircleHelp, Gavel, History, MoreHorizontal, PackageSearch, Palette, Plus, RefreshCw, Search, Tag, Trash2, TrendingUp, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { BotonReporte } from "@/componentes/boton-reporte";
import { PantallaComite } from "@/componentes/pantalla-comite";
import { FichaTecnicaTarjeta } from "@/componentes/ficha-tecnica";
import { Modal } from "@/componentes/modal";
import { InsigniaColor, Semaforo } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { TipoProducto } from "@/componentes/tipo-producto";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { SEMAFORO } from "@/lib/precios";
import { RUTA as RUTA_BUSQUEDAS, type BusquedaBreve } from "@/lib/busquedas";
import { Asistente, type Turno } from "../../propuestas/comite/[id]/presentar/asistente";
import {
  colorVigente, ESTADOS_IDEA, RUTA, urlFoto,
  type Color, type Comparable, type EstadoIdea, type Evaluacion, type OpcionClasificacion, type RevisionPoliticas, type ProductoCatalogo,
} from "@/lib/productos";

// Preguntas para el asistente de cada producto (Diego, 2026-11-09: «preguntarle sobre la decisión de cada producto»)
const SUGERENCIAS_RADAR = [
  { texto: "¿Por qué salió de este color?", icono: CircleHelp },
  { texto: "¿Qué lo haría subir de calificación?", icono: TrendingUp },
  { texto: "¿Cómo está su precio contra internet?", icono: Tag },
  { texto: "¿Qué decidió el comité y por qué?", icono: Gavel },
];

const ORIGEN_CLASIFICACION = { ia: "Sugerida por la IA, sin confirmar", compras: "Confirmada por Compras", parecidos: "Tomada de los productos parecidos, sin confirmar", variante: "La misma que el producto en otro sabor, sin confirmar", sin_clasificar: "Sin clasificar" } as const;

export default function DetalleEvaluacion() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const evalua = puede("compras.productos.evaluar");
  const ajusta = puede("compras.productos.ajustar");
  const [e, setE] = useState<Evaluacion | null>(null);
  const [ia, setIa] = useState(false);
  const [turnos, setTurnos] = useState<Turno[]>([]);
  useEffect(() => {
    setTurnos([]);
    setIa(false);
  }, [id]);
  useEffect(() => {
    if (!ia) return;
    const tecla = (x: KeyboardEvent) => x.key === "Escape" && setIa(false);
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [ia]);
  const [abierto, setAbierto] = useState<"color" | "clasificacion" | "parecidos" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [masAbierto, setMasAbierto] = useState(false);
  const [acciones, setAcciones] = useState(false);

  const cargar = useCallback(() => api<Evaluacion>(`${RUTA}/evaluaciones/${id}`).then(setE).catch((x) => avisar(mensajeDe(x), "info")), [id, avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);
  // La búsqueda de proveedor de la idea, si la tiene (se abre sola si sale verde sin proveedor, o con «Buscar proveedor»)
  const [busqueda, setBusqueda] = useState<BusquedaBreve | null>(null);
  const idea = e?.sujeto.tipo === "idea" ? e.sujeto.id : null;
  const verBusquedas = puede("compras.busquedas.ver");
  const cargarBusqueda = useCallback(() => {
    if (!idea || !verBusquedas) return setBusqueda(null);
    api<BusquedaBreve | null>(`${RUTA_BUSQUEDAS}/idea/${idea}`).then(setBusqueda).catch(() => setBusqueda(null));
  }, [idea, verBusquedas]);
  useEffect(() => {
    cargarBusqueda();
  }, [cargarBusqueda, e?.estado, e?.color_final]);
  useEffect(() => {
    if (e?.estado !== "en_curso") return;
    const t = setTimeout(cargar, 2500);
    return () => clearTimeout(t);
  }, [e, cargar]);

  if (!e) return <Esqueleto className="h-96" />;

  /** Las correcciones crean una evaluación nueva: se cambia la dirección a ella. */
  const nueva = async (ruta: string, cuerpo: unknown, metodo = "PUT", texto = "Recalculando con tu corrección") => {
    setOcupado(true);
    try {
      const r = await api<Evaluacion>(`${RUTA}/evaluaciones/${e.id}/${ruta}`, { metodo, cuerpo });
      setAbierto(null);
      avisar(texto);
      router.replace(`/compras/productos/${r.id}`);
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setOcupado(false);
    }
  };

  const estadoIdea = async (estado: EstadoIdea) => {
    try {
      await api(`${RUTA}/ideas/${e.sujeto.id}/estado`, { metodo: "PATCH", cuerpo: { estado } });
      setE({ ...e, sujeto: { ...e.sujeto, estado } });
      avisar(estado === "buscar_proveedor" ? "Se abrió la búsqueda de proveedor y se avisó a quienes buscan proveedores" : `Quedó como «${ESTADOS_IDEA[estado]}»`);
      cargarBusqueda();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };

  const color = colorVigente(e);
  const lista = e.estado === "lista";
  const vigente = e.historial[0]?.id;
  const yaVendemos = e.comparables.find((c) => Number(c.similitud) >= 1);

  const recalcularBoton = (texto = "Recalcular", variante: "primario" | "secundario" = "secundario") =>
    evalua && e.vigente ? (
      <Boton variante={variante} cargando={ocupado && !abierto} onClick={() => nueva("recalcular", undefined, "POST", "Recalculando")}>
        <RefreshCw className="h-4 w-4" /> {texto}
      </Boton>
    ) : null;
  const foto = e.sujeto.tipo === "idea" && e.fotos[0] ? (
    // eslint-disable-next-line @next/next/no-img-element -- foto servida por la API con sesión
    <Imagen src={urlFoto(e.sujeto.id, e.fotos[0].archivo_id, 900)} alt="" className="h-full w-full object-contain" />
  ) : undefined;

  return (
    <>
      {/* Plan aprobado por Diego (22 nov 2026): el producto se ve por niveles, igual que en el comité; lo demás va en
          «Más del producto» */}
      <Entrada className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-naranja-tinta">
            {e.sujeto.tipo === "propuesta" ? `${e.sujeto.folio} · ${e.sujeto.proveedor}` : "Idea de Compras"}
            <span className="font-normal text-smn-gris-500"> · evaluado el {fechaLocal(e.creada_en)}</span>
          </p>
          {!lista && <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{e.sujeto.nombre}</h1>}
        </div>
        {/* En el celular solo queda a la vista «Pregúntale a la IA»; lo demás va en «⋯» para que el producto se vea primero */}
        <div className="relative flex items-center gap-2">
          {lista && (
            <Boton variante="secundario" onClick={() => setIa(true)}>
              <Bot className="h-4 w-4" /> Pregúntale a la IA
            </Boton>
          )}
          {lista && (
            <button
              type="button"
              onClick={() => setAcciones((v) => !v)}
              aria-expanded={acciones}
              aria-label="Más acciones"
              className="grid h-10 w-10 place-items-center rounded-xl border border-smn-gris-300 text-smn-gris-700 hover:bg-smn-gris-50 sm:hidden"
            >
              <MoreHorizontal className="h-5 w-5" />
            </button>
          )}
          {lista && (
            <div
              className={`${acciones ? "flex" : "hidden"} absolute top-full right-0 z-20 mt-2 w-60 flex-col gap-2 rounded-2xl border border-smn-gris-100 bg-superficie p-2 shadow-xl sm:static sm:mt-0 sm:flex sm:w-auto sm:flex-row sm:flex-wrap sm:border-0 sm:bg-transparent sm:p-0 sm:shadow-none [&>*]:justify-start sm:[&>*]:justify-center`}
            >
              <BotonReporte ruta={`${RUTA}/evaluaciones/${e.id}/reporte`} nombre={e.sujeto.nombre} />
              {ajusta && e.vigente && (
                <Boton variante="secundario" onClick={() => setAbierto("color")}>
                  <Palette className="h-4 w-4" /> Cambiar el color final
                </Boton>
              )}
              {recalcularBoton()}
            </div>
          )}
        </div>
      </Entrada>

      <AnimatePresence>
        {ia && (
          <motion.aside
            key="ia"
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.18 }}
            role="dialog"
            aria-label="Pregúntale a la IA"
            className="fixed inset-0 z-50 flex flex-col bg-superficie shadow-2xl sm:inset-y-3 sm:right-3 sm:left-auto sm:w-[480px] sm:rounded-2xl sm:border sm:border-smn-gris-100"
          >
            <div className="flex items-start gap-3 border-b border-smn-gris-100 px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-smn-gris-500">Pregúntale a la IA</p>
                <p className="truncate text-base font-semibold">{e.sujeto.nombre}</p>
              </div>
              {e.puntaje !== null && color && <InsigniaColor color={color} />}
              <button type="button" onClick={() => setIa(false)} aria-label="Cerrar" className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100">
                <X className="h-5 w-5" />
              </button>
            </div>
            <Asistente
              url={`${RUTA}/evaluaciones/${e.id}/preguntar`}
              turnos={turnos}
              guardar={setTurnos}
              anotar={false}
              titulo="¿Qué quieres saber de este producto?"
              sugerencias={SUGERENCIAS_RADAR}
            />
          </motion.aside>
        )}
      </AnimatePresence>

      {yaVendemos && (
        <p className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-aviso-fondo p-3 text-sm text-aviso-texto">
          <AlertTriangle className="h-4 w-4" />
          <span>
            <b>Ya lo vendemos:</b> {yaVendemos.sku} {yaVendemos.descripcion}
            {yaVendemos.precio && ` a ${pesos(yaVendemos.precio)}`}. La demanda, el margen y el precio se calcularon con ese producto.
          </span>
        </p>
      )}

      {!e.vigente && (
        <p className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-aviso-fondo p-3 text-sm text-aviso-texto">
          <History className="h-4 w-4" /> Esta es una evaluación anterior.
          <Link href={`/compras/productos/${vigente}`} className="font-semibold underline">Ver la vigente</Link>
        </p>
      )}

      {lista && e.color_final && (
        <p className="mb-4 rounded-2xl bg-smn-gris-50 px-4 py-3 text-sm">
          Compras lo cambió de <b>{SEMAFORO[e.color!].texto.toLowerCase()}</b> a <b>{SEMAFORO[e.color_final].texto.toLowerCase()}</b>: {e.motivo_cambio}
          <span className="block text-[13px] text-smn-gris-500">{e.cambiado_por} · {e.cambiado_en && fechaLocal(e.cambiado_en)}</span>
        </p>
      )}

      {e.estado === "en_curso" && (
        <Entrada retraso={0.05} className="mb-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
          <div className="flex items-center gap-4">
            <Semaforo color={null} tam="lg" />
            <div>
              <p className="flex items-center gap-2 text-xl font-semibold"><Loader2 className="h-5 w-5 animate-spin text-smn-naranja" /> Evaluando…</p>
              <p className="text-sm text-smn-gris-500">{e.avance ?? "Preparando la evaluación…"}</p>
              <p className="mt-1 text-[13px] text-smn-gris-500">Los pasos que buscan en internet o usan la IA son los que más tardan. Puedes salir de esta pantalla; sigue corriendo.</p>
            </div>
          </div>
        </Entrada>
      )}
      {e.estado === "fallida" && (
        <Entrada retraso={0.05} className="mb-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-4">
            <AlertTriangle className="h-8 w-8 text-smn-naranja" />
            <div className="min-w-0 flex-1">
              <p className="text-xl font-semibold">No se pudo evaluar</p>
              <p className="text-sm text-smn-gris-700">{e.error}</p>
            </div>
            {recalcularBoton("Recalcular", "primario")}
          </div>
        </Entrada>
      )}

      {lista && (
        <>
          <section className="mb-6 rounded-3xl border border-smn-gris-100 bg-superficie p-4 sm:p-6">
            <PantallaComite
              key={e.id}
              ruta={`${RUTA}/evaluaciones/${e.id}/pantalla${e.cambiado_en ? `?v=${encodeURIComponent(e.cambiado_en)}` : ""}`}
              nombre={e.sujeto.nombre}
              foto={foto}
              inicio="Radar de productos"
              recalcular={recalcularBoton("Recalcular ahora", "primario")}
            />
          </section>

          <details className="group rounded-2xl border border-smn-gris-100 bg-superficie" open={masAbierto} onToggle={(x) => setMasAbierto(x.currentTarget.open)}>
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 select-none">
              <span>
                <span className="font-semibold">Más del producto</span>
                <span className="block text-[13px] text-smn-gris-500">Ficha técnica, lo que capturó Compras, clasificación, parecidos, políticas e historial</span>
              </span>
              <ChevronDown className="h-5 w-5 shrink-0 text-smn-gris-500 transition-transform group-open:rotate-180" aria-hidden />
            </summary>
            <div className="grid gap-4 border-t border-smn-gris-100 p-4 sm:p-5 lg:grid-cols-[1fr_22rem]">
              <div className="min-w-0 space-y-4">
                <section className="rounded-2xl border border-smn-gris-100 p-5">
                  <h2 className="mb-2 font-semibold">{e.color_final ? "¿Por qué el radar dio otro color?" : "Explicación completa del radar"}</h2>
                  <TextoExplicado texto={e.explicacion ?? ""} />
                </section>
                <FichaTecnicaTarjeta ruta={`${RUTA}/evaluaciones/${e.id}/ficha`} />
                {e.politicas && <Politicas r={e.politicas} />}
              </div>

              <aside className="min-w-0 space-y-4">
                {(busqueda || e.sujeto.tipo === "propuesta" || evalua) && (
                  <section className="rounded-2xl border border-smn-gris-100 p-5">
                    <h2 className="mb-3 font-semibold">{e.sujeto.tipo === "propuesta" ? "Propuesta" : "Estado de la idea"}</h2>
                    <div className="flex flex-col items-start gap-3">
                      {e.sujeto.tipo === "propuesta" ? (
                        <Link href={`/compras/propuestas/${e.sujeto.id}`} className="text-sm font-semibold text-naranja-tinta hover:underline">Ver la propuesta</Link>
                      ) : evalua ? (
                        <select
                          value={e.sujeto.estado ?? "nueva"}
                          onChange={(x) => estadoIdea(x.target.value as EstadoIdea)}
                          aria-label="Estado de la idea"
                          className="rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-sm font-semibold outline-none focus:border-smn-naranja"
                        >
                          {Object.entries(ESTADOS_IDEA).map(([v, t]) => (
                            <option key={v} value={v}>{t}</option>
                          ))}
                        </select>
                      ) : (
                        <Insignia className="bg-smn-gris-100 text-smn-gris-700">{ESTADOS_IDEA[e.sujeto.estado ?? "nueva"]}</Insignia>
                      )}
                      {busqueda && (
                        <Link
                          href={`/compras/propuestas/busquedas/${busqueda.id}`}
                          className="inline-flex items-center gap-1.5 text-sm font-medium text-naranja-tinta hover:underline"
                        >
                          <PackageSearch className="h-4 w-4" aria-hidden />
                          Búsqueda de proveedor: {busqueda.estado_texto.toLowerCase()}
                          {busqueda.responsable && ` · ${busqueda.responsable.nombre}`}
                        </Link>
                      )}
                    </div>
                  </section>
                )}

                <TipoProducto
                  lista={e.lista_margen}
                  membresia={e.precio_membresia}
                  editable={evalua && e.vigente && (e.sujeto.tipo === "idea" || puede("compras.propuestas.revisar"))}
                  nota="Rentabilidad pide el margen mínimo de esta lista al precio de lista y al de membresía, y Precio usa los dos. Al cambiarlo, usa «Recalcular» para que cuente. Sin elegir, se evalúa con la lista A."
                  guardar={async (lista, membresia) => {
                    const ruta = e.sujeto.tipo === "idea"
                      ? `${RUTA}/ideas/${e.sujeto.id}/margen`
                      : `/api/compras/propuestas/${e.sujeto.id}/margen`;
                    await api(ruta, { metodo: "PATCH", cuerpo: { lista_margen: lista, precio_membresia: membresia } });
                    await cargar();
                  }}
                />

                {e.sujeto.tipo === "idea" && (
                  <section className="rounded-2xl border border-smn-gris-100 p-5">
                    <h2 className="mb-3 font-semibold">Lo que capturó Compras</h2>
                    {e.fotos.length > 0 && (
                      <div className="mb-3 grid grid-cols-3 gap-2">
                        {e.fotos.map((f) => (
                          <a key={f.archivo_id} href={urlFoto(e.sujeto.id, f.archivo_id)} target="_blank" rel="noreferrer" className="aspect-square overflow-hidden rounded-xl bg-smn-gris-50">
                            {/* eslint-disable-next-line @next/next/no-img-element -- foto servida por la API con sesión */}
                            <Imagen src={urlFoto(e.sujeto.id, f.archivo_id, 400)} alt={f.nombre} loading="lazy" decoding="async" className="h-full w-full object-cover" />
                          </a>
                        ))}
                      </div>
                    )}
                    {e.descripcion && <p className="mb-2 text-sm">{e.descripcion}</p>}
                    <dl className="space-y-1 text-sm">
                      {e.precio_nuestro && (
                        <div><dt className="inline text-smn-gris-500">Nuestro precio: </dt><dd className="inline font-semibold">{pesos(e.precio_nuestro)}</dd></div>
                      )}
                      <div><dt className="inline text-smn-gris-500">{e.precio_nuestro ? "Precio visto afuera: " : "Precio visto: "}</dt><dd className="inline font-semibold">{e.precio_visto ? pesos(e.precio_visto) : "—"}</dd></div>
                      <div><dt className="inline text-smn-gris-500">Dónde: </dt><dd className="inline font-semibold">{e.donde_se_vio ?? "—"}</dd></div>
                      <div><dt className="inline text-smn-gris-500">Costo estimado: </dt><dd className="inline font-semibold">{e.costo_estimado ? pesos(e.costo_estimado) : "—"}</dd></div>
                      {e.codigo_barras && (
                        <div><dt className="inline text-smn-gris-500">Código de barras: </dt><dd className="inline font-semibold tabular-nums">{e.codigo_barras}</dd></div>
                      )}
                      {e.activo_g_porcion && e.porciones && (
                        <div><dt className="inline text-smn-gris-500">Activo: </dt><dd className="inline font-semibold">{Number(e.activo_g_porcion)} g por porción × {e.porciones} porciones</dd></div>
                      )}
                    </dl>
                  </section>
                )}

                <section className="rounded-2xl border border-smn-gris-100 p-5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <h2 className="flex items-center gap-2 font-semibold"><Tag className="h-4 w-4 text-smn-naranja" /> Clasificación</h2>
                    {evalua && e.vigente && (
                      <button onClick={() => setAbierto("clasificacion")} className="text-sm font-semibold text-naranja-tinta hover:underline">
                        {e.clasificacion_origen === "compras" ? "Cambiar" : "Confirmar"}
                      </button>
                    )}
                  </div>
                  {e.subcategoria ? (
                    <dl className="space-y-1 text-sm">
                      <div><dt className="inline text-smn-gris-500">Rama: </dt><dd className="inline font-semibold">{e.rama ?? "—"}</dd></div>
                      <div><dt className="inline text-smn-gris-500">Subcategoría: </dt><dd className="inline font-semibold">{e.subcategoria}</dd></div>
                      <div><dt className="inline text-smn-gris-500">Segmento: </dt><dd className="inline font-semibold">{e.segmento ?? "—"}</dd></div>
                    </dl>
                  ) : (
                    <p className="text-sm text-smn-gris-500">Todavía no tiene subcategoría.</p>
                  )}
                  <p className={`mt-2 flex items-center gap-1 text-[13px] ${e.clasificacion_origen === "compras" ? "text-smn-gris-500" : "text-aviso-texto"}`}>
                    {e.clasificacion_origen === "ia" && <Bot className="h-3.5 w-3.5" />}
                    {e.clasificacion_origen === "compras" && <Check className="h-3.5 w-3.5" />}
                    {ORIGEN_CLASIFICACION[e.clasificacion_origen ?? "sin_clasificar"]}
                  </p>
                </section>

                <section className="rounded-2xl border border-smn-gris-100 p-5">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <h2 className="font-semibold">Productos parecidos</h2>
                    {evalua && e.vigente && (
                      <button onClick={() => setAbierto("parecidos")} className="text-sm font-semibold text-naranja-tinta hover:underline">
                        Corregir
                      </button>
                    )}
                  </div>
                  <p className="text-sm text-smn-gris-700">
                    {e.comparables.length === 0 ? "No se encontraron parecidos en el catálogo." : `${e.comparables.length} del catálogo; se ven con su venta en el nivel «Con qué datos» de cada factor.`}
                  </p>
                  <p className="mt-1 text-[13px] text-smn-gris-500">
                    {e.comparables.some((c) => c.origen === "compras") ? "Lista fijada por Compras; se conserva al recalcular." : "Los eligió el sistema."}
                  </p>
                </section>

                <section className="rounded-2xl border border-smn-gris-100 p-5">
                  <h2 className="mb-3 font-semibold">Historial</h2>
                  <ol className="space-y-2">
                    {e.historial.map((h) => (
                      <li key={h.id}>
                        <Link
                          href={`/compras/productos/${h.id}`}
                          className={`flex items-center gap-3 rounded-xl px-2 py-1.5 text-sm ${h.id === e.id ? "bg-smn-gris-100 font-semibold" : "hover:bg-smn-gris-50"}`}
                        >
                          <Semaforo color={h.estado === "lista" ? h.color_final ?? h.color : null} tam="sm" horizontal />
                          <span className="tabular-nums">{h.puntaje ?? "—"}</span>
                          <span className="ml-auto text-[13px] text-smn-gris-500">{fechaLocal(h.creada_en)}</span>
                        </Link>
                      </li>
                    ))}
                  </ol>
                </section>
              </aside>
            </div>
          </details>
        </>
      )}

      <AnimatePresence>
        {abierto === "color" && <CambiarColor e={e} cerrar={() => setAbierto(null)} listo={setE} />}
        {abierto === "clasificacion" && <ConfirmarClasificacion e={e} ocupado={ocupado} cerrar={() => setAbierto(null)} guardar={(c) => nueva("clasificacion", c)} />}
        {abierto === "parecidos" && <CorregirParecidos e={e} ocupado={ocupado} cerrar={() => setAbierto(null)} guardar={(skus) => nueva("comparables", { skus })} />}
      </AnimatePresence>
    </>
  );
}

const RESULTADO_POLITICA = {
  cumple: { texto: "Cumple", clase: SEMAFORO.verde.insignia },
  no_cumple: { texto: "No cumple", clase: SEMAFORO.rojo.insignia },
  sin_datos: { texto: "Faltan datos", clase: "bg-smn-gris-100 text-smn-gris-500" },
  sin_revisar: { texto: "Sin revisar", clase: "bg-smn-gris-100 text-smn-gris-500" },
} as const;
const TIPO_POLITICA = { rechazo: "Regla de rechazo", umbral: "Umbral", politica: "Política" } as const;
const DECISION_CASO: Record<string, string> = { aprobado: "Aprobado", rechazado: "Rechazado", condicionado: "Condicionado" };
const RESULTADO_CASO: Record<string, string> = { funciono: "funcionó", no_funciono: "no funcionó", sin_dato: "sin dato de cómo le fue", no_aplica: "no aplica" };

function Politicas({ r }: { r: RevisionPoliticas }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-3 font-semibold">Políticas y reglas de Compras</h2>
      {r.rechazo && (
        <p className="mb-3 flex gap-2 rounded-2xl bg-red-600/10 p-3 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span><b>Rechazo directo: {r.rechazo.titulo}.</b> {r.rechazo.motivo}</span>
        </p>
      )}
      {r.hallazgos.length > 0 && (
        <ul className="divide-y divide-smn-gris-100">
          {r.hallazgos.map((h) => (
            <li key={h.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="font-semibold">{h.titulo} <span className="font-normal text-smn-gris-500">· {TIPO_POLITICA[h.tipo]}</span></p>
                {h.motivo && <p className="text-[13px] text-smn-gris-500">{h.motivo}</p>}
              </div>
              {h.sin_prueba ? (
                <Insignia className={RESULTADO_POLITICA.sin_datos.clase}>Por confirmar</Insignia>
              ) : (
                <Insignia className={RESULTADO_POLITICA[h.resultado].clase}>{RESULTADO_POLITICA[h.resultado].texto}</Insignia>
              )}
            </li>
          ))}
        </ul>
      )}
      {r.notas.map((n, i) => <p key={i} className="mt-2 text-[13px] text-smn-gris-500">{n}</p>)}
      {r.casos.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1 text-sm font-semibold">Casos parecidos que Compras ya decidió</h3>
          <ul className="space-y-1 text-sm">
            {r.casos.map((c) => (
              <li key={c.caso_id}>
                <b>{c.producto}</b>: {DECISION_CASO[c.decision] ?? c.decision}{c.fecha ? ` el ${fechaLocal(c.fecha, { dateStyle: "medium" })}` : ""}, {RESULTADO_CASO[c.resultado] ?? c.resultado}.
                {c.motivo && <span className="text-smn-gris-500"> {c.motivo}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.revisada_ia && <p className="mt-2 flex items-center gap-1 text-[13px] text-smn-gris-500"><Bot className="h-3.5 w-3.5" /> Revisado por la IA con los datos de esta evaluación.</p>}
    </section>
  );
}

function FilaParecido({ c, quitar }: { c: Comparable | ProductoCatalogo; quitar?: () => void }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{c.descripcion ?? "Sin descripción"}</p>
        <p className="truncate text-[13px] text-smn-gris-500">
          {c.sku} · {c.marca ?? "Sin marca"}{c.subcategoria && ` · ${c.subcategoria}`}
        </p>
      </div>
      <span className="text-sm font-semibold tabular-nums">{c.precio ? pesos(c.precio) : "—"}</span>
      {"similitud" in c && c.origen === "sistema" && (
        <span className="hidden w-12 text-right text-[13px] text-smn-gris-500 tabular-nums sm:inline">{Math.round(Number(c.similitud) * 100)} %</span>
      )}
      {quitar && (
        <button type="button" onClick={quitar} aria-label={`Quitar ${c.sku}`} className="rounded-lg p-1 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta">
          <Trash2 className="h-4 w-4" />
        </button>
      )}
    </li>
  );
}

function CambiarColor({ e, cerrar, listo }: { e: Evaluacion; cerrar: () => void; listo: (e: Evaluacion) => void }) {
  const avisar = useAvisos();
  const [color, setColor] = useState<Color>(colorVigente(e) ?? "amarillo");
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);

  const guardar = async (x: React.FormEvent) => {
    x.preventDefault();
    setGuardando(true);
    try {
      listo(await api<Evaluacion>(`${RUTA}/evaluaciones/${e.id}/color`, { cuerpo: { color: color === e.color ? null : color, motivo } }));
      avisar("Color final guardado");
      cerrar();
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <Modal titulo="Cambiar el color final" cerrar={cerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <p className="text-sm text-smn-gris-500">El radar dio <b>{e.color && SEMAFORO[e.color].texto.toLowerCase()}</b>. El color final lo decide Compras y el motivo queda en la bitácora.</p>
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Color">
          {(["verde", "amarillo", "rojo"] as Color[]).map((c) => (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={color === c}
              onClick={() => setColor(c)}
              className={`flex flex-col items-center gap-2 rounded-2xl border-2 p-3 text-sm font-semibold transition ${color === c ? "border-tinta" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
            >
              <span className={`h-6 w-6 rounded-full ${SEMAFORO[c].punto}`} />
              {SEMAFORO[c].texto}
              {c === e.color && <span className="text-[13px] font-semibold text-smn-gris-500">el del radar</span>}
            </button>
          ))}
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Motivo *</span>
          <textarea
            value={motivo}
            onChange={(x) => setMotivo(x.target.value)}
            rows={3}
            required
            minLength={10}
            maxLength={1000}
            placeholder="Qué sabe Compras que el radar no ve"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <div className="flex justify-end gap-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={guardando} disabled={motivo.trim().length < 10}>
            Guardar <InsigniaColor color={color} />
          </Boton>
        </div>
      </form>
    </Modal>
  );
}

function ConfirmarClasificacion({ e, ocupado, cerrar, guardar }: { e: Evaluacion; ocupado: boolean; cerrar: () => void; guardar: (c: OpcionClasificacion) => void }) {
  const [opciones, setOpciones] = useState<OpcionClasificacion[] | null>(null);
  const [q, setQ] = useState("");
  const clave = (o: { rama: string | null; subcategoria: string | null; segmento: string | null }) => `${o.rama ?? ""}|${o.subcategoria ?? ""}|${o.segmento ?? ""}`;
  const [elegida, setElegida] = useState(clave(e));

  useEffect(() => {
    const p = new URLSearchParams(e.sujeto.departamento ? { departamento: e.sujeto.departamento } : {});
    api<OpcionClasificacion[]>(`${RUTA}/clasificaciones?${p}`).then(setOpciones).catch(() => setOpciones([]));
  }, [e.sujeto.departamento]);

  const filtro = q.trim().toLowerCase();
  const visibles = (opciones ?? []).filter((o) => !filtro || clave(o).toLowerCase().includes(filtro)).slice(0, 80);
  const actual = opciones?.find((o) => clave(o) === elegida);

  return (
    <Modal titulo="Clasificación del producto" cerrar={cerrar} ancho="max-w-xl">
      <p className="mb-3 text-sm text-smn-gris-500">Elige dónde va en el catálogo{e.sujeto.departamento && ` de ${e.sujeto.departamento}`}. Se recalcula con ella y se conserva en los siguientes cálculos.</p>
      <label className="relative mb-3 block">
        <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input value={q} onChange={(x) => setQ(x.target.value)} placeholder="Buscar rama, subcategoría o segmento"
          className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja" />
      </label>
      {opciones === null ? (
        <Esqueleto className="h-40" />
      ) : opciones.length === 0 ? (
        <p className="rounded-2xl bg-smn-gris-50 p-4 text-sm text-smn-gris-500">El catálogo no tiene subcategorías para este departamento todavía.</p>
      ) : (
        <ul className="max-h-72 space-y-1 overflow-y-auto">
          {visibles.map((o) => (
            <li key={clave(o)}>
              <button
                type="button"
                onClick={() => setElegida(clave(o))}
                className={`w-full rounded-xl px-3 py-2 text-left text-sm ${elegida === clave(o) ? "bg-smn-naranja/15 ring-2 ring-smn-naranja" : "hover:bg-smn-gris-50"}`}
              >
                <span className="font-semibold">{o.subcategoria}</span>
                <span className="text-smn-gris-500"> · {o.rama}{o.segmento && ` · ${o.segmento}`}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
        <Boton cargando={ocupado} disabled={!actual} onClick={() => actual && guardar(actual)}>
          <Check className="h-4 w-4" /> Confirmar y recalcular
        </Boton>
      </div>
    </Modal>
  );
}

function CorregirParecidos({ e, ocupado, cerrar, guardar }: { e: Evaluacion; ocupado: boolean; cerrar: () => void; guardar: (skus: string[]) => void }) {
  const [lista, setLista] = useState<(Comparable | ProductoCatalogo)[]>(e.comparables);
  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<ProductoCatalogo[]>([]);

  useEffect(() => {
    if (q.trim().length < 2) return setResultados([]);
    const t = setTimeout(() => api<ProductoCatalogo[]>(`${RUTA}/catalogo?q=${encodeURIComponent(q.trim())}`).then(setResultados).catch(() => setResultados([])), 300);
    return () => clearTimeout(t);
  }, [q]);

  const tiene = new Set(lista.map((c) => c.sku));

  return (
    <Modal titulo="Productos parecidos" cerrar={cerrar} ancho="max-w-2xl">
      <p className="mb-3 text-sm text-smn-gris-500">Quita los que no se parecen y agrega los que sí (hasta 10). Se usan para precio, demanda y categoría. La lista queda fija al recalcular.</p>
      <ul className="mb-4 divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 px-3">
        {lista.length === 0 && <li className="py-3 text-sm text-smn-gris-500">Sin productos: el sistema volverá a buscarlos.</li>}
        {lista.map((c) => (
          <FilaParecido key={c.sku} c={c} quitar={() => setLista(lista.filter((x) => x.sku !== c.sku))} />
        ))}
      </ul>
      <label className="relative block">
        <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input value={q} onChange={(x) => setQ(x.target.value)} placeholder="Agregar por SKU, descripción o marca"
          className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja" />
      </label>
      {resultados.length > 0 && (
        <ul className="mt-2 max-h-56 overflow-y-auto rounded-2xl border border-smn-gris-100">
          {resultados.map((p) => (
            <li key={p.sku}>
              <button
                type="button"
                disabled={tiene.has(p.sku) || lista.length >= 10}
                onClick={() => setLista([...lista, p])}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-smn-gris-50 disabled:opacity-40"
              >
                <Plus className="h-4 w-4 shrink-0 text-smn-naranja" />
                <span className="min-w-0 flex-1 truncate">{p.descripcion}</span>
                <span className="text-[13px] text-smn-gris-500">{p.sku}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
        <Boton cargando={ocupado} onClick={() => guardar(lista.map((c) => c.sku))}>
          <Check className="h-4 w-4" /> Guardar y recalcular
        </Boton>
      </div>
    </Modal>
  );
}


/** Párrafos con **negritas**, como los escribe el resumen. */
function TextoExplicado({ texto }: { texto: string }) {
  return (
    <div className="space-y-2 leading-relaxed">
      {texto.split(/\n\s*\n/).map((p, i) => (
        <p key={i} className="whitespace-pre-line">
          {p.split(/(\*\*[^*]+\*\*)/g).map((t, j) => (t.startsWith("**") && t.endsWith("**") ? <b key={j}>{t.slice(2, -2)}</b> : t))}
        </p>
      ))}
    </div>
  );
}
