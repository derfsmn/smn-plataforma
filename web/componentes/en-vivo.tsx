"use client";

// Qué está corriendo ahora y bitácora en vivo de la API (Diego, 26 nov 2026: «un log visible en el sitio para ver
// qué se está corriendo»). Se actualiza sola cada 5 segundos.
import { Activity, MonitorPlay, Pause, Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Proceso = { tipo: string; nombre: string; detalle: string | null; minutos: number | null; lento: boolean };
type Linea = { n: number; hora: string; nivel: "info" | "aviso" | "error" | "detalle"; origen: string; mensaje: string };
type Respuesta = { procesos: Proceso[]; bitacora: Linea[]; guarda: number; ultima: number };

const CADA_MS = 5000;
const hora = (iso: string) =>
  new Date(iso).toLocaleTimeString("es-MX", { timeZone: "America/Mexico_City", hour: "2-digit", minute: "2-digit", second: "2-digit" });
const lleva = (m: number | null) => (m === null ? "" : m < 1 ? "menos de 1 min" : m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);

export function EnVivo() {
  const [procesos, setProcesos] = useState<Proceso[] | null>(null);
  const [lineas, setLineas] = useState<Linea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pausa, setPausa] = useState(false);
  const [soloAvisos, setSoloAvisos] = useState(false);
  const ultima = useRef(0);
  const guarda = useRef(300);

  useEffect(() => {
    if (pausa) return;
    let vivo = true;
    const traer = () =>
      api<Respuesta>(`/api/nucleo/en-vivo?desde=${ultima.current}`)
        .then((r) => {
          if (!vivo) return;
          setError(null);
          setProcesos(r.procesos);
          guarda.current = r.guarda;
          // Si la API se reinició, su numeración vuelve a empezar: se borra lo de antes y se toma todo de nuevo
          if (r.ultima < ultima.current) {
            ultima.current = 0;
            setLineas([]);
            return;
          }
          const nuevas = r.bitacora;
          if (nuevas.length) {
            ultima.current = nuevas[nuevas.length - 1].n;
            setLineas((l) => [...nuevas.slice().reverse(), ...l].slice(0, guarda.current));
          }
        })
        .catch((e: Error) => vivo && setError(e.message));
    traer();
    const t = setInterval(traer, CADA_MS);
    return () => {
      vivo = false;
      clearInterval(t);
    };
  }, [pausa]);

  const visibles = soloAvisos ? lineas.filter((l) => l.nivel === "aviso" || l.nivel === "error") : lineas;

  return (
    <div className="mt-8 grid gap-6">
      <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-smn-naranja" />
          <h2 className="flex-1 text-lg font-semibold">Qué está corriendo ahora</h2>
          <Link href="/admin/monitor" className="inline-flex items-center gap-1.5 rounded-full bg-smn-naranja px-3 py-1.5 text-sm font-semibold text-smn-negro hover:opacity-90">
            <MonitorPlay className="h-4 w-4" /> Abrir monitor
          </Link>
        </div>
        <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">
          Los procesos pesados que comparten el servidor (búsquedas en internet, tiendas e IA local). Se actualiza cada 5 segundos.
        </p>
        {error && <p className="mb-3 rounded-xl bg-aviso-fondo px-3 py-2 text-sm text-aviso-texto">No se pudo consultar: {error}</p>}
        {procesos === null ? (
          <p className="py-6 text-center text-sm text-smn-gris-500">Consultando…</p>
        ) : procesos.length === 0 ? (
          <p className="py-6 text-center text-sm text-smn-gris-500">Nada pesado corriendo. El servidor está libre.</p>
        ) : (
          <ul className="divide-y divide-smn-gris-100">
            {procesos.map((p, i) => (
              <li key={`${p.nombre}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2.5">
                <span className="relative flex h-2.5 w-2.5 shrink-0 self-center">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-smn-naranja opacity-60" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-smn-naranja" />
                </span>
                <span className="min-w-0 flex-1 text-[15px] font-semibold">{p.nombre}</span>
                {p.minutos !== null && (
                  <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-semibold ${p.lento ? "bg-aviso-fondo text-aviso-texto" : "bg-smn-gris-50 text-smn-gris-700"}`}>
                    {p.lento ? "lleva " : ""}
                    {lleva(p.minutos)}
                  </span>
                )}
                {p.detalle && <span className="basis-full pl-5 text-sm text-smn-gris-500">{p.detalle}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="flex-1 text-lg font-semibold">Bitácora en vivo</h2>
          <label className="flex items-center gap-2 text-sm text-smn-gris-700">
            <input type="checkbox" checked={soloAvisos} onChange={(e) => setSoloAvisos(e.target.checked)} />
            Solo avisos y errores
          </label>
          <button
            onClick={() => setPausa((x) => !x)}
            className="inline-flex items-center gap-1.5 rounded-full border border-smn-gris-300 px-3 py-1 text-sm font-semibold hover:bg-smn-gris-50"
          >
            {pausa ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
            {pausa ? "Seguir" : "Pausar"}
          </button>
        </div>
        <p className="mt-0.5 mb-4 text-sm text-smn-gris-500">
          Lo que va haciendo la API, lo más nuevo arriba (últimas {guarda.current} líneas desde que arrancó; hora de México).
        </p>
        {visibles.length === 0 ? (
          <p className="py-6 text-center text-sm text-smn-gris-500">{soloAvisos ? "Sin avisos ni errores." : "Todavía no hay líneas."}</p>
        ) : (
          <ol className="max-h-[32rem] overflow-y-auto rounded-xl bg-smn-gris-50 p-2 font-mono text-[13px] leading-relaxed">
            {visibles.map((l) => (
              <li
                key={l.n}
                className={`grid grid-cols-[auto_1fr] gap-x-3 rounded-lg px-2 py-1 sm:grid-cols-[auto_9rem_1fr] ${
                  l.nivel === "error" || l.nivel === "aviso" ? "bg-aviso-fondo text-aviso-texto" : ""
                }`}
              >
                <span className="text-smn-gris-500">{hora(l.hora)}</span>
                <span className="hidden truncate text-smn-gris-500 sm:block">{l.origen}</span>
                <span className="col-span-2 break-words sm:col-span-1">
                  {l.nivel === "error" ? "Error: " : l.nivel === "aviso" ? "Aviso: " : ""}
                  {l.mensaje}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
