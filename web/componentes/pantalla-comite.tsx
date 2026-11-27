"use client";
// Pantalla del comité de producto nuevo (plan aprobado por Diego el 20 nov 2026; bocetos de 4 niveles).
// Nivel 1 ¿cómo salió? (foto, semáforo con anillo de aporte, 4 donas y cifras) → Nivel 2 ¿por qué? (por factor) →
// Nivel 3 ¿cómo se calculó? → Nivel 4 ¿con qué datos? (parecidos con foto; al picar uno se abre su ventana).
// Esc regresa un nivel. Todo sale de la API (pantalla_comite.py): aquí no se calcula nada que cambie la decisión.

import { Imagen as ImagenSegura } from "@/componentes/imagen";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowUpRight, ChevronRight, ImageOff, Loader2, X } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, mensajeDe, urlApi } from "@/lib/api";
import type { Color } from "@/lib/precios";
import {
  colorPuntaje,
  hexDe,
  miles,
  num,
  pesos,
  siglas,
  type Escenario,
  type FactorClave,
  type FactorPantalla,
  type MitadPrecio,
  type Pantalla,
  type ParecidoPantalla,
  type Titular,
} from "@/lib/pantalla";

type Vista = { n: 1 } | { n: 2 | 3 | 4; f: FactorClave };

// Cualquier producto que menciona la pantalla se puede picar y abre su panel al lado (Diego, 22 nov 2026)
const AbrirProducto = createContext<(sku: string) => void>(() => {});

const TEXTO_COLOR: Record<Color, string> = { verde: "text-green-700 dark:text-green-400", amarillo: "text-yellow-700 dark:text-yellow-400", rojo: "text-red-700 dark:text-red-400" };
const PILDORA: Record<Color, string> = {
  verde: "bg-green-600/10 text-green-700 ring-green-600/30 dark:text-green-400",
  amarillo: "bg-yellow-500/15 text-yellow-800 ring-yellow-500/40 dark:text-yellow-300",
  rojo: "bg-red-600/10 text-red-700 ring-red-600/30 dark:text-red-400",
};
const NIVEL3: Record<FactorClave, string> = { demanda: "Cómo se calculó", categoria: "Cómo se calculó", rentabilidad: "Cómo se calculó", precio: "Cómo se calculó", precio_anaquel: "Cómo se calculó", precio_afuera: "Cómo se calculó" };

/** La sección de la pantalla de un tema; los dos del Precio caen al Precio junto si la evaluación es de antes. */
function seccion(p: Pantalla, f: FactorClave) {
  return f === "precio_anaquel" || f === "precio_afuera" ? (p[f] ?? p.precio) : p[f];
}

// 4 temas (evaluaciones de antes) o 5 (el Precio en dos, 25 nov 2026)
const COLUMNAS: Record<number, string> = { 4: "@6xl:grid-cols-4", 5: "@6xl:grid-cols-5" };
const TIRA: Record<number, string> = { 4: "@5xl:grid-cols-4", 5: "@5xl:grid-cols-5" };

function colorVeredicto(v: string): Color {
  const t = v.toLowerCase();
  if (t.startsWith("no meter")) return "rojo";
  if (t.startsWith("meter")) return "verde";
  return "amarillo";
}

/** Carga la pantalla de un producto y la muestra con sus 4 niveles. */
// Pantallas ya pedidas en esta pestaña: regresar o avanzar en la presentación no vuelve a esperar a la API
const pedidas = new Map<string, Promise<Pantalla>>();
function cargarPantalla(ruta: string): Promise<Pantalla> {
  let p = pedidas.get(ruta);
  if (!p) {
    p = api<Pantalla>(ruta);
    p.catch(() => pedidas.delete(ruta));
    pedidas.set(ruta, p);
  }
  return p;
}

/** Pide por adelantado, una tras otra, las pantallas de la presentación para que cada diapositiva abra al momento. */
export async function precargarPantallas(rutas: string[]) {
  for (const ruta of rutas) {
    try {
      await cargarPantalla(ruta);
    } catch {
      /* si una falla, la diapositiva lo dirá al abrirla */
    }
  }
}

export function PantallaComite({ ruta, foto, nombre, inicio = "Comité de producto nuevo", recalcular }: { ruta: string; foto?: ReactNode; nombre?: string; inicio?: string; recalcular?: ReactNode }) {
  const [p, setP] = useState<Pantalla | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lento, setLento] = useState(false);
  const [intento, setIntento] = useState(0);
  useEffect(() => {
    let vivo = true;
    setP(null);
    setError(null);
    setLento(false);
    const reloj = setTimeout(() => vivo && setLento(true), 20000);
    cargarPantalla(ruta)
      .then((d) => vivo && setP(d))
      .catch((e) => vivo && setError(mensajeDe(e)))
      .finally(() => clearTimeout(reloj));
    return () => {
      vivo = false;
      clearTimeout(reloj);
    };
  }, [ruta, intento]);
  if (error || (!p && lento))
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-smn-gris-100 p-6 text-lg text-smn-gris-500">
        <p>{error ? `No se pudo cargar la pantalla: ${error}` : "La pantalla está tardando más de lo normal."}</p>
        <button
          type="button"
          onClick={() => setIntento((n) => n + 1)}
          className="rounded-lg border border-smn-gris-200 px-4 py-2 text-base font-medium text-tinta hover:bg-smn-gris-50"
        >
          Volver a intentar
        </button>
      </div>
    );
  if (!p) return <Esqueleto nombre={nombre} foto={foto} />;
  return <Niveles p={p} foto={foto} inicio={inicio} recalcular={recalcular} />;
}

