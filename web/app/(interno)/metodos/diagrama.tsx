"use client";
// Diagrama de flujo de un borrador: verlo, volver a sacarlo del texto y corregirlo paso por paso.
// El dibujo lo hace la API (mismo dibujo que va en el PDF y en el Word); aquí solo se edita la lista de pasos.

import { ArrowDown, ArrowUp, GitBranch, Pencil, Plus, Sparkles, Trash2, Workflow, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { ORIGEN_FLUJO, RUTA, TIPOS_PASO, type Flujo, type PasoFlujo, type TipoPaso } from "@/lib/metodos";
import { TARJETA } from "./estilos";

const CHICO = "rounded-lg border border-smn-gris-300 bg-superficie px-2 py-1.5 text-sm outline-none focus:border-smn-naranja focus:ring-2 focus:ring-smn-naranja/20";
let consecutivo = 0;
const nuevoId = () => `n${Date.now().toString(36)}${consecutivo++}`;

export function VerDiagrama({ svg }: { svg: string }) {
  return (
    <div className="max-w-full overflow-x-auto rounded-2xl bg-white p-2">
      <div className="mx-auto min-w-[520px] max-w-[760px] [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  );
}

export function DiagramaBorrador({ borradorId, flujo, svg, editable, iaPrendida, alCambiar }: {
  borradorId: number;
  flujo: Flujo | null;
  svg: string | null;
  editable: boolean;
  iaPrendida: boolean;
  alCambiar: () => void;
}) {
  const avisar = useAvisos();
  const [editando, setEditando] = useState<Flujo | null>(null);
  const [vista, setVista] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<"" | "ia" | "texto" | "guardar">("");
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);

  // vista previa mientras se corrige
  useEffect(() => {
    if (!editando) return;
    if (temporizador.current) clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => {
      api<{ svg: string }>(`${RUTA}/diagrama`, { cuerpo: { flujo: editando } })
        .then((r) => { setVista(r.svg); setError(null); })
        .catch((e) => setError(mensajeDe(e)));
    }, 500);
    return () => { if (temporizador.current) clearTimeout(temporizador.current); };
  }, [editando]);

  const sacar = async (usar_ia: boolean) => {
    setOcupado(usar_ia ? "ia" : "texto");
    try {
      const r = await api<{ flujo: Flujo; svg: string }>(`${RUTA}/borradores/${borradorId}/flujo/sacar`, { cuerpo: { usar_ia } });
      setEditando(r.flujo);
      setVista(r.svg);
      avisar(r.flujo.aviso ?? "Listo. Revísalo y guárdalo si te sirve.", "info");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado("");
    }
  };
  const guardar = async () => {
    if (!editando) return;
    setOcupado("guardar");
    try {
      await api(`${RUTA}/borradores/${borradorId}/flujo`, { metodo: "PUT", cuerpo: { flujo: editando } });
      avisar("Diagrama guardado. Así sale en el PDF y en el Word.", "exito");
      setEditando(null);
      alCambiar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado("");
    }
  };

  return (
    <div className={`${TARJETA} min-w-0`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <p className="flex items-center gap-2 font-semibold"><Workflow className="h-4 w-4 text-smn-naranja" /> Diagrama de flujo</p>
        {editable && !editando && (
          <div className="ml-auto flex flex-wrap gap-1">
            {flujo && <Boton variante="fantasma" className="!px-3 !py-1.5 text-[13px]" onClick={() => { setEditando(structuredClone(flujo)); setVista(svg); }}><Pencil className="h-3.5 w-3.5" /> Corregir</Boton>}
            {iaPrendida && <Boton variante="fantasma" className="!px-3 !py-1.5 text-[13px]" cargando={ocupado === "ia"} onClick={() => sacar(true)}><Sparkles className="h-3.5 w-3.5" /> Volver a sacar con la IA</Boton>}
            <Boton variante="fantasma" className="!px-3 !py-1.5 text-[13px]" cargando={ocupado === "texto"} onClick={() => sacar(false)}>Sacar de los pasos numerados</Boton>
          </div>
        )}
      </div>
      {!editando && flujo?.origen && <p className="mb-2 text-[13px] text-smn-gris-500">{ORIGEN_FLUJO[flujo.origen]}{editable ? " Revisa que cada paso esté en el puesto correcto y que las decisiones lleven a donde deben." : ""}</p>}
      {!editando && flujo?.aviso && <p className="mb-2 rounded-xl bg-amber-50 px-3 py-2 text-[13px] text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">{flujo.aviso}</p>}
      {!editando && (svg ? <VerDiagrama svg={svg} /> : <p className="text-sm text-smn-gris-500">Este borrador no tiene diagrama. {editable ? "Sácalo de los pasos o con la IA." : ""}</p>)}

      {editando && (
        <div className="grid gap-4">
          <Editor flujo={editando} cambiar={setEditando} />
          {error ? <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p> : null}
          {vista && <VerDiagrama svg={vista} />}
          <div className="flex flex-wrap justify-end gap-2">
            <Boton variante="secundario" onClick={() => { setEditando(null); setError(null); }}><X className="h-4 w-4" /> Cancelar</Boton>
            <Boton cargando={ocupado === "guardar"} disabled={Boolean(error)} onClick={guardar}>Guardar diagrama</Boton>
          </div>
        </div>
      )}
    </div>
  );
}

function Editor({ flujo, cambiar }: { flujo: Flujo; cambiar: (f: Flujo) => void }) {
  const [puesto, setPuesto] = useState("");
  const pasos = flujo.pasos;
  const poner = (pasosNuevos: PasoFlujo[], carriles = flujo.carriles) => cambiar({ ...flujo, carriles, pasos: pasosNuevos, aviso: null });
  const cambiarPaso = (i: number, cambio: Partial<PasoFlujo>) => poner(pasos.map((p, j) => (j === i ? { ...p, ...cambio } : p)));
  const mover = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= pasos.length) return;
    const n = [...pasos];
    [n[i], n[j]] = [n[j], n[i]];
    poner(n);
  };
  const quitar = (i: number) => {
    const id = pasos[i].id;
    poner(pasos.filter((_, j) => j !== i).map((p) => ({ ...p, sig: p.sig.filter((s) => s.a !== id) })));
  };
  const agregar = (i: number) => {
    const n = [...pasos];
    n.splice(i + 1, 0, { id: nuevoId(), tipo: "paso", texto: "", carril: pasos[i]?.carril ?? flujo.carriles[0] ?? "", sig: [] });
    poner(n);
  };
  const tipo = (i: number, t: TipoPaso) => {
    const p = pasos[i];
    const sig = t === "fin" ? [] : t === "decision"
      ? [p.sig[0] ?? { a: pasos[i + 1]?.id ?? "", etiqueta: "Sí" }, p.sig[1] ?? { a: "", etiqueta: "No" }].map((s, k) => ({ ...s, etiqueta: s.etiqueta ?? (k ? "No" : "Sí") }))
      : p.sig.slice(0, 1).map((s) => ({ ...s, etiqueta: null }));
    cambiarPaso(i, { tipo: t, sig });
  };
  const renombrar = (viejo: string, nuevo: string) =>
    poner(pasos.map((p) => (p.carril === viejo ? { ...p, carril: nuevo } : p)), flujo.carriles.map((c) => (c === viejo ? nuevo : c)));
  const nombre = (id: string) => {
    const k = pasos.findIndex((p) => p.id === id);
    return k < 0 ? "—" : `${k + 1}. ${pasos[k].texto.slice(0, 40) || TIPOS_PASO[pasos[k].tipo]}`;
  };

  return (
    <div className="grid gap-4">
      <div>
        <p className="mb-1 text-sm font-semibold text-smn-gris-700">Puestos (un carril cada uno)</p>
        <div className="flex flex-wrap gap-2">
          {flujo.carriles.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              <input aria-label={`Puesto ${i + 1}`} defaultValue={c} onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== c && renombrar(c, e.target.value.trim())} className={`${CHICO} w-44`} />
              {!pasos.some((p) => p.carril === c) && (
                <button aria-label="Quitar puesto" onClick={() => poner(pasos, flujo.carriles.filter((x) => x !== c))} className="text-smn-gris-500 hover:text-tinta"><X className="h-4 w-4" /></button>
              )}
            </span>
          ))}
          <span className="flex items-center gap-1">
            <input value={puesto} onChange={(e) => setPuesto(e.target.value)} placeholder="Agregar puesto" className={`${CHICO} w-40`} />
            <Boton variante="fantasma" className="!px-2 !py-1.5" disabled={!puesto.trim() || flujo.carriles.includes(puesto.trim())}
              onClick={() => { poner(pasos, [...flujo.carriles, puesto.trim()]); setPuesto(""); }}>
              <Plus className="h-4 w-4" />
            </Boton>
          </span>
        </div>
      </div>

      <ol className="grid gap-2">
        {pasos.map((p, i) => (
          <li key={p.id} className="rounded-2xl border border-smn-gris-100 p-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-6 text-right text-[13px] font-medium text-smn-gris-500">{i + 1}</span>
              <select aria-label="Tipo" value={p.tipo} onChange={(e) => tipo(i, e.target.value as TipoPaso)} className={CHICO}>
                {(Object.keys(TIPOS_PASO) as TipoPaso[]).map((t) => <option key={t} value={t}>{TIPOS_PASO[t]}</option>)}
              </select>
              <input aria-label="Qué se hace" value={p.texto} maxLength={160} onChange={(e) => cambiarPaso(i, { texto: e.target.value })}
                placeholder={p.tipo === "decision" ? "Pregunta, p. ej. ¿Llegó completa?" : "Qué se hace"} className={`${CHICO} min-w-0 flex-1 basis-56`} />
              <select aria-label="Puesto" value={p.carril} onChange={(e) => cambiarPaso(i, { carril: e.target.value })} className={`${CHICO} max-w-44`}>
                {flujo.carriles.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <span className="ml-auto flex gap-0.5">
                <button aria-label="Subir" onClick={() => mover(i, -1)} className="rounded p-1 text-smn-gris-500 hover:bg-smn-gris-100"><ArrowUp className="h-4 w-4" /></button>
                <button aria-label="Bajar" onClick={() => mover(i, 1)} className="rounded p-1 text-smn-gris-500 hover:bg-smn-gris-100"><ArrowDown className="h-4 w-4" /></button>
                <button aria-label="Agregar paso abajo" onClick={() => agregar(i)} className="rounded p-1 text-smn-gris-500 hover:bg-smn-gris-100"><Plus className="h-4 w-4" /></button>
                <button aria-label="Quitar paso" onClick={() => quitar(i)} disabled={pasos.length <= 1} className="rounded p-1 text-smn-gris-500 hover:bg-smn-gris-100 disabled:opacity-40"><Trash2 className="h-4 w-4" /></button>
              </span>
            </div>
            {p.tipo === "decision" ? (
              <div className="mt-2 grid gap-1 pl-8">
                {p.sig.map((s, k) => (
                  <div key={k} className="flex flex-wrap items-center gap-2 text-sm">
                    <GitBranch className="h-4 w-4 text-smn-naranja" />
                    <input aria-label="Respuesta" value={s.etiqueta ?? ""} maxLength={20} onChange={(e) => cambiarPaso(i, { sig: p.sig.map((x, m) => (m === k ? { ...x, etiqueta: e.target.value } : x)) })} className={`${CHICO} w-28`} placeholder="Sí / No" />
                    <span className="text-smn-gris-500">lleva a</span>
                    <select aria-label="Lleva a" value={s.a} onChange={(e) => cambiarPaso(i, { sig: p.sig.map((x, m) => (m === k ? { ...x, a: e.target.value } : x)) })} className={`${CHICO} max-w-72`}>
                      <option value="">Elige el paso</option>
                      {pasos.filter((q) => q.id !== p.id).map((q) => <option key={q.id} value={q.id}>{nombre(q.id)}</option>)}
                    </select>
                    {p.sig.length > 2 && <button aria-label="Quitar salida" onClick={() => cambiarPaso(i, { sig: p.sig.filter((_, m) => m !== k) })} className="text-smn-gris-500"><X className="h-4 w-4" /></button>}
                  </div>
                ))}
                {p.sig.length < 4 && <button onClick={() => cambiarPaso(i, { sig: [...p.sig, { a: "", etiqueta: "" }] })} className="w-fit text-[13px] font-semibold text-naranja-tinta hover:underline">Agregar otra respuesta</button>}
              </div>
            ) : p.tipo !== "fin" && (
              <div className="mt-2 flex flex-wrap items-center gap-2 pl-8 text-sm">
                <span className="text-smn-gris-500">Sigue con</span>
                <select aria-label="Sigue con" value={p.sig[0]?.a ?? ""} onChange={(e) => cambiarPaso(i, { sig: e.target.value ? [{ a: e.target.value, etiqueta: null }] : [] })} className={`${CHICO} max-w-72`}>
                  <option value="">El siguiente de la lista</option>
                  {pasos.filter((q) => q.id !== p.id).map((q) => <option key={q.id} value={q.id}>{nombre(q.id)}</option>)}
                </select>
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
