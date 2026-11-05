"use client";
// Centro de datos y modelos: tablas reales de la base (registros, última carga y campos), cómo se conectan y los
// modelos que corren sobre ellas con sus últimas ejecuciones. Todo sale de /api/datos/centro.

import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Database, ExternalLink, Network, Search, Sigma, Table2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { CLASE_DOMINIO, ESTADO_CORRIDA, RUTA, type Centro, type Dominio, type Filas, type Modelo, type Tabla } from "@/lib/centro";
import { fechaDia } from "@/lib/etl";
import { Modal } from "@/componentes/modal";
import { VisorDatos } from "@/componentes/visor-datos";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";

const ANCHO = 160;
const ALTO = 104;
const SEMAFORO: Record<string, string> = { verde: "bg-green-600", amarillo: "bg-yellow-500", rojo: "bg-red-600" };
const numero = (n: number) => n.toLocaleString("es-MX");
// Las fechas sin hora (fecha de corte, semana) se muestran como día; las demás, con hora local
const cuando = (f: string | null) => (!f ? "Sin cargas" : f.length <= 10 ? fechaDia(f) : fechaLocal(f));

type Pestana = "mapa" | "fuentes" | "modelos";

export default function CentroDatos() {
  const [centro, setCentro] = useState<Centro | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("mapa");
  const [tabla, setTabla] = useState("producto");
  const [modelo, setModelo] = useState("semaforo");
  const [verDatos, setVerDatos] = useState<string | null>(null);

  useEffect(() => {
    api<Centro>(RUTA).then(setCentro).catch((e) => setError(mensajeDe(e)));
  }, []);

  const porId = useMemo(() => Object.fromEntries((centro?.tablas ?? []).map((t) => [t.id, t])), [centro]);

  if (error) return <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>;
  if (!centro) return <Esqueleto className="h-96" />;

  const pestanas: { id: Pestana; texto: string; icono: typeof Network; cuenta?: number }[] = [
    { id: "mapa", texto: "Mapa de datos", icono: Network },
    { id: "fuentes", texto: "Fuentes y cargas", icono: Database, cuenta: centro.tablas.length },
    { id: "modelos", texto: "Modelos", icono: Sigma, cuenta: centro.modelos.length },
  ];

  return (
    <>
      <Encabezado
        titulo="Centro de datos y modelos"
        descripcion="Qué datos tiene hoy la base de la plataforma, de dónde vienen, cómo se conectan y qué modelos corren sobre ellos."
      />

      <div role="tablist" className="mb-6 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-smn-gris-100">
        {pestanas.map(({ id, texto, icono: Icono, cuenta }) => (
          <button
            key={id}
            role="tab"
            aria-selected={pestana === id}
            onClick={() => setPestana(id)}
            className={`relative flex h-11 shrink-0 items-center gap-2 px-3.5 text-[15px] font-medium transition-colors ${
              pestana === id ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"
            }`}
          >
            <Icono className={`h-4 w-4 ${pestana === id ? "text-smn-naranja" : ""}`} />
            {texto}
            {cuenta !== undefined && <span className="rounded-full bg-smn-gris-100 px-2 text-[13px] text-smn-gris-700">{cuenta}</span>}
            {pestana === id && <motion.span layoutId="pestana-datos" className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-[var(--resalte)]" />}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={pestana} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          {pestana === "mapa" && (
            <Mapa
              centro={centro}
              porId={porId}
              seleccion={tabla}
              elegir={setTabla}
              abrirDatos={setVerDatos}
              irModelo={(id) => {
                setModelo(id);
                setPestana("modelos");
              }}
            />
          )}
          {pestana === "fuentes" && (
            <Fuentes
              centro={centro}
              abrirDatos={setVerDatos}
              verEnMapa={(id) => {
                setTabla(id);
                setPestana("mapa");
              }}
            />
          )}
          {pestana === "modelos" && <Modelos centro={centro} porId={porId} seleccion={modelo} elegir={setModelo} />}
        </motion.div>
      </AnimatePresence>

      <AnimatePresence>{verDatos && <VentanaDatos tabla={porId[verDatos]} cerrar={() => setVerDatos(null)} />}</AnimatePresence>
    </>
  );
}

function Punto({ dominio }: { dominio: Dominio }) {
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${CLASE_DOMINIO[dominio]}`} />;
}

function Pastilla({ t }: { t: Tabla }) {
  return t.estado === "cargado" ? (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-[12px] text-smn-gris-700">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Con datos
    </span>
  ) : (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-[12px] text-smn-gris-500">
      <span className="h-1.5 w-1.5 rounded-full border border-smn-gris-500" /> Vacía
    </span>
  );
}

function BotonVerDatos({ t, abrir, className = "" }: { t: Tabla; abrir: (id: string) => void; className?: string }) {
  return (
    <Boton className={className} onClick={() => abrir(t.id)} disabled={!t.ver_datos} title={t.ver_datos ? undefined : "Tiene RFC: se consulta desde Contraloría"}>
      <Table2 className="h-4 w-4" /> Ver datos
    </Boton>
  );
}

function Abrir({ ruta, texto = "Abrir", className = "" }: { ruta: string | null; texto?: string; className?: string }) {
  if (!ruta) return null;
  return (
    <Link
      href={ruta}
      className={`inline-flex items-center justify-center gap-2 rounded-xl border border-smn-gris-300 px-3 py-2 text-[13px] font-semibold hover:border-smn-naranja ${className}`}
    >
      <ExternalLink className="h-4 w-4" /> {texto}
    </Link>
  );
}

// Curva entre los bordes de dos tarjetas: horizontal si están lado a lado, vertical si están una sobre otra.
function curva(a: Tabla, b: Tabla) {
  const ac = { x: a.x + ANCHO / 2, y: a.y + ALTO / 2 };
  const bc = { x: b.x + ANCHO / 2, y: b.y + ALTO / 2 };
  if (Math.abs(ac.x - bc.x) > Math.abs(ac.y - bc.y) * 1.2) {
    const x1 = ac.x < bc.x ? a.x + ANCHO : a.x;
    const x2 = ac.x < bc.x ? b.x : b.x + ANCHO;
    const m = (x1 + x2) / 2;
    return `M${x1},${ac.y} C${m},${ac.y} ${m},${bc.y} ${x2},${bc.y}`;
  }
  const y1 = ac.y < bc.y ? a.y + ALTO : a.y;
  const y2 = ac.y < bc.y ? b.y : b.y + ALTO;
  const m = (y1 + y2) / 2;
  return `M${ac.x},${y1} C${ac.x},${m} ${bc.x},${m} ${bc.x},${y2}`;
}

function Mapa({
  centro,
  porId,
  seleccion,
  elegir,
  abrirDatos,
  irModelo,
}: {
  centro: Centro;
  porId: Record<string, Tabla>;
  seleccion: string;
  elegir: (id: string) => void;
  abrirDatos: (id: string) => void;
  irModelo: (id: string) => void;
}) {
  const dominios = Object.keys(centro.dominios) as Dominio[];
  const [buscar, setBuscar] = useState("");
  const [activos, setActivos] = useState<Set<Dominio>>(new Set(dominios));
  const q = buscar.trim().toLowerCase();
  const visible = (t: Tabla) =>
    activos.has(t.dominio) && (!q || t.nombre.toLowerCase().includes(q) || t.tabla.toLowerCase().includes(q) || t.campos.some(([c]) => c.includes(q)));
  const t = porId[seleccion] ?? centro.tablas[0];
  const ancho = Math.max(...centro.tablas.map((n) => n.x)) + ANCHO + 16;
  const alto = Math.max(...centro.tablas.map((n) => n.y)) + ALTO + 24;

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-[1_1_240px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            id="buscar-datos"
            type="search"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            placeholder="Buscar tabla o campo (p. ej. sku, proveedor)"
            className="h-10 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-sm outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
          />
        </label>
        {dominios.map((d) => (
          <button
            key={d}
            aria-pressed={activos.has(d)}
            onClick={() =>
              setActivos((s) => {
                const n = new Set(s);
                if (n.has(d)) n.delete(d);
                else n.add(d);
                return n;
              })
            }
            className={`flex h-9 items-center gap-1.5 rounded-full border border-smn-gris-100 bg-superficie px-3 text-[13px] transition-opacity hover:border-smn-gris-300 ${
              activos.has(d) ? "" : "opacity-40"
            }`}
          >
            <Punto dominio={d} /> {centro.dominios[d]}
          </button>
        ))}
      </div>

      <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie [background-image:radial-gradient(var(--color-smn-gris-100)_1px,transparent_1px)] [background-size:20px_20px]">
          <div className="relative" style={{ width: ancho, height: alto }}>
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
              {centro.relaciones.map(([a, b]) => {
                const on = a === t.id || b === t.id;
                const off = !visible(porId[a]) || !visible(porId[b]);
                return (
                  <motion.path
                    key={a + b}
                    d={curva(porId[a], porId[b])}
                    fill="none"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1, opacity: off ? 0.12 : on ? 1 : 0.7 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className={on ? "stroke-smn-naranja" : "stroke-smn-gris-300"}
                    strokeWidth={on ? 2.6 : 1.4}
                  />
                );
              })}
            </svg>
            {centro.tablas.map((n, i) => {
              const sel = n.id === t.id;
              return (
                <motion.button
                  key={n.id}
                  onClick={() => elegir(n.id)}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: visible(n) ? 1 : 0.25, y: 0 }}
                  whileHover={{ y: -2 }}
                  transition={{ duration: 0.25, delay: i * 0.02 }}
                  style={{ left: n.x, top: n.y, width: ANCHO, height: ALTO }}
                  className={`absolute flex flex-col rounded-lg border bg-superficie px-3 py-2.5 text-left transition-colors ${
                    sel ? "border-[var(--resalte)] ring-4 ring-[color-mix(in_srgb,var(--resalte)_20%,transparent)]" : "border-smn-gris-100 hover:border-smn-gris-300"
                  }`}
                >
                  <span className="flex items-center gap-1.5 truncate text-[11px] text-smn-gris-500">
                    <Punto dominio={n.dominio} /> {centro.dominios[n.dominio]}
                  </span>
                  <span className="mt-1 truncate text-[14px] leading-tight font-semibold">{n.nombre}</span>
                  <span className="mt-0.5 truncate font-mono text-[11px] text-smn-gris-500">{n.tabla}</span>
                  <span className="mt-auto flex items-center justify-between gap-2 text-[12px] text-smn-gris-700">
                    <span className="tabular-nums">{numero(n.registros)} reg.</span>
                    <Pastilla t={n} />
                  </span>
                </motion.button>
              );
            })}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.aside
            key={t.id}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 2xl:sticky 2xl:top-20"
          >
            <p className="flex items-center gap-1.5 text-[13px] font-medium text-smn-gris-500">
              <Punto dominio={t.dominio} /> {centro.dominios[t.dominio]}
            </p>
            <h2 className="mt-1 text-lg font-semibold">{t.nombre}</h2>
            <p className="font-mono text-[13px] text-smn-gris-500">{t.tabla}</p>
            <p className="mt-2 text-sm text-smn-gris-700">{t.descripcion}</p>
            <div className="mt-3 flex gap-2">
              <BotonVerDatos t={t} abrir={abrirDatos} className="flex-1" />
              <Abrir ruta={t.ruta} />
            </div>
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 rounded-lg border border-smn-gris-100 px-3 py-2.5 text-[13px]">
              <dt className="text-smn-gris-500">Estado</dt>
              <dd>
                <Pastilla t={t} />
              </dd>
              <dt className="text-smn-gris-500">Registros</dt>
              <dd className="font-medium tabular-nums">{numero(t.registros)}</dd>
              <dt className="text-smn-gris-500">Origen</dt>
              <dd>{t.origen}</dd>
              <dt className="text-smn-gris-500">Frecuencia</dt>
              <dd>{t.frecuencia}</dd>
              <dt className="text-smn-gris-500">Último dato</dt>
              <dd>{cuando(t.ultima_carga)}</dd>
            </dl>
            <Subtitulo>Campos</Subtitulo>
            <ul className="max-h-72 divide-y divide-smn-gris-100 overflow-y-auto border-y border-smn-gris-100">
              {t.campos.map(([c, tipo]) => (
                <li key={c} className="flex justify-between gap-2 py-1.5 text-[13px]">
                  <code className="font-mono text-[12px]">{c}</code>
                  <span
                    className={`text-right text-[13px] ${
                      tipo === "llave" || tipo.startsWith("→") ? "font-semibold text-naranja-tinta" : tipo === "oculto" ? "text-smn-gris-500" : "text-smn-gris-500"
                    }`}
                  >
                    {tipo === "oculto" ? "no se muestra" : tipo}
                  </span>
                </li>
              ))}
            </ul>
            <Subtitulo>Se conecta con</Subtitulo>
            <div className="flex flex-wrap gap-1.5">
              {centro.relaciones
                .filter((r) => r.includes(t.id))
                .map((r) => (r[0] === t.id ? r[1] : r[0]))
                .map((v) => (
                  <button key={v} onClick={() => elegir(v)} className="rounded-md border border-smn-gris-100 px-2.5 py-1 text-[13px] hover:border-smn-gris-300">
                    {porId[v].nombre}
                  </button>
                ))}
            </div>
            <Subtitulo>Modelos que la usan</Subtitulo>
            <div className="flex flex-wrap gap-1.5">
              {centro.modelos
                .filter((m) => m.usa.includes(t.id))
                .map((m) => (
                  <button key={m.id} onClick={() => irModelo(m.id)} className="rounded-md bg-smn-gris-50 px-2.5 py-1 text-[13px] text-smn-gris-700 hover:bg-smn-gris-100 hover:text-tinta">
                    {m.nombre}
                  </button>
                ))}
              {!centro.modelos.some((m) => m.usa.includes(t.id)) && <span className="text-[13px] text-smn-gris-500">Ninguno todavía</span>}
            </div>
          </motion.aside>
        </AnimatePresence>
      </div>
    </>
  );
}

function Subtitulo({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 mb-1.5 text-[13px] font-medium text-smn-gris-500">{children}</p>;
}

function Fuentes({ centro, verEnMapa, abrirDatos }: { centro: Centro; verEnMapa: (id: string) => void; abrirDatos: (id: string) => void }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {centro.tablas.map((t, i) => (
        <Entrada key={t.id} retraso={i * 0.02}>
          <article className="flex h-full flex-col gap-2 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
            <h3 className="flex items-center gap-2 font-semibold">
              <Punto dominio={t.dominio} /> {t.nombre}
              <span className="ml-auto">
                <Pastilla t={t} />
              </span>
            </h3>
            <p className="text-sm text-smn-gris-500">{t.descripcion}</p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">
              {[
                ["Registros", numero(t.registros)],
                ["Origen", t.origen],
                ["Frecuencia", t.frecuencia],
                ["Último dato", cuando(t.ultima_carga)],
              ].map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-smn-gris-500">{k}</dt>
                  <dd className="text-right font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-auto flex flex-wrap gap-2 pt-2">
              <BotonVerDatos t={t} abrir={abrirDatos} className="px-3 py-2 text-[13px]" />
              <Abrir ruta={t.ruta} />
              <Boton variante="fantasma" className="px-3 py-2 text-[13px]" onClick={() => verEnMapa(t.id)}>
                Ver en el mapa
              </Boton>
            </div>
          </article>
        </Entrada>
      ))}
    </div>
  );
}

function Modelos({ centro, porId, seleccion, elegir }: { centro: Centro; porId: Record<string, Tabla>; seleccion: string; elegir: (id: string) => void }) {
  const m: Modelo = centro.modelos.find((x) => x.id === seleccion) ?? centro.modelos[0];
  const vacias = m.usa.filter((u) => porId[u]?.estado !== "cargado").map((u) => porId[u].nombre);
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <div className="flex flex-col gap-2.5">
        {centro.modelos.map((x) => (
          <motion.button
            key={x.id}
            onClick={() => elegir(x.id)}
            whileHover={{ x: 2 }}
            className={`grid grid-cols-[40px_1fr_auto] items-center gap-3 rounded-2xl border-[1.5px] bg-superficie px-3.5 py-3 text-left ${
              x.id === m.id ? "border-smn-naranja" : "border-smn-gris-100"
            }`}
          >
            <span className="grid h-10 w-10 place-items-center rounded-lg border border-smn-gris-100 bg-superficie font-mono text-[13px] font-semibold text-smn-naranja">{x.sigla}</span>
            <span className="min-w-0">
              <strong className="block truncate font-semibold">{x.nombre}</strong>
              <small className="text-smn-gris-500">
                {x.tipo} · {x.iniciativa}
              </small>
            </span>
            <Insignia
              className={
                x.estado === "Activo"
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                  : x.estado === "Idea"
                    ? "bg-smn-gris-100 text-smn-gris-500"
                    : "bg-aviso-fondo text-aviso-texto"
              }
            >
              {x.estado}
            </Insignia>
          </motion.button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.section
          key={m.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="min-w-0 rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5"
        >
          <h2 className="text-xl font-semibold">{m.nombre}</h2>
          <p className="text-sm text-smn-gris-500">
            {m.tipo} · {m.iniciativa} · {m.estado}
          </p>
          <p className="mt-2 max-w-prose text-sm text-smn-gris-700">{m.descripcion}</p>

          <div className="my-4 flex flex-col items-stretch gap-2 sm:flex-row">
            {[
              ["Entra", m.usa.map((u) => porId[u].nombre).join(", ")],
              ["Corre en", m.motor],
              ["Sale", m.salida],
            ].map(([k, v], i) => (
              <div key={k} className="contents">
                {i > 0 && <ArrowRight className="h-4 w-4 shrink-0 rotate-90 self-center text-smn-naranja sm:rotate-0" />}
                <div className="min-w-0 flex-1 rounded-xl bg-smn-gris-50 px-3 py-2.5 text-sm">
                  <p className="text-[13px] font-medium text-smn-gris-500">{k}</p>
                  <p className="font-semibold">{v}</p>
                </div>
              </div>
            ))}
          </div>

          <Subtitulo>Últimas ejecuciones</Subtitulo>
          {m.ejecuciones.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[13px] text-smn-gris-500">
                    <th className="py-2 pr-3">Fecha</th>
                    <th className="py-2 pr-3">Caso</th>
                    {m.id === "semaforo" && <th className="py-2 pr-3">Puntaje</th>}
                    <th className="py-2">Resultado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-smn-gris-100">
                  {m.ejecuciones.map((e, i) => (
                    <tr key={i} className="whitespace-nowrap">
                      <td className="py-2 pr-3">{e.fecha ? fechaLocal(e.fecha) : "Sin fecha"}</td>
                      <td className="py-2 pr-3">{e.caso}</td>
                      {m.id === "semaforo" && <td className="py-2 pr-3 font-mono tabular-nums">{e.calificacion ?? "Sin puntaje"}</td>}
                      <td className="py-2">
                        {e.color ? (
                          <span className="inline-flex items-center gap-1.5 font-semibold capitalize">
                            <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[e.color] ?? "bg-smn-gris-300"}`} /> {e.color}
                          </span>
                        ) : (
                          <span className="font-semibold">{ESTADO_CORRIDA[e.estado ?? ""] ?? e.estado ?? "Sin estado"}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="rounded-xl bg-smn-gris-50 px-4 py-3 text-center text-sm text-smn-gris-500">
              {m.ruta ? "Todavía no se ha corrido." : "Todavía no está construido."}
              {vacias.length ? ` Tablas que usa y siguen vacías: ${vacias.join(", ")}.` : ""}
            </p>
          )}
          {m.ruta && (
            <div className="mt-4">
              <Abrir ruta={m.ruta} texto="Ir al módulo para correrlo" />
            </div>
          )}
        </motion.section>
      </AnimatePresence>
    </div>
  );
}

