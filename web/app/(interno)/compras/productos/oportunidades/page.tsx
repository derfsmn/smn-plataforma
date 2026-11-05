"use client";
// «Buscar oportunidades» (fase 2 del radar de productos): productos nuevos para SMN con prueba de que ya se venden
// (Diego, 2026-10-28): más vendidos en México guiados por las tendencias y, si se pide, lo que vende la competencia.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Ban, Bot, Check, ChevronDown, ChevronRight, ImageOff, Loader2, RotateCcw, Sparkles } from "lucide-react";
import { AnimatePresence } from "motion/react";
import { Modal } from "@/componentes/modal";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import {
  RUTA_OPORTUNIDADES as R,
  type CorridaOportunidadesDetalle, type EstadoOportunidades, type Oportunidad, type Prioridad,
} from "@/lib/productos";

const PRIORIDAD: Record<Prioridad, { texto: string; punto: string }> = {
  alta: { texto: "Prioridad alta", punto: "bg-smn-naranja" },
  media: { texto: "Prioridad media", punto: "bg-smn-gris-500" },
  baja: { texto: "Prioridad baja", punto: "border border-smn-gris-500" },
};

// Los pasos que reporta el servidor (api/modulos/compras/oportunidades.py), en orden; se reconocen por cómo empiezan.
const PASOS = [
  { inicio: "Revisando el radar", texto: "Revisar el radar de tendencias" },
  { inicio: "Buscando huecos", texto: "Buscar huecos del surtido en la venta" },
  { inicio: "El agente busca", texto: "Buscar los más vendidos en México" },
  { inicio: "Buscando lo que vende la competencia", texto: "Buscar lo que vende la competencia", competencia: true },
  { inicio: "La IA está eligiendo", texto: "Elegir los productos" },
  { inicio: "Revisando que no", texto: "Quitar lo que ya vendemos y buscar fotos" },
];

const COMO_BUSCA = [
  "Parte del radar de tendencias y de los huecos de nuestro surtido.",
  "Busca en las listas de más vendidos de México: Amazon, Mercado Libre, farmacias y tiendas naturistas. Trae prueba de venta, liga y foto.",
  "Si lo pides, también revisa lo que venden 2 o más tiendas de la competencia en Google Shopping.",
  "Cada producto necesita una prueba de venta; la tendencia y los huecos solo lo respaldan.",
  "Quita lo que ya vendemos, lo que Compras ya rechazó y lo que descontinuamos.",
];

