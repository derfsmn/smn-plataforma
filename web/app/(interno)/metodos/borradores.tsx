"use client";
// Borradores que redacta la IA local: manual nuevo, versión actualizada o pasar al formato estándar.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { Paperclip, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { SubirArchivo } from "@/componentes/subir-archivo";
import { Boton, Campo, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, type Archivo } from "@/lib/api";
import { ESTADOS_BORRADOR, RUTA, TIPOS_BORRADOR, type Borrador, type Documento, type Estado } from "@/lib/metodos";
import { AREA, TARJETA } from "./estilos";

export type PedirBorrador = { tipo: Borrador["tipo"]; documento_id?: number; instrucciones?: string; area?: string };

export function Borradores({ estado }: { estado: Estado }) {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Borrador[] | null>(null);
  const [pedir, setPedir] = useState<PedirBorrador | null>(null);
  const cargar = useCallback(() => api<Borrador[]>(`${RUTA}/borradores`).then(setLista).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);
  // mientras la IA redacta, se refresca solo
  useEffect(() => {
    if (!lista?.some((b) => b.estado === "generando")) return;
    const t = setInterval(cargar, 5000);
    return () => clearInterval(t);
  }, [lista, cargar]);

  if (!lista) return <Esqueleto className="h-64" />;
  return (
    <>
      <div className={`${TARJETA} flex flex-wrap items-center gap-4`}>
        <div className="min-w-0 flex-1 text-sm text-smn-gris-500">
          <p className="font-semibold text-tinta">La IA local redacta, el área dueña decide</p>
          <p>El borrador nunca se usa para contestar hasta que alguien del área lo aprueba. Lo que la IA no sabe lo deja como pregunta para que lo contestes.</p>
        </div>
        <Boton onClick={() => setPedir({ tipo: "nuevo" })} disabled={!estado.ollama} title={estado.ollama ? undefined : "La IA local está apagada"}>
          <Sparkles className="h-4 w-4" /> Pedir un borrador
        </Boton>
      </div>
      {!estado.ollama && <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">La IA local (Ollama) está apagada; sin ella no se pueden pedir borradores.</p>}
      <ul className="mt-4 grid gap-2">
        {lista.length === 0 && <li className={`${TARJETA} text-sm text-smn-gris-500`}>Todavía no hay borradores.</li>}
        {lista.map((b) => (
          <li key={b.id}>
            <Link href={`/metodos/borradores/${b.id}`} className={`${TARJETA} flex flex-wrap items-center gap-3 !py-3 transition hover:border-smn-naranja`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{b.titulo}</p>
                <p className="text-[13px] text-smn-gris-500">
                  {TIPOS_BORRADOR[b.tipo]}
                  {b.version_anterior ? ` de la versión ${b.version_anterior}` : ""} · {b.area} · pedido por {b.creado_por ?? "—"} el {fechaLocal(b.creado_en)}
                </p>
              </div>
              <Insignia className={ESTADOS_BORRADOR[b.estado].clase}>{ESTADOS_BORRADOR[b.estado].texto}</Insignia>
            </Link>
          </li>
        ))}
      </ul>
      <AnimatePresence>
        {pedir && (
          <PedirBorradorVentana
            estado={estado}
            inicial={pedir}
            cerrar={() => setPedir(null)}
            listo={() => {
              setPedir(null);
              avisar("La IA está redactando. Te aviso en la campana cuando esté listo.", "exito");
              cargar();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

export function PedirBorradorVentana({ estado, inicial, cerrar, listo }: { estado: Estado; inicial: PedirBorrador; cerrar: () => void; listo: (b: Borrador) => void }) {
  const avisar = useAvisos();
  const [tipo, setTipo] = useState<Borrador["tipo"]>(inicial.tipo);
  const [docs, setDocs] = useState<Documento[]>([]);
  const [documentoId, setDocumentoId] = useState(inicial.documento_id ? String(inicial.documento_id) : "");
  const [titulo, setTitulo] = useState("");
  const [area, setArea] = useState(inicial.area ?? "");
  const [instrucciones, setInstrucciones] = useState(inicial.instrucciones ?? "");
  const [fuentes, setFuentes] = useState<number[]>([]);
  const [archivos, setArchivos] = useState<Archivo[]>([]);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    api<Documento[]>(`${RUTA}/documentos`).then(setDocs).catch(() => setDocs([]));
  }, []);
  const propios = docs.filter((d) => d.origen === "cargado" || d.origen === "ia");

  const enviar = async () => {
    setEnviando(true);
    try {
      const b = await api<Borrador>(`${RUTA}/borradores`, {
        cuerpo: {
          tipo, documento_id: tipo === "nuevo" ? null : Number(documentoId) || null, titulo: tipo === "nuevo" ? titulo : null,
          area: tipo === "nuevo" ? area : null, instrucciones: instrucciones || null, fuentes,
          archivos: archivos.map((a) => a.id),
        },
      });
      listo(b);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setEnviando(false);
    }
  };
  const listoParaEnviar =
    tipo === "nuevo" ? titulo.trim().length >= 3 && area.trim().length >= 2 && (instrucciones.trim().length > 0 || archivos.length > 0) : Boolean(documentoId) && (tipo === "formato" || instrucciones.trim().length > 0);

  return (
    <Modal titulo="Pedir un borrador a la IA" cerrar={cerrar} ancho="max-w-2xl">
      <div className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          {(Object.keys(TIPOS_BORRADOR) as Borrador["tipo"][]).map((t) => (
            <button key={t} onClick={() => setTipo(t)} className={`rounded-full px-3 py-1.5 text-sm font-semibold ${tipo === t ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}`}>
              {TIPOS_BORRADOR[t]}
            </button>
          ))}
        </div>
        {tipo === "nuevo" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo etiqueta="Título del manual" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Área dueña</span>
              <input list="areas-borrador" value={area} onChange={(e) => setArea(e.target.value)} className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20" />
              <datalist id="areas-borrador">{estado.areas.map((a) => <option key={a} value={a} />)}</datalist>
            </label>
          </div>
        ) : (
          <Selector
            etiqueta="Manual vigente"
            valor={documentoId}
            cambiar={setDocumentoId}
            opciones={[{ valor: "", texto: "Elige el manual" }, ...propios.map((d) => ({ valor: String(d.id), texto: `${d.titulo} · versión ${d.version} · ${d.area}` }))]}
          />
        )}
        {tipo !== "formato" && (
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">
              {tipo === "nuevo" ? "Cuenta cómo se hace hoy (notas, pasos, quién hace qué)" : "Qué cambió en el proceso"}
            </span>
            <textarea
              rows={6}
              value={instrucciones}
              onChange={(e) => setInstrucciones(e.target.value)}
              placeholder={tipo === "nuevo" ? "Pega tus notas o cuenta el proceso con tus palabras. Usa puestos, no nombres de personas." : "Por ejemplo: ahora el alta de proveedor pide también la opinión de cumplimiento del SAT."}
              className={AREA}
            />
          </label>
        )}
        {tipo !== "formato" && (
          <div>
            <p className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-smn-gris-700">
              <Paperclip className="h-4 w-4" /> {tipo === "nuevo" ? "O sube lo que tengas del proceso" : "Archivos de apoyo"} (Word, PDF o Excel; hasta 5)
            </p>
            {archivos.length < 5 && (
              <SubirArchivo modulo="metodos" entidad="metodos_borrador_apoyo" maximoMb={20}
                alSubir={(a) => setArchivos((xs) => (xs.some((x) => x.id === a.id) || xs.length >= 5 ? xs : [...xs, a]))} />
            )}
            {archivos.length > 0 && (
              <ul className="mt-2 grid gap-1 text-sm">
                {archivos.map((a) => (
                  <li key={a.id} className="flex items-center gap-2">
                    {a.nombre}
                    <button aria-label={`Quitar ${a.nombre}`} onClick={() => setArchivos((xs) => xs.filter((x) => x.id !== a.id))} className="text-smn-gris-500 hover:text-tinta"><X className="h-4 w-4" /></button>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-1 text-[13px] text-smn-gris-500">Solo se usan para redactar; no se publican ni se usan para contestar. Además del texto, la IA saca el diagrama de flujo y lo revisas antes de aprobar.</p>
          </div>
        )}
        {tipo === "formato" && <p className="text-sm text-smn-gris-500">La IA acomoda el manual en las secciones estándar (objetivo, alcance, responsables, pasos, excepciones, formatos) sin cambiar lo que dice. Verás cada diferencia antes de aprobar.</p>}
        {tipo !== "formato" && propios.length > 0 && (
          <details className="rounded-xl border border-smn-gris-100 px-3 py-2">
            <summary className="cursor-pointer text-sm font-semibold">Documentos de apoyo (opcional, hasta 5): {fuentes.length}</summary>
            <div className="mt-2 grid max-h-48 gap-1 overflow-y-auto">
              {propios.filter((d) => String(d.id) !== documentoId).map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={fuentes.includes(d.id)}
                    disabled={!fuentes.includes(d.id) && fuentes.length >= 5}
                    onChange={(e) => setFuentes((f) => (e.target.checked ? [...f, d.id] : f.filter((x) => x !== d.id)))}
                  />
                  {d.titulo} <span className="text-smn-gris-500">· {d.area}</span>
                </label>
              ))}
            </div>
          </details>
        )}
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={cerrar}>Cancelar</Boton>
          <Boton onClick={enviar} cargando={enviando} disabled={!listoParaEnviar}>
            <Sparkles className="h-4 w-4" /> Pedir borrador
          </Boton>
        </div>
      </div>
    </Modal>
  );
}
