"use client";

// Monitor de pantalla completa para dejarlo abierto (Diego, 26 nov 2026): estado del servidor, lo que corre ahora con
// su avance, línea de tiempo de las últimas 12 horas y los últimos avisos. Se actualiza solo cada 5 segundos.
import { Cpu, Expand, MemoryStick, Minimize, Sparkles, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Proceso = { tipo: string; nombre: string; detalle: string | null; minutos: number | null; lento: boolean; muy_lento: boolean; progreso: number | null };
type Barra = { carril: string; nombre: string; inicio: string; fin: string | null; estado: string };
type Aviso = { n: number; hora: string; nivel: string; origen: string; mensaje: string };
type Monitor = {
  ahora: string;
  horas: number;
  carriles: string[];
  servidor: {
    sistema: { cpu_pct: number | null; memoria_pct: number | null; memoria_gb: number | null; gpu: { nombre: string; uso_pct: number; memoria_pct: number }[] };
    ia: { responde: boolean | null; modelos: { nombre: string; en_video_gb: number }[] };
    dataforseo: { gasto_mes: number | null; tope_mes: number | null };
  };
  procesos: Proceso[];
  linea: Barra[];
  avisos: Aviso[];
};

const CADA_MS = 5000;
const ZONA = "America/Mexico_City";
const horaMx = (d: Date, segundos = false) =>
  d.toLocaleTimeString("es-MX", { timeZone: ZONA, hour: "2-digit", minute: "2-digit", ...(segundos ? { second: "2-digit" } : {}) });
const lleva = (m: number | null) => (m === null ? "" : m < 1 ? "menos de 1 min" : m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);
const terminado = (e: string) => ["lista", "listo", "completa"].includes(e);
const fallo = (e: string) => ["fallida", "error", "parcial"].includes(e);

function Medidor({ icono, titulo, valor, pct, nota, alerta }: { icono: React.ReactNode; titulo: string; valor: string; pct?: number | null; nota?: string; alerta?: boolean }) {
  return (
    <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <div className="flex items-center gap-2 text-sm text-smn-gris-500">
        {icono}
        {titulo}
      </div>
      <p className={`mt-1 text-3xl font-semibold tabular-nums ${alerta ? "text-aviso-texto" : ""}`}>{valor}</p>
      {pct !== undefined && pct !== null && (
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-smn-gris-100">
          <div className={`h-full rounded-full ${alerta ? "bg-aviso-texto" : "bg-smn-naranja"}`} style={{ width: `${Math.min(100, Math.max(2, pct))}%` }} />
        </div>
      )}
      {nota && <p className="mt-1.5 truncate text-[13px] text-smn-gris-500">{nota}</p>}
    </div>
  );
}

export default function MonitorPage() {
  const [d, setD] = useState<Monitor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ultima, setUltima] = useState<Date | null>(null);
  const [reloj, setReloj] = useState(new Date());
  const [completa, setCompleta] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let vivo = true;
    const traer = () =>
      api<Monitor>("/api/nucleo/en-vivo/monitor")
        .then((r) => {
          if (!vivo) return;
          setD(r);
          setError(null);
          setUltima(new Date());
        })
        .catch((e: Error) => vivo && setError(e.message));
    traer();
    const t = setInterval(traer, CADA_MS);
    const r = setInterval(() => setReloj(new Date()), 1000);
    const fs = () => setCompleta(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", fs);
    return () => {
      vivo = false;
      clearInterval(t);
      clearInterval(r);
      document.removeEventListener("fullscreenchange", fs);
    };
  }, []);

  const pantallaCompleta = () => (document.fullscreenElement ? document.exitFullscreen() : raiz.current?.requestFullscreen());
  const hace = ultima ? Math.round((reloj.getTime() - ultima.getTime()) / 1000) : null;
  const viejo = hace !== null && hace > 30;

  const s = d?.servidor;
  const gasto = s?.dataforseo;
  const gastoPct = gasto?.gasto_mes != null && gasto?.tope_mes ? (100 * gasto.gasto_mes) / gasto.tope_mes : null;

  // Línea de tiempo: de (ahora − horas) a ahora
  const fin = d ? new Date(d.ahora).getTime() : reloj.getTime();
  const inicio = fin - (d?.horas ?? 12) * 3600_000;
  const x = (t: number) => ((Math.min(Math.max(t, inicio), fin) - inicio) / (fin - inicio)) * 100;
  const marcas = Array.from({ length: (d?.horas ?? 12) + 1 }, (_, i) => {
    const t = new Date(inicio + i * 3600_000);
    t.setMinutes(0, 0, 0);
    return t.getTime() + 3600_000;
  }).filter((t) => t > inicio && t <= fin);

  return (
    <div ref={raiz} className="fixed inset-0 z-50 overflow-y-auto bg-fondo p-4 text-tinta sm:p-6">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">Monitor</h1>
        <span className="text-2xl font-semibold tabular-nums text-smn-gris-500 sm:text-3xl">{horaMx(reloj, true)}</span>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${error || viejo ? "bg-aviso-fondo text-aviso-texto" : "bg-smn-gris-50 text-smn-gris-700"}`}>
          {error ? `Sin conexión: ${error}` : hace === null ? "Conectando…" : viejo ? `Sin datos nuevos desde hace ${hace} s` : "En vivo"}
        </span>
        <div className="ml-auto flex gap-2">
          <button onClick={pantallaCompleta} className="inline-flex items-center gap-1.5 rounded-full border border-smn-gris-300 px-3 py-1.5 text-sm font-semibold hover:bg-smn-gris-50">
            {completa ? <Minimize className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
            {completa ? "Salir de pantalla completa" : "Pantalla completa"}
          </button>
          <Link href="/admin/sistema" className="inline-flex items-center gap-1.5 rounded-full border border-smn-gris-300 px-3 py-1.5 text-sm font-semibold hover:bg-smn-gris-50">
            <X className="h-4 w-4" /> Cerrar
          </Link>
        </div>
      </header>

      {/* 1. Estado del servidor */}
      <section className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <Medidor
          icono={<Sparkles className="h-4 w-4" />}
          titulo="IA local"
          valor={!s ? "—" : s.ia.responde === false ? "No responde" : s.ia.modelos.length ? "Ocupada" : "Libre"}
          alerta={s?.ia.responde === false}
          nota={s?.ia.modelos.length ? s.ia.modelos.map((m) => `${m.nombre}${m.en_video_gb ? ` · ${m.en_video_gb} GB` : ""}`).join(" · ") : s?.ia.responde ? "Sin modelos cargados" : undefined}
        />
        <Medidor
          icono={<Wallet className="h-4 w-4" />}
          titulo="DataForSEO del mes"
          valor={gasto?.gasto_mes != null ? `US$${gasto.gasto_mes.toFixed(2)}` : "—"}
          pct={gastoPct}
          alerta={gastoPct !== null && gastoPct >= 90}
          nota={gasto?.tope_mes ? `de US$${gasto.tope_mes.toFixed(2)} de tope` : undefined}
        />
        <Medidor icono={<Cpu className="h-4 w-4" />} titulo="Procesador" valor={s?.sistema.cpu_pct != null ? `${s.sistema.cpu_pct} %` : "—"} pct={s?.sistema.cpu_pct} alerta={(s?.sistema.cpu_pct ?? 0) >= 90} nota="carga del último minuto" />
        <Medidor
          icono={<MemoryStick className="h-4 w-4" />}
          titulo="Memoria"
          valor={s?.sistema.memoria_pct != null ? `${s.sistema.memoria_pct} %` : "—"}
          pct={s?.sistema.memoria_pct}
          alerta={(s?.sistema.memoria_pct ?? 0) >= 90}
          nota={s?.sistema.memoria_gb ? `de ${s.sistema.memoria_gb} GB` : undefined}
        />
        {s?.sistema.gpu.length ? (
          s.sistema.gpu.map((g) => (
            <Medidor key={g.nombre} icono={<Cpu className="h-4 w-4" />} titulo="Tarjeta de video" valor={`${g.uso_pct} %`} pct={g.uso_pct} alerta={g.uso_pct >= 95} nota={`${g.nombre} · memoria ${g.memoria_pct} %`} />
          ))
        ) : (
          <Medidor icono={<Cpu className="h-4 w-4" />} titulo="Tarjeta de video" valor="—" nota="la API no la puede leer; ver IA local" />
        )}
      </section>

      {/* 2. Lo que corre ahora */}
      <section className="mt-6">
        <h2 className="mb-3 text-lg font-semibold">Corriendo ahora</h2>
        {!d ? (
          <p className="text-smn-gris-500">Consultando…</p>
        ) : d.procesos.length === 0 ? (
          <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-6 text-center text-xl text-smn-gris-500">Nada pesado corriendo. El servidor está libre.</div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {d.procesos.map((p, i) => (
              <div key={`${p.nombre}-${i}`} className={`rounded-2xl border bg-superficie p-4 ${p.muy_lento ? "border-aviso-texto" : p.lento ? "border-aviso-fondo" : "border-smn-gris-100"}`}>
                <div className="flex items-start gap-3">
                  <span className="relative mt-2 flex h-3 w-3 shrink-0">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-smn-naranja opacity-60" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-smn-naranja" />
                  </span>
                  <p className="min-w-0 flex-1 text-lg font-semibold leading-snug">{p.nombre}</p>
                  {p.minutos !== null && (
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-sm font-semibold ${p.lento ? "bg-aviso-fondo text-aviso-texto" : "bg-smn-gris-50 text-smn-gris-700"}`}>{lleva(p.minutos)}</span>
                  )}
                </div>
                {p.progreso !== null && (
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-smn-gris-100">
                    <div className="h-full rounded-full bg-smn-naranja transition-all duration-700" style={{ width: `${Math.max(3, p.progreso * 100)}%` }} />
                  </div>
                )}
                {p.detalle && <p className="mt-2 text-sm text-smn-gris-500">{p.detalle}</p>}
                {p.muy_lento && <p className="mt-1 text-sm font-semibold text-aviso-texto">Lleva mucho más de lo normal</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 3. Línea de tiempo */}
      <section className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
        <div className="mb-3 flex flex-wrap items-baseline gap-x-4">
          <h2 className="text-lg font-semibold">Últimas {d?.horas ?? 12} horas</h2>
          <span className="flex items-center gap-1.5 text-sm text-smn-gris-500"><i className="inline-block h-2.5 w-4 rounded bg-smn-naranja" /> corriendo</span>
          <span className="flex items-center gap-1.5 text-sm text-smn-gris-500"><i className="inline-block h-2.5 w-4 rounded bg-smn-gris-300" /> terminó</span>
          <span className="flex items-center gap-1.5 text-sm text-smn-gris-500"><i className="inline-block h-2.5 w-4 rounded bg-aviso-texto" /> falló o se cortó</span>
        </div>
        <div className="grid grid-cols-[minmax(7rem,12rem)_1fr] gap-x-3">
          {(d?.carriles ?? []).map((c) => {
            const barras = (d?.linea ?? []).filter((b) => b.carril === c);
            return (
              <div key={c} className="contents">
                <div className="flex items-center py-2 text-sm text-smn-gris-700">{c}</div>
                <div className="relative my-1 h-8 rounded-lg bg-smn-gris-50">
                  {marcas.map((t) => (
                    <span key={t} className="absolute inset-y-0 w-px bg-smn-gris-100" style={{ left: `${x(t)}%` }} />
                  ))}
                  {barras.map((b, i) => {
                    const a = new Date(b.inicio).getTime();
                    const z = b.fin ? new Date(b.fin).getTime() : fin;
                    const izq = x(a);
                    const ancho = Math.max(0.4, x(z) - izq);
                    const color = !b.fin && !terminado(b.estado) && !fallo(b.estado) ? "bg-smn-naranja" : fallo(b.estado) ? "bg-aviso-texto" : "bg-smn-gris-300";
                    return (
                      <span
                        key={`${b.inicio}-${i}`}
                        title={`${b.nombre}\n${horaMx(new Date(a))} – ${b.fin ? horaMx(new Date(z)) : "sigue"} · ${b.estado}`}
                        className={`absolute top-1.5 bottom-1.5 rounded ${color} opacity-90`}
                        style={{ left: `${izq}%`, width: `${ancho}%` }}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
          <div />
          <div className="relative h-5">
            {marcas.map((t) => (
              <span key={t} className="absolute -translate-x-1/2 text-xs tabular-nums text-smn-gris-500" style={{ left: `${x(t)}%` }}>
                {new Date(t).toLocaleTimeString("es-MX", { timeZone: ZONA, hour: "numeric" })}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* 4. Avisos */}
      <section className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
        <h2 className="mb-2 text-lg font-semibold">Últimos avisos y errores</h2>
        {!d || d.avisos.length === 0 ? (
          <p className="text-smn-gris-500">Sin avisos desde que arrancó la plataforma.</p>
        ) : (
          <ul className="divide-y divide-smn-gris-100">
            {d.avisos.map((a) => (
              <li key={a.n} className="flex gap-3 py-2 text-[15px]">
                <span className="shrink-0 tabular-nums text-smn-gris-500">{horaMx(new Date(a.hora))}</span>
                <span className={a.nivel === "error" ? "font-semibold text-aviso-texto" : ""}>
                  {a.nivel === "error" ? "Error: " : ""}
                  {a.mensaje}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
