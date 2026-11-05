"use client";
// Avisos (contradicciones y manuales viejos), sugerencias de qué escribir o actualizar, y el reporte del mes.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { AlertTriangle, Search, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Esqueleto } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { RUTA, fecha, type Alerta, type Estado, type Reporte, type Sugerencias } from "@/lib/metodos";
import { PedirBorradorVentana, type PedirBorrador } from "./borradores";
import { TARJETA } from "./estilos";

export function Avisos({ estado, alCambiar }: { estado: Estado; alCambiar: () => void }) {
  const avisar = useAvisos();
  const [alertas, setAlertas] = useState<Alerta[] | null>(null);
  const [sug, setSug] = useState<Sugerencias | null>(null);
  const [pedir, setPedir] = useState<PedirBorrador | null>(null);
  const cargar = useCallback(() => {
    api<Alerta[]>(`${RUTA}/alertas`).then(setAlertas).catch((e) => avisar(mensajeDe(e), "info"));
    api<Sugerencias>(`${RUTA}/sugerencias`).then(setSug).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);
  useEffect(() => {
    if (!estado.contradicciones_en_curso) return;
    const t = setInterval(() => {
      alCambiar();
      cargar();
    }, 8000);
    return () => clearInterval(t);
  }, [estado.contradicciones_en_curso, alCambiar, cargar]);

  const buscar = async () => {
    try {
      await api(`${RUTA}/alertas/buscar`, { metodo: "POST" });
      avisar("La IA local está comparando los manuales en segundo plano.", "exito");
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const atender = async (a: Alerta, estadoNuevo: "atendida" | "descartada") => {
    const nota = window.prompt(estadoNuevo === "atendida" ? "¿Qué se hizo? (opcional)" : "¿Por qué no es contradicción? (opcional)");
    if (nota === null) return;
    try {
      await api(`${RUTA}/alertas/${a.id}`, { metodo: "PATCH", cuerpo: { estado: estadoNuevo, nota } });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!alertas || !sug) return <Esqueleto className="h-64" />;
  return (
    <div className="grid gap-6">
      <section>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="text-lg font-semibold">Manuales que se contradicen</h2>
          <Boton variante="secundario" className="ml-auto" onClick={buscar} cargando={estado.contradicciones_en_curso} disabled={!estado.ollama}>
            <Search className="h-4 w-4" /> Buscar contradicciones
          </Boton>
        </div>
        {!estado.ollama && <p className="mb-2 text-sm text-smn-gris-500">La IA local está apagada; ella compara los manuales.</p>}
        {alertas.length === 0 && <p className={`${TARJETA} text-sm text-smn-gris-500`}>No hay contradicciones abiertas.</p>}
        <ul className="grid gap-3">
          {alertas.map((a) => (
            <li key={a.id} className={TARJETA}>
              <p className="flex items-start gap-2 font-semibold"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" /> {a.detalle}</p>
              <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <Lado titulo={a.documento} area={a.area} id={a.documento_id} texto={a.texto} />
                {a.otro_documento_id && <Lado titulo={a.otro_documento!} area={a.otra_area!} id={a.otro_documento_id} texto={a.otro_texto} />}
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Boton variante="fantasma" className="!py-1.5 text-[13px]" onClick={() => atender(a, "descartada")}>No es contradicción</Boton>
                <Boton variante="secundario" className="!py-1.5 text-[13px]" onClick={() => atender(a, "atendida")}>Ya se corrigió</Boton>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Qué preguntan y no encuentra respuesta</h2>
        <p className="mb-2 text-sm text-smn-gris-500">Preguntas de los últimos 90 días sin respuesta o calificadas con 👎, juntas por tema. Cada tema dice qué manual tocar.</p>
        {sug.temas.length === 0 && <p className={`${TARJETA} text-sm text-smn-gris-500`}>Nada pendiente.</p>}
        <ul className="grid gap-2">
          {sug.temas.map((t, i) => (
            <li key={i} className={`${TARJETA} flex flex-wrap items-center gap-3 !py-3`}>
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-semibold">«{t.preguntas[0]}»{t.veces > 1 ? ` y ${t.veces - 1} parecidas` : ""}</p>
                <p className="text-[13px] text-smn-gris-500">
                  {t.sin_respuesta} sin respuesta, {t.no_sirvio} no sirvieron · {t.documento ? `El más cercano: ${t.documento} (${t.area})` : "Ningún manual habla de esto"}
                </p>
              </div>
              {estado.ollama && (
                <Boton variante="secundario" className="!py-1.5 text-[13px]" onClick={() => setPedir({
                  tipo: t.accion, documento_id: t.documento_id ?? undefined, area: t.area ?? undefined,
                  instrucciones: `La gente pregunta esto y el manual no lo contesta:\n${t.preguntas.map((p) => `- ${p}`).join("\n")}`,
                })}>
                  <Sparkles className="h-3.5 w-3.5" /> {t.accion === "actualizacion" ? "Borrador de actualización" : "Borrador de manual nuevo"}
                </Boton>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Manuales que toca revisar</h2>
        {sug.viejos.length === 0 && <p className={`${TARJETA} text-sm text-smn-gris-500`}>Ninguno vencido.</p>}
        <ul className="grid gap-2">
          {sug.viejos.map((v) => (
            <li key={v.documento_id} className={`${TARJETA} !py-3 text-sm`}>
              <Link href={`/metodos/documentos/${v.documento_id}`} className="font-semibold hover:underline">{v.titulo}</Link>
              <span className="text-smn-gris-500"> · {v.area} · versión {v.version}. {v.motivo}</span>
            </li>
          ))}
        </ul>
      </section>

      {sug.criterios.length > 0 && (
        <section>
          <h2 className="mb-2 text-lg font-semibold">Criterios fiscales aprobados hace poco</h2>
          <p className="mb-2 text-sm text-smn-gris-500">Si un manual de Contraloría habla de ellos, revisa que diga lo mismo.</p>
          <ul className="grid gap-2">
            {sug.criterios.map((c, i) => (
              <li key={i} className={`${TARJETA} !py-3 text-sm`}>
                <span className="font-semibold">{c.titulo}</span>
                <span className="text-smn-gris-500"> · aprobado {fecha(c.aprobado_en)} · {c.documento ? <Link href={`/metodos/documentos/${c.documento_id}`} className="underline">{c.documento}</Link> : "ningún manual lo menciona"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <AnimatePresence>
        {pedir && <PedirBorradorVentana estado={estado} inicial={pedir} cerrar={() => setPedir(null)} listo={(b) => { setPedir(null); window.location.href = `/metodos/borradores/${b.id}`; }} />}
      </AnimatePresence>
    </div>
  );
}

function Lado({ titulo, area, id, texto }: { titulo: string; area: string; id: number; texto: string | null }) {
  return (
    <div className="rounded-2xl bg-smn-gris-50 p-3 dark:bg-white/5">
      <Link href={`/metodos/documentos/${id}`} className="font-semibold hover:underline">{titulo}</Link>
      <p className="text-[13px] text-smn-gris-500">{area}</p>
      {texto && <p className="mt-1 whitespace-pre-line text-smn-gris-700">{texto}</p>}
    </div>
  );
}

export function ReporteMes() {
  const avisar = useAvisos();
  const [mes, setMes] = useState(new Date().toISOString().slice(0, 7));
  const [r, setR] = useState<Reporte | null>(null);
  useEffect(() => {
    setR(null);
    api<Reporte>(`${RUTA}/reporte?mes=${mes}`).then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [mes, avisar]);
  return (
    <div className="grid gap-4">
      <label className="flex items-center gap-2 text-sm font-semibold">
        Mes <input type="month" value={mes} onChange={(e) => e.target.value && setMes(e.target.value)} className="rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2" />
      </label>
      {!r ? (
        <Esqueleto className="h-48" />
      ) : (
        <>
          <div className={`${TARJETA} grid gap-4 sm:grid-cols-4`}>
            <Dato titulo="Preguntas" valor={String(r.total)} />
            <Dato titulo="Con respuesta" valor={r.total ? `${Math.round((r.encontradas / r.total) * 100)} %` : "—"} />
            <Dato titulo="Les sirvió (de las calificadas)" valor={r.calificadas ? `${r.utiles} de ${r.calificadas}` : "—"} />
            <Dato titulo="Tiempo promedio" valor={r.total ? `${(r.promedio_ms / 1000).toFixed(1)} s` : "—"} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className={TARJETA}>
              <p className="font-semibold">Sin respuesta en los manuales</p>
              {r.sin_respuesta.length === 0 ? <p className="mt-1 text-sm text-smn-gris-500">Ninguna.</p> : (
                <ul className="mt-2 space-y-1 text-sm">{r.sin_respuesta.map((g, i) => <li key={i}>«{g.preguntas[0]}»{g.veces > 1 ? <span className="text-smn-gris-500"> · {g.veces} veces</span> : null}</li>)}</ul>
              )}
            </div>
            <div className={TARJETA}>
              <p className="font-semibold">No les sirvió</p>
              {r.no_sirvieron.length === 0 ? <p className="mt-1 text-sm text-smn-gris-500">Ninguna.</p> : (
                <ul className="mt-2 space-y-2 text-sm">{r.no_sirvieron.map((x, i) => <li key={i}><p className="font-semibold">«{x.pregunta}»</p>{x.comentario && <p className="text-smn-gris-500">Comentario: {x.comentario}</p>}</li>)}</ul>
              )}
            </div>
            <div className={TARJETA}>
              <p className="font-semibold">Manuales más citados</p>
              <ul className="mt-2 space-y-1 text-sm">{r.mas_citados.map((m) => <li key={m.documento_id}><Link href={`/metodos/documentos/${m.documento_id}`} className="hover:underline">{m.titulo}</Link> <span className="text-smn-gris-500">· {m.veces}</span></li>)}</ul>
            </div>
            <div className={TARJETA}>
              <p className="font-semibold">Desde dónde preguntan</p>
              <ul className="mt-2 space-y-1 text-sm">{r.por_origen.map((o) => <li key={o.origen}>{o.origen} <span className="text-smn-gris-500">· {o.veces}</span></li>)}</ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Dato({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div>
      <p className="text-[13px] font-medium text-smn-gris-500">{titulo}</p>
      <p className="text-2xl font-semibold tabular-nums">{valor}</p>
    </div>
  );
}