export default function Oportunidades() {
  const router = useRouter();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const evalua = puede("compras.productos.evaluar");
  const [estado, setEstado] = useState<EstadoOportunidades | null>(null);
  const [corridaId, setCorridaId] = useState<number | null>(null);
  const [corrida, setCorrida] = useState<CorridaOportunidadesDetalle | null>(null);
  const [competencia, setCompetencia] = useState(false);
  const [lanzando, setLanzando] = useState(false);
  const [ocupado, setOcupado] = useState<number | null>(null);
  const [verDescartadas, setVerDescartadas] = useState(false);
  const [verInstrucciones, setVerInstrucciones] = useState(false);

  const cargarEstado = useCallback(
    () => api<EstadoOportunidades>(R).then((x) => {
      setEstado(x);
      setCorridaId((actual) => actual ?? x.corridas[0]?.id ?? null);
    }).catch((e) => avisar(mensajeDe(e), "info")),
    [avisar],
  );
  const cargarCorrida = useCallback(
    () => corridaId ? api<CorridaOportunidadesDetalle>(`${R}/corridas/${corridaId}`).then(setCorrida).catch((e) => avisar(mensajeDe(e), "info")) : undefined,
    [corridaId, avisar],
  );

  useEffect(() => { cargarEstado(); }, [cargarEstado]);
  useEffect(() => { cargarCorrida(); }, [cargarCorrida]);

  // Mientras corre, se pregunta cada 3 segundos
  const enCurso = corrida?.estado === "en_curso";
  useEffect(() => {
    if (!enCurso) return;
    const t = setInterval(() => {
      cargarCorrida();
    }, 3000);
    return () => clearInterval(t);
  }, [enCurso, cargarCorrida]);
  useEffect(() => {
    if (corrida && !enCurso) cargarEstado();
  }, [corrida, enCurso, cargarEstado]);

  async function buscar() {
    setLanzando(true);
    try {
      const c = await api<CorridaOportunidadesDetalle>(R, { cuerpo: { competencia } });
      setCorrida(c);
      setCorridaId(c.id);
    } catch (e) {
      avisar(mensajeDe(e));
    } finally {
      setLanzando(false);
    }
  }

  async function evaluar(o: Oportunidad) {
    setOcupado(o.id);
    try {
      const r = await api<Oportunidad>(`${R}/${o.id}/evaluar`, { metodo: "POST" });
      if (r.evaluacion_id) router.push(`/compras/productos/${r.evaluacion_id}`);
    } catch (e) {
      avisar(mensajeDe(e));
      setOcupado(null);
    }
  }

  async function cambiar(o: Oportunidad, nuevo: "nueva" | "descartada") {
    setOcupado(o.id);
    try {
      const r = await api<Oportunidad>(`${R}/${o.id}`, { metodo: "PATCH", cuerpo: { estado: nuevo } });
      setCorrida((c) => c && { ...c, oportunidades: c.oportunidades.map((x) => (x.id === r.id ? r : x)) });
    } catch (e) {
      avisar(mensajeDe(e));
    } finally {
      setOcupado(null);
    }
  }

  const sinCompetencia = (estado?.falta_configurar.length ?? 0) > 0;
  const visibles = corrida?.oportunidades.filter((o) => verDescartadas || o.estado !== "descartada") ?? [];
  const descartadas = corrida?.oportunidades.filter((o) => o.estado === "descartada").length ?? 0;

  return (
    <>
      <Entrada className="mb-6">
        <p className="text-[15px] text-smn-gris-500"><span className="font-mono">TD001</span> · Compras</p>
        <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">Buscar oportunidades</h1>
        <p className="mt-2 max-w-2xl text-[16px] text-smn-gris-700">
          Productos que todavía no vendemos y que ya se venden en otros lados. Revisa cada uno y mándalo al semáforo con «Evaluar».
        </p>
        <details className="group mt-3 max-w-2xl text-[15px]">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 font-medium text-smn-gris-700 hover:text-tinta">
            ¿Cómo busca? <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-smn-gris-700">
            {COMO_BUSCA.map((t) => <li key={t}>{t}</li>)}
          </ul>
          <button type="button" onClick={() => setVerInstrucciones(true)} className="mt-2 inline-flex items-center gap-1.5 font-medium text-naranja-tinta hover:underline">
            <Bot className="h-4 w-4" /> Ver las instrucciones que sigue la IA
          </button>
        </details>
      </Entrada>
      <AnimatePresence>{verInstrucciones && <Instrucciones cerrar={() => setVerInstrucciones(false)} />}</AnimatePresence>

      {evalua && (
        <Entrada retraso={0.05} className="mb-8 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="text-lg font-semibold">Nueva búsqueda</h2>
          <div role="radiogroup" aria-label="Qué buscar" className="mt-3 grid gap-3 md:grid-cols-2">
            <Opcion
              elegida={!competencia || sinCompetencia}
              elegir={() => setCompetencia(false)}
              deshabilitada={enCurso}
              titulo="Más vendidos en México"
              texto="Amazon, Mercado Libre, farmacias y tiendas naturistas, guiado por las tendencias."
            />
            <Opcion
              elegida={competencia && !sinCompetencia}
              elegir={() => setCompetencia(true)}
              deshabilitada={enCurso || sinCompetencia}
              titulo="Más vendidos y competencia"
              texto={`Además, lo que venden 2 o más tiendas en Google Shopping (${estado?.busquedas_competencia ?? "—"} subcategorías).`}
              nota={
                sinCompetencia
                  ? `Falta en Configuración: ${estado?.falta_configurar.join(", ")}.`
                  : `Cuesta hasta US$ ${estado ? Number(estado.costo_maximo_competencia_usd).toFixed(2) : "—"} y cuenta para el tope del mes.`
              }
            />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Boton onClick={buscar} cargando={lanzando} disabled={enCurso}>
              <Sparkles className="h-4 w-4" /> Buscar oportunidades
            </Boton>
            {enCurso && <span className="text-[14px] text-smn-gris-700">Espera a que termine la búsqueda en curso.</span>}
          </div>
        </Entrada>
      )}

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Resultados</h2>
          {corrida && corrida.estado === "lista" && (
            <p className="mt-0.5 text-[14px] text-smn-gris-700">
              {corrida.oportunidades.length} {corrida.oportunidades.length === 1 ? "producto" : "productos"} · {fechaLocal(corrida.creada_en)}
              {corrida.competencia && " · con competencia"}
            </p>
          )}
        </div>
        {estado && estado.corridas.length > 1 && (
          <label className="flex items-center gap-2 text-[14px]">
            <span className="text-smn-gris-700">Búsquedas anteriores</span>
            <select
              value={corridaId ?? ""}
              onChange={(e) => setCorridaId(Number(e.target.value))}
              className="h-10 max-w-[70vw] rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[14px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
            >
              {estado.corridas.map((c) => (
                <option key={c.id} value={c.id}>
                  {fechaLocal(c.creada_en)} · {c.estado === "en_curso" ? "en curso" : c.estado === "fallida" ? "no terminó" : `${c.total} ${c.total === 1 ? "producto" : "productos"}`}
                  {c.competencia ? " · con competencia" : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {estado === null || (corridaId && !corrida) ? (
        <div className="space-y-2">
          <Esqueleto className="h-28" />
          <Esqueleto className="h-28" />
        </div>
      ) : !corrida ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-[15px] text-smn-gris-700">
          Todavía no se ha buscado. Elige qué buscar y pica «Buscar oportunidades».
        </p>
      ) : corrida.estado === "en_curso" ? (
        <Avance corrida={corrida} />
      ) : corrida.estado === "fallida" ? (
        <p className="rounded-2xl bg-aviso-fondo p-6 text-sm text-aviso-texto">{corrida.error}</p>
      ) : (
        <>
          <p className="mb-4 text-[14px] text-smn-gris-700">
            {Object.keys(corrida.fuentes).length > 0 && (
              <>De dónde salieron: {Object.entries(corrida.fuentes).map(([f, n]) => `${f} ${n}`).join(" · ")}. </>
            )}
            {corrida.con_ia ? "Redactado por la IA con estos datos" : "Sin IA: salen directo de los datos"}
            {corrida.competencia && ` · competencia US$ ${Number(corrida.costo_usd).toFixed(3)}`}
            {corrida.disparada_por && ` · buscó ${corrida.disparada_por}`}.
          </p>

          {corrida.notas.length > 0 && (
            <details open={!corrida.con_ia} className="mb-4 rounded-xl border border-smn-gris-100 bg-superficie px-4 py-3 text-[14px] text-smn-gris-700">
              <summary className="cursor-pointer font-medium text-tinta">Notas de la búsqueda ({corrida.notas.length})</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {corrida.notas.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </details>
          )}

          {visibles.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-[15px] text-smn-gris-700">
              No salieron productos con prueba de venta. Revisa las notas para ver qué faltó.
            </p>
          ) : (
            <ol className="space-y-3">
              {visibles.map((o) => (
                <li key={o.id} className={`flex flex-col gap-4 rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:flex-row ${o.estado === "descartada" ? "opacity-60" : ""}`}>
                  <Foto o={o} />
                  <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-[17px] font-semibold leading-snug">
                        <span className="mr-1.5 text-smn-gris-500">{o.orden}.</span>
                        {o.nombre}
                      </h3>
                      <p className="mt-1 inline-flex items-center gap-1.5 text-[13px] font-medium text-smn-gris-700">
                        <span className={`h-2 w-2 rounded-full ${PRIORIDAD[o.prioridad].punto}`} /> {PRIORIDAD[o.prioridad].texto}
                      </p>
                      <p className="mt-1 text-[14px] text-smn-gris-700">
                        {[o.marca, o.departamento, o.subcategoria, o.forma].filter(Boolean).join(" · ") || "Sin clasificar"}
                        {o.precio_visto && ` · precio visto ${pesos(o.precio_visto)}`}
                        {o.donde_se_vio && ` · ${o.donde_se_vio}`}
                      </p>
                    </div>
                    {evalua && (
                      <div className="flex shrink-0 gap-2">
                        {o.evaluacion_id ? (
                          <Link href={`/compras/productos/${o.evaluacion_id}`} className="inline-flex min-h-10 items-center gap-1 text-[15px] font-medium text-naranja-tinta hover:underline">
                            Ver semáforo <ChevronRight className="h-4 w-4" />
                          </Link>
                        ) : o.estado === "descartada" ? (
                          <Boton variante="fantasma" onClick={() => cambiar(o, "nueva")} cargando={ocupado === o.id}>
                            <RotateCcw className="h-4 w-4" /> Regresar
                          </Boton>
                        ) : (
                          <>
                            <Boton variante="fantasma" onClick={() => cambiar(o, "descartada")} disabled={ocupado === o.id}>
                              <Ban className="h-4 w-4" /> Descartar
                            </Boton>
                            <Boton onClick={() => evaluar(o)} cargando={ocupado === o.id}>Evaluar</Boton>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="mt-3 text-[15px]">{o.por_que}</p>
                  <ul className="mt-3 space-y-1 border-t border-smn-gris-100 pt-3 text-[14px] text-smn-gris-700">
                    {o.evidencia.map((x) => (
                      <li key={x.clave} className="flex gap-2">
                        <span className="shrink-0 font-semibold text-tinta">{x.fuente}:</span>
                        <span>{x.texto}</span>
                      </li>
                    ))}
                  </ul>
                  </div>
                </li>
              ))}
            </ol>
          )}

          {descartadas > 0 && (
            <button onClick={() => setVerDescartadas((v) => !v)} className="mt-4 text-[15px] font-medium text-smn-gris-700 hover:text-tinta">
              {verDescartadas ? "Ocultar descartadas" : `Ver descartadas (${descartadas})`}
            </button>
          )}
        </>
      )}
    </>
  );
}

function Foto({ o }: { o: Oportunidad }) {
  const [fallo, setFallo] = useState(false);
  if (!o.imagen || fallo)
    return (
      <div className="flex h-28 w-full shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-smn-gris-100 text-[13px] text-smn-gris-500 sm:w-28" title="Sin foto">
        <ImageOff className="h-6 w-6 text-smn-gris-500" /> Sin foto
      </div>
    );
  return (
    <figure className="w-full shrink-0 sm:w-28">
      {/* eslint-disable-next-line @next/next/no-img-element -- fotos externas de la página del producto o de Google */}
      <img src={o.imagen} alt={o.nombre} loading="lazy" referrerPolicy="no-referrer" onError={() => setFallo(true)} className="h-28 w-full rounded-xl border border-smn-gris-100 bg-white object-contain p-1" />
      {o.imagen_de && <figcaption className="mt-1 text-center text-[13px] leading-tight text-smn-gris-500">Foto: {o.imagen_de}</figcaption>}
    </figure>
  );
}

function Opcion({ elegida, elegir, deshabilitada, titulo, texto, nota }: {
  elegida: boolean; elegir: () => void; deshabilitada?: boolean; titulo: string; texto: string; nota?: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={elegida}
      disabled={deshabilitada}
      onClick={elegir}
      className={`flex gap-3 rounded-xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
        elegida ? "border-[var(--resalte)] ring-1 ring-[var(--resalte)]" : "border-smn-gris-100 hover:border-smn-gris-300"
      }`}
    >
      <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${elegida ? "border-[var(--resalte)] bg-[var(--resalte)] text-[var(--resalte-tinta)]" : "border-smn-gris-300"}`}>
        {elegida && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
      </span>
      <span className="min-w-0">
        <span className="block text-[15px] font-semibold">{titulo}</span>
        <span className="mt-0.5 block text-[14px] text-smn-gris-700">{texto}</span>
        {nota && <span className="mt-1.5 block text-[13px] text-smn-gris-500">{nota}</span>}
      </span>
    </button>
  );
}

function Avance({ corrida }: { corrida: CorridaOportunidadesDetalle }) {
  const pasos = PASOS.filter((p) => !p.competencia || corrida.competencia);
  const actual = pasos.findIndex((p) => corrida.paso?.startsWith(p.inicio));
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const seg = Math.max(0, Math.round((ahora - new Date(corrida.creada_en).getTime()) / 1000));
  return (
    <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-[16px] font-semibold">
          <Loader2 className="h-5 w-5 animate-spin text-smn-naranja" /> Buscando oportunidades
        </p>
        <span className="text-[14px] tabular-nums text-smn-gris-700">
          {Math.floor(seg / 60)}:{String(seg % 60).padStart(2, "0")} min
        </span>
      </div>
      <ol className="mt-4 space-y-2.5">
        {pasos.map((p, i) => {
          const hecho = actual > i;
          const ahoraVa = actual === i;
          return (
            <li key={p.inicio} className={`flex items-center gap-3 text-[15px] ${hecho || ahoraVa ? "text-tinta" : "text-smn-gris-500"}`}>
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${
                hecho ? "border-emerald-600 bg-emerald-600 text-white" : ahoraVa ? "border-smn-naranja" : "border-smn-gris-300"
              }`}>
                {hecho ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : ahoraVa ? <span className="h-2 w-2 rounded-full bg-smn-naranja" /> : null}
              </span>
              <span className={ahoraVa ? "font-semibold" : ""}>{ahoraVa && corrida.paso ? corrida.paso : p.texto}</span>
            </li>
          );
        })}
      </ol>
      {actual === -1 && corrida.paso && <p className="mt-3 text-[14px] text-smn-gris-700">{corrida.paso}…</p>}
      <p className="mt-4 text-[13px] text-smn-gris-500">Puedes salir de esta pantalla; la búsqueda sigue y aquí verás el resultado.</p>
    </div>
  );
}

type Instruccion = { paso: string; que_hace: string; texto: string };

// Lo que recibe la IA en cada paso, tal cual (Diego, 2026-11-03: «en donde puedo ver la descripción del agente?»)
function Instrucciones({ cerrar }: { cerrar: () => void }) {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Instruccion[] | null>(null);
  useEffect(() => {
    api<Instruccion[]>(`${R}/instrucciones`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  return (
    <Modal titulo="Instrucciones que sigue la IA" cerrar={cerrar} ancho="max-w-3xl">
      <p className="mb-4 text-sm text-smn-gris-700">
        Es el texto exacto que recibe la IA en cada paso. Además de esto recibe los datos de la búsqueda (tendencias, huecos, más vendidos y lo que Compras rechazó).
        Para cambiarlo, pídeselo a Transformación Digital.
      </p>
      {!lista ? (
        <Esqueleto className="h-60" />
      ) : (
        <div className="max-h-[65vh] space-y-5 overflow-y-auto pr-1">
          {lista.map((x) => (
            <section key={x.paso}>
              <h3 className="font-semibold">{x.paso}</h3>
              <p className="mb-2 text-sm text-smn-gris-700">{x.que_hace}</p>
              <div className="rounded-xl bg-smn-gris-50 p-4 text-[14px] leading-relaxed whitespace-pre-wrap text-tinta">{x.texto}</div>
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}
