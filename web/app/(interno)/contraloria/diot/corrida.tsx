"use client";
// TD003 · DIOT: los pasos del proceso de Fiscal y su bitácora, en vivo mientras corre y de cada corrida anterior.

import { AlertTriangle, CheckCircle2, ChevronRight, CircleDashed, ExternalLink, Info, Loader2, MinusCircle, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { RUTA, type Corrida, type CorridaResumen, type EstadoCorrida, type EstadoPaso, type LineaBitacora, type Periodo } from "@/lib/diot";

const ESTADO_CORRIDA: Record<EstadoCorrida, { texto: string; clase: string }> = {
  en_curso: { texto: "Procesando", clase: "bg-smn-naranja/15 text-naranja-tinta" },
  terminada: { texto: "Terminada", clase: "bg-emerald-100 text-emerald-700" },
  detenida: { texto: "Se detuvo", clase: "bg-amber-100 text-amber-800" },
  fallida: { texto: "Falló", clase: "bg-red-100 text-red-700" },
};

const ESTADO_PASO: Record<EstadoPaso, { texto: string; borde: string; icono: React.ReactNode }> = {
  pendiente: { texto: "Pendiente", borde: "border-smn-gris-100", icono: <CircleDashed className="h-5 w-5 text-smn-gris-500" /> },
  en_curso: { texto: "En curso", borde: "border-smn-naranja", icono: <Loader2 className="h-5 w-5 animate-spin text-naranja-tinta" /> },
  ok: { texto: "Correcto", borde: "border-emerald-300", icono: <CheckCircle2 className="h-5 w-5 text-emerald-600" /> },
  aviso: { texto: "Con avisos", borde: "border-amber-300", icono: <AlertTriangle className="h-5 w-5 text-amber-600" /> },
  detenido: { texto: "Detenido", borde: "border-red-300", icono: <XCircle className="h-5 w-5 text-red-700" /> },
  no_ejecutado: { texto: "No se ejecutó", borde: "border-smn-gris-100", icono: <MinusCircle className="h-5 w-5 text-smn-gris-500" /> },
};

const NIVEL: Record<LineaBitacora["nivel"], { icono: React.ReactNode; clase: string }> = {
  info: { icono: <Info className="h-3.5 w-3.5 text-smn-gris-500" />, clase: "" },
  ok: { icono: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />, clase: "" },
  aviso: { icono: <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />, clase: "text-amber-800 dark:text-amber-300" },
  error: { icono: <XCircle className="h-3.5 w-3.5 text-red-700" />, clase: "text-red-700 dark:text-red-400" },
};

const hora = (f: string) => fechaLocal(f, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const duracion = (a: string | null, b: string | null) => {
  if (!a || !b) return "";
  const s = (new Date(b.endsWith("Z") ? b : `${b}Z`).getTime() - new Date(a.endsWith("Z") ? a : `${a}Z`).getTime()) / 1000;
  return s < 1 ? "menos de 1 s" : `${s.toFixed(s < 10 ? 1 : 0)} s`;
};

export function PasosDelProceso({ p, alTerminar }: { p: Periodo; alTerminar: () => void }) {
  const [historial, setHistorial] = useState<CorridaResumen[]>([]);
  const [id, setId] = useState<number | null>(p.corrida?.id ?? null);
  const [c, setC] = useState<Corrida | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<number | null>(null);
  const caja = useRef<HTMLDivElement>(null);
  const terminar = useRef(alTerminar);
  terminar.current = alTerminar;

  // Una corrida nueva (al dar «Procesar») se muestra en cuanto arranca
  useEffect(() => {
    setId(p.corrida?.id ?? null);
    setFiltro(null);
  }, [p.corrida?.id]);
  useEffect(() => {
    api<CorridaResumen[]>(`${RUTA}/periodos/${p.id}/corridas`).then(setHistorial).catch(() => setHistorial([]));
  }, [p.id, p.corrida?.id, p.corrida?.estado]);

  // Carga la corrida y, mientras siga en curso, pide cada segundo solo los renglones nuevos
  useEffect(() => {
    if (id === null) return setC(null);
    let vivo = true;
    let ultimo = 0;
    let enCurso = false; // la vimos correr: al terminar se recarga el periodo con su resultado
    let temporizador: ReturnType<typeof setTimeout>;
    const pedir = async () => {
      try {
        const r = await api<Corrida>(`${RUTA}/corridas/${id}?desde=${ultimo}`);
        if (!vivo) return;
        const nuevas = r.lineas;
        if (nuevas.length) ultimo = nuevas[nuevas.length - 1].id;
        setC((previa) => ({ ...r, lineas: previa && previa.id === r.id ? [...previa.lineas, ...nuevas] : nuevas }));
        setError(null);
        if (r.estado === "en_curso") {
          enCurso = true;
          temporizador = setTimeout(pedir, 1000);
        } else if (enCurso) terminar.current();
      } catch (e) {
        if (!vivo) return;
        setError(mensajeDe(e));
        temporizador = setTimeout(pedir, 3000);
      }
    };
    setC(null);
    pedir();
    return () => {
      vivo = false;
      clearTimeout(temporizador);
    };
  }, [id]);

  // Mientras corre, la bitácora baja sola al último renglón
  useEffect(() => {
    if (c?.estado === "en_curso" && filtro === null && caja.current) caja.current.scrollTop = caja.current.scrollHeight;
  }, [c?.lineas.length, c?.estado, filtro]);

  if (!id) return null;
  const lineas = c ? (filtro === null ? c.lineas : c.lineas.filter((l) => l.paso === filtro)) : [];
  const pasoFiltro = c?.pasos.find((x) => x.orden === filtro);
  return (
    <div className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Paso a paso</h2>
        {c && <Insignia className={ESTADO_CORRIDA[c.estado].clase}>{ESTADO_CORRIDA[c.estado].texto}</Insignia>}
        {c && (
          <span className="text-sm text-smn-gris-500">
            {c.iniciada_por ?? "—"} · {fechaLocal(c.iniciada_en)}
            {c.terminada_en && ` · ${duracion(c.iniciada_en, c.terminada_en)}`}
          </span>
        )}
        {historial.length > 1 && (
          <select
            value={id}
            onChange={(e) => setId(Number(e.target.value))}
            className="w-full max-w-full rounded-xl border border-smn-gris-100 bg-superficie px-3 py-1.5 text-sm sm:ml-auto sm:w-auto"
            aria-label="Corridas anteriores"
          >
            {historial.map((h, i) => (
              <option key={h.id} value={h.id}>
                {i === 0 ? "Última corrida" : "Corrida"} · {fechaLocal(h.iniciada_en)} · {ESTADO_CORRIDA[h.estado].texto}
              </option>
            ))}
          </select>
        )}
      </div>
      <p className="mt-1 text-sm text-smn-gris-500">
        Los mismos pasos que sigue Fiscal. Cada uno dice qué hizo; si un paso no se puede completar, el proceso se detiene ahí y no se salta al siguiente.
      </p>
      {c?.resultado && c.estado !== "en_curso" && <p className="mt-2 text-sm font-semibold">{c.resultado}</p>}
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}

      {!c ? (
        <div className="mt-4 h-28 animate-pulse rounded-2xl bg-smn-gris-100/60" />
      ) : (
        <>
          <ol className="mt-4 grid gap-2 sm:flex sm:gap-1 sm:overflow-x-auto sm:pb-2">
            {c.pasos.map((x) => {
              const e = ESTADO_PASO[x.estado];
              return (
                <li key={x.orden} className="flex items-stretch sm:shrink-0">
                  <button
                    onClick={() => setFiltro(filtro === x.orden ? null : x.orden)}
                    title={x.que_hace}
                    className={`flex w-full flex-col rounded-2xl border-2 p-3 sm:w-40 text-left transition ${e.borde} ${filtro === x.orden ? "bg-smn-naranja/10" : "hover:bg-smn-gris-100/60"} ${x.estado === "pendiente" || x.estado === "no_ejecutado" ? "opacity-60" : ""}`}
                  >
                    <span className="flex items-center gap-2">
                      {e.icono}
                      <span className="text-[13px] font-medium text-smn-gris-500">Paso {x.orden}</span>
                    </span>
                    <span className="mt-1 text-sm font-semibold leading-tight">{x.nombre}</span>
                    <span className="mt-1 line-clamp-3 text-[13px] text-smn-gris-500">{x.resumen ?? e.texto}</span>
                    {x.fin_en && <span className="mt-auto pt-1 text-[13px] text-smn-gris-500">{duracion(x.inicio_en, x.fin_en)}</span>}
                  </button>
                  <ChevronRight className="mx-0.5 hidden h-4 w-4 self-center text-smn-gris-500 sm:block" />
                </li>
              );
            })}
            <li className="flex sm:shrink-0">
              <div className="flex w-full flex-col sm:w-40 rounded-2xl border-2 border-dashed border-smn-gris-100 p-3">
                <span className="flex items-center gap-2">
                  <ExternalLink className="h-5 w-5 text-smn-gris-500" />
                  <span className="text-[13px] font-medium text-smn-gris-500">Fuera de la plataforma</span>
                </span>
                <span className="mt-1 text-sm font-semibold leading-tight">Validar con la herramienta del SAT</span>
                <span className="mt-1 text-[13px] text-smn-gris-500">Fiscal carga el TXT en la herramienta del SAT y presenta la DIOT.</span>
              </div>
            </li>
          </ol>

          <div className="mt-4 flex flex-wrap items-baseline gap-2">
            <h3 className="font-semibold">Bitácora</h3>
            <span className="text-sm text-smn-gris-500">
              {pasoFiltro ? (
                <>
                  Paso {pasoFiltro.orden} · {pasoFiltro.que_hace}{" "}
                  <button onClick={() => setFiltro(null)} className="font-semibold text-naranja-tinta hover:underline">
                    Ver todos los pasos
                  </button>
                </>
              ) : (
                `${c.lineas.length.toLocaleString("es-MX")} renglones. Da clic en un paso para ver solo lo suyo.`
              )}
            </span>
          </div>
          <div ref={caja} className="mt-2 max-h-[28rem] overflow-y-auto rounded-2xl bg-smn-gris-100/40 p-3 font-mono text-[13px] leading-relaxed">
            {lineas.length === 0 && <p className="text-smn-gris-500">{c.estado === "en_curso" ? "Arrancando…" : "Sin renglones."}</p>}
            {lineas.map((l, i) => {
              const nuevoPaso = filtro === null && (i === 0 || lineas[i - 1].paso !== l.paso);
              const paso = c.pasos.find((x) => x.orden === l.paso);
              return (
                <div key={l.id}>
                  {nuevoPaso && (
                    <p className={`font-sans text-[13px] font-semibold ${i ? "mt-3" : ""}`}>
                      Paso {l.paso} · {paso?.nombre}
                    </p>
                  )}
                  <p className={`flex gap-2 ${NIVEL[l.nivel].clase}`}>
                    <span className="shrink-0 text-smn-gris-500 tabular-nums">{hora(l.momento)}</span>
                    <span className="mt-0.5 shrink-0">{NIVEL[l.nivel].icono}</span>
                    <span className="whitespace-pre-wrap">{l.mensaje}</span>
                  </p>
                </div>
              );
            })}
            {c.estado === "en_curso" && (
              <p className="mt-2 flex items-center gap-2 text-naranja-tinta">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Procesando…
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
