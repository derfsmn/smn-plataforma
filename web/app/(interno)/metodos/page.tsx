"use client";
// TD004 · Métodos y procedimientos: preguntar a los manuales con cita, documentos y versiones, borradores de la IA local,
// avisos y reporte, y la prueba de preguntas antes de abrirla a todos. Pedido de Diego, 2026-10-30.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, BookOpen, Cpu, FileText, Search, Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { PERMISO_CARGAR, PERMISO_CONSULTAR, RUTA, fecha, partesConCitas, type Cita, type Estado, type Respuesta } from "@/lib/metodos";
import { Borradores } from "./borradores";
import { Documentos } from "./documentos";
import { AREA, TARJETA } from "./estilos";
import { Prueba } from "./prueba";
import { Avisos, ReporteMes } from "./revision";


const PESTANAS = [
  { valor: "preguntar", texto: "Preguntar", carga: false },
  { valor: "documentos", texto: "Documentos", carga: false },
  { valor: "borradores", texto: "Borradores con IA", carga: true },
  { valor: "avisos", texto: "Avisos y sugerencias", carga: true },
  { valor: "reporte", texto: "Reporte del mes", carga: true },
  { valor: "prueba", texto: "Prueba de preguntas", carga: true },
] as const;
type Pestana = (typeof PESTANAS)[number]["valor"];

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <MetodosYProcedimientos />
    </Suspense>
  );
}

