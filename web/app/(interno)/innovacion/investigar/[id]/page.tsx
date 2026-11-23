"use client";
// Una investigación: 1) preguntas y términos confirmados, 2) búsqueda, 3) selección, 4) lectura de lo abierto,
// 5) informe con citas, 6) agregar a la base lo que sirva (entra pendiente de revisión).

import Link from "next/link";
import { useParams } from "next/navigation";
import { CheckCircle2, ExternalLink, Loader2, Plus, Telescope, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";
import { api, dolares, mensajeDe } from "@/lib/api";
import { ESTADO_INV, P, RUTA, TEMAS, fecha, partesConCitas, type Investigacion } from "@/lib/innovacion";
import { AREA, ETIQUETA, MenuModulo, SinAcceso, TARJETA, Vacio, Volver } from "../../comunes";

const PASOS = [
  ["preguntas", "Preguntas y términos"], ["busqueda", "Búsqueda"], ["seleccion", "Selección"], ["lectura", "Lectura"], ["informe", "Informe"],
] as const;

export default function PaginaInvestigacion() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [inv, setInv] = useState<Investigacion | null>(null);
  const [preguntas, setPreguntas] = useState<{ tema: string; texto: string }[]>([]);
  const [terminos, setTerminos] = useState<string[]>([]);
  const [fuentes, setFuentes] = useState<string[]>([]);
  const [web, setWeb] = useState(false);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const cargar = useCallback(async () => {
    try {
      const x = await api<Investigacion>(`${RUTA}/investigaciones/${id}`);
      setInv(x);
      setPreguntas(x.preguntas);
      setTerminos(x.terminos);
      setFuentes(x.fuentes);
      setWeb(x.usar_web);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  }, [id, avisar]);
  useEffect(() => {
    if (puede(P.investigar)) cargar();
  }, [puede, cargar]);
  useEffect(() => {
    if (inv?.estado !== "corriendo") return;
    const t = setInterval(cargar, 4000);
    return () => clearInterval(t);
  }, [inv?.estado, cargar]);

  if (!puede(P.investigar)) return <SinAcceso />;
  if (!inv) return <Esqueleto className="h-64" />;
  const editable = inv.estado !== "corriendo";
  const correr = async () => {
    setOcupado("correr");
    try {
      await api(`${RUTA}/investigaciones/${inv.id}`, { metodo: "PATCH", cuerpo: { preguntas, terminos, fuentes, usar_web: web } });
      await api(`${RUTA}/investigaciones/${inv.id}/correr`, { metodo: "POST", cuerpo: {} });
      await cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const agregar = async (hid: number) => {
    setOcupado(`h${hid}`);
    try {
      const r = await api<{ id: number }>(`${RUTA}/investigaciones/${inv.id}/hallazgos/${hid}/agregar`, { metodo: "POST", cuerpo: {} });
      avisar("Agregada a la base como pendiente de revisión.", "exito");
      setInv({ ...inv, hallazgos: inv.hallazgos.map((h) => (h.id === hid ? { ...h, recurso_id: r.id } : h)) });
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const hechos = new Set(inv.pasos.map((p) => p.paso));
  const elegidos = inv.hallazgos.filter((h) => h.seleccionado);
  const otros = inv.hallazgos.filter((h) => !h.seleccionado);
  return (
    <>
      <Volver href="/innovacion/investigar" texto="Investigaciones" />
      <Encabezado titulo={inv.tema} descripcion={`${inv.folio ? `${inv.folio} · ` : ""}${inv.creado_por} · ${fecha(inv.creado_en)}`}
        accion={<Insignia className={ESTADO_INV[inv.estado]?.clase ?? ""}>{ESTADO_INV[inv.estado]?.texto ?? inv.estado}</Insignia>} />
      <MenuModulo />
      <ol className="mb-5 flex flex-wrap gap-2 text-[13px]">
        {PASOS.map(([k, t]) => (
          <li key={k} className={`inline-flex items-center gap-1 rounded-full px-3 py-1 font-semibold ${hechos.has(k) ? "bg-smn-gris-100 text-smn-gris-700" : "text-smn-gris-500"}`}>
            {hechos.has(k) ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : inv.estado === "corriendo" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} {t}
          </li>
        ))}
      </ol>
      {inv.error && <p className={`${TARJETA} mb-5 border-red-300 text-sm text-red-700 dark:text-red-400`}>{inv.error}</p>}

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="grid content-start gap-5">
          {inv.informe && (
            <div className={TARJETA}>
              <h2 className="mb-3 font-semibold">Informe</h2>
              <div className="grid gap-4">
                {inv.informe.map((p, i) => (
                  <div key={i}>
                    <p className="text-sm font-semibold">{p.tema ? `${TEMAS[p.tema] ?? p.tema} · ` : ""}{p.pregunta}</p>
                    <p className={`mt-1 whitespace-pre-line text-[15px] ${p.insuficiente ? "text-smn-gris-500" : ""}`}>
                      {partesConCitas(p.texto).map((x, j) => {
                        if (typeof x !== "number") return <span key={j}>{x}</span>;
                        const c = p.citas.find((y) => y.n === x);
                        return c?.url ? <a key={j} href={c.url} target="_blank" rel="noreferrer noopener" title={c.titulo} className="font-semibold text-smn-naranja">[{x}]</a> : <b key={j}>[{x}]</b>;
                      })}
                    </p>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[12px] text-smn-gris-500">Redactado con la IA local a partir de lo que se leyó. Úsalo como punto de partida: lo que cites en un expediente debe pasar por revisión.</p>
            </div>
          )}
          {elegidos.length > 0 && (
            <div className={TARJETA}>
              <h2 className="mb-2 font-semibold">Fuentes elegidas ({elegidos.length})</h2>
              <ul className="divide-y divide-smn-gris-100">{elegidos.map((h) => <FilaHallazgo key={h.id} h={h} agregar={agregar} ocupado={ocupado === `h${h.id}`} puede={puede(P.cargar)} />)}</ul>
            </div>
          )}
          {otros.length > 0 && (
            <details className={TARJETA}>
              <summary className="cursor-pointer font-semibold">Otras encontradas ({otros.length})</summary>
              <ul className="mt-2 divide-y divide-smn-gris-100">{otros.map((h) => <FilaHallazgo key={h.id} h={h} agregar={agregar} ocupado={ocupado === `h${h.id}`} puede={puede(P.cargar)} />)}</ul>
            </details>
          )}
          {inv.hallazgos.length === 0 && inv.estado !== "corriendo" && hechos.has("busqueda") && <Vacio>No se encontraron fuentes con esos términos. Ajusta los términos y vuelve a correr.</Vacio>}
        </div>

        <div className={`${TARJETA} grid content-start gap-4`}>
          <h2 className="font-semibold">{inv.estado === "terminada" || inv.estado === "error" ? "Ajustar y volver a correr" : "Confirma antes de buscar"}</h2>
          <div>
            <span className={ETIQUETA}>Preguntas</span>
            <div className="grid gap-2">
              {preguntas.map((p, i) => (
                <div key={i} className="grid gap-1 rounded-lg border border-smn-gris-100 p-2">
                  <div className="flex gap-2">
                    <select value={p.tema} disabled={!editable} onChange={(e) => setPreguntas((x) => x.map((y, j) => (j === i ? { ...y, tema: e.target.value } : y)))} className={`${AREA} h-9 py-1 text-[13px]`}>
                      {Object.entries(TEMAS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                    {editable && <button aria-label="Quitar pregunta" onClick={() => setPreguntas((x) => x.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>}
                  </div>
                  <textarea rows={2} value={p.texto} disabled={!editable} onChange={(e) => setPreguntas((x) => x.map((y, j) => (j === i ? { ...y, texto: e.target.value } : y)))} className={`${AREA} text-[13px]`} />
                </div>
              ))}
              {editable && <Boton variante="fantasma" className="justify-self-start" onClick={() => setPreguntas((x) => [...x, { tema: "eficacia", texto: "" }])}><Plus className="h-4 w-4" /> Pregunta</Boton>}
            </div>
          </div>
          <div>
            <span className={ETIQUETA}>Términos de búsqueda (en inglés suelen dar más)</span>
            <textarea rows={4} value={terminos.join("\n")} disabled={!editable} onChange={(e) => setTerminos(e.target.value.split("\n"))} className={`${AREA} text-[13px]`} />
            <p className="mt-1 text-[12px] text-smn-gris-500">Uno por renglón. Se quitan cantidades y números largos: nada de la fórmula sale a internet.</p>
          </div>
          <div>
            <span className={ETIQUETA}>Dónde buscar</span>
            <div className="grid gap-1 text-sm">
              {Object.entries(inv.catalogo_fuentes).filter(([k]) => !inv.con_gasto.includes(k)).map(([k, t]) => (
                <label key={k} className="flex items-center gap-2">
                  <input type="checkbox" disabled={!editable} checked={fuentes.includes(k)} onChange={(e) => setFuentes((x) => (e.target.checked ? [...x, k] : x.filter((y) => y !== k)))} /> {t}
                </label>
              ))}
              <label className="mt-1 flex items-start gap-2">
                <input type="checkbox" className="mt-1" disabled={!editable} checked={web} onChange={(e) => { setWeb(e.target.checked); setFuentes((x) => (e.target.checked ? [...new Set([...x, "oficial"])] : x.filter((y) => !inv.con_gasto.includes(y)))); }} />
                <span>Sitios oficiales y web (COFEPRIS, DOF, FDA, EFSA, NIH) <span className="block text-[12px] text-smn-gris-500">Usa DataForSEO: lleva gastado {dolares(inv.gasto_mes_usd)} de {dolares(inv.tope_usd)} este mes.</span></span>
              </label>
            </div>
          </div>
          {editable && (
            <Boton onClick={correr} cargando={ocupado === "correr"} disabled={!preguntas.some((p) => p.texto.trim()) || !terminos.some((t) => t.trim()) || !fuentes.length}>
              <Telescope className="h-4 w-4" /> {inv.estado === "propuesta" ? "Investigar" : "Volver a investigar"}
            </Boton>
          )}
          {inv.pasos.length > 0 && (
            <ul className="border-t border-smn-gris-100 pt-3 text-[13px] text-smn-gris-500">
              {inv.pasos.map((p, i) => <li key={i}>{p.texto}</li>)}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

function FilaHallazgo({ h, agregar, ocupado, puede }: { h: Investigacion["hallazgos"][number]; agregar: (id: number) => void; ocupado: boolean; puede: boolean }) {
  return (
    <li className="py-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block font-medium">{h.titulo}</span>
          <span className="block text-[13px] text-smn-gris-500">
            {h.origen} · {h.tipo_estudio ?? "otro"}{h.anio ? ` · ${h.anio}` : ""}{h.publicado_en ? ` · ${h.publicado_en}` : ""}{h.texto_abierto ? " · texto abierto leído" : ""}
          </span>
          {h.extraccion.resultado && <span className="mt-1 block">{h.extraccion.resultado}</span>}
          {(h.extraccion.poblacion || h.extraccion.cantidad) && (
            <span className="block text-[13px] text-smn-gris-500">{[h.extraccion.poblacion, h.extraccion.cantidad, h.extraccion.duracion].filter(Boolean).join(" · ")}</span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1">
          {h.url && <a href={h.url} target="_blank" rel="noreferrer noopener" aria-label="Abrir en internet" className="rounded p-1.5 hover:bg-smn-gris-50"><ExternalLink className="h-4 w-4" /></a>}
          {h.recurso_id ? (
            <Link href={`/innovacion/fuentes/${h.recurso_id}`} className="text-[13px] font-semibold text-smn-naranja">En la base</Link>
          ) : puede ? (
            <Boton variante="secundario" className="min-h-8 px-2.5 text-sm" cargando={ocupado} onClick={() => agregar(h.id)}><Plus className="h-4 w-4" /> A la base</Boton>
          ) : null}
        </span>
      </div>
    </li>
  );
}
