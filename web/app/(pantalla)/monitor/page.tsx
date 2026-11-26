"use client";

// Monitor de la plataforma para dejarlo prendido en una pantalla (Diego, 26 nov 2026: «que se vea más pro» y «una
// gráfica que se está moviendo»). Pantalla fija de 1920×1080 que se escala a la ventana, sin el menú del sitio.
// Todo se consulta cada 10 s; la gráfica en vivo, cada 2 s.
import { Expand, Minimize, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import s from "./monitor.module.css";

type Proceso = { tipo: string; nombre: string; detalle: string | null; minutos: number | null; lento: boolean; muy_lento: boolean; progreso: number | null };
type Barra = { carril: string; nombre: string; inicio: string; fin: string | null; estado: string };
type Cuadro = { clave: string; nombre: string; estado: "ok" | "ocupado" | "aviso" | "mal" | "apagado"; detalle: string };
type Grupo = { nivel: "aviso" | "error"; origen: string; veces: number; mensaje: string; hora: string };
type Sigue = { cuando: string | null; que: string; detalle: string | null };
type Hoy = {
  evaluaciones?: { terminadas: number; en_curso: number; con_error: number; minutos_promedio: number | null };
  noche?: { lotes: number; productos: number; con_precio: number };
  busquedas?: { aceptadas: number; rechazadas: number; gasto_usd: number };
};
type Monitor = {
  ahora: string;
  horas: number;
  carriles: string[];
  version: string | null;
  servidor: { dataforseo: { gasto_mes: number | null; tope_mes: number | null } };
  salud: Cuadro[];
  hoy: Hoy;
  sigue: Sigue[];
  grupos: Grupo[];
  procesos: Proceso[];
  linea: Barra[];
};
type Muestra = { t: number; cpu: number | null; ia: number | null; ia_fuente: "tarjeta" | "llamadas"; busquedas: number };

const CADA_MS = 10_000;
const SERIE_MS = 2_000;
const PUNTOS = 150;
const ZONA = "America/Mexico_City";
const ANCHO = 1920;
const ALTO = 1080;

const mx = (d: Date, o: Intl.DateTimeFormatOptions) => d.toLocaleString("es-MX", { timeZone: ZONA, ...o });
const horaCorta = (d: Date) => mx(d, { hour: "numeric", minute: "2-digit" });
const dia = (d: Date) => mx(d, { year: "numeric", month: "2-digit", day: "2-digit" });
const miles = (n: number) => n.toLocaleString("es-MX");
const lleva = (m: number | null) => (m === null ? "" : m < 1 ? "<1 min" : m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);
const fallo = (e: string) => ["fallida", "error", "parcial"].includes(e);
const COLOR: Record<Cuadro["estado"], string> = { ok: s.cOk, ocupado: s.cOcupado, aviso: s.cAviso, mal: s.cMal, apagado: s.cApagado };
const CARRIL: Record<string, string> = { "Evaluaciones del radar de productos": "Evaluaciones de productos" };
const TIPO: Record<string, string> = {
  evaluacion: "Radar de productos",
  precios: "Radar de precios",
  tendencias: "Radar de tendencias",
  oportunidades: "Buscar oportunidades",
  examen: "Examen de clasificación",
  prueba: "Prueba por lote",
};

function cuandoTexto(iso: string | null, ahora: Date): string {
  if (!iso) return "Ahora";
  const d = new Date(iso);
  const manana = new Date(ahora.getTime() + 86_400_000);
  const pref = dia(d) === dia(ahora) ? "Hoy" : dia(d) === dia(manana) ? "Mañana" : mx(d, { weekday: "short" }).replace(".", "");
  return `${pref[0].toUpperCase()}${pref.slice(1)} ${horaCorta(d)}`;
}

function nombreProceso(p: Proceso) {
  return p.nombre.replace(/^Radar de productos: /, "");
}

function Pasos({ detalle }: { detalle: string }) {
  const m = detalle.match(/Paso (\d+) de (\d+)/);
  if (!m) return null;
  const n = Number(m[1]);
  const total = Math.min(12, Number(m[2]));
  return (
    <div className={s.pasos} aria-label={`Paso ${n} de ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={i + 1 < n ? s.hecho : i + 1 === n ? s.actual : ""} />
      ))}
    </div>
  );
}

function Tarjeta({ p }: { p: Proceso }) {
  const paso = p.detalle?.match(/Paso \d+ de \d+/);
  const texto = (p.detalle ?? "").replace(/^Paso \d+ de \d+:?\s*/, "");
  return (
    <div className={`${s.p} ${p.lento ? s.pLento : ""}`}>
      <div className={s.fila}>
        <div className={s.pn}>{nombreProceso(p)}</div>
        {p.minutos !== null && <span className={`${s.pill} ${p.lento ? s.pillA : ""} ${s.num}`}>{lleva(p.minutos)}</span>}
      </div>
      <div className={s.pk}>{TIPO[p.tipo] ?? p.tipo}</div>
      {paso ? (
        <Pasos detalle={p.detalle ?? ""} />
      ) : p.progreso !== null ? (
        <div className={s.barra}>
          <i style={{ width: `${Math.max(2, p.progreso * 100)}%` }} />
        </div>
      ) : null}
      <div className={s.pt}>
        {paso ? `${paso[0]} · ${texto}` : p.detalle}
        {p.lento && <em> · más lento que lo normal</em>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ gráfica en vivo (canvas, se recorre sola)

function GraficaEnVivo({ muestras, llegó }: { muestras: Muestra[]; llegó: number }) {
  const lienzo = useRef<HTMLCanvasElement>(null);
  const datos = useRef({ muestras, llegó });
  datos.current = { muestras, llegó };

  useEffect(() => {
    const cv = lienzo.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const quieto = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let cuadro = 0;
    const dibujar = () => {
      const { muestras: ms, llegó: t0 } = datos.current;
      const W = cv.offsetWidth;
      const H = cv.offsetHeight;
      if (W && H) {
        const escala = (cv.getBoundingClientRect().width / W || 1) * Math.max(1, window.devicePixelRatio || 1);
        if (cv.width !== Math.round(W * escala) || cv.height !== Math.round(H * escala)) {
          cv.width = Math.round(W * escala);
          cv.height = Math.round(H * escala);
        }
        ctx.setTransform(escala, 0, 0, escala, 0, 0);
        ctx.clearRect(0, 0, W, H);
        const izq = 46;
        const der = 40;
        const pad = 8;
        const ancho = W - izq - der;
        const dx = ancho / (PUNTOS - 1);
        const desp = quieto ? 0 : Math.min(1, (performance.now() - t0) / SERIE_MS);
        const maxBus = Math.max(10, Math.ceil(Math.max(0, ...ms.map((m) => m.busquedas)) / 10) * 10);
        const y = (v: number, max: number) => pad + (H - pad * 2) * (1 - Math.min(v, max) / max);
        ctx.font = "13px Geist, Inter, system-ui, sans-serif";
        ctx.textBaseline = "middle";
        for (const v of [0, 25, 50, 75, 100]) {
          const yy = y(v, 100);
          ctx.strokeStyle = "#2a2a28";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(izq, yy);
          ctx.lineTo(W - der, yy);
          ctx.stroke();
          ctx.fillStyle = "#9b9b96";
          ctx.textAlign = "right";
          ctx.fillText(`${v} %`, izq - 8, yy);
          ctx.fillStyle = "#5fb98a";
          ctx.textAlign = "left";
          ctx.fillText(String(Math.round((v / 100) * maxBus)), W - der + 8, yy);
        }
        // El punto más nuevo queda a la derecha; mientras llega el siguiente, todo se recorre un paso a la izquierda
        const x = (i: number) => izq + ancho - (ms.length - 1 - i) * dx - dx * desp + dx;
        const linea = (valor: (m: Muestra) => number | null, max: number, color: string, area: string | null) => {
          const pts = ms.map((m, i) => [x(i), valor(m)] as const).filter((p): p is readonly [number, number] => p[1] !== null);
          if (pts.length < 2) return;
          ctx.beginPath();
          pts.forEach(([px, v], i) => (i ? ctx.lineTo(px, y(v, max)) : ctx.moveTo(px, y(v, max))));
          ctx.strokeStyle = color;
          ctx.lineWidth = 2.5;
          ctx.lineJoin = "round";
          ctx.stroke();
          if (area) {
            ctx.lineTo(pts[pts.length - 1][0], H - pad);
            ctx.lineTo(pts[0][0], H - pad);
            ctx.closePath();
            const g = ctx.createLinearGradient(0, pad, 0, H);
            g.addColorStop(0, area);
            g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g;
            ctx.fill();
          }
          const [lx, lv] = pts[pts.length - 1];
          ctx.beginPath();
          ctx.arc(lx, y(lv, max), 5, 0, 7);
          ctx.fillStyle = color;
          ctx.fill();
        };
        ctx.save();
        ctx.beginPath();
        ctx.rect(izq, 0, ancho + 8, H);
        ctx.clip();
        linea((m) => m.busquedas, maxBus, "#5fb98a", null);
        linea((m) => m.ia, 100, "#7fb2e5", "rgba(127,178,229,.16)");
        linea((m) => m.cpu, 100, "#de951b", "rgba(222,149,27,.16)");
        ctx.restore();
      }
      cuadro = requestAnimationFrame(dibujar);
    };
    cuadro = requestAnimationFrame(dibujar);
    return () => cancelAnimationFrame(cuadro);
  }, []);

  return (
    <div className={s.lienzo}>
      <canvas ref={lienzo} aria-label="Gráfica en vivo de procesador, IA local y búsquedas por minuto" />
      {muestras.length < 2 && <div className={s.esperando}>Juntando las primeras muestras…</div>}
    </div>
  );
}

// ------------------------------------------------------------------ pantalla

export default function MonitorPage() {
  const [d, setD] = useState<Monitor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ultima, setUltima] = useState<number | null>(null);
  const [reloj, setReloj] = useState(() => new Date());
  const [serie, setSerie] = useState<Muestra[]>([]);
  const [llegó, setLlegó] = useState(0);
  const [completa, setCompleta] = useState(false);
  const [vista, setVista] = useState({ k: 1, x: 0, y: 0 });
  const raiz = useRef<HTMLDivElement>(null);

  const ajustar = useCallback(() => {
    const k = Math.min(window.innerWidth / ANCHO, window.innerHeight / ALTO);
    setVista({ k, x: (window.innerWidth - ANCHO * k) / 2, y: (window.innerHeight - ALTO * k) / 2 });
  }, []);

  useEffect(() => {
    let vivo = true;
    const traer = () =>
      api<Monitor>("/api/nucleo/en-vivo/monitor")
        .then((r) => {
          if (!vivo) return;
          setD(r);
          setError(null);
          setUltima(Date.now());
        })
        .catch((e: Error) => vivo && setError(e.message));
    const traerSerie = () =>
      api<{ muestras: Muestra[] }>("/api/nucleo/en-vivo/monitor/serie")
        .then((r) => {
          if (!vivo) return;
          setSerie(r.muestras.slice(-PUNTOS));
          setLlegó(performance.now());
        })
        .catch(() => undefined);
    // Cada consulta espera a que termine la anterior (26 nov 2026: con la base lenta, setInterval apilaba peticiones
    // hasta agotar las conexiones de la API)
    let t1: ReturnType<typeof setTimeout> | undefined;
    let t2: ReturnType<typeof setTimeout> | undefined;
    const cicloDatos = () => traer().finally(() => { if (vivo) t1 = setTimeout(cicloDatos, CADA_MS); });
    const cicloSerie = () => traerSerie().finally(() => { if (vivo) t2 = setTimeout(cicloSerie, SERIE_MS); });
    cicloDatos();
    cicloSerie();
    const t3 = setInterval(() => setReloj(new Date()), 1000);
    const fs = () => setCompleta(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", fs);
    ajustar();
    window.addEventListener("resize", ajustar);
    // Que la pantalla no se apague mientras el Monitor está abierto (si el navegador lo permite)
    let candado: { release: () => Promise<void> } | null = null;
    const despierta = () =>
      (navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } }).wakeLock
        ?.request("screen")
        .then((c) => (candado = c))
        .catch(() => undefined);
    despierta();
    const visible = () => document.visibilityState === "visible" && despierta();
    document.addEventListener("visibilitychange", visible);
    return () => {
      vivo = false;
      clearTimeout(t1);
      clearTimeout(t2);
      clearInterval(t3);
      document.removeEventListener("fullscreenchange", fs);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("resize", ajustar);
      candado?.release().catch(() => undefined);
    };
  }, [ajustar]);

  const pantallaCompleta = () => (document.fullscreenElement ? document.exitFullscreen() : raiz.current?.requestFullscreen())?.catch(() => undefined);
  const hace = ultima ? Math.round((reloj.getTime() - ultima) / 1000) : null;
  const viejo = hace !== null && hace > 30;

  // Semáforo: cuadros de salud en rojo o ámbar + procesos lentos
  const malos = d?.salud.filter((c) => c.estado === "mal").length ?? 0;
  const avisos = (d?.salud.filter((c) => c.estado === "aviso").length ?? 0) + (d?.procesos.filter((p) => p.lento).length ?? 0);
  const revisar = malos + avisos;
  const sem = !d ? null : revisar === 0 ? { c: s.semOk, t: "Todo en orden" } : { c: malos ? s.semMal : s.semAviso, t: revisar === 1 ? "1 cosa por revisar" : `${revisar} cosas por revisar` };

  // Línea de tiempo: de (ahora − horas) a ahora
  const fin = d ? new Date(d.ahora).getTime() : reloj.getTime();
  const inicio = fin - (d?.horas ?? 12) * 3600_000;
  const pos = (t: number) => ((Math.min(Math.max(t, inicio), fin) - inicio) / (fin - inicio)) * 100;
  const marcas: number[] = [];
  for (let t = Math.ceil(inicio / 3600_000) * 3600_000; t <= fin - 15 * 60_000; t += 3600_000) marcas.push(t);
  const procesos = [...(d?.procesos ?? [])].sort((a, b) => Number(b.lento) - Number(a.lento) || (b.minutos ?? 0) - (a.minutos ?? 0));

  const ultimaMuestra = serie[serie.length - 1];
  const iaNombre = ultimaMuestra?.ia_fuente === "tarjeta" ? "Tarjeta de video (IA)" : "IA local trabajando";
  const ev = d?.hoy.evaluaciones;
  const noche = d?.hoy.noche;
  const bus = d?.hoy.busquedas;
  const totalBus = (bus?.aceptadas ?? 0) + (bus?.rechazadas ?? 0);
  const dfs = d?.servidor.dataforseo;

  return (
    <div ref={raiz} className={s.fondo}>
      <div className={s.escenario} style={{ transform: `translate(${vista.x}px, ${vista.y}px) scale(${vista.k})` }}>
        <div className={s.top}>
          <div className={s.logo}>
            <i>S</i>Súper Naturista <span>· Monitor de la plataforma</span>
          </div>
          <div className={s.reloj}>
            <b className={s.num}>{horaCorta(reloj).replace(/\s?[ap]\.?\s?m\.?/i, "")}</b>
            <small>
              {mx(reloj, { weekday: "long" })}
              <br />
              {mx(reloj, { day: "numeric", month: "short", year: "numeric" }).replace(".", "")}
            </small>
          </div>
          {sem && (
            <div className={`${s.sem} ${sem.c}`} role="status">
              <span className={s.dot} />
              {sem.t}
            </div>
          )}
          <div className={`${s.vivo} ${error || viejo ? s.vivoMal : ""}`} style={sem ? undefined : { marginLeft: "auto" }}>
            <span className={s.dot} style={{ background: error || viejo ? "var(--amb)" : "var(--ok)" }} />
            {error ? "Sin conexión con la API" : hace === null ? "Conectando…" : viejo ? `Sin datos nuevos hace ${hace} s` : "En vivo"}
            {d?.version ? ` · ${d.version}` : ""}
          </div>
          <div className={s.botones}>
            <button type="button" className={s.boton} onClick={pantallaCompleta}>
              {completa ? <Minimize size={15} /> : <Expand size={15} />}
              {completa ? "Salir" : "Pantalla completa"}
            </button>
            <Link href="/admin/sistema" className={s.boton} aria-label="Cerrar el Monitor">
              <X size={15} />
            </Link>
          </div>
        </div>

        <div className={s.salud}>
          {(d?.salud ?? []).map((c) => (
            <div key={c.clave} className={`${s.s} ${c.estado === "aviso" ? s.sAviso : c.estado === "mal" ? s.sMal : ""}`} title={c.detalle}>
              <b>
                <span className={`${s.dot} ${COLOR[c.estado]}`} />
                {c.nombre}
              </b>
              <small>{c.detalle}</small>
            </div>
          ))}
        </div>

        <div className={s.main}>
          <div className={`${s.col} ${s.izq}`}>
            <div className={s.card}>
              <h2 className={s.h2}>
                Corriendo ahora <em>{procesos.length === 1 ? "1 proceso" : `${procesos.length} procesos`}</em>
                {procesos.length > 3 && <em>se ven los 3 que llevan más</em>}
              </h2>
              <div className={s.proc}>
                {!d ? (
                  <div className={s.libre}>Consultando…</div>
                ) : procesos.length === 0 ? (
                  <div className={s.libre}>Nada pesado corriendo. El servidor está libre.</div>
                ) : (
                  procesos.slice(0, 3).map((p, i) => <Tarjeta key={`${p.nombre}-${i}`} p={p} />)
                )}
              </div>
            </div>

            <div className={s.card}>
              <h2 className={s.h2}>
                Últimas {d?.horas ?? 12} horas
                <span className={s.ley}>
                  <span>
                    <i style={{ background: "var(--nar)" }} />
                    corriendo
                  </span>
                  <span>
                    <i style={{ background: "#55554f" }} />
                    terminó
                  </span>
                  <span>
                    <i style={{ background: "var(--amb)" }} />
                    falló o se cortó
                  </span>
                </span>
              </h2>
              <div className={s.lt}>
                {(d?.carriles ?? []).map((carril, ci) => (
                  <Carril key={carril} nombre={carril} primero={ci === 0}>
                    {d!.linea
                      .filter((b) => b.carril === carril)
                      .map((b, i) => {
                        const a = pos(new Date(b.inicio).getTime());
                        const z = b.fin ? pos(new Date(b.fin).getTime()) : 100;
                        const clase = b.estado === "en_curso" ? s.bOn : fallo(b.estado) ? s.bX : "";
                        const desde = horaCorta(new Date(b.inicio));
                        const hasta = b.fin ? horaCorta(new Date(b.fin)) : "ahora";
                        return <div key={i} className={`${s.b} ${clase}`} style={{ left: `${a}%`, width: `${Math.max(0.4, z - a)}%` }} title={`${b.nombre} · ${desde} a ${hasta}`} />;
                      })}
                  </Carril>
                ))}
                <div />
                <div className={`${s.horas} ${s.num}`}>
                  {marcas.map((t) => (
                    <span key={t} style={{ left: `${pos(t)}%` }}>
                      {mx(new Date(t), { hour: "numeric" }).replace(/\s?([ap])\.?\s?m\.?/i, " $1.m.")}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className={`${s.card} ${s.vivoCard}`}>
              <h2 className={s.h2}>
                Actividad en vivo <em>últimos 5 minutos · cada 2 s</em>
                <span className={s.ley2}>
                  <span>
                    <i style={{ background: "var(--nar)" }} />
                    Procesador <b className={s.num}>{ultimaMuestra?.cpu != null ? `${Math.round(ultimaMuestra.cpu)} %` : "–"}</b>
                  </span>
                  <span>
                    <i style={{ background: "var(--gpu)" }} />
                    {iaNombre} <b className={s.num}>{ultimaMuestra?.ia != null ? `${Math.round(ultimaMuestra.ia)} %` : "–"}</b>
                  </span>
                  <span>
                    <i style={{ background: "var(--ok)" }} />
                    Búsquedas por minuto <b className={s.num}>{ultimaMuestra ? ultimaMuestra.busquedas : "–"}</b>
                  </span>
                </span>
              </h2>
              <GraficaEnVivo muestras={serie} llegó={llegó} />
            </div>
          </div>

          <div className={`${s.col} ${s.der}`}>
            <div className={s.card}>
              <h2 className={s.h2}>Hoy en números</h2>
              <div className={s.kpis}>
                <div className={s.kpi}>
                  <div className={`${s.kv} ${s.num}`}>
                    {ev ? miles(ev.terminadas) : "–"}
                    <small>{ev?.terminadas === 1 ? "evaluación" : "evaluaciones"}</small>
                  </div>
                  <div className={s.kl}>terminadas hoy{ev ? ` · ${ev.en_curso} en curso` : ""}</div>
                  <div className={`${s.kd} ${ev?.con_error ? s.kdA : ev?.minutos_promedio == null ? s.kdN : ""}`}>
                    {ev?.con_error
                      ? `${ev.con_error} con error`
                      : ev?.minutos_promedio != null
                        ? `tardan ${ev.minutos_promedio.toLocaleString("es-MX")} min en promedio`
                        : "todavía sin tiempos de hoy"}
                  </div>
                </div>
                <div className={s.kpi}>
                  <div className={`${s.kv} ${s.num}`}>{noche ? miles(noche.productos) : "–"}</div>
                  <div className={s.kl}>productos revisados anoche{noche?.lotes ? ` · ${noche.lotes} lotes` : ""}</div>
                  <div className={`${s.kd} ${noche?.productos ? "" : s.kdN}`}>
                    {noche?.productos ? `${miles(noche.con_precio)} con precio de afuera (${Math.round((100 * noche.con_precio) / noche.productos)} %)` : "el lote empieza en la noche"}
                  </div>
                </div>
                <div className={s.kpi}>
                  <div className={`${s.kv} ${s.num}`}>
                    {totalBus ? Math.round((100 * (bus?.aceptadas ?? 0)) / totalBus) : "–"}
                    {totalBus ? <small>%</small> : null}
                  </div>
                  <div className={s.kl}>búsquedas aceptadas por DataForSEO</div>
                  <div className={`${s.kd} ${bus?.rechazadas ? s.kdA : totalBus ? "" : s.kdN}`}>
                    {bus?.rechazadas ? `${miles(bus.rechazadas)} rechazadas de ${miles(totalBus)}` : totalBus ? `${miles(totalBus)} hoy, ninguna rechazada` : "ninguna búsqueda hoy"}
                  </div>
                </div>
                <div className={s.kpi}>
                  <div className={`${s.kv} ${s.num}`}>{bus ? `US$${bus.gasto_usd.toFixed(2)}` : "–"}</div>
                  <div className={s.kl}>gasto de hoy en búsquedas</div>
                  <div className={`${s.kd} ${dfs?.tope_mes && (dfs.gasto_mes ?? 0) >= 0.9 * dfs.tope_mes ? s.kdA : s.kdN}`}>
                    {dfs?.gasto_mes != null ? `US$${dfs.gasto_mes.toFixed(2)} en el mes${dfs.tope_mes ? ` de ${dfs.tope_mes.toFixed(0)} de tope` : ""}` : ""}
                  </div>
                </div>
              </div>
            </div>

            <div className={`${s.card} ${s.sigue}`}>
              <h2 className={s.h2}>Lo que sigue</h2>
              {d && d.sigue.length === 0 ? (
                <p className={s.vacio}>Nada programado por ahora.</p>
              ) : (
                <ul className={s.lista}>
                  {(d?.sigue ?? []).slice(0, 4).map((x, i) => (
                    <li key={i}>
                      <span className={`${s.h} ${s.num}`}>{cuandoTexto(x.cuando, reloj)}</span>
                      <div>
                        {x.que}
                        {x.detalle && <small>{x.detalle}</small>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className={`${s.card} ${s.av}`}>
              <h2 className={s.h2}>
                Avisos y errores <em>desde que arrancó la API</em>
              </h2>
              {d && d.grupos.length === 0 ? (
                <p className={s.vacio}>Sin avisos ni errores.</p>
              ) : (
                <ul className={s.lista}>
                  {(d?.grupos ?? []).map((g, i) => (
                    <li key={i}>
                      <span className={`${s.cnt} ${g.nivel === "error" ? s.cntR : s.cntA} ${s.num}`}>{g.veces}</span>
                      <div>
                        <p>{g.mensaje}</p>
                        <small>
                          {g.nivel === "error" ? "Error" : "Aviso"} · {g.origen} · {g.veces > 1 ? "la última " : ""}
                          {horaCorta(new Date(g.hora))}
                        </small>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Carril({ nombre, primero, children }: { nombre: string; primero: boolean; children: React.ReactNode }) {
  return (
    <>
      <div className={s.c}>{CARRIL[nombre] ?? nombre}</div>
      <div className={s.carril}>
        {children}
        <div className={s.ahora}>{primero && <span className={s.ahoraTxt}>ahora</span>}</div>
      </div>
    </>
  );
}
