"use client";
// Detalle de una evaluación del radar de productos: semáforo, explicación, los 6 factores, clasificación, parecidos y color final.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Bot, Check, CircleHelp, Gavel, History, PackageSearch, Palette, Pencil, Plus, RefreshCw, Search, Tag, Trash2, TrendingUp, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { BotonReporte } from "@/componentes/boton-reporte";
import { FichaTecnicaTarjeta } from "@/componentes/ficha-tecnica";
import { Modal } from "@/componentes/modal";
import { InsigniaColor, Semaforo } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { SEMAFORO } from "@/lib/precios";
import { RUTA as RUTA_BUSQUEDAS, type BusquedaBreve } from "@/lib/busquedas";
import { Asistente, type Turno } from "../../propuestas/comite/[id]/presentar/asistente";
import {
  aportes, colorVigente, CONFIANZA, ESTADOS_IDEA, faltaPara, QUE_MIDE, RUTA, urlFoto,
  type Color, type Comparable, type EstadoIdea, type Evaluacion, type HallazgoWeb, type Investigacion, type MercadoInternet, type Pronostico, type OpcionClasificacion, type RevisionPoliticas, type ProductoCatalogo,
} from "@/lib/productos";

// Preguntas para el asistente de cada producto (Diego, 2026-11-09: «preguntarle sobre la decisión de cada producto»)
const SUGERENCIAS_RADAR = [
  { texto: "¿Por qué salió de este color?", icono: CircleHelp },
  { texto: "¿Qué lo haría subir de calificación?", icono: TrendingUp },
  { texto: "¿Cómo está su precio contra internet?", icono: Tag },
  { texto: "¿Qué decidió el comité y por qué?", icono: Gavel },
];

