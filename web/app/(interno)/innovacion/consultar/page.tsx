"use client";
// Consultar la base de conocimiento: la IA local responde solo con fuentes revisadas y cita cada afirmación.
// Si no alcanza, lo dice. Las fuentes pendientes de revisión que hablan del tema se listan aparte, sin usarse.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Cpu, Search, Send } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Esqueleto, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { P, RUTA, TIPOS, partesConCitas, type FilaExpediente, type Respuesta } from "@/lib/innovacion";
import { AREA, ChipClasificacion, MenuModulo, SinAcceso, TARJETA } from "../comunes";

const EJEMPLOS = ["¿Qué forma de magnesio se absorbe mejor?", "¿Qué dosis de ashwagandha se ha estudiado para estrés?", "¿Qué pide la norma para declarar vitamina D?"];

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <Consultar />
    </Suspense>
  );
}

function Consultar() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const params = useSearchParams();
  const [texto, setTexto] = useState(params.get("q") ?? "");
  const [folio, setFolio] = useState(params.get("folio") ?? "");
  const [expedientes, setExpedientes] = useState<FilaExpediente[]>([]);
  const [pensando, setPensando] = useState(false);
  const [historial, setHistorial] = useState<(Respuesta & { pregunta: string })[]>([]);
  const entrada = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (puede(P.expVer)) api<FilaExpediente[]>(`${RUTA}/expedientes`).then((x) => setExpedientes(x.filter((e) => e.soy_del_equipo))).catch(() => {});
  }, [puede]);

  if (!puede(P.consultar)) return <SinAcceso texto="No tienes permiso para consultar la base de conocimiento." />;
  const preguntar = async (q: string) => {
    const limpia = q.trim();
    if (limpia.length < 4) return;
    setPensando(true);
    try {
      const r = await api<Respuesta>(`${RUTA}/consultar`, { cuerpo: { pregunta: limpia, folio: folio || null } });
      setHistorial((h) => [{ ...r, pregunta: limpia }, ...h]);
      setTexto("");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setPensando(false);
      entrada.current?.focus();
    }
  };
  return (
    <>
      <Encabezado titulo="Consultar" descripcion="Pregunta a la base de conocimiento. La respuesta sale solo de fuentes revisadas y dice de cuál, qué versión y qué página." />
      <MenuModulo />
      <div className={TARJETA}>
        <form onSubmit={(e) => { e.preventDefault(); preguntar(texto); }}>
          <label htmlFor="pregunta" className="text-sm font-semibold text-smn-gris-700">Tu pregunta</label>
          <div className="mt-1.5 flex gap-2">
            <textarea id="pregunta" ref={entrada} rows={2} value={texto} maxLength={1000} onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); preguntar(texto); } }}
              placeholder="Por ejemplo: ¿qué estudios hay de bisglicinato de magnesio y sueño?" className={`${AREA} resize-none`} />
            <Boton type="submit" cargando={pensando} disabled={texto.trim().length < 4} aria-label="Preguntar" className="self-stretch">{!pensando && <Send className="h-4 w-4" />}</Boton>
          </div>
        </form>
        {expedientes.length > 0 && (
          <div className="mt-3 max-w-sm">
            <Selector etiqueta="Incluir lo restringido de un folio de mi equipo" valor={folio} cambiar={setFolio}
              opciones={[{ valor: "", texto: "No, solo lo general" }, ...expedientes.map((e) => ({ valor: e.folio, texto: `${e.folio} · ${e.nombre}` }))]} />
          </div>
        )}
        {historial.length === 0 && !pensando && (
          <div className="mt-3 flex flex-wrap gap-2">
            {EJEMPLOS.map((e) => <button key={e} onClick={() => preguntar(e)} className="rounded-full bg-smn-gris-100 px-3 py-1.5 text-[13px] font-semibold text-smn-gris-700">{e}</button>)}
          </div>
        )}
      </div>
      {pensando && (
        <div className={`${TARJETA} mt-4 flex items-center gap-3 text-sm text-smn-gris-500`}><Search className="h-4 w-4 animate-pulse text-smn-naranja" /> Buscando en las fuentes revisadas y redactando con la IA local…</div>
      )}
      <div className="mt-4 grid gap-4">
        {historial.map((r) => (
          <div key={r.consulta_id} className={TARJETA}>
            <p className="text-sm font-semibold text-smn-gris-500">{r.pregunta}</p>
            <p className={`mt-2 whitespace-pre-line text-[16px] leading-relaxed ${r.insuficiente ? "text-smn-gris-700" : ""}`}>
              {partesConCitas(r.texto).map((p, i) => typeof p === "number" ? <a key={i} href={`#cita-${r.consulta_id}-${p}`} className="font-semibold text-smn-naranja">[{p}]</a> : <span key={i}>{p}</span>)}
            </p>
            {r.aviso && <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">{r.aviso}</p>}
            {r.citas.length > 0 && (
              <ol className="mt-4 grid gap-2 border-t border-smn-gris-100 pt-3">
                {r.citas.map((c) => (
                  <li key={c.numero} id={`cita-${r.consulta_id}-${c.numero}`} className="text-sm">
                    <Link href={`/innovacion/fuentes/${c.recurso_id}?seccion=${c.fragmento_id}`} className="font-semibold hover:text-smn-naranja">[{c.numero}] {c.titulo}</Link>{" "}
                    <ChipClasificacion valor={c.clasificacion} />
                    <span className="block text-[13px] text-smn-gris-500">{TIPOS[c.tipo] ?? c.tipo} · versión {c.version}{c.pagina ? ` · pág. ${c.pagina}` : ""}{c.seccion ? ` · ${c.seccion}` : ""}</span>
                    <span className="mt-0.5 line-clamp-2 block text-smn-gris-700">{c.extracto}</span>
                  </li>
                ))}
              </ol>
            )}
            {r.no_usadas.length > 0 && (
              <div className="mt-3 rounded-lg bg-smn-gris-50 p-3 text-sm">
                <p className="font-semibold">Pendientes de revisión que hablan del tema (no se usaron):</p>
                <ul className="mt-1">{r.no_usadas.map((x) => <li key={x.recurso_id}><Link href={`/innovacion/fuentes/${x.recurso_id}`} className="text-smn-naranja underline">{x.titulo}</Link></li>)}</ul>
              </div>
            )}
            <p className="mt-3 inline-flex items-center gap-1.5 text-[12px] text-smn-gris-500">
              <Cpu className="h-3.5 w-3.5" /> {r.modo === "ia" ? "Redactado con la IA local" : "Sin IA local: se muestran las secciones que más se parecen"} · {(r.duracion_ms / 1000).toFixed(1)} s
            </p>
          </div>
        ))}
      </div>
    </>
  );
}
