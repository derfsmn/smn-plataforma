"use client";
// Prueba de preguntas: las áreas capturan preguntas reales con el documento de donde sale la respuesta (o que deben
// contestar «no está»); un botón las corre todas y las califica contra las metas para abrir la base a todos.

import { AnimatePresence } from "motion/react";
import { CheckCircle2, Play, Plus, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Esqueleto, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { CALIFICACION, PERMISO_APROBAR, RUTA, type Corrida, type CorridaDetalle, type Documento, type Estado, type PruebaPregunta } from "@/lib/metodos";
import { AREA, TARJETA } from "./estilos";

export function Prueba({ estado }: { estado: Estado }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [preguntas, setPreguntas] = useState<PruebaPregunta[] | null>(null);
  const [corridas, setCorridas] = useState<Corrida[]>([]);
  const [detalle, setDetalle] = useState<CorridaDetalle | null>(null);
  const [editar, setEditar] = useState<PruebaPregunta | "nueva" | null>(null);
  const [docs, setDocs] = useState<Documento[]>([]);

  const cargar = useCallback(() => {
    api<PruebaPregunta[]>(`${RUTA}/prueba/preguntas`).then(setPreguntas).catch((e) => avisar(mensajeDe(e), "info"));
    api<Corrida[]>(`${RUTA}/prueba/corridas`).then((c) => {
      setCorridas(c);
      if (c[0]) api<CorridaDetalle>(`${RUTA}/prueba/corridas/${c[0].id}`).then(setDetalle).catch(() => {});
    });
  }, [avisar]);
  useEffect(() => {
    cargar();
    api<Documento[]>(`${RUTA}/documentos`).then(setDocs).catch(() => {});
  }, [cargar]);
  useEffect(() => {
    if (corridas[0]?.estado !== "en_curso") return;
    const t = setInterval(cargar, 4000);
    return () => clearInterval(t);
  }, [corridas, cargar]);

  const correr = async () => {
    try {
      await api(`${RUTA}/prueba/correr`, { metodo: "POST" });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!preguntas) return <Esqueleto className="h-64" />;
  const activas = preguntas.filter((p) => p.activa);
  const ultima = corridas[0];
  return (
    <div className="grid gap-4">
      <div className={`${TARJETA} flex flex-wrap items-center gap-4`}>
        <div className="min-w-0 flex-1 text-sm text-smn-gris-500">
          <p className="font-semibold text-tinta">Antes de abrirla a todos: 40 preguntas reales</p>
          <p>Metas: 32 de 40 correctas con la cita correcta, 0 inventadas, todas las que no están contestan «no está», menos de 15 segundos por respuesta y con la IA local prendida. Llevas {activas.length} preguntas activas.</p>
        </div>
        <Boton variante="secundario" onClick={() => setEditar("nueva")}><Plus className="h-4 w-4" /> Agregar pregunta</Boton>
        {puede(PERMISO_APROBAR) && (
          <Boton onClick={correr} disabled={!activas.length || ultima?.estado === "en_curso"} cargando={ultima?.estado === "en_curso"}>
            <Play className="h-4 w-4" /> Correr la prueba
          </Boton>
        )}
      </div>
      {!estado.ollama && <p className="text-sm text-amber-700 dark:text-amber-400">La IA local está apagada: la prueba correrá solo por palabras y no cuenta para abrir la base.</p>}

      {ultima && (
        <div className={TARJETA}>
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-semibold">
              {ultima.estado === "en_curso" ? `Corriendo: ${ultima.hechas} de ${ultima.total}` : `Última prueba: ${fechaLocal(ultima.iniciada_en)}`}
            </p>
            {ultima.estado === "terminada" && (
              <span className={`ml-auto inline-flex items-center gap-1 font-semibold ${ultima.metas.pasa ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>
                {ultima.metas.pasa ? <CheckCircle2 className="h-5 w-5" /> : <XCircle className="h-5 w-5" />}
                {ultima.metas.pasa ? "Pasa las metas: se puede abrir a todos" : "Todavía no pasa las metas"}
              </span>
            )}
          </div>
          {ultima.error && <p className="mt-2 text-sm text-red-700">{ultima.error}</p>}
          <div className="mt-3 grid gap-3 sm:grid-cols-4">
            <Meta titulo="Correctas" texto={`${ultima.correctas} de ${ultima.metas.correctas.de ?? 0}`} meta={`meta ${ultima.metas.correctas.meta}`} pasa={ultima.metas.correctas.pasa} />
            <Meta titulo="Inventadas" texto={String(ultima.inventadas)} meta="meta 0" pasa={ultima.metas.inventadas.pasa} />
            <Meta titulo="«No está» bien dicho" texto={`${ultima.no_esta_bien} de ${ultima.no_esta_total}`} meta="meta todas" pasa={ultima.metas.no_esta.pasa} />
            <Meta titulo="Segundos por respuesta" texto={String(ultima.metas.segundos.valor)} meta="meta menos de 15" pasa={ultima.metas.segundos.pasa} />
          </div>
          {!ultima.metas.con_ia && ultima.estado === "terminada" && <p className="mt-2 text-[13px] text-smn-gris-500">Esta corrida fue sin la IA local; para abrir la base tiene que correr con ella.</p>}
          {detalle && detalle.id === ultima.id && (
            <details className="mt-4">
              <summary className="cursor-pointer text-sm font-semibold">Ver cada pregunta</summary>
              <ul className="mt-2 grid gap-2">
                {detalle.detalle.map((x) => (
                  <li key={x.id} className="rounded-2xl border border-smn-gris-100 px-3 py-2 text-sm">
                    <p className="flex items-start gap-2 font-semibold">
                      {CALIFICACION[x.calificacion].bien ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />}
                      {x.pregunta}
                    </p>
                    <p className="text-[13px] text-smn-gris-500">{CALIFICACION[x.calificacion].texto} · {(x.ms / 1000).toFixed(1)} s{x.documento_esperado ? ` · se esperaba «${x.documento_esperado}»` : ""}</p>
                    <p className="mt-1 whitespace-pre-line text-smn-gris-700">{x.respuesta}</p>
                    {x.citas.length > 0 && <p className="mt-1 text-[13px] text-smn-gris-500">Citó: {x.citas.map((c) => c.titulo).join(", ")}</p>}
                    {x.esperada && <p className="mt-1 text-[13px] text-smn-gris-500">Respuesta esperada: {x.esperada}</p>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <div className={TARJETA}>
        <p className="mb-2 font-semibold">Preguntas de prueba</p>
        {preguntas.length === 0 && <p className="text-sm text-smn-gris-500">Todavía no hay. Pide a las áreas con más manuales que escriban preguntas reales con su respuesta.</p>}
        <ul className="divide-y divide-smn-gris-100">
          {preguntas.map((p) => (
            <li key={p.id} className={`flex flex-wrap items-center gap-2 py-2 text-sm ${p.activa ? "" : "opacity-50"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{p.pregunta}</p>
                <p className="text-[13px] text-smn-gris-500">{p.debe_contestar ? `Sale de: ${p.documento ?? "cualquier manual"}` : "Debe contestar «no está»"}{p.area ? ` · ${p.area}` : ""}</p>
              </div>
              <Boton variante="fantasma" className="!px-3 !py-1 text-[13px]" onClick={() => setEditar(p)}>Editar</Boton>
            </li>
          ))}
        </ul>
      </div>
      <AnimatePresence>
        {editar && <EditarPregunta p={editar === "nueva" ? null : editar} docs={docs} cerrar={() => setEditar(null)} listo={() => { setEditar(null); cargar(); }} />}
      </AnimatePresence>
    </div>
  );
}

function Meta({ titulo, texto, meta, pasa }: { titulo: string; texto: string; meta: string; pasa: boolean }) {
  return (
    <div>
      <p className="text-[13px] font-medium text-smn-gris-500">{titulo}</p>
      <p className={`text-2xl font-semibold tabular-nums ${pasa ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>{texto}</p>
      <p className="text-[13px] text-smn-gris-500">{meta}</p>
    </div>
  );
}

function EditarPregunta({ p, docs, cerrar, listo }: { p: PruebaPregunta | null; docs: Documento[]; cerrar: () => void; listo: () => void }) {
  const avisar = useAvisos();
  const [pregunta, setPregunta] = useState(p?.pregunta ?? "");
  const [esperada, setEsperada] = useState(p?.respuesta_esperada ?? "");
  const [contesta, setContesta] = useState(p?.debe_contestar ?? true);
  const [documento, setDocumento] = useState(p?.documento_id ? String(p.documento_id) : "");
  const [area, setArea] = useState(p?.area ?? "");
  const [activa, setActiva] = useState(p?.activa ?? true);
  const guardar = async () => {
    const cuerpo = { pregunta, respuesta_esperada: esperada || null, debe_contestar: contesta, documento_id: contesta && documento ? Number(documento) : null, area: area || null, activa };
    try {
      await api(`${RUTA}/prueba/preguntas${p ? `/${p.id}` : ""}`, { metodo: p ? "PUT" : "POST", cuerpo });
      listo();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const borrar = async () => {
    if (!p || !window.confirm("¿Borrar esta pregunta de prueba?")) return;
    await api(`${RUTA}/prueba/preguntas/${p.id}`, { metodo: "DELETE" }).catch(() => {});
    listo();
  };
  return (
    <Modal titulo={p ? "Editar pregunta de prueba" : "Agregar pregunta de prueba"} cerrar={cerrar} ancho="max-w-xl">
      <div className="grid gap-3 text-sm">
        <Campo etiqueta="Pregunta, como la haría alguien del área" value={pregunta} onChange={(e) => setPregunta(e.target.value)} />
        <div className="flex gap-2">
          <button onClick={() => setContesta(true)} className={`rounded-full px-3 py-1.5 font-semibold ${contesta ? "bg-tinta text-superficie" : "bg-smn-gris-100"}`}>Está en los manuales</button>
          <button onClick={() => setContesta(false)} className={`rounded-full px-3 py-1.5 font-semibold ${!contesta ? "bg-tinta text-superficie" : "bg-smn-gris-100"}`}>Debe decir «no está»</button>
        </div>
        {contesta && (
          <>
            <Selector etiqueta="Documento de donde sale" valor={documento} cambiar={setDocumento}
              opciones={[{ valor: "", texto: "Cualquiera" }, ...docs.map((d) => ({ valor: String(d.id), texto: `${d.titulo} · ${d.area}` }))]} />
            <label className="block">
              <span className="mb-1.5 block font-semibold text-smn-gris-700">Respuesta correcta (para compararla a ojo)</span>
              <textarea rows={3} value={esperada} onChange={(e) => setEsperada(e.target.value)} className={AREA} />
            </label>
          </>
        )}
        <Campo etiqueta="Área que la escribió (opcional)" value={area} onChange={(e) => setArea(e.target.value)} />
        <label className="flex items-center gap-2"><input type="checkbox" checked={activa} onChange={(e) => setActiva(e.target.checked)} /> Activa</label>
        <div className="flex justify-end gap-2">
          {p && <Boton variante="fantasma" onClick={borrar}>Borrar</Boton>}
          <Boton variante="secundario" onClick={cerrar}>Cancelar</Boton>
          <Boton onClick={guardar} disabled={pregunta.trim().length < 3}>Guardar</Boton>
        </div>
      </div>
    </Modal>
  );
}