// Mientras llega la pantalla se ve que el sistema está trabajando (Diego, 22 nov 2026): foto del producto si ya la
// tenemos, su nombre, un círculo que gira y los segundos que lleva
function Esqueleto({ nombre, foto }: { nombre?: string; foto?: ReactNode }) {
  const [seg, setSeg] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeg((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="@container"><div className="grid items-center gap-6 @4xl:grid-cols-[minmax(0,0.9fr)_minmax(0,0.9fr)_minmax(0,1.6fr)]" role="status" aria-live="polite">
      <div className="mx-auto aspect-square w-full max-w-[min(100%,34vh)] overflow-hidden rounded-3xl bg-smn-gris-50">{foto}</div>
      <div className="mx-auto grid aspect-square w-full max-w-[min(100%,34vh)] place-items-center">
        <Loader2 className="h-24 w-24 text-smn-naranja motion-safe:animate-spin" strokeWidth={1.5} aria-hidden />
      </div>
      <div className="min-w-0">
        {nombre && <p className="line-clamp-2 text-3xl leading-tight font-semibold tracking-tight">{nombre}</p>}
        <p className="mt-3 text-xl text-tinta">Preparando la evaluación…</p>
        <p className="mt-1 text-[17px] text-smn-gris-500">Juntando la venta en tiendas, los parecidos y el pronóstico{seg >= 2 ? ` · ${seg} s` : ""}</p>
        <div className="mt-6 space-y-3 motion-safe:animate-pulse">
          <div className="h-6 w-2/3 rounded-lg bg-smn-gris-50" />
          <div className="h-6 w-1/2 rounded-lg bg-smn-gris-50" />
          <div className="h-24 rounded-2xl bg-smn-gris-50" />
        </div>
      </div>
    </div></div>
  );
}

export function Niveles({ p, foto, inicio, recalcular }: { p: Pantalla; foto?: ReactNode; inicio: string; recalcular?: ReactNode }) {
  const [vista, setVista] = useState<Vista>({ n: 1 });
  const [abierto, setAbierto] = useState<ParecidoPantalla | null>(null);
  const abrirSku = useCallback(
    (sku: string) => {
      const x = p.catalogo?.[sku] ?? p.parecidos.find((y) => y.sku === sku);
      if (x) setAbierto(x);
    },
    [p],
  );
  const quieto = useReducedMotion();
  const atras = useCallback(() => {
    if (abierto) return setAbierto(null);
    setVista((v) => (v.n === 1 ? v : v.n === 2 ? { n: 1 } : { n: (v.n - 1) as 2 | 3, f: v.f }));
  }, [abierto]);

  // Esc regresa un nivel antes de que la presentación lo use para salir
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || (vista.n === 1 && !abierto)) return;
      e.stopImmediatePropagation();
      e.preventDefault();
      atras();
    };
    window.addEventListener("keydown", tecla, { capture: true });
    return () => window.removeEventListener("keydown", tecla, { capture: true });
  }, [vista, abierto, atras]);

  // 25 nov 2026 (Diego): al picar un tema la vista se quedaba abajo; cada cambio de nivel sube al inicio de la pantalla
  const arriba = useRef<HTMLDivElement>(null);
  const primera = useRef(true);
  useEffect(() => {
    if (primera.current) {
      primera.current = false;
      return;
    }
    const el = arriba.current;
    if (el && el.getBoundingClientRect().top < 80) el.scrollIntoView({ behavior: quieto ? "auto" : "smooth", block: "start" });
  }, [vista, quieto]);

  const nombre = [p.producto.nombre, p.producto.marca?.toUpperCase()].filter(Boolean).join(" · ");
  const factor = vista.n === 1 ? null : p.factores.find((f) => f.factor === vista.f)!;
  const migas: { texto: string; ir?: () => void }[] = [{ texto: inicio }, { texto: nombre, ir: vista.n > 1 ? () => setVista({ n: 1 }) : undefined }];
  if (vista.n > 1 && factor) migas.push({ texto: factor.nombre, ir: vista.n > 2 ? () => setVista({ n: 2, f: factor.factor }) : undefined });
  if (vista.n > 2 && factor) migas.push({ texto: NIVEL3[factor.factor], ir: vista.n > 3 ? () => setVista({ n: 3, f: factor.factor }) : undefined });
  if (vista.n > 3) migas.push({ texto: "Con qué datos" });

  return (
    <AbrirProducto.Provider value={abrirSku}>
    <div ref={arriba} className="@container scroll-mt-20 text-tinta">
      {/* en el nivel 1 la ruta sobra (el nombre ya está en grande) y quita espacio para que todo quepa sin bajar */}
      <div className={`mb-6 flex-wrap items-center gap-3 ${vista.n > 1 ? "flex" : "hidden"}`}>
        <nav aria-label="Niveles" className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 text-[15px] text-smn-gris-500">
          {migas.map((m, k) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              {k > 0 && <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
              {m.ir ? (
                <button type="button" onClick={m.ir} className="hover:text-tinta hover:underline">{m.texto}</button>
              ) : (
                <span className={k === migas.length - 1 ? "font-semibold text-tinta" : ""}>{m.texto}</span>
              )}
            </span>
          ))}
        </nav>
        {vista.n > 1 && (
          <button type="button" onClick={atras} className="rounded-xl border border-smn-gris-100 px-3 py-1.5 text-sm text-smn-gris-700 hover:bg-smn-gris-50">
            Esc · Regresar
          </button>
        )}
      </div>
      {!p.pesos_direccion && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-aviso-fondo px-4 py-2 text-[15px] text-aviso-texto">
          <p>Esta evaluación se calculó con los pesos anteriores. Recalcúlala para usar los de Dirección (Demanda 50, Categoría 25, Rentabilidad 12.5 y Precio 12.5).</p>
          {recalcular}
        </div>
      )}
      {p.venta_al && (
        <p className="mb-5 text-[15px] text-smn-gris-500">Con la venta al {p.venta_al}. Ya llegó venta más reciente y se está actualizando; vuelve a abrirla en un momento.</p>
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={vista.n === 1 ? "1" : `${vista.n}-${vista.f}`}
          initial={quieto ? { opacity: 0 } : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        >
          {vista.n === 1 ? (
            <Nivel1 p={p} foto={foto} abrir={(f) => setVista({ n: 2, f })} />
          ) : vista.n === 2 ? (
            <Nivel2 p={p} f={factor!} ir={setVista} />
          ) : vista.n === 3 ? (
            <Nivel3 p={p} f={factor!} ir={setVista} />
          ) : (
            <Nivel4 p={p} f={factor!} abrir={setAbierto} />
          )}
        </motion.div>
      </AnimatePresence>
      <Fuente p={p} />
      <AnimatePresence>{abierto && <VentanaParecido x={abierto} p={p} cerrar={() => setAbierto(null)} />}</AnimatePresence>
    </div>
    </AbrirProducto.Provider>
  );
}

function Fuente({ p }: { p: Pantalla }) {
  if (!p.fuentes.length) return null;
  return <p className="mt-10 text-xs text-smn-gris-500">Fuente: {p.fuentes.join(" · ")}</p>;
}

// ---------------------------------------------------------------- gráficas

/** Anillo de aporte: cada factor ocupa lo que aporta a la calificación, con el color de su calificación. */
function AnilloAporte({ p, tam = 400 }: { p: Pantalla; tam?: number | string }) {
  const quieto = useReducedMotion();
  const r = 180;
  const largo = 2 * Math.PI * r;
  const con = p.factores.filter((f) => f.aporte != null && f.aporte > 0);
  const hueco = con.length > 1 ? 6 : 0;
  let inicio = 0;
  const color = p.color ?? colorPuntaje(p.puntaje);
  return (
    <div className="relative mx-auto w-full" style={{ maxWidth: tam }}>
      <svg viewBox="0 0 400 400" className="w-full" role="img" aria-label={`Calificación ${p.puntaje ?? "sin dato"} de 100`}>
        <circle cx="200" cy="200" r={r} fill="none" strokeWidth="30" className="stroke-smn-gris-100" />
        {con.map((f) => {
          const seg = Math.max(0, ((f.aporte ?? 0) / 100) * largo - hueco);
          const el = (
            <motion.circle
              key={f.factor}
              cx="200"
              cy="200"
              r={r}
              fill="none"
              strokeWidth="30"
              stroke={hexDe(f.color)}
              strokeDasharray={`${seg} ${largo}`}
              transform={`rotate(${-90 + (inicio / largo) * 360} 200 200)`}
              initial={quieto ? false : { strokeDasharray: `0 ${largo}` }}
              animate={{ strokeDasharray: `${seg} ${largo}` }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            >
              <title>{`${f.nombre}: aporta ${num(f.aporte)} de ${num(f.de)} puntos`}</title>
            </motion.circle>
          );
          inicio += seg + hueco;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[clamp(48px,8vh,104px)] leading-none font-semibold tracking-tight tabular-nums">{p.puntaje ?? "—"}</span>
        <span className="mt-1 text-lg text-smn-gris-500">de 100</span>
        {color && <span className={`mt-3 rounded-full px-4 py-1 text-sm font-semibold tracking-wide uppercase ring-1 ${PILDORA[color]}`}>{color}</span>}
      </div>
    </div>
  );
}

/** Dona del factor: el anillo de afuera es lo que pesa; el de adentro, su calificación; la marca es el corte de verde (80). */
function Dona({ f, tam = 200 }: { f: FactorPantalla; tam?: number }) {
  const quieto = useReducedMotion();
  const R1 = 92, R2 = 74;
  const l1 = 2 * Math.PI * R1, l2 = 2 * Math.PI * R2;
  const peso = (f.peso / 100) * l1;
  const cal = ((f.puntaje ?? 0) / 100) * l2;
  const a = (80 / 100) * 2 * Math.PI - Math.PI / 2;
  return (
    <div className="relative mx-auto" style={{ width: tam, height: tam }}>
      <svg viewBox="0 0 200 200" className="h-full w-full" aria-hidden>
        <circle cx="100" cy="100" r={R1} fill="none" strokeWidth="4" className="stroke-smn-gris-100" />
        <circle cx="100" cy="100" r={R1} fill="none" strokeWidth="4" className="stroke-smn-gris-500" strokeDasharray={`${peso} ${l1}`} transform="rotate(-90 100 100)" strokeLinecap="round" />
        <circle cx="100" cy="100" r={R2} fill="none" strokeWidth="18" className="stroke-smn-gris-100" />
        {f.puntaje != null && (
          <motion.circle
            cx="100"
            cy="100"
            r={R2}
            fill="none"
            strokeWidth="18"
            stroke={hexDe(f.color)}
            strokeLinecap="round"
            transform="rotate(-90 100 100)"
            initial={quieto ? false : { strokeDasharray: `0 ${l2}` }}
            animate={{ strokeDasharray: `${cal} ${l2}` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        )}
        <line x1={100 + (R2 - 14) * Math.cos(a)} y1={100 + (R2 - 14) * Math.sin(a)} x2={100 + (R2 + 14) * Math.cos(a)} y2={100 + (R2 + 14) * Math.sin(a)} className="stroke-tinta" strokeWidth="2" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-5xl leading-none font-semibold tabular-nums" style={{ fontSize: tam * 0.24 }}>{f.puntaje ?? "—"}</span>
        <span className="mt-1 text-sm text-smn-gris-500">{f.puntaje == null ? "sin datos" : "de 100"}</span>
      </div>
    </div>
  );
}

function MiniDona({ f }: { f: FactorPantalla }) {
  const r = 20, l = 2 * Math.PI * r;
  return (
    <span className="relative inline-grid h-12 w-12 shrink-0 place-items-center">
      <svg viewBox="0 0 50 50" className="absolute inset-0" aria-hidden>
        <circle cx="25" cy="25" r={r} fill="none" strokeWidth="5" className="stroke-smn-gris-100" />
        <circle cx="25" cy="25" r={r} fill="none" strokeWidth="5" stroke={hexDe(f.color)} strokeDasharray={`${((f.puntaje ?? 0) / 100) * l} ${l}`} transform="rotate(-90 25 25)" strokeLinecap="round" />
      </svg>
      <span className="text-sm font-semibold tabular-nums">{f.puntaje ?? "—"}</span>
    </span>
  );
}

/** Venta acumulada en 3 meses: banda de pesimista a optimista y la línea del esperado. */
function Abanico({ e }: { e: Escenario[] }) {
  const [pes, esp, opt] = e;
  if (!esp || esp.acumulado.some((x) => x == null)) return null;
  const W = 520, H = 220, izq = 70, der = 90, arr = 16, aba = 34;
  const max = Math.max(...opt.acumulado.map((x) => x ?? 0)) * 1.08 || 1;
  const x = (i: number) => izq + (i / 3) * (W - izq - der);
  const y = (v: number) => arr + (1 - v / max) * (H - arr - aba);
  const pts = (s: Escenario) => [0, ...s.acumulado.map((v) => v ?? 0)].map((v, i) => [x(i), y(v)] as const);
  const banda = [...pts(opt), ...pts(pes).reverse()].map(([a, b]) => `${a},${b}`).join(" ");
  const linea = pts(esp).map(([a, b]) => `${a},${b}`).join(" ");
  const marcas = [0, max / 3, (2 * max) / 3, max].map((v) => Math.round(v / 10000) * 10000);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="max-h-[300px] w-full" role="img" aria-label="Venta acumulada en sus primeros 3 meses">
      {marcas.map((m) => (
        <g key={m}>
          <line x1={izq} x2={W - der} y1={y(m)} y2={y(m)} className="stroke-smn-gris-100" />
          <text x={izq - 8} y={y(m) + 4} textAnchor="end" className="fill-smn-gris-500 text-[11px]">{miles(m)}</text>
        </g>
      ))}
      <polygon points={banda} className="fill-smn-gris-100" />
      <polyline points={linea} fill="none" className="stroke-tinta" strokeWidth="2.5" />
      {[1, 2, 3].map((i) => (
        <text key={i} x={x(i)} y={H - 10} textAnchor="middle" className="fill-smn-gris-500 text-[11px]">Mes {i}</text>
      ))}
      {[opt, esp, pes].map((s) => (
        <text key={s.clave} x={W - der + 8} y={y(s.acumulado[2] ?? 0) + 4} className={`text-[11px] ${s.clave === "esperado" ? "fill-tinta font-semibold" : "fill-smn-gris-500"}`}>
          {miles(s.acumulado[2])}
        </text>
      ))}
    </svg>
  );
}

/** Barras horizontales sencillas, con una línea opcional (el pronóstico del producto nuevo). */
function Barras({ filas, formato, linea, lineaTexto }: { filas: { nombre: string; valor: number; resaltar?: "nuevo" | "cuenta" | "afuera" | null }[]; formato: (v: number) => string; linea?: number | null; lineaTexto?: string }) {
  const max = Math.max(...filas.map((f) => f.valor), linea ?? 0) || 1;
  return (
    <div className="space-y-2.5">
      {filas.map((f, k) => (
        <div key={k} className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-sm">
          <span className="truncate text-right text-smn-gris-700" title={f.nombre}>{f.nombre}</span>
          <span className="relative flex items-center gap-2">
            <motion.span
              initial={{ width: 0 }}
              animate={{ width: `${(f.valor / max) * 78}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className={`h-6 rounded-md ${f.resaltar === "nuevo" ? "bg-tinta" : f.resaltar === "cuenta" ? "bg-green-600" : f.resaltar === "afuera" ? "bg-smn-gris-500" : "bg-smn-gris-300"}`}
            />
            <span className="whitespace-nowrap tabular-nums">{formato(f.valor)}</span>
            {linea != null && <span className="absolute inset-y-[-6px] w-0 border-l-2 border-dashed border-red-600" style={{ left: `${(linea / max) * 78}%` }} />}
          </span>
        </div>
      ))}
      {linea != null && lineaTexto && <p className="pl-[calc(9rem+12px)] text-xs font-semibold text-red-700 dark:text-red-400">{lineaTexto}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- piezas

function Tarjeta({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`min-w-0 rounded-3xl border border-smn-gris-100 bg-superficie p-5 sm:p-6 ${className}`}>{children}</section>;
}

function Etiqueta({ children }: { children: ReactNode }) {
  return <h3 className="text-sm font-semibold tracking-wider text-smn-gris-500 uppercase">{children}</h3>;
}

function Cifra({ titulo, valor, sub, chica }: { titulo: string; valor: ReactNode; sub?: ReactNode; chica?: boolean }) {
  return (
    <div>
      <p className="text-sm text-smn-gris-500">{titulo}</p>
      <p className={`mt-0.5 font-semibold tracking-tight tabular-nums ${chica ? "text-2xl" : "text-3xl sm:text-4xl"}`}>{valor}</p>
      {sub && <p className="mt-0.5 text-sm text-smn-gris-500">{sub}</p>}
    </div>
  );
}

function FotoProducto({ p, foto }: { p: Pantalla; foto?: ReactNode }) {
  const [n, setN] = useState(0);
  const [rota, setRota] = useState(false);
  // la foto se limita por la altura para que el nivel 1 quepa sin bajar (Diego, 22 nov 2026)
  if (foto) return <div className="mx-auto aspect-square w-full max-w-[min(100%,34vh)] overflow-hidden rounded-3xl bg-smn-gris-50">{foto}</div>;
  const src = p.producto.fotos[n];
  const marca = (p.producto.marca ?? siglas(p.producto.nombre)).toUpperCase();
  // Sin foto: en el celular basta un renglón; el recuadro grande empujaba el contenido 300 px hacia abajo
  if (!src || (rota && p.producto.fotos.length < 2))
    return (
      <>
        <div className="flex h-14 items-center gap-3 rounded-2xl bg-smn-gris-50 px-4 text-smn-gris-500 sm:hidden">
          <ImageOff className="h-5 w-5" aria-hidden />
          <span className="text-sm"><b className="font-semibold tracking-[0.15em]">{marca}</b> · Sin foto</span>
        </div>
        <div className="mx-auto hidden aspect-square w-full max-w-[min(100%,34vh)] place-items-center rounded-3xl bg-smn-gris-50 text-center text-smn-gris-500 sm:grid">
          <span>
            <span className="block text-3xl font-semibold tracking-[0.2em]">{marca}</span>
            <span className="mt-2 block text-sm">Sin foto</span>
          </span>
        </div>
      </>
    );
  return (
    <div className="mx-auto w-full max-w-[min(100%,34vh)] space-y-2">
      <div className="grid aspect-square place-items-center overflow-hidden rounded-3xl bg-smn-gris-50">
        {src && !rota ? (
          // eslint-disable-next-line @next/next/no-img-element -- la foto sale de la API con la sesión
          <img src={`${urlApi()}${src}`} alt={p.producto.nombre} onError={() => setRota(true)} className="h-full w-full object-contain" />
        ) : (
          <span className="text-center text-smn-gris-500">
            <span className="block text-3xl font-semibold tracking-[0.2em]">{(p.producto.marca ?? siglas(p.producto.nombre)).toUpperCase()}</span>
            <span className="mt-2 block text-sm">Sin foto</span>
          </span>
        )}
      </div>
      {p.producto.fotos.length > 1 && (
        <div className="flex gap-2">
          {p.producto.fotos.map((f, k) => (
            <button key={f} type="button" onClick={() => { setN(k); setRota(false); }} className={`h-12 w-12 overflow-hidden rounded-lg border-2 ${k === n ? "border-smn-naranja" : "border-transparent"}`} aria-label={`Foto ${k + 1}`}>
              {/* eslint-disable-next-line @next/next/no-img-element -- miniatura de la API */}
              <ImagenSegura src={`${urlApi()}${f}`} alt="" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Imagen({ liga, texto, tam = "h-11 w-11", className = "" }: { liga: string | null; texto: string; tam?: string; className?: string }) {
  const [rota, setRota] = useState(false);
  if (!liga || rota)
    return <span className={`${tam} grid shrink-0 place-items-center rounded-xl bg-smn-gris-100 text-[11px] font-semibold tracking-wide text-smn-gris-700 ${className}`}>{siglas(texto)}</span>;
  // eslint-disable-next-line @next/next/no-img-element -- imágenes del catálogo (tienda en línea)
  return <img src={liga} alt="" loading="lazy" onError={() => setRota(true)} className={`${tam} shrink-0 rounded-xl bg-white object-contain p-0.5 ${className}`} />;
}

function Frase({ t, color }: { t: Titular; color: Color | null }) {
  return (
    <h2 className="text-3xl leading-tight font-semibold tracking-tight @5xl:text-[36px] @5xl:leading-[1.15] @7xl:text-[40px]">
      {t.antes}
      <span className={color ? TEXTO_COLOR[color] : ""}>{t.resaltado}</span>
      {t.despues}
    </h2>
  );
}

type FilaProducto = { sku?: string | null; descripcion: string; imagen?: string | null; dato: ReactNode; sub?: ReactNode; valor?: number | null; resaltar?: boolean };

/** Productos en renglones que se pueden picar: foto, nombre, dato a la derecha y, si trae valor, una barra. */
function ListaProductos({ filas, max }: { filas: FilaProducto[]; max?: number }) {
  const abrir = useContext(AbrirProducto);
  const tope = max ?? Math.max(...filas.map((f) => f.valor ?? 0), 0);
  return (
    <ul className="divide-y divide-smn-gris-100">
      {filas.map((f, k) => {
        const contenido = (
          <>
            <Imagen liga={f.imagen ?? null} texto={f.descripcion} />
            <span className="min-w-0 flex-1">
              <span className={`block truncate text-[16px] ${f.resaltar ? "font-semibold" : ""}`}>{f.descripcion}</span>
              {f.sub && <span className="block truncate text-sm text-smn-gris-500">{f.sub}</span>}
              {f.valor != null && tope > 0 && (
                <span className="mt-1 block h-1.5 rounded-full bg-smn-gris-100">
                  <span className={`block h-full rounded-full ${f.resaltar ? "bg-smn-naranja" : "bg-smn-gris-500"}`} style={{ width: `${Math.max(2, (f.valor / tope) * 100)}%` }} />
                </span>
              )}
            </span>
            <span className="shrink-0 text-right text-[16px] tabular-nums">{f.dato}</span>
            {f.sku ? <ChevronRight className="h-4 w-4 shrink-0 text-smn-gris-500" aria-hidden /> : <span className="w-4 shrink-0" />}
          </>
        );
        return (
          <li key={`${f.sku ?? f.descripcion}-${k}`}>
            {f.sku ? (
              <button type="button" onClick={() => abrir(f.sku!)} className="flex w-full items-center gap-3 rounded-xl px-1 py-2.5 text-left hover:bg-smn-gris-50">
                {contenido}
              </button>
            ) : (
              <div className="flex items-center gap-3 px-1 py-2.5">{contenido}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Lista({ titulo, puntos, tono }: { titulo: string; puntos: string[]; tono: "bien" | "mal" }) {
  return (
    <Tarjeta>
      <Etiqueta>{titulo}</Etiqueta>
      {puntos.length ? (
        <ul className="mt-3 space-y-2.5">
          {puntos.map((x) => (
            <li key={x} className="flex gap-3 text-[17px] leading-snug">
              <span className={`mt-2 h-2 w-2 shrink-0 rounded-full ${tono === "bien" ? "bg-green-600" : "bg-red-600"}`} />
              <span>{x}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-smn-gris-500">Nada que destacar.</p>
      )}
    </Tarjeta>
  );
}

/** Precio en el nivel 1: las dos mitades, «Afuera 83 · Anaquel 64» (Dirección, 22 nov 2026). */
function precioCorto(p: Pantalla, valor: string | null) {
  const m = p.precio.mitades;
  const a = m?.afuera?.puntaje, b = m?.anaquel?.puntaje;
  if (a != null && b != null) return `Afuera ${a} · Anaquel ${b}`;
  return corto(valor);
}

function corto(valor: string | null) {
  if (!valor) return "Sin datos";
  const i = valor.search(/[:,]/);
  return i > 0 && i < 48 ? valor.slice(0, i) : valor.length > 60 ? `${valor.slice(0, 58)}…` : valor;
}

/** «No meter: vendería poco…» → «Vendería poco…»: la etiqueta ya dice el veredicto. */
function sinVeredicto(d: string) {
  const m = d.match(/^(No meter|Meter|Negociar|Se puede meter, a prueba|No meter por ahora)[:.]\s*/i);
  if (!m) return d;
  const resto = d.slice(m[0].length);
  return resto ? resto.charAt(0).toUpperCase() + resto.slice(1) : d;
}

// ---------------------------------------------------------------- Nivel 1

/** El dictamen en 3 renglones para que el nivel 1 quepa; si no cabe, «Ver completo» lo abre ahí mismo (revisión de
 *  usabilidad, 26 nov 2026: se cortaba justo en el costo a pedir). */
function Dictamen({ texto }: { texto: string }) {
  const [abierto, setAbierto] = useState(false);
  const largo = texto.length > 200;
  return (
    <p className="mt-2 text-[17px] leading-snug">
      <span className={abierto ? "" : "line-clamp-3"}>{texto}</span>
      {largo && (
        <button type="button" onClick={() => setAbierto(!abierto)} className="mt-0.5 block text-[15px] font-medium text-naranja-tinta hover:underline">
          {abierto ? "Ver menos" : "Ver completo"}
        </button>
      )}
    </p>
  );
}

function Nivel1({ p, foto, abrir }: { p: Pantalla; foto?: ReactNode; abrir: (f: FactorClave) => void }) {
  // Todo el nivel 1 cabe en una pantalla de 1920×1080 sin bajar (Diego, 22 nov 2026): foto y anillo se miden por la altura
  const c = p.cifras;
  const vc = colorVeredicto(p.veredicto);
  const cinco = p.factores.length === 5;
  return (
    <div className="space-y-5">
      <div className="grid items-center gap-6 @4xl:grid-cols-[minmax(0,0.9fr)_minmax(0,0.9fr)_minmax(0,1.6fr)]">
        <FotoProducto p={p} foto={foto} />
        <div>
          <AnilloAporte p={p} tam="min(100%, 34vh)" />
          <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-sm text-smn-gris-700">
            {p.factores.map((f) => (
              <span key={f.factor} className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: hexDe(f.color) }} /> {f.nombre}
              </span>
            ))}
          </div>
        </div>
        <div className="min-w-0">
          <span className={`inline-block rounded-full px-3 py-0.5 text-sm font-semibold tracking-wide uppercase ring-1 ${PILDORA[vc]}`}>{p.veredicto}</span>
          <h1 className="mt-2 line-clamp-2 text-3xl leading-tight font-semibold tracking-tight" title={p.producto.nombre}>{p.producto.nombre}</h1>
          <p className="mt-1 truncate text-lg text-smn-gris-700">{[p.producto.marca?.toUpperCase(), p.producto.presentacion, p.producto.proveedor].filter(Boolean).join(" · ")}</p>
          {p.dictamen && <Dictamen texto={sinVeredicto(p.dictamen)} />}
          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 @2xl:grid-cols-3">
            <Cifra chica titulo="Nuestro precio" valor={pesos(c.precio, c.precio != null && c.precio % 1 ? 2 : 0)} sub={c.precio_membresia != null ? `membresía ${pesos(c.precio_membresia, c.precio_membresia % 1 ? 2 : 0)}` : undefined} />
            <Cifra chica titulo="Costo sin IVA" valor={pesos(c.costo, c.costo != null && c.costo % 1 ? 2 : 0)} />
            <Cifra chica titulo="Margen" valor={c.margen == null ? "—" : `${num(c.margen)} %`} sub={c.minimo != null ? `mínimo ${num(c.minimo)} %` : undefined} />
            <Cifra chica titulo="Porciones" valor={c.porciones ?? "—"} sub={c.por_porcion != null ? `${pesos(c.por_porcion)} por porción` : undefined} />
            <Cifra chica titulo="Venta en 3 meses" valor={c.venta_3m_texto ? `~${c.venta_3m_texto}` : "—"} sub={c.tiendas ? `sin IVA, prueba en ${c.tiendas} tiendas${c.venta_cadena_texto ? ` · ~${c.venta_cadena_texto} en ${c.tiendas_cadena}` : ""}` : undefined} />
            <Cifra chica titulo="Clase esperada" valor={c.clase_esperada || "—"} sub={c.clase_esperada ? "regla de abril 2026" : undefined} />
          </div>
          {/* Solo si hay una calificación de proveedor, en palabras de negocio (revisión del 26 nov 2026: «Proveedor (contexto,
              no califica): Proveedor 52/100» en una idea sin proveedor; el 52 es de quien ya nos surte la marca) */}
          {p.proveedor.puntaje != null && (
            <p className="mt-2 truncate text-sm text-smn-gris-500">
              {p.proveedor.nombre ? `Proveedor ${p.proveedor.nombre}` : "Quien ya nos surte la marca"}: {p.proveedor.puntaje} de 100 · no cuenta en la calificación
            </p>
          )}
        </div>
      </div>
      {/* Con 5 temas (el precio partido en anaquel y afuera, 25 nov 2026) van en una sola fila, con la dona arriba, para que
          el nivel 1 quepa sin bajar en 1920×1080 (Diego, 22 nov 2026); en pantallas angostas siguen de 2 en 2 */}
      <div className={`grid gap-4 @2xl:grid-cols-2 ${cinco ? "@4xl:grid-cols-5" : COLUMNAS[p.factores.length] ?? COLUMNAS[4]}`}>
        {p.factores.map((f) => (
          <button key={f.factor} type="button" onClick={() => abrir(f.factor)} className={`group flex items-center gap-4 rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3 text-left transition hover:-translate-y-0.5 hover:shadow-lg ${cinco ? "@4xl:flex-col @4xl:items-stretch @4xl:gap-2" : ""}`}>
            <div className={`shrink-0 ${cinco ? "@4xl:self-center" : ""}`}>
              <Dona f={f} tam={cinco ? 96 : 112} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className={`text-lg font-semibold ${cinco ? "@4xl:text-base @4xl:leading-snug" : ""}`}>{f.nombre}</span>
                <span className="whitespace-nowrap text-smn-gris-500 tabular-nums">{num(f.peso)} %</span>
              </div>
              <p className="text-sm text-smn-gris-700">
                {f.aporte != null ? `aporta ${num(f.aporte)} de ${num(f.de)} puntos` : "no cuenta todavía"}
                {f.provisional && f.aporte != null && <span className="ml-1.5 rounded-full bg-aviso-fondo px-2 py-0.5 text-xs text-aviso-texto">provisional</span>}
              </p>
              <p className="mt-1 line-clamp-2 text-[15px] leading-snug">{f.factor === "precio" ? precioCorto(p, f.valor) : corto(f.valor)}</p>
              <p className="mt-1 text-sm text-smn-gris-500 group-hover:text-tinta">
                Ver por qué <ArrowRight className="inline h-3.5 w-3.5" />
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Nivel 2

function ColumnaFactor({ p, f, ir, children }: { p: Pantalla; f: FactorPantalla; ir: (v: Vista) => void; children?: ReactNode }) {
  // En anchos medianos (el detalle del radar) la columna se vuelve una tira de 4 arriba para no apretar el contenido
  // (Diego, 22 nov 2026: «se ve muy apretado»); en Presentar, a pantalla completa, queda la columna con la dona grande
  return (
    <>
      <div className="min-w-0 space-y-4 @7xl:hidden">
        <div className={`grid gap-3 @2xl:grid-cols-2 ${TIRA[p.factores.length] ?? TIRA[4]}`}>
          <div className="flex items-center gap-4 rounded-2xl border-2 border-tinta bg-superficie px-4 py-3">
            <MiniDona f={f} />
            <span className="min-w-0 flex-1">
              <span className="block text-lg font-semibold">{f.nombre} <span className="font-normal whitespace-nowrap text-smn-gris-500 tabular-nums">{num(f.peso)} %</span></span>
              <span className="block text-sm text-smn-gris-500">{f.aporte != null ? `aporta ${num(f.aporte)} de ${num(f.de)} puntos` : "no cuenta todavía"}</span>
            </span>
          </div>
          {p.factores
            .filter((o) => o.factor !== f.factor)
            .map((o) => (
              <button key={o.factor} type="button" onClick={() => ir({ n: 2, f: o.factor })} className="flex w-full items-center gap-4 rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3 text-left hover:bg-smn-gris-50">
                <MiniDona f={o} />
                <span className="min-w-0 flex-1 truncate text-lg">{o.nombre}</span>
                <span className="whitespace-nowrap text-smn-gris-500 tabular-nums">{num(o.peso)} %</span>
              </button>
            ))}
        </div>
        {children}
      </div>
      <ColumnaGrande p={p} f={f} ir={ir}>{children}</ColumnaGrande>
    </>
  );
}

function ColumnaGrande({ p, f, ir, children }: { p: Pantalla; f: FactorPantalla; ir: (v: Vista) => void; children?: ReactNode }) {
  return (
    <div className="hidden min-w-0 space-y-4 @7xl:block">
      <Tarjeta>
        <div className="flex items-baseline justify-between">
          <span className="text-xl font-semibold">{f.nombre}</span>
          <span className="text-xl text-smn-gris-500 tabular-nums">{num(f.peso)} %</span>
        </div>
        <div className="my-4">
          <Dona f={f} tam={240} />
        </div>
        <p className="text-center text-[15px] text-smn-gris-700">
          {f.aporte != null ? `aporta ${num(f.aporte)} de ${num(f.de)} puntos` : "no cuenta todavía"}
          {f.color && ` · ${f.color}`}
        </p>
      </Tarjeta>
      {children}
      {p.factores
        .filter((o) => o.factor !== f.factor)
        .map((o) => (
          <button key={o.factor} type="button" onClick={() => ir({ n: 2, f: o.factor })} className="flex w-full items-center gap-4 rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3 text-left hover:bg-smn-gris-50">
            <MiniDona f={o} />
            <span className="flex-1 text-lg">{o.nombre}</span>
            <span className="text-smn-gris-500 tabular-nums">{num(o.peso)} %</span>
          </button>
        ))}
    </div>
  );
}

function Nivel2({ p, f, ir }: { p: Pantalla; f: FactorPantalla; ir: (v: Vista) => void }) {
  const d = seccion(p, f.factor);
  const izquierda = (f.factor === "precio" || f.factor === "precio_anaquel") && p.precio.se_lleva ? <SeLleva p={p} /> : null;
  return (
    <div className="grid gap-6 @7xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] @7xl:gap-8">
      <ColumnaFactor p={p} f={f} ir={ir}>{izquierda}</ColumnaFactor>
      <div className="min-w-0 space-y-6">
        <Frase t={d.titular} color={f.color} />
        {f.factor === "demanda" && <CuerpoDemanda p={p} />}
        {f.factor === "precio" && <CuerpoPrecio p={p} />}
        {f.factor === "precio_anaquel" && <CuerpoPrecio p={p} lado="anaquel" />}
        {f.factor === "precio_afuera" && <CuerpoPrecio p={p} lado="afuera" />}
        {f.factor === "categoria" && <CuerpoCategoria p={p} />}
        {f.factor === "rentabilidad" && <CuerpoRentabilidad p={p} />}
        <div className={`grid gap-5 ${d.subiria ? "@5xl:grid-cols-3" : "@3xl:grid-cols-2"}`}>
          <Lista titulo="A favor" puntos={d.a_favor} tono="bien" />
          <Lista titulo="En contra" puntos={d.en_contra} tono="mal" />
          {d.subiria && (
            <Tarjeta>
              <Etiqueta>Qué lo subiría</Etiqueta>
              <p className="mt-3 text-[17px] leading-snug">{d.subiria}</p>
            </Tarjeta>
          )}
        </div>
        <Pasos p={p} f={f} ir={ir} />
      </div>
    </div>
  );
}

function Pasos({ p, f, ir }: { p: Pantalla; f: FactorPantalla; ir: (v: Vista) => void }) {
  const pasos = seccion(p, f.factor).pasos;
  if (!pasos.length) return null;
  const conCifra = pasos.filter((x) => x.cifra != null);
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold tracking-wider text-smn-gris-500 uppercase">
        Cómo se calculó · <span className="normal-case">toca un paso</span>
      </h3>
      {conCifra.length ? (
        <div className="grid gap-3 @3xl:grid-cols-2 @5xl:grid-cols-4">
          {conCifra.map((x, k) => (
            <button key={k} type="button" onClick={() => ir({ n: 3, f: f.factor })} className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-left hover:bg-smn-gris-50">
              <p className="text-sm text-smn-gris-500">{k + 1}. {x.titulo}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{x.cifra}</p>
              <p className="mt-1 line-clamp-2 text-sm text-smn-gris-500">{x.sub}</p>
            </button>
          ))}
        </div>
      ) : (
        <button type="button" onClick={() => ir({ n: 3, f: f.factor })} className="w-full rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-left hover:bg-smn-gris-50">
          <span className="text-lg">{pasos[0].texto}</span>
          <span className="mt-1 block text-sm text-smn-gris-500">Ver los {pasos.length} pasos <ArrowRight className="inline h-3.5 w-3.5" /></span>
        </button>
      )}
    </div>
  );
}

function CuerpoDemanda({ p }: { p: Pantalla }) {
  const d = p.demanda;
  if (!d.escenarios.length)
    return (
      <Tarjeta>
        <p className="text-lg leading-relaxed">{p.factores.find((f) => f.factor === "demanda")?.detalle}</p>
      </Tarjeta>
    );
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold tracking-wider text-smn-gris-500 uppercase">
        Pronóstico a 3 meses{d.tiendas ? ` · prueba en ${d.tiendas} tiendas` : ""}
      </h3>
      {d.cadena && (
        <p className="-mt-1 mb-3 text-[15px] text-smn-gris-700">
          Si se lleva a las {d.cadena.tiendas} tiendas: ~{miles(d.cadena.venta)} de venta y {miles(d.cadena.utilidad)} de utilidad en 3 meses ({num(d.cadena.piezas, 0)} piezas, escenario esperado).
        </p>
      )}
      <div className="grid gap-4 @7xl:grid-cols-[minmax(0,3fr)_minmax(0,2.2fr)]">
        <div className="grid gap-4 @2xl:grid-cols-3">
          {d.escenarios.map((e) => (
            <div key={e.clave} className={`rounded-3xl bg-superficie p-5 ${e.clave === "esperado" ? "border-2 border-tinta" : "border border-smn-gris-100"}`}>
              <p className="text-sm font-semibold tracking-wider text-smn-gris-500 uppercase">{e.nombre}</p>
              <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">{miles(e.venta)}</p>
              <p className="text-[15px] text-smn-gris-700">de venta sin IVA</p>
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-[15px] text-smn-gris-700">
                  Utilidad <b className="text-tinta">{miles(e.utilidad)}</b>
                </span>
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-smn-gris-100 text-lg font-semibold" title="Clase AA–E esperada">{e.clase}</span>
              </div>
              <p className="mt-3 text-sm text-smn-gris-500">
                {num(e.piezas, 0)} piezas · {num(e.por_tienda)} por tienda al mes
              </p>
            </div>
          ))}
        </div>
        <Tarjeta>
          <p className="font-semibold">Venta acumulada en sus primeros 3 meses</p>
          <p className="text-sm text-smn-gris-500">Pesos sin IVA · banda de pesimista a optimista</p>
          <div className="mt-2">
            <Abanico e={d.escenarios} />
          </div>
        </Tarjeta>
      </div>
      {d.misma_sub.length > 0 && <Lanzamientos p={p} />}
    </div>
  );
}

function Lanzamientos({ p }: { p: Pantalla }) {
  const d = p.demanda;
  const sub = (p.producto.subcategoria ?? "su subcategoría").toLowerCase();
  const esperado = d.rango?.[1] ?? null;
  const filas = [...d.misma_sub].sort((a, b) => b.por_tienda - a.por_tienda);
  const mas = esperado != null ? filas.filter((x) => x.por_tienda > esperado).length : null;
  return (
    <Tarjeta className="mt-4">
      <p className="font-semibold">Los {filas.length} lanzamientos de {sub} en 2026</p>
      <p className="mb-3 text-sm text-smn-gris-500">
        Piezas por tienda al mes en sus primeras 12 semanas
        {esperado != null && mas != null ? ` · ${mas} de ${filas.length} vendieron más que el pronóstico de ${p.producto.marca ?? p.producto.nombre} (${num(esperado)})` : ""}
      </p>
      <ListaProductos
        filas={[
          ...filas.map((x) => ({ sku: p.catalogo?.[x.sku] ? x.sku : null, descripcion: p.catalogo?.[x.sku]?.descripcion ?? x.descripcion, imagen: p.catalogo?.[x.sku]?.imagen, dato: num(x.por_tienda), valor: x.por_tienda })),
          ...(esperado != null ? [{ descripcion: `${p.nuevo.descripcion} (pronóstico)`, dato: num(esperado), valor: esperado, resaltar: true }] : []),
        ].sort((a, b) => (b.valor ?? 0) - (a.valor ?? 0))}
      />
    </Tarjeta>
  );
}

function SeLleva({ p }: { p: Pantalla }) {
  const s = p.precio.se_lleva!;
  return (
    <Tarjeta>
      <p className="font-semibold">Con {pesos(s.monto, 0)} el cliente se lleva</p>
      <p className="mb-4 text-sm text-smn-gris-500">{s.unidad === "porciones" ? "Porciones" : s.unidad.charAt(0).toUpperCase() + s.unidad.slice(1)} por cada {pesos(s.monto, 0)}</p>
      <ListaProductos
        filas={s.filas.map((x) => ({
          sku: x.sku,
          descripcion: x.nombre,
          imagen: x.imagen,
          valor: x.cantidad,
          resaltar: x.tipo === "nuevo",
          dato: `${num(x.cantidad, 0)} ${s.unidad === "porciones" ? "porc." : s.unidad === "gramos" ? "g" : s.unidad === "mililitros" ? "ml" : "pz"}`,
        }))}
      />
    </Tarjeta>
  );
}

function Mitad({ titulo, m, sin }: { titulo: string; m: MitadPrecio | null | undefined; sin: string }) {
  const r = 26, l = 2 * Math.PI * r;
  return (
    <Tarjeta>
      <div className="flex items-center gap-4">
        <span className="relative inline-grid h-16 w-16 shrink-0 place-items-center">
          <svg viewBox="0 0 64 64" className="absolute inset-0" aria-hidden>
            <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" className="stroke-smn-gris-100" />
            <circle cx="32" cy="32" r={r} fill="none" strokeWidth="6" stroke={hexDe(m?.color ?? null)} strokeDasharray={`${((m?.puntaje ?? 0) / 100) * l} ${l}`} transform="rotate(-90 32 32)" strokeLinecap="round" />
          </svg>
          <span className="text-lg font-semibold tabular-nums">{m?.puntaje ?? "—"}</span>
        </span>
        <div className="min-w-0">
          <Etiqueta>{titulo}</Etiqueta>
          <p className="mt-1 text-lg leading-snug font-semibold">
            {m?.diferencia_pct != null
              ? m.diferencia_pct === 0
                ? "Al mismo precio"
                : `${Math.abs(m.diferencia_pct)} % más ${m.diferencia_pct < 0 ? "barato" : "caro"}`
              : sin}
          </p>
          {m?.puntaje != null &&
            (m.por_unidad ? (
              <p className="text-sm text-smn-gris-500">
                por {m.por_unidad.unidad}: {pesos(m.por_unidad.propio)} contra {pesos(m.por_unidad.medio)} en medio{m.provisional ? " · provisional" : ""}
              </p>
            ) : (
              m.referencia != null && <p className="text-sm text-smn-gris-500">contra {pesos(m.referencia)} de referencia</p>
            ))}
        </div>
      </div>
      {m?.detalle && <p className="mt-3 line-clamp-4 text-[15px] leading-snug text-smn-gris-700">{m.detalle}</p>}
    </Tarjeta>
  );
}

function CuerpoPrecio({ p, lado }: { p: Pantalla; lado?: "anaquel" | "afuera" }) {
  // lado: uno de los dos temas del Precio (25 nov 2026); sin lado, el Precio junto de las evaluaciones de antes
  const d = p.precio;
  const m = d.mitades;
  const abrir = useContext(AbrirProducto);
  const mem = d.membresia;
  const deMembresia = lado === "anaquel" ? mem?.anaquel : lado === "afuera" ? mem?.afuera : null;
  return (
    <div className="space-y-5">
    {lado && m && (
      <div className="grid gap-5 @3xl:grid-cols-2">
        {lado === "afuera" ? (
          <Mitad titulo="Con precio de lista · pesa la mitad del tema" m={m.afuera} sin="Sin precios de afuera" />
        ) : (
          <Mitad titulo="Con precio de lista · pesa la mitad del tema" m={m.anaquel} sin={m.anaquel ? "Sin con qué compararlo" : "Ya lo vendemos"} />
        )}
        {mem && (
          <Mitad
            titulo={`Con membresía · ${pesos(mem.precio, 2)}${mem.calculado ? " (calculado con su lista)" : ""} · pesa la otra mitad`}
            m={deMembresia}
            sin={lado === "afuera" ? "Sin precios de afuera" : "Sin con qué compararlo"}
          />
        )}
      </div>
    )}
    {!lado && m && (m.afuera || m.anaquel) && (
      <div className="grid gap-5 @3xl:grid-cols-2">
        <Mitad titulo="Contra afuera · pesa la mitad" m={m.afuera} sin="Sin precios de afuera" />
        <Mitad titulo="Contra nuestro anaquel · pesa la mitad" m={m.anaquel} sin={m.anaquel ? "Sin con qué compararlo" : "Ya lo vendemos"} />
      </div>
    )}
    {!lado && d.membresia && d.membresia.puntaje != null && (
      <Tarjeta>
        <Etiqueta>
          Con precio de membresía · {pesos(d.membresia.precio, 2)}
          {d.membresia.calculado ? " (calculado con su lista)" : ""} · pesa la mitad del Precio
        </Etiqueta>
        <p className="mt-1 text-lg leading-snug font-semibold">{d.membresia.valor ?? "—"}</p>
        <p className="mt-1 text-sm text-smn-gris-500 tabular-nums">
          {[d.membresia.afuera?.puntaje != null && `Afuera ${d.membresia.afuera.puntaje}`,
            d.membresia.anaquel?.puntaje != null && `Anaquel ${d.membresia.anaquel.puntaje}`,
            `Membresía ${d.membresia.puntaje}`].filter(Boolean).join(" · ")}
          {" · las mitades de arriba son con precio de lista"}
        </p>
      </Tarjeta>
    )}
    {lado !== "afuera" && !!d.compite?.length && (
      <Tarjeta>
        <Etiqueta>Va a competir con · los parecidos del mismo formato que más venden</Etiqueta>
        <div className="mt-3 grid gap-3 @3xl:grid-cols-3">
          {d.compite.map((c) => (
            <button type="button" key={c.sku} onClick={() => abrir(c.sku)} className="flex min-w-0 items-center gap-3 rounded-2xl border border-smn-gris-100 p-3 text-left hover:bg-smn-gris-50">
              {c.imagen ? (
                // eslint-disable-next-line @next/next/no-img-element -- imagen del catálogo
                <ImagenSegura src={c.imagen} alt="" className="h-14 w-14 shrink-0 rounded-xl bg-smn-gris-50 object-contain" />
              ) : (
                <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-smn-gris-50 text-xs text-smn-gris-500">{c.sku}</span>
              )}
              <span className="min-w-0">
                <span className="line-clamp-2 text-[15px] leading-snug">{c.descripcion}</span>
                <span className="block text-sm text-smn-gris-500 tabular-nums">
                  {[c.clasificacion && `Clas. catálogo ${c.clasificacion}`, c.por_tienda != null && `${num(c.por_tienda)} pzas/tienda`, pesos(c.precio), c.por_porcion != null && `${pesos(c.por_porcion)} por porción`].filter(Boolean).join(" · ")}
                </span>
              </span>
            </button>
          ))}
        </div>
      </Tarjeta>
    )}
    <div className={`grid gap-5 ${lado ? "" : "@5xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"}`}>
      {lado !== "anaquel" && (
      <Tarjeta>
        <Etiqueta>Cómo se ve afuera · quién lo vende</Etiqueta>
        <div className="mt-3 divide-y divide-smn-gris-100">
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_2.5rem] gap-3 pb-2 text-sm text-smn-gris-500">
            <span>Publicación</span>
            <span className="w-24 text-right">Precio</span>
            <span className="w-24 text-right">Por porción</span>
            <span />
          </div>
          {d.afuera.map((a, k) => (
            <div key={k} className={`grid grid-cols-[minmax(0,1fr)_auto_auto_2.5rem] items-center gap-3 py-3 ${a.cuenta === false ? "opacity-70" : ""}`}>
              <span className="flex min-w-0 items-center gap-3">
                <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl text-xs font-bold ${a.mercado_libre ? "bg-yellow-300 text-smn-negro" : "bg-smn-gris-100 text-smn-gris-700"}`}>
                  {a.mercado_libre ? "ML" : siglas(a.vendedor)}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[17px]">{a.titulo}</span>
                  <span className="block text-sm leading-snug text-smn-gris-500">
                    {a.vendedor}
                    {a.fuente === "marca"
                      ? " · página de la marca: precio sugerido, no cuenta"
                      : a.fuente === "compras"
                        ? " · lo vio Compras, de referencia (no cuenta)"
                        : a.fuente === "proveedor"
                          ? " · lo dijo el proveedor"
                          : ""}
                    {a.nota && ` · ${a.nota}`}
                  </span>
                  {a.venta && <span className={`block truncate text-sm ${a.venta_fuerte ? "font-semibold text-green-700 dark:text-green-400" : "text-smn-gris-700"}`}>{a.venta}</span>}
                </span>
              </span>
              <span className="w-24 text-right text-[17px] tabular-nums">{pesos(a.precio)}</span>
              <span className="w-24 text-right text-[17px] tabular-nums">{pesos(a.por_porcion)}</span>
              {a.liga ? (
                <a href={a.liga} target="_blank" rel="noreferrer noopener" className="text-sm text-naranja-tinta hover:underline">
                  Ver <ArrowUpRight className="inline h-3.5 w-3.5" />
                </a>
              ) : (
                <span />
              )}
            </div>
          ))}
          {!d.mercado_libre.length && d.mercado_libre_nota && (
            <div className="flex items-center gap-3 py-3 text-smn-gris-500">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-smn-gris-50 text-xs font-bold">ML</span>
              <span className="text-[15px]">{d.mercado_libre_nota}</span>
            </div>
          )}
          {!d.afuera.length && <p className="py-3 text-smn-gris-500">No se encontraron precios de este mismo producto afuera.</p>}
          {d.busqueda_notas && d.busqueda_notas.length > 0 && (
            <details className="mt-2 border-t border-smn-gris-100 pt-3" open={!d.afuera.length}>
              <summary className="cursor-pointer text-sm font-semibold text-smn-gris-500">Qué se buscó afuera y qué se encontró</summary>
              <ul className="mt-2 space-y-1.5 text-sm text-smn-gris-500">
                {d.busqueda_notas.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </details>
          )}
        </div>
      </Tarjeta>
      )}
      {lado !== "afuera" && d.barras_nota && d.barras.length === 0 && <p className="text-[15px] text-smn-gris-500">{d.barras_nota}</p>}
      {lado !== "afuera" && d.barras.length > 0 && (
        <Tarjeta>
          <p className="font-semibold">Precio por porción</p>
          <p className="mb-4 text-sm text-smn-gris-500">Pesos con IVA por porción</p>
          <ListaProductos filas={d.barras.map((b) => ({ sku: b.sku, descripcion: b.nombre, imagen: b.imagen, valor: b.valor, resaltar: b.tipo === "nuevo", dato: pesos(b.valor), sub: b.tipo === "afuera" ? "afuera" : undefined }))} />
        </Tarjeta>
      )}
    </div>
    </div>
  );
}

function CuerpoCategoria({ p }: { p: Pantalla }) {
  const d = p.categoria;
  return (
    <div className="grid gap-5 @5xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Tarjeta>
        <Etiqueta>Su subcategoría{p.producto.subcategoria ? ` · ${p.producto.subcategoria.toLowerCase()}` : ""}</Etiqueta>
        <div className="mt-4 grid grid-cols-2 gap-5">
          <Cifra titulo="Productos activos" valor={d.productos ?? "—"} sub={d.tipica ? `una normal tiene unos ${d.tipica}` : undefined} />
          <Cifra titulo="Inventario en tiendas" valor={d.dias_inventario != null ? `${num(d.dias_inventario, 0)} días` : "—"} sub="de venta" />
        </div>
        {d.productos != null && d.tipica ? (
          <div className="mt-6">
            <div className="relative h-3 rounded-full bg-smn-gris-100">
              <span className="absolute inset-y-0 left-0 rounded-full bg-tinta" style={{ width: `${Math.min(100, (d.productos / (d.tipica * 4)) * 100)}%` }} />
              <span className="absolute -top-1.5 h-6 border-l-2 border-dashed border-smn-gris-500" style={{ left: "25%" }} />
            </div>
            <div className="mt-1.5 flex justify-between text-xs text-smn-gris-500">
              <span>0</span>
              <span>típica ({d.tipica})</span>
              <span>4 veces ({d.tipica * 4})</span>
            </div>
          </div>
        ) : null}
      </Tarjeta>
      {d.mas_vendidos.length > 0 && (
        <Tarjeta>
          <p className="font-semibold">Lo más vendido de {(p.producto.subcategoria ?? "su subcategoría").toLowerCase()} en SMN</p>
          <p className="mb-3 text-sm text-smn-gris-500">Piezas al mes · toca uno para ver sus datos</p>
          <ListaProductos filas={d.mas_vendidos.map((x) => ({ sku: x.sku, descripcion: x.descripcion, imagen: x.imagen, dato: `${num(x.al_mes, 0)} pzas`, sub: x.por_tienda != null ? `${num(x.por_tienda)} por tienda al mes` : undefined, valor: x.al_mes }))} />
        </Tarjeta>
      )}
    </div>
  );
}

function CuerpoRentabilidad({ p }: { p: Pantalla }) {
  const d = p.rentabilidad;
  const tope = Math.max(50, (d.margen ?? 0) + 10, (d.margen_sub ?? 0) + 10);
  const marca = (v: number | null, texto: string, clase: string, arriba = false) =>
    v == null ? null : (
      <span className={`absolute flex -translate-x-1/2 items-center ${arriba ? "top-0 flex-col-reverse" : "top-5 flex-col"}`} style={{ left: `${(v / tope) * 100}%` }}>
        <span className={`h-5 w-0.5 ${clase}`} />
        <span className="text-xs whitespace-nowrap text-smn-gris-700">{texto}</span>
      </span>
    );
  return (
    <div className="grid gap-5 @5xl:grid-cols-2">
      <Tarjeta>
        <Etiqueta>Margen contra el mínimo{d.lista ? ` · ${d.lista}` : " · lista A por omisión"}</Etiqueta>
        <div className="relative mt-4 h-24">
          <div className="absolute top-9 h-3 w-full rounded-full bg-smn-gris-100" />
          {d.minimo != null && <div className="absolute top-9 h-3 rounded-l-full bg-red-600/20" style={{ width: `${(d.minimo / tope) * 100}%` }} />}
          <span className="absolute top-12 left-0 h-12 w-full">
            {marca(d.minimo, `mínimo ${num(d.minimo)} %`, "bg-red-600")}
          </span>
          <span className="absolute top-0 left-0 h-9 w-full">
            {marca(d.margen, `este ${num(d.margen)} %`, "bg-tinta", true)}
          </span>
          <span className="absolute top-12 left-0 h-12 w-full">
            {d.margen_sub != null && d.minimo != null && Math.abs(d.margen_sub - d.minimo) < tope * 0.12 ? (
              <span className="absolute top-8 text-xs whitespace-nowrap text-smn-gris-700" style={{ left: `${(d.margen_sub / tope) * 100}%` }}>
                ▲ {(p.producto.subcategoria ?? "subcategoría").toLowerCase()} {num(d.margen_sub)} %
              </span>
            ) : (
              marca(d.margen_sub, `${(p.producto.subcategoria ?? "subcategoría").toLowerCase()} ${num(d.margen_sub)} %`, "bg-smn-gris-500")
            )}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-5">
          <Cifra titulo="Margen" valor={d.margen != null ? `${num(d.margen)} %` : "—"} sub={d.minimo != null ? `al precio de lista; mínimo ${num(d.minimo)} %` : undefined} />
          {d.membresia && (
            <Cifra titulo="Con membresía" valor={d.membresia.margen != null ? `${num(d.membresia.margen)} %` : "—"}
              sub={`a ${pesos(d.membresia.precio, 2)}${d.membresia.minimo != null ? `; mínimo ${num(d.membresia.minimo)} %` : ""}`} />
          )}
          <Cifra titulo="Utilidad por pieza" valor={pesos(d.utilidad_pieza)} sub="sin IVA" />
        </div>
      </Tarjeta>
      {d.escenarios.length > 0 && (
        <Tarjeta>
          <Etiqueta>Con otro precio o costo</Etiqueta>
          <table className="mt-3 w-full text-[15px]">
            <thead className="text-left text-sm text-smn-gris-500">
              <tr>
                <th className="py-1.5 font-normal" />
                <th className="py-1.5 text-right font-normal">Precio</th>
                <th className="py-1.5 text-right font-normal">Costo</th>
                <th className="py-1.5 text-right font-normal">Margen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-smn-gris-100">
              {d.escenarios.map((e) => (
                <tr key={e.nombre}>
                  <td className="py-2">{e.nombre}</td>
                  <td className="py-2 text-right tabular-nums">{pesos(e.precio)}</td>
                  <td className="py-2 text-right tabular-nums">{pesos(e.costo)}</td>
                  <td className="py-2 text-right font-semibold tabular-nums">{e.margen != null ? `${num(e.margen)} %` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Tarjeta>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Nivel 3

function Nivel3({ p, f, ir }: { p: Pantalla; f: FactorPantalla; ir: (v: Vista) => void }) {
  const pasos = seccion(p, f.factor).pasos;
  const conCifra = pasos.some((x) => x.cifra != null);
  return (
    <div className="space-y-8">
      <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        {pasos.length === 1 ? "Un paso" : `${["", "Un", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete"][pasos.length] ?? pasos.length} pasos`}, del producto a su calificación de {f.puntaje ?? "—"}.
      </h2>
      <div className={`grid gap-5 ${conCifra ? "@3xl:grid-cols-2 @5xl:grid-cols-4" : "@3xl:grid-cols-2"}`}>
        {pasos.map((x, k) => (
          <Tarjeta key={k} className={k === 0 && conCifra ? "border-2 border-tinta" : ""}>
            <p className="text-sm font-semibold tracking-wider text-smn-gris-500 uppercase">Paso {k + 1}</p>
            {x.cifra != null ? (
              <>
                <p className="mt-1 text-2xl font-semibold">{x.titulo}</p>
                {x.pregunta && <p className="mt-2 text-[15px] text-smn-gris-500">{x.pregunta}</p>}
                <p className="mt-5 text-5xl font-semibold tracking-tight tabular-nums">{x.cifra}</p>
                {x.sub && <p className="mt-2 text-[15px] text-smn-gris-500">{x.sub}</p>}
                {x.puntos && (
                  <ul className="mt-4 space-y-2 text-[15px]">
                    {x.puntos.map((t) => (
                      <li key={t} className="flex gap-2"><span className="text-smn-gris-500">·</span> {t}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="mt-2 text-lg leading-snug">{x.texto}</p>
            )}
          </Tarjeta>
        ))}
      </div>
      {f.factor === "demanda" && p.demanda.lugar != null && <Tira p={p} />}
      <button type="button" onClick={() => ir({ n: 4, f: f.factor })} className="inline-flex items-center gap-2 rounded-2xl border border-smn-gris-100 px-5 py-3 text-lg hover:bg-smn-gris-50">
        Ver con qué datos: los {p.parecidos.length} parecidos <ArrowRight className="h-4 w-4" />
      </button>
    </div>
  );
}

/** Dónde quedó entre los lanzamientos de 2026: cada punto es un lanzamiento; las zonas, el color que da cada lugar. */
function Tira({ p }: { p: Pantalla }) {
  const d = p.demanda;
  const lugar = d.lugar ?? 0;
  const est = 1.3;
  const lugarPara = (meta: number) => Math.min(100, 50 + (meta - 50) / est);
  const rojo = lugarPara(60), verde = lugarPara(80.5);
  const nombre = p.producto.marca ?? p.producto.nombre;
  const n = d.lanzamientos.length;
  return (
    <Tarjeta>
      <p className="text-lg font-semibold">Dónde quedó {nombre} entre los lanzamientos de 2026</p>
      <p className="text-[15px] text-smn-gris-500">
        Lugar entre {n} lanzamientos {d.del_depto ? "del departamento" : "de toda la cadena"} y el color que da cada lugar. Cada punto es un lanzamiento.
      </p>
      <div className="relative mt-10 mb-12 px-1">
        <div className="relative flex h-6 overflow-hidden rounded-md">
          <span className="bg-red-600/15" style={{ width: `${rojo}%` }} />
          <span className="bg-yellow-500/20" style={{ width: `${verde - rojo}%` }} />
          <span className="flex-1 bg-green-600/15" />
        </div>
        {d.lanzamientos.map((_, k) => (
          <span key={k} className="absolute top-1.5 h-3 w-0.5 rounded bg-smn-gris-500/50" style={{ left: `${((k + 0.5) / n) * 100}%` }} />
        ))}
        <span className="absolute -top-7 bottom-0 flex flex-col items-start" style={{ left: `${lugar}%` }}>
          <span className="-ml-px h-full border-l-2 border-tinta" />
        </span>
        <span className="absolute -top-8 text-sm font-semibold whitespace-nowrap" style={{ left: `calc(${lugar}% + 6px)` }}>
          {nombre} · {lugar} de 100 → {p.demanda.pasos.find((x) => x.titulo === "Puntaje")?.cifra ?? "—"} puntos
        </span>
        <span className="absolute top-0 h-6 border-l border-dashed border-smn-gris-500" style={{ left: "50%" }} />
        <div className="absolute top-8 flex w-full justify-between text-xs text-smn-gris-500">
          {[0, 25, 50, 75, 100].map((x) => (
            <span key={x}>{x}</span>
          ))}
        </div>
        <div className="absolute top-14 w-full text-xs text-smn-gris-700">
          <span className="absolute" style={{ left: 0 }}>Demanda en rojo (menos de 60)</span>
          <span className="absolute" style={{ left: `${rojo}%` }}>amarillo</span>
          <span className="absolute" style={{ left: `${verde}%` }}>verde (más de 80)</span>
        </div>
      </div>
      <p className="text-sm text-smn-gris-500">Línea punteada: lanzamiento típico (lugar 50) → 50 puntos.</p>
      {d.prueba?.probados ? (
        <p className="mt-2 text-sm text-smn-gris-500">
          Qué tan seguido atina: a {d.prueba.probados} productos que lanzamos en 2026 se les pronosticó como si fueran nuevos y atinó el color de la Demanda en {d.prueba.color} y la clase AA–E en {d.prueba.clase}.
        </p>
      ) : null}
    </Tarjeta>
  );
}

// ---------------------------------------------------------------- Nivel 4

const COMO_SE_ELIGE = [
  "Parte de todos los productos activos con precio de $5 o más.",
  "Solo entran los que comparten una palabra del nombre (sin el sabor), la marca o la subcategoría.",
  "Se califica qué tan parecido es: palabras en común, misma marca, subcategoría, forma, presentación y tipo según su ficha.",
  "Entran también sustitutos que sirven para lo mismo, buscados por el significado de su ficha.",
  "Se quedan los de su subcategoría y los 10 más parecidos, sin repetir.",
  "La IA local quita los que un cliente no vería como alternativa en el anaquel.",
  "Para la Demanda solo cuentan los de precio cercano: de 0.4 a 2.5 veces, por pieza y por gramo.",
];

function Nivel4({ p, f, abrir }: { p: Pantalla; f: FactorPantalla; abrir: (x: ParecidoPantalla) => void }) {
  const usados = p.parecidos.filter((x) => x.cuenta);
  const nuevo = p.nuevo;
  const conPorcion = usados.filter((x) => x.por_porcion);
  const veces = nuevo.por_porcion && conPorcion.length ? nuevo.por_porcion / median(conPorcion.map((x) => x.por_porcion!)) : null;
  const marca = p.producto.marca ?? p.producto.nombre;
  const barras = useMemo(
    () => [...p.parecidos.filter((x) => x.por_tienda != null)].sort((a, b) => (b.por_tienda ?? 0) - (a.por_tienda ?? 0)).slice(0, 8),
    [p.parecidos],
  );
  return (
    <div className="grid gap-8 @5xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
      <div className="min-w-0">
        <h2 className="text-3xl leading-tight font-semibold tracking-tight">
          {usados.length === p.parecidos.length
            ? `Se pronostica con sus ${usados.length} parecidos.`
            : `Solo ${usados.length} de ${p.parecidos.length} parecidos tienen un precio comparable; con ellos se pronostica.`}
          {veces && veces >= 1.5 ? ` Por porción, ${marca} cuesta ${num(veces)} veces más.` : ""}
        </h2>
        <p className="mt-2 text-sm text-smn-gris-500">Toca un producto para ver sus datos. {f.factor !== "demanda" && "Son los mismos parecidos para todos los factores."}</p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[56rem] text-[15px]">
            <thead className="text-left text-sm text-smn-gris-500">
              <tr className="border-b border-smn-gris-100">
                <th className="py-2 pl-3 font-normal">Producto</th>
                <th className="py-2 font-normal">Clas. catálogo</th>
                <th className="py-2 text-right font-normal">Pzas por tienda al mes</th>
                <th className="py-2 text-right font-normal">Precio prom.</th>
                <th className="py-2 text-right font-normal">Porciones</th>
                <th className="py-2 text-right font-normal">Por porción</th>
                <th className="py-2 pl-4 font-normal">¿Cuenta?</th>
                <th className="py-2 font-normal">Por qué</th>
              </tr>
            </thead>
            <tbody>
              {p.parecidos.map((x) => (
                <tr key={x.producto_id} onClick={() => abrir(x)} className={`cursor-pointer border-b border-smn-gris-100 hover:bg-smn-gris-50 ${x.cuenta ? "bg-green-600/5" : ""}`}>
                  <td className="py-3 pl-3">
                    <span className="flex items-center gap-3">
                      <Imagen liga={x.imagen} texto={x.descripcion} />
                      <span className="min-w-0">
                        <span className="block max-w-[20rem] truncate font-medium">{x.descripcion}</span>
                        <span className="block text-sm text-smn-gris-500">SKU {x.sku}</span>
                      </span>
                    </span>
                  </td>
                  <td className="py-3">{x.clasificacion ?? "—"}</td>
                  <td className="py-3 text-right tabular-nums">{num(x.por_tienda)}</td>
                  <td className="py-3 text-right tabular-nums">{pesos(x.precio)}</td>
                  <td className="py-3 text-right tabular-nums">{x.porciones ?? "—"}</td>
                  <td className="py-3 text-right tabular-nums">{pesos(x.por_porcion)}</td>
                  <td className="py-3 pl-4">
                    <span className={`rounded-full px-2.5 py-0.5 text-sm font-semibold ${x.cuenta ? "bg-green-600/10 text-green-700 dark:text-green-400" : "bg-smn-gris-100 text-smn-gris-700"}`}>{x.cuenta ? "Sí" : "No"}</span>
                  </td>
                  <td className="py-3">{x.por_que}</td>
                </tr>
              ))}
              <tr className="bg-aviso-fondo/50">
                <td className="py-3 pl-3">
                  <span className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-tinta text-[10px] font-bold text-superficie">{siglas(marca)}</span>
                    <span>
                      <span className="block font-semibold">{nuevo.descripcion}</span>
                      <span className="block text-sm text-smn-gris-500">nuevo · pronóstico</span>
                    </span>
                  </span>
                </td>
                <td className="py-3">{nuevo.clase ? `${nuevo.clase}*` : "—"}</td>
                <td className="py-3 text-right tabular-nums">{num(nuevo.por_tienda)}</td>
                <td className="py-3 text-right tabular-nums">{pesos(nuevo.precio)}</td>
                <td className="py-3 text-right tabular-nums">{nuevo.porciones ?? "—"}</td>
                <td className="py-3 text-right font-semibold tabular-nums">{pesos(nuevo.por_porcion)}</td>
                <td />
                <td className="py-3">Pronóstico</td>
              </tr>
            </tbody>
          </table>
        </div>
        {nuevo.clase && <p className="mt-2 text-xs text-smn-gris-500">*Clase del nuevo: la esperada a 3 meses. Porciones de su ficha técnica; «—» si la ficha no las dice.</p>}
      </div>
      <div className="space-y-5">
        {barras.length > 0 && (
          <Tarjeta>
            <p className="font-semibold">Piezas por tienda al mes</p>
            <p className="mb-4 text-sm text-smn-gris-500">Lo que venden hoy sus parecidos contra el pronóstico de {marca}</p>
            <Barras
              filas={barras.map((x) => ({ nombre: x.descripcion, valor: x.por_tienda ?? 0, resaltar: x.cuenta ? "cuenta" : null }))}
              formato={(v) => num(v)}
              linea={nuevo.por_tienda}
              lineaTexto={nuevo.por_tienda != null ? `${marca} ${num(nuevo.por_tienda)} (pronóstico) · verde = cuenta` : undefined}
            />
          </Tarjeta>
        )}
        <Tarjeta>
          <p className="text-xl font-semibold">Cómo se elige un parecido</p>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-[15px] leading-snug">
            {COMO_SE_ELIGE.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
        </Tarjeta>
      </div>
    </div>
  );
}

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// ---------------------------------------------------------------- ventana del parecido

function VentanaParecido({ x, p, cerrar }: { x: ParecidoPantalla; p: Pantalla; cerrar: () => void }) {
  const max = Math.max(...x.meses.map((m) => m.piezas), 1);
  const veces = p.nuevo.precio && x.precio ? p.nuevo.precio / x.precio : null;
  return (
    <motion.div className="fixed inset-0 z-[80] flex justify-end bg-smn-negro/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={cerrar}>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label={x.descripcion}
        onClick={(e) => e.stopPropagation()}
        initial={{ x: 40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 40, opacity: 0 }}
        transition={{ type: "spring", stiffness: 400, damping: 38 }}
        className="relative h-full w-full max-w-3xl overflow-y-auto bg-superficie p-6 shadow-2xl sm:rounded-l-3xl sm:p-10"
      >
        <button type="button" onClick={cerrar} aria-label="Cerrar" className="absolute top-5 right-5 rounded-full p-1.5 hover:bg-smn-gris-100">
          <X className="h-5 w-5" />
        </button>
        <div className="grid gap-8 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
          <div>
            {x.imagen ? <Imagen liga={x.imagen} texto={x.descripcion} tam="aspect-square w-full" className="rounded-3xl p-4" /> : (
              <span className="grid aspect-square w-full place-items-center rounded-3xl bg-smn-gris-100 text-smn-gris-500">
                <span className="text-center">
                  <ImageOff className="mx-auto h-8 w-8" />
                  <span className="mt-2 block text-2xl font-semibold tracking-[0.2em]">{(x.marca ?? siglas(x.descripcion)).toUpperCase()}</span>
                </span>
              </span>
            )}
            <p className="mt-2 text-center text-sm text-smn-gris-500">Foto del catálogo</p>
          </div>
          <div className="min-w-0">
            <p className="text-sm text-smn-gris-500">{["SKU " + x.sku, x.subcategoria?.toLowerCase(), x.departamento?.toLowerCase()].filter(Boolean).join(" · ")}</p>
            <h2 className="mt-1 pr-8 text-3xl leading-tight font-semibold tracking-tight">{x.descripcion}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {x.cuenta != null && (
                <span className={`rounded-full px-3 py-1 text-sm font-semibold uppercase ring-1 ${x.cuenta ? PILDORA.verde : "bg-smn-gris-100 text-smn-gris-700 ring-smn-gris-300"}`}>{x.cuenta ? "Cuenta para la Demanda" : "No cuenta para la Demanda"}</span>
              )}
              {x.clasificacion && <span className="rounded-full bg-smn-gris-100 px-3 py-1 text-sm font-semibold">CLASE {x.clasificacion}</span>}
            </div>
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
              <Cifra chica titulo="Vende al mes" valor={x.al_mes != null ? `${num(x.al_mes, 0)} pzas` : "—"} />
              <Cifra chica titulo="En" valor={x.tiendas != null ? `${x.tiendas} tiendas` : "—"} />
              <Cifra chica titulo="Por tienda al mes" valor={num(x.por_tienda)} />
              <Cifra chica titulo="Precio promedio" valor={pesos(x.precio)} sub={x.precio_lista && x.precio && Math.abs(x.precio_lista - x.precio) >= 1 ? `lista ${pesos(x.precio_lista)}` : undefined} />
              <Cifra chica titulo="Margen" valor={x.margen != null ? `${num(x.margen)} %` : "—"} />
              <Cifra chica titulo="Por porción" valor={pesos(x.por_porcion)} sub={x.porciones ? `${x.porciones} porciones` : x.tamano ?? undefined} />
            </div>
            {x.meses.length > 0 && (
              <div className="mt-6 rounded-3xl border border-smn-gris-100 bg-smn-gris-50 p-5">
                <p className="font-semibold">Venta por mes</p>
                <p className="text-sm text-smn-gris-500">Piezas netas en tiendas, SMNBI</p>
                <div className="mt-4 flex h-36 items-end gap-2">
                  {x.meses.map((m) => (
                    <div key={m.mes} className="flex flex-1 flex-col items-center gap-1" title={`${m.etiqueta}: ${m.piezas} piezas`}>
                      <span className="text-[11px] text-smn-gris-500 tabular-nums">{m.piezas}</span>
                      <motion.span initial={{ height: 0 }} animate={{ height: `${(m.piezas / max) * 96}px` }} transition={{ duration: 0.4 }} className="w-full max-w-10 rounded-t-md bg-smn-gris-500" />
                      <span className="text-[11px] text-smn-gris-500">{m.etiqueta}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <p className="mt-5 text-[15px] leading-relaxed">
              {x.cuenta != null && (
                <>
                  <b>Por qué {x.cuenta ? "cuenta" : "no cuenta"}:</b> {x.por_que}
                  {veces && x.cuenta ? `. ${p.producto.marca ?? p.producto.nombre} cuesta ${num(veces)} veces su precio, dentro del rango de 0.4 a 2.5` : ""}.
                </>
              )}
              {x.cambio != null && (x.cambio === 0 ? " En las últimas 13 semanas vendió lo mismo que en las 13 anteriores." : ` En las últimas 13 semanas vendió ${Math.abs(x.cambio)} % ${x.cambio > 0 ? "más" : "menos"} que en las 13 anteriores.`)}
            </p>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
