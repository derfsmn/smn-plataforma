"use client";
// Radar · Hoy: el reporte del día (o el de ?fecha=), con decisiones, y el estado de la corrida automática.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, CalendarClock, CircleAlert, Clock, Loader2, Mail, Play, Radar, Send, Sparkles } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { fechaHora, fechaLarga, type EstadoRadar, type ReporteDetalle, type ReporteResumen } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { BotonesDecision, Etiquetas, Nota, UltimaAccion, Vacio } from "./piezas";

export default function PaginaHoy() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <Hoy />
    </Suspense>
  );
}

function Hoy() {
  const fecha = useSearchParams().get("fecha");
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [estado, setEstado] = useState<EstadoRadar | null>(null);
  const [reporte, setReporte] = useState<ReporteDetalle | null | undefined>(undefined);
  const [lanzando, setLanzando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const espera = useRef<ReturnType<typeof setInterval> | null>(null);

  const cargar = useCallback(async () => {
    try {
      const [e, r] = await Promise.all([
        api<EstadoRadar>("/api/compras/radar/estado"),
        fecha ? api<ReporteDetalle>(`/api/compras/radar/reportes/${fecha}`).catch(() => null) : api<ReporteDetalle | null>("/api/compras/radar/reportes/ultimo"),
      ]);
      setEstado(e);
      setReporte(r);
      return e;
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setReporte(null);
      return null;
    }
  }, [fecha, avisar]);

  // Mientras corre, revisa cada 5 segundos
  const vigilar = useCallback(() => {
    if (espera.current) return;
    espera.current = setInterval(async () => {
      const e = await cargar();
      if (e && !e.en_curso && espera.current) {
        clearInterval(espera.current);
        espera.current = null;
        avisar(e.ultimo?.estado === "error" ? "La corrida terminó con error" : "El radar terminó", e.ultimo?.estado === "error" ? "info" : "exito");
      }
    }, 5000);
  }, [cargar, avisar]);

  useEffect(() => {
    cargar().then((e) => e?.en_curso && vigilar());
    return () => {
      if (espera.current) clearInterval(espera.current);
      espera.current = null;
    };
  }, [cargar, vigilar]);

  const correr = async () => {
    setLanzando(true);
    try {
      await api<ReporteResumen>("/api/compras/radar/correr", { metodo: "POST", cuerpo: { enviar_correo: true } });
      avisar("El radar empezó; tarda unos minutos", "exito");
      await cargar();
      vigilar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(false);
    }
  };

  const enviarme = async () => {
    if (!reporte) return;
    setEnviando(true);
    try {
      const r = await api<{ enviado: boolean; mensaje: string }>(`/api/compras/radar/reportes/${reporte.fecha}/enviarme`, { metodo: "POST" });
      avisar(r.mensaje, r.enviado ? "exito" : "info");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setEnviando(false);
    }
  };

  // Envío a todos los destinatarios activos: pide un segundo clic para confirmar
  const [confirmarEnvio, setConfirmarEnvio] = useState(false);
  const [enviandoTodos, setEnviandoTodos] = useState(false);
  useEffect(() => {
    if (!confirmarEnvio) return;
    const t = setTimeout(() => setConfirmarEnvio(false), 6000);
    return () => clearTimeout(t);
  }, [confirmarEnvio]);
  const enviarATodos = async () => {
    if (!reporte) return;
    if (!confirmarEnvio) return setConfirmarEnvio(true);
    setConfirmarEnvio(false);
    setEnviandoTodos(true);
    try {
      const r = await api<{ enviado: boolean; mensaje: string }>(`/api/compras/radar/reportes/${reporte.fecha}/enviar-destinatarios`, { metodo: "POST" });
      avisar(r.mensaje, r.enviado ? "exito" : "info");
      if (r.enviado) cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setEnviandoTodos(false);
    }
  };

  const decidido = (senalId: number, estadoSenal: ReporteDetalle["detalle_hallazgos"][number]["estado_senal"]) => {
    cargar();
    setReporte((r) => r && { ...r, detalle_hallazgos: r.detalle_hallazgos.map((h) => (h.senal_id === senalId ? { ...h, estado_senal: estadoSenal } : h)) });
  };

  if (reporte === undefined || !estado)
    return (
      <div className="space-y-4">
        <Esqueleto className="h-24" />
        <Esqueleto className="h-64" />
      </div>
    );

  return (
    <div className="space-y-6">
      <BarraEstado estado={estado} correr={puede("compras.radar.administrar") ? correr : undefined} lanzando={lanzando} />

      {!reporte ? (
        <Vacio
          icono={<Radar className="h-10 w-10" />}
          titulo={fecha ? "No hay reporte de ese día" : "Todavía no hay reportes"}
          texto={
            fecha ? (
              <Link href="/compras/radar/corridas" className="font-semibold text-tinta hover:underline">
                Ver todas las corridas
              </Link>
            ) : (
              `El primer reporte sale solo a las ${estado.hora}:00${puede("compras.radar.administrar") ? ", o puedes correrlo ahora." : "."}`
            )
          }
        />
      ) : (
        <>
          <Entrada className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie p-6 sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[13px] font-medium text-naranja-tinta">Reporte del día</p>
                <h2 className="mt-1 text-xl font-semibold first-letter:uppercase sm:text-2xl">{fechaLarga(reporte.fecha)}</h2>
              </div>
              {reporte.estado === "listo" && (
                <div className="flex flex-wrap gap-2">
                  <Boton variante="secundario" onClick={enviarme} cargando={enviando}>
                    <Mail className="h-4 w-4" /> Enviármelo
                  </Boton>
                  {puede("compras.radar.administrar") && (
                    <Boton
                      variante={confirmarEnvio ? "primario" : "secundario"}
                      onClick={enviarATodos}
                      cargando={enviandoTodos}
                      disabled={!estado.destinatarios_activos}
                      title={estado.destinatarios_activos ? undefined : "No hay destinatarios activos"}
                    >
                      <Send className="h-4 w-4" />
                      {confirmarEnvio
                        ? `¿Enviar a ${estado.destinatarios_activos}? Confirmar`
                        : `Enviar a destinatarios (${estado.destinatarios_activos})`}
                    </Boton>
                  )}
                </div>
              )}
            </div>
            {reporte.resumen && <p className="mt-4 max-w-3xl text-smn-gris-700">{reporte.resumen}</p>}
            <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Fuentes revisadas", reporte.fuentes_leidas],
                ["Notas nuevas", reporte.articulos_nuevos],
                ["Relevantes", reporte.articulos_relevantes],
                ["Hallazgos", reporte.detalle_hallazgos.length],
              ].map(([n, v], i) => (
                <motion.div key={n} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }} className="rounded-2xl bg-smn-gris-50 p-3">
                  <dt className="text-[13px] font-semibold text-smn-gris-500">{n}</dt>
                  <dd className="text-2xl font-semibold tabular-nums">{v}</dd>
                </motion.div>
              ))}
            </dl>
          </Entrada>

          {reporte.estado === "error" && (
            <p role="alert" className="flex gap-2 rounded-2xl bg-red-500/10 p-4 text-sm font-semibold text-red-700 dark:text-red-400">
              <CircleAlert className="h-5 w-5 shrink-0" /> La corrida falló: {reporte.error}. Se reintenta sola hasta 3 veces.
            </p>
          )}

          <section>
            <h3 className="mb-3 text-lg font-semibold">Hallazgos</h3>
            {reporte.detalle_hallazgos.length === 0 ? (
              <Vacio icono={<Sparkles className="h-8 w-8" />} titulo="Sin hallazgos" texto="Este día no hubo notas nuevas relevantes, o la IA no estuvo disponible (revisa los avisos abajo)." />
            ) : (
              <ol className="space-y-4">
                {reporte.detalle_hallazgos.map((h, i) => (
                  <Entrada key={h.senal_id} retraso={i * 0.05}>
                    <li className="rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
                      <div className="flex gap-4">
                        <span className="font-mono text-2xl font-semibold text-naranja-tinta tabular-nums">{String(h.orden).padStart(2, "0")}</span>
                        <div className="min-w-0 flex-1">
                          <Etiquetas nivel={h.nivel} tipo={h.tipo} estado={h.estado_senal} area={h.area} paises={h.paises} />
                          <Link href={`/compras/radar/senal/${h.senal_id}`} className="mt-2 block text-lg font-semibold hover:underline">
                            {h.titulo}
                          </Link>
                          <p className="mt-2 text-smn-gris-700">{h.por_que}</p>
                          <ul className="mt-3 divide-y divide-smn-gris-100 border-t border-smn-gris-100">
                            {h.articulos.map((a) => (
                              <Nota key={a.id} a={a} />
                            ))}
                          </ul>
                          <div className="mt-4 space-y-2">
                            {puede("compras.radar.decidir") && <BotonesDecision senalId={h.senal_id} titulo={h.titulo} alDecidir={(s) => decidido(h.senal_id, s.estado)} compacto />}
                            <UltimaAccion a={h.ultima_accion} />
                          </div>
                        </div>
                      </div>
                    </li>
                  </Entrada>
                ))}
              </ol>
            )}
          </section>

          {reporte.radar_ejecutivo.length > 0 && (
            <Entrada className="rounded-2xl border-l-4 border-smn-naranja bg-superficie p-5 sm:p-6">
              <h3 className="text-[13px] font-medium text-naranja-tinta">Radar ejecutivo</h3>
              <ul className="mt-2 space-y-1.5">
                {reporte.radar_ejecutivo.map((l) => (
                  <li key={l} className="flex gap-2">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-smn-naranja" />
                    {l}
                  </li>
                ))}
              </ul>
            </Entrada>
          )}

          {reporte.avisos.length > 0 && (
            <details className="rounded-2xl bg-aviso-fondo p-4 text-sm text-aviso-texto">
              <summary className="flex cursor-pointer items-center gap-2 font-semibold">
                <AlertTriangle className="h-4 w-4" /> {reporte.avisos.length} aviso{reporte.avisos.length > 1 ? "s" : ""} de la corrida
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-6">
                {reporte.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
          )}
          <p className="text-[13px] text-smn-gris-500">
            Información pública resumida con IA a partir de las fuentes citadas. Revisa la fuente antes de decidir; no sustituye una evaluación regulatoria ni médica.
          </p>
        </>
      )}
    </div>
  );
}