function VentanaDatos({ tabla: t, cerrar }: { tabla: Tabla; cerrar: () => void }) {
  const [datos, setDatos] = useState<Filas | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Filas>(`${RUTA}/tablas/${t.id}/filas`).then(setDatos).catch((e) => setError(mensajeDe(e)));
  }, [t.id]);
  return (
    <Modal titulo={t.nombre} cerrar={cerrar} ancho="sm:max-w-5xl">
      <div className="-mt-3 mb-4 flex flex-wrap items-center gap-2 text-sm text-smn-gris-500">
        <span className="font-mono text-[13px]">{t.tabla}</span>
        <Pastilla t={t} />
        <span>
          {numero(t.registros)} registros · Origen: {t.origen} · Último dato: {cuando(t.ultima_carga)}
        </span>
      </div>
      {error ? (
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>
      ) : !datos ? (
        <Esqueleto className="h-64" />
      ) : (
        <>
          <VisorDatos
            columnas={datos.columnas}
            filas={datos.filas}
            vacio={
              <>
                <p className="font-semibold text-tinta">Esta tabla todavía no tiene datos.</p>
                <p className="mt-1">Se llena desde: {t.origen}.</p>
              </>
            }
          />
          {t.registros > datos.filas.length && datos.filas.length > 0 && (
            <p className="mt-2 text-[13px] text-smn-gris-500">
              Se muestran los {numero(datos.filas.length)} registros más recientes de {numero(t.registros)}. No se muestran RFC, correos, teléfonos ni quién capturó.
            </p>
          )}
        </>
      )}
    </Modal>
  );
}