const ORIGEN_CLASIFICACION = { ia: "Sugerida por la IA, sin confirmar", compras: "Confirmada por Compras", parecidos: "Tomada de los productos parecidos, sin confirmar", sin_clasificar: "Sin clasificar" } as const;

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

  return (
    <>
      <Entrada className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-naranja-tinta">
            {e.sujeto.tipo === "propuesta" ? `${e.sujeto.folio} · ${e.sujeto.proveedor}` : "Idea de Compras"}
          </p>
          <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{e.sujeto.nombre}</h1>
          <p className="mt-1 text-sm text-smn-gris-500">
            {[e.sujeto.marca, e.sujeto.departamento ?? "Sin departamento"].filter(Boolean).join(" · ")} · evaluado el {fechaLocal(e.creada_en)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
        {busqueda && (
          <Link
            href={`/compras/propuestas/busquedas/${busqueda.id}`}
            className="inline-flex items-center gap-1.5 rounded-xl border border-smn-gris-100 bg-superficie px-3 py-2 text-sm font-medium hover:border-smn-naranja"
          >
            <PackageSearch className="h-4 w-4" aria-hidden />
            Búsqueda de proveedor: {busqueda.estado_texto.toLowerCase()}
            {busqueda.responsable && ` · ${busqueda.responsable.nombre}`}
          </Link>
        )}
        {lista && (
          <Boton variante="secundario" onClick={() => setIa(true)}>
            <Bot className="h-4 w-4" /> Pregúntale a la IA
          </Boton>
        )}
        {lista && <BotonReporte ruta={`${RUTA}/evaluaciones/${e.id}/reporte`} nombre={e.sujeto.nombre} />}
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

      {/* Resultado */}
      <Entrada retraso={0.05} className="mb-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
        {e.estado === "en_curso" ? (
          <div className="flex items-center gap-4">
            <Semaforo color={null} tam="lg" />
            <div>
              <p className="flex items-center gap-2 text-xl font-semibold"><Loader2 className="h-5 w-5 animate-spin text-smn-naranja" /> Evaluando…</p>
              <p className="text-sm text-smn-gris-500">{e.avance ?? "Preparando la evaluación…"}</p>
              <p className="mt-1 text-[13px] text-smn-gris-500">Los pasos que buscan en internet o usan la IA son los que más tardan. Puedes salir de esta pantalla; sigue corriendo.</p>
            </div>
          </div>
        ) : e.estado === "fallida" ? (
          <div className="flex flex-wrap items-center gap-4">
            <AlertTriangle className="h-8 w-8 text-smn-naranja" />
            <div className="min-w-0 flex-1">
              <p className="text-xl font-semibold">No se pudo evaluar</p>
              <p className="text-sm text-smn-gris-700">{e.error}</p>
            </div>
            {evalua && e.vigente && (
              <Boton cargando={ocupado} onClick={() => nueva("recalcular", undefined, "POST", "Recalculando")}>
                <RefreshCw className="h-4 w-4" /> Recalcular
              </Boton>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-5">
            <Semaforo color={color} tam="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-5xl font-semibold tabular-nums">
                {e.puntaje ?? "—"}<span className="text-lg font-semibold text-smn-gris-500"> de 100</span>
              </p>
              <p className="mt-1 text-sm text-smn-gris-700">
                {color && SEMAFORO[color].texto} · {e.confianza && CONFIANZA[e.confianza]}
                {e.pesos_origen === "iguales" && " · los 6 factores pesan igual"}
                {e.modelo === "con_proveedor" && " · semáforo con proveedor actual"}
                {e.modelo === "sin_proveedor" && " · semáforo sin proveedor actual"}
              </p>
              {faltaPara(e.puntaje, e.color) && <p className="mt-1 text-sm font-semibold text-smn-gris-700">{faltaPara(e.puntaje, e.color)}</p>}
              {e.color_final && (
                <p className="mt-2 rounded-xl bg-smn-gris-50 px-3 py-2 text-sm">
                  Compras lo cambió de <b>{SEMAFORO[e.color!].texto.toLowerCase()}</b> a <b>{SEMAFORO[e.color_final].texto.toLowerCase()}</b>: {e.motivo_cambio}
                  <span className="block text-[13px] text-smn-gris-500">{e.cambiado_por} · {e.cambiado_en && fechaLocal(e.cambiado_en)}</span>
                </p>
              )}
            </div>
            {e.vigente && (evalua || ajusta) && (
              <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:flex-col">
                {ajusta && (
                  <Boton onClick={() => setAbierto("color")}>
                    <Palette className="h-4 w-4" /> Cambiar color
                  </Boton>
                )}
                {evalua && (
                  <Boton variante="secundario" cargando={ocupado && !abierto} onClick={() => nueva("recalcular", undefined, "POST", "Recalculando")}>
                    <RefreshCw className="h-4 w-4" /> Recalcular
                  </Boton>
                )}
              </div>
            )}
          </div>
        )}
      </Entrada>

      {lista && (
        <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-4">
            <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
              <h2 className="mb-2 flex items-center gap-2 font-semibold">
                {e.color_final ? "¿Por qué el radar dio otro color?" : "¿Por qué este color?"}
                <span className="text-[13px] font-medium text-smn-gris-500">{e.explicacion_ia ? "· redactado por la IA con los datos de abajo" : "· armado con los números de los 6 factores"}</span>
              </h2>
              <TextoExplicado texto={e.explicacion ?? ""} />
            </section>

            <section>
              <h2 className="mb-3 font-semibold">Los 6 factores</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {e.factores.map((f, i) => {
                  const aporte = aportes(e.factores)[f.factor];
                  return (
                  <motion.article
                    key={f.factor}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="rounded-2xl border border-smn-gris-100 bg-superficie p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold">{f.nombre}</p>
                        <p className="text-[13px] text-smn-gris-500">Pesa {Number(f.peso).toFixed(0)} %</p>
                      </div>
                      <div className="text-right">
                        <p className="text-2xl font-semibold tabular-nums">{f.puntaje ?? "—"}</p>
                        {f.provisional && <Insignia className="bg-aviso-fondo text-aviso-texto">Provisional</Insignia>}
                      </div>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-smn-gris-100">
                      <motion.div
                        className="h-full rounded-full bg-smn-naranja"
                        initial={{ width: 0 }}
                        animate={{ width: `${f.puntaje ?? 0}%` }}
                        transition={{ duration: 0.6, delay: 0.1 + i * 0.04 }}
                      />
                    </div>
                    {QUE_MIDE[f.factor] && <p className="mt-2 text-[13px] text-smn-gris-500">{QUE_MIDE[f.factor]}</p>}
                    {f.valor && <p className="mt-2 text-sm font-semibold">{f.valor}</p>}
                    <dl className="mt-1 space-y-1.5 text-sm">
                      <div>
                        <dt className="sr-only">Qué encontramos</dt>
                        <dd className={f.puntaje === null ? "text-smn-gris-500 italic" : "text-smn-gris-700"}>{f.detalle}</dd>
                      </div>
                      {f.mejora && (
                        <div>
                          <dt className="text-[13px] font-medium text-smn-gris-500">{f.puntaje !== null && f.puntaje > 80 ? "Qué significa" : "Qué lo subiría"}</dt>
                          <dd className="text-smn-gris-700">{f.mejora}</dd>
                        </div>
                      )}
                      {f.calculo && (
                        <details className="text-[13px] text-smn-gris-500">
                          <summary className="cursor-pointer select-none">Cómo se calificó</summary>
                          <p className="mt-1 text-smn-gris-700">{f.calculo}</p>
                        </details>
                      )}
                    </dl>
                    {aporte !== undefined && (
                      <p className="mt-2 text-[13px] text-smn-gris-500">
                        Aporta <b className="text-tinta">{aporte.toLocaleString("es-MX", { maximumFractionDigits: 1 })}</b> de los {e.puntaje} puntos del total.
                      </p>
                    )}
                  </motion.article>
                  );
                })}
              </div>
              <p className="mt-2 text-[13px] text-smn-gris-500">
                Cómo se suma: cada factor se califica de 0 a 100 y cuenta según lo que pesa; los que no tienen datos no cuentan. «Provisional» quiere
                decir que la regla todavía no la definió Compras en su Base de conocimiento. «Confianza» dice qué parte del peso tiene datos: alta con 80 % o
                más, media con la mitad o más, baja con menos; con confianza baja no puede salir verde. «Precio de en medio»: la mitad de los precios está
                arriba y la mitad abajo.
              </p>
            </section>

            <FichaTecnicaTarjeta ruta={`${RUTA}/evaluaciones/${e.id}/ficha`} />
            {e.politicas && <Politicas r={e.politicas} />}
            {e.mercado && <PreciosInternet m={e.mercado} />}
            {e.investigacion && <Afuera inv={e.investigacion} />}
            {e.pronostico && <CuantoVendera p={e.pronostico} />}

            <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-semibold">Productos parecidos que ya vendemos</h2>
                {evalua && e.vigente && (
                  <Boton variante="secundario" onClick={() => setAbierto("parecidos")}>
                    <Pencil className="h-4 w-4" /> Corregir
                  </Boton>
                )}
              </div>
              {e.comparables.length === 0 ? (
                <p className="text-sm text-smn-gris-500">No se encontraron productos parecidos en el catálogo.</p>
              ) : (
                <ul className="divide-y divide-smn-gris-100">
                  {e.comparables.map((c) => (
                    <FilaParecido key={c.producto_id} c={c} />
                  ))}
                </ul>
              )}
              <p className="mt-2 text-[13px] text-smn-gris-500">
                {e.comparables.some((c) => c.origen === "compras") ? "Lista fijada por Compras; se conserva al recalcular." : "Los eligió el sistema por palabras en común y subcategoría."}
              </p>
            </section>
          </div>

          <aside className="space-y-4">
            <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
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

            {e.sujeto.tipo === "idea" && (
              <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
                <h2 className="mb-3 font-semibold">Lo que capturó Compras</h2>
                {e.fotos.length > 0 && (
                  <div className="mb-3 grid grid-cols-3 gap-2">
                    {e.fotos.map((f) => (
                      <a key={f.archivo_id} href={urlFoto(e.sujeto.id, f.archivo_id)} target="_blank" rel="noreferrer" className="aspect-square overflow-hidden rounded-xl bg-smn-gris-50">
                        {/* eslint-disable-next-line @next/next/no-img-element -- foto servida por la API con sesión */}
                        <img src={urlFoto(e.sujeto.id, f.archivo_id, 400)} alt={f.nombre} loading="lazy" decoding="async" className="h-full w-full object-cover" />
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

            <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
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

function PreciosInternet({ m }: { m: MercadoInternet }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Precios en internet</h2>
        {m.mediana && <span className="text-sm text-smn-gris-500">Mediana <b className="text-smn-negro">{pesos(m.mediana)}</b></span>}
      </div>
      {m.precios.length === 0 ? (
        <p className="text-sm text-smn-gris-500">El radar de precios no encontró este producto en Google Shopping ni en el sitio de las tiendas clave.</p>
      ) : (
        <ul className="divide-y divide-smn-gris-100">
          {m.precios.map((p, i) => (
            <li key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="font-semibold">{p.vendedor} <span className="font-normal text-smn-gris-500">· {p.fuente === "google" ? "Google Shopping" : p.fuente === "web" ? "página que leyó la IA local" : "su sitio"}</span></p>
                <p className="truncate text-[13px] text-smn-gris-500">
                  {p.liga ? <a href={p.liga} target="_blank" rel="noreferrer" className="hover:underline">{p.titulo}</a> : p.titulo}
                </p>
              </div>
              <span className="shrink-0 font-semibold">{pesos(p.precio)}</span>
            </li>
          ))}
        </ul>
      )}
      {m.notas.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[13px] text-smn-gris-500">
          {m.notas.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      <p className="mt-2 text-[13px] text-smn-gris-500">
        Búsqueda del {m.buscado_en ? fechaLocal(m.buscado_en) : "—"}; se reusa 7 días al recalcular. Costo DataForSEO: US$ {Number(m.costo_usd).toFixed(3)}.
      </p>
    </section>
  );
}

const TIPO_WEB: Record<HallazgoWeb["tipo"], string> = { mismo: "Este producto", misma_marca: "Otro de la marca", sustituto: "Sustituto" };

function Afuera({ inv }: { inv: Investigacion }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-1 font-semibold">Lo que encontramos afuera</h2>
      <p className="mb-3 text-[13px] text-smn-gris-500">Páginas de internet que leyó la IA local. Cada dato está tal cual en la página; pasa el mouse para ver la frase.</p>
      {inv.hallazgos.length === 0 ? (
        <p className="text-sm text-smn-gris-500">No encontramos páginas que hablen de este producto o de uno parecido.</p>
      ) : (
        <ul className="divide-y divide-smn-gris-100">
          {inv.hallazgos.map((h, i) => (
            <li key={i} className="py-2.5 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a href={h.url} target="_blank" rel="noreferrer" className="min-w-0 truncate font-semibold hover:underline">{h.producto ?? h.titulo}</a>
                {h.precio && <span className="shrink-0 font-semibold" title={h.citas.precio}>{pesos(h.precio)}</span>}
              </div>
              <p className="text-[13px] text-smn-gris-500">
                {TIPO_WEB[h.tipo]} · {h.dominio}
                {h.presentacion && <span title={h.citas.presentacion}> · {h.presentacion}</span>}
                {h.dosis && <span title={h.citas.dosis}> · {h.dosis}</span>}
              </p>
              {h.afirmaciones.length > 0 && <p className="mt-0.5 text-[13px] text-smn-gris-700">Dice: {h.afirmaciones.map((a) => `«${a}»`).join(" ")}</p>}
            </li>
          ))}
        </ul>
      )}
      {inv.notas.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-[13px] text-smn-gris-700">
          {inv.notas.slice(0, 6).map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      <p className="mt-2 text-[13px] text-smn-gris-500">
        Búsqueda del {inv.buscado_en ? fechaLocal(inv.buscado_en) : "—"}; se reusa 7 días al recalcular.
      </p>
    </section>
  );
}

const piezas = (n: number) => n.toLocaleString("es-MX", { maximumFractionDigits: 1 });

function CuantoVendera({ p }: { p: Pronostico }) {
  const tramos = (["4", "8", "12"] as const).filter((t) => p.tramos[t]);
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-1 font-semibold">¿Cuánto venderá y dónde?</h2>
      {tramos.length === 0 ? (
        <p className="text-sm text-smn-gris-500">{p.nota ?? "Todavía no se puede pronosticar."}</p>
      ) : (
        <>
          <p className="mb-3 text-[13px] text-smn-gris-500">
            Piezas por tienda al mes. Parte de {p.base_de} ({piezas(p.base ?? 0)}) y de cómo arrancaron {p.lanzamientos} productos nuevos de 2026.
          </p>
          <div className="grid gap-2 sm:grid-cols-3">
            {tramos.map((t) => {
              const [bajo, medio, alto] = p.tramos[t];
              return (
                <div key={t} className="rounded-xl border border-smn-gris-100 p-3">
                  <p className="text-[13px] text-smn-gris-500">Semanas {Number(t) - 3} a {t}</p>
                  <p className="text-2xl font-semibold tabular-nums">{piezas(medio)}</p>
                  <p className="text-[13px] text-smn-gris-500 tabular-nums">entre {piezas(bajo)} y {piezas(alto)}</p>
                </div>
              );
            })}
          </div>
          {p.grupos.length > 0 && (
            <>
              <h3 className="mt-4 mb-1 text-sm font-semibold">Por grupo de tiendas, a 12 semanas</h3>
              <ul className="divide-y divide-smn-gris-100">
                {[...p.grupos].sort((a, b) => b.medio - a.medio).map((g) => (
                  <li key={g.grupo} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0 truncate">{g.nombre} <span className="text-[13px] text-smn-gris-500">· {g.tiendas} tiendas</span></span>
                    <span className="shrink-0 tabular-nums"><b>{piezas(g.medio)}</b> <span className="text-[13px] text-smn-gris-500">({piezas(g.bajo)} a {piezas(g.alto)})</span></span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-2 text-[13px] text-smn-gris-500">
            {p.canibal_pct != null && `De lo que vende un nuevo, cerca de ${p.canibal_pct} % se lo quita a los que ya tenemos de su subcategoría. `}
            {p.examen.suficientes
              ? `Probado con los lanzamientos de 2026: ${p.examen.dentro_pct} % cayó dentro del rango.`
              : "Todavía hay pocos lanzamientos para medir qué tan bien le atina."}
          </p>
        </>
      )}
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