function BarraEstado({ estado, correr, lanzando }: { estado: EstadoRadar; correr?: () => void; lanzando: boolean }) {
  const pendientes = [
    !estado.ia_encendida && `IA externa apagada: ${estado.ia_motivos.join(" ")}`,
    !estado.correo_configurado && "Sin correo de salida: el reporte se ve aquí, pero no se envía.",
    estado.correo_configurado && estado.destinatarios_activos === 0 && "No hay destinatarios activos.",
  ].filter(Boolean) as string[];
  return (
    <Entrada className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <AnimatePresence mode="wait">
          {estado.en_curso ? (
            <motion.p key="corre" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2 font-semibold">
              <Loader2 className="h-5 w-5 animate-spin text-smn-naranja" /> Corriendo: leyendo fuentes y analizando con IA…
            </motion.p>
          ) : (
            <motion.p key="espera" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-2 text-sm">
              <CalendarClock className="h-5 w-5 text-smn-naranja" />
              {estado.activo ? (
                <span>
                  Próxima corrida: <b>{fechaHora(estado.proxima_corrida, estado.zona_horaria)}</b>
                  <span className="text-smn-gris-500"> · {estado.frecuencia}</span>
                </span>
              ) : (
                <span>La corrida automática está apagada (Configuración).</span>
              )}
            </motion.p>
          )}
        </AnimatePresence>
        {estado.ultimo && (
          <p className="flex items-center gap-2 text-sm text-smn-gris-500">
            <Clock className="h-4 w-4" /> Última: {fechaHora(estado.ultimo.iniciado_en, estado.zona_horaria)}
          </p>
        )}
        <p className="text-sm text-smn-gris-500">
          {estado.fuentes_activas} fuentes · {estado.temas_activos} temas · IA {estado.ia_proveedor}
        </p>
        {correr && (
          <Boton onClick={correr} cargando={lanzando} disabled={estado.en_curso} className="ml-auto">
            <Play className="h-4 w-4" /> Correr ahora
          </Boton>
        )}
      </div>
      {pendientes.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-smn-gris-100 pt-3 text-sm text-aviso-texto">
          {pendientes.map((p) => (
            <li key={p} className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {p}
            </li>
          ))}
        </ul>
      )}
    </Entrada>
  );
}