function MetodosYProcedimientos() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const params = useSearchParams();
  const router = useRouter();
  const [estado, setEstado] = useState<Estado | null>(null);
  const pestana = (params.get("vista") as Pestana) || "preguntar";
  const cargar = useCallback(() => api<Estado>(`${RUTA}/estado`).then(setEstado).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    if (puede(PERMISO_CONSULTAR)) cargar();
  }, [cargar, puede]);

  if (!puede(PERMISO_CONSULTAR)) return <p className="text-smn-gris-500">No tienes acceso a los manuales de métodos y procedimientos.</p>;
  if (!estado) return <Esqueleto className="h-64" />;
  const ir = (v: Pestana) => router.replace(v === "preguntar" ? "/metodos" : `/metodos?vista=${v}`);
  return (
    <>
      <Link href="/modulos/metodos" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Métodos y procedimientos
      </Link>
      <Encabezado
        titulo="Manuales de métodos y procedimientos"
        descripcion="Pregunta cómo se hace algo. La respuesta sale solo de los manuales vigentes y dice de qué documento, sección y versión viene."
      />
      <Entrada className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-smn-gris-500">
        <span className="inline-flex items-center gap-1.5"><BookOpen className="h-4 w-4" /> {estado.documentos} documentos vigentes</span>
        <span className="inline-flex items-center gap-1.5">
          <Cpu className="h-4 w-4" />
          {estado.ollama ? "IA local prendida" : "IA local apagada: se busca por palabras"}
        </span>
        {estado.puede_cargar && estado.fragmentos > 0 && estado.con_huella < estado.fragmentos && (
          <span className="text-amber-700 dark:text-amber-400">
            {estado.fragmentos - estado.con_huella} de {estado.fragmentos} secciones sin huella de significado
          </span>
        )}
      </Entrada>

      <div className="mt-6 flex flex-wrap gap-2">
        {PESTANAS.filter((x) => !x.carga || puede(PERMISO_CARGAR)).map((x) => (
          <button
            key={x.valor}
            onClick={() => ir(x.valor)}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${pestana === x.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:bg-smn-gris-300/50"}`}
          >
            {x.texto}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {pestana === "preguntar" && <Preguntar estado={estado} inicial={params.get("q") ?? ""} origen={params.get("origen")} />}
        {pestana === "documentos" && <Documentos estado={estado} alCambiar={cargar} />}
        {pestana === "borradores" && puede(PERMISO_CARGAR) && <Borradores estado={estado} />}
        {pestana === "avisos" && puede(PERMISO_CARGAR) && <Avisos estado={estado} alCambiar={cargar} />}
        {pestana === "reporte" && puede(PERMISO_CARGAR) && <ReporteMes />}
        {pestana === "prueba" && puede(PERMISO_CARGAR) && <Prueba estado={estado} />}
      </div>
    </>
  );
}

// ---------------------------------------------------------------- preguntar

const EJEMPLOS = ["¿Cómo doy de alta a un proveedor?", "¿Qué reviso al recibir mercancía en tienda?", "¿Quién autoriza una devolución?"];

function Preguntar({ estado, inicial, origen }: { estado: Estado; inicial: string; origen: string | null }) {
  const avisar = useAvisos();
  const [texto, setTexto] = useState(inicial);
  const [pensando, setPensando] = useState(false);
  const [historial, setHistorial] = useState<(Respuesta & { pregunta: string; calificada?: boolean })[]>([]);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const yaPreguntada = useRef(false);

  const preguntar = useCallback(
    async (q: string) => {
      const limpia = q.trim();
      if (limpia.length < 3) return;
      setPensando(true);
      try {
        const r = await api<Respuesta>(`${RUTA}/preguntar`, { cuerpo: { pregunta: limpia, origen } });
        setHistorial((h) => [{ ...r, pregunta: limpia }, ...h]);
        setTexto("");
      } catch (e) {
        avisar(mensajeDe(e), "info");
      } finally {
        setPensando(false);
        entrada.current?.focus();
      }
    },
    [avisar, origen],
  );
  useEffect(() => {
    if (inicial && !yaPreguntada.current) {
      yaPreguntada.current = true;
      preguntar(inicial);
    }
  }, [inicial, preguntar]);

  const calificar = async (r: Respuesta, util: boolean) => {
    const comentario = util ? null : window.prompt("¿Qué faltó o qué estuvo mal? (opcional)") ?? null;
    try {
      await api(`${RUTA}/preguntas/${r.pregunta_id}`, { metodo: "PATCH", cuerpo: { util, comentario } });
      setHistorial((h) => h.map((x) => (x.pregunta_id === r.pregunta_id ? { ...x, calificada: true } : x)));
      avisar(util ? "Gracias, eso nos dice que el manual sirve." : "Gracias. El área dueña lo verá en su reporte del mes.", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <div className="grid gap-4">
      <Entrada className={TARJETA}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            preguntar(texto);
          }}
        >
          <label htmlFor="pregunta" className="text-sm font-semibold text-smn-gris-700">Tu pregunta</label>
          <div className="mt-1.5 flex gap-2">
            <textarea
              id="pregunta"
              ref={entrada}
              rows={2}
              value={texto}
              maxLength={1000}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  preguntar(texto);
                }
              }}
              placeholder="Por ejemplo: ¿qué documentos pide el alta de un proveedor?"
              className={`${AREA} resize-none text-base`}
            />
            <Boton type="submit" cargando={pensando} disabled={texto.trim().length < 3} aria-label="Preguntar" className="self-stretch">
              {!pensando && <Send className="h-4 w-4" />}
            </Boton>
          </div>
        </form>
        {historial.length === 0 && !pensando && (
          <div className="mt-3 flex flex-wrap gap-2">
            {EJEMPLOS.map((e) => (
              <button key={e} onClick={() => preguntar(e)} className="rounded-full bg-smn-gris-100 px-3 py-1.5 text-[13px] font-semibold text-smn-gris-700 hover:bg-smn-gris-300/50">
                {e}
              </button>
            ))}
          </div>
        )}
        {estado.documentos === 0 && (
          <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">Todavía no hay manuales cargados; cualquier pregunta saldrá como «no está».</p>
        )}
      </Entrada>

      <AnimatePresence initial={false}>
        {pensando && (
          <motion.div key="pensando" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className={`${TARJETA} flex items-center gap-3 text-sm text-smn-gris-500`}>
            <Search className="h-4 w-4 animate-pulse text-smn-naranja" /> Buscando en los manuales{estado.ollama ? " y redactando la respuesta" : ""}…
          </motion.div>
        )}
        {historial.map((r) => (
          <motion.div key={r.pregunta_id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <RespuestaTarjeta r={r} calificar={r.calificada ? undefined : (util) => calificar(r, util)} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function RespuestaTarjeta({ r, calificar }: { r: Respuesta & { pregunta: string }; calificar?: (util: boolean) => void }) {
  const [abierta, setAbierta] = useState<number | null>(null);
  return (
    <div className={TARJETA}>
      <p className="text-sm font-semibold text-smn-gris-500">{r.pregunta}</p>
      {r.aviso && <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">{r.aviso}</p>}
      <div className={`mt-2 whitespace-pre-line leading-relaxed ${r.encontrada ? "" : "font-semibold"}`}>
        {partesConCitas(r.texto).map((p, i) =>
          typeof p === "number" ? (
            <button key={i} onClick={() => setAbierta(p)} className="mx-0.5 rounded-md bg-smn-naranja/20 px-1.5 text-[13px] font-semibold text-smn-negro align-super hover:bg-smn-naranja/40 dark:text-naranja-tinta">
              {p}
            </button>
          ) : (
            <span key={i}>{p}</span>
          ),
        )}
      </div>
      {r.citas.length > 0 && (
        <ul className="mt-4 space-y-2">
          {r.citas.map((c) => (
            <CitaFila key={c.numero} c={c} abierta={abierta === c.numero || r.modo === "palabras"} alternar={() => setAbierta(abierta === c.numero ? null : c.numero)} />
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3 text-[13px] text-smn-gris-500">
        <Insignia className={r.modo === "ia" ? "bg-smn-naranja/15 text-smn-negro dark:text-smn-naranja" : "bg-smn-gris-100 text-smn-gris-700"}>
          {r.modo === "ia" ? "Redactada por la IA local con los manuales" : "Búsqueda por palabras"}
        </Insignia>
        <span>{(r.duracion_ms / 1000).toFixed(1)} s</span>
        {calificar ? (
          <span className="ml-auto flex items-center gap-1">
            ¿Te sirvió?
            <button onClick={() => calificar(true)} className="rounded-lg p-1.5 hover:bg-smn-gris-100" aria-label="Sí me sirvió"><ThumbsUp className="h-4 w-4" /></button>
            <button onClick={() => calificar(false)} className="rounded-lg p-1.5 hover:bg-smn-gris-100" aria-label="No me sirvió"><ThumbsDown className="h-4 w-4" /></button>
          </span>
        ) : (
          <span className="ml-auto">Calificada, gracias.</span>
        )}
      </div>
    </div>
  );
}

function CitaFila({ c, abierta, alternar }: { c: Cita; abierta: boolean; alternar: () => void }) {
  return (
    <li className="rounded-2xl border border-smn-gris-100 bg-smn-gris-50 px-3 py-2 text-sm dark:bg-white/5">
      <button onClick={alternar} className="flex w-full items-start gap-2 text-left">
        <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md bg-smn-naranja/20 text-[13px] font-semibold">{c.numero}</span>
        <span className="min-w-0 flex-1">
          <span className="font-semibold">{c.titulo}</span>
          <span className="text-smn-gris-500">
            {c.seccion ? ` · ${c.seccion.split(" > ").slice(-1)[0]}` : ""} · versión {c.version}
            {c.vigente_desde ? `, vigente desde ${fecha(c.vigente_desde)}` : ""}
            {c.pagina ? ` · página ${c.pagina}` : ""} · {c.area}
          </span>
        </span>
        <FileText className="h-4 w-4 shrink-0 text-smn-gris-500" />
      </button>
      {abierta && (
        <div className="mt-2 border-t border-smn-gris-100 pt-2">
          <p className="whitespace-pre-line text-smn-gris-700">{c.extracto}</p>
          <Link href={`/metodos/documentos/${c.documento_id}#seccion-${c.fragmento_id}`} className="mt-1 inline-block text-[13px] font-semibold text-naranja-tinta hover:underline">
            Abrir el documento en esta sección
          </Link>
        </div>
      )}
    </li>
  );
}
