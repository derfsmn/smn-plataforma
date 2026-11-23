"use client";
// Pestaña «Evidencia»: lo citado en el expediente, ligado a una versión y página concretas de la fuente. «Citar» busca
// en la base (solo lo que la persona puede ver) y guarda qué respalda y si aplica.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { Quote, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { RUTA, fecha, type Busqueda, type PropsPestana, type Resultado } from "@/lib/innovacion";
import { AREA, ChipFuente, TARJETA, Texto, Vacio } from "../../comunes";

const APLICA: Record<string, string> = { si: "Aplica", parcial: "Aplica en parte", no: "No aplica", por_dictaminar: "Por dictaminar" };

export function EvidenciaCitada({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const [citar, setCitar] = useState(false);
  const retirar = async (id: number) => {
    try {
      await api(`${RUTA}/evidencia/${id}`, { metodo: "DELETE" });
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-smn-gris-500">Cada cita queda ligada a la versión de la fuente que se leyó. Si la fuente cambia, la cita sigue apuntando a la que se usó.</p>
        {e.puede.editar && <Boton onClick={() => setCitar(true)}><Quote className="h-4 w-4" /> Citar una fuente</Boton>}
      </div>
      {e.evidencia.length === 0 ? (
        <Vacio>Todavía no hay evidencia citada.</Vacio>
      ) : (
        e.evidencia.map((x) => (
          <div key={x.id} className={TARJETA}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <span>
                {x.recurso_id ? (
                  <Link href={`/innovacion/fuentes/${x.recurso_id}${x.fragmento_id ? `?seccion=${x.fragmento_id}` : ""}`} className="font-semibold hover:text-smn-naranja">{x.titulo}</Link>
                ) : (
                  <span className="font-semibold">{x.titulo}</span>
                )}
                <span className="block text-[13px] text-smn-gris-500">versión {x.version}{x.pagina ? ` · pág. ${x.pagina}` : ""}{x.seccion ? ` · ${x.seccion}` : ""} · {x.creado_por} · {fecha(x.creado_en)}</span>
              </span>
              <span className="flex items-center gap-2">
                <ChipFuente estado={x.estado_fuente} />
                <Insignia className={x.sentido === "contradictoria" ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300" : "bg-smn-gris-100 text-smn-gris-700"}>
                  {x.sentido === "contradictoria" ? "En contra" : APLICA[x.aplica] ?? x.aplica}
                </Insignia>
                {e.puede.editar && <button aria-label="Retirar cita" onClick={() => retirar(x.id)} className="rounded p-1 hover:bg-smn-gris-50"><Trash2 className="h-4 w-4" /></button>}
              </span>
            </div>
            <p className="mt-2 text-[15px]">{x.respalda}</p>
            {x.limites && <p className="mt-1 text-sm text-smn-gris-500">Límites: {x.limites}</p>}
          </div>
        ))
      )}
      <AnimatePresence>{citar && <Citar folio={e.folio} cerrar={() => setCitar(false)} alCambiar={alCambiar} />}</AnimatePresence>
    </div>
  );
}

function Citar({ folio, cerrar, alCambiar }: { folio: string; cerrar: () => void; alCambiar: () => Promise<void> }) {
  const avisar = useAvisos();
  const [q, setQ] = useState("");
  const [r, setR] = useState<Busqueda | null>(null);
  const [buscando, setBuscando] = useState(false);
  const [elegida, setElegida] = useState<Resultado | null>(null);
  const [respalda, setRespalda] = useState("");
  const [limites, setLimites] = useState("");
  const [aplica, setAplica] = useState("por_dictaminar");
  const [sentido, setSentido] = useState("a_favor");
  const [enviando, setEnviando] = useState(false);
  const buscar = async () => {
    if (q.trim().length < 2) return;
    setBuscando(true);
    try {
      setR(await api<Busqueda>(`${RUTA}/buscar?q=${encodeURIComponent(q.trim())}`));
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setBuscando(false);
    }
  };
  const guardar = async () => {
    if (!elegida) return;
    setEnviando(true);
    try {
      await api(`${RUTA}/expedientes/${folio}/evidencia`, {
        cuerpo: { version_id: elegida.version_id, fragmento_id: elegida.fragmento_id, respalda: respalda.trim(), limites: limites.trim() || null, aplica, sentido },
      });
      avisar("Cita guardada.", "exito");
      cerrar();
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
      setEnviando(false);
    }
  };
  return (
    <Modal titulo="Citar una fuente" cerrar={cerrar} ancho="max-w-2xl">
      {!elegida ? (
        <div className="grid gap-3">
          <form className="flex gap-2" onSubmit={(x) => { x.preventDefault(); buscar(); }}>
            <input autoFocus value={q} onChange={(x) => setQ(x.target.value)} placeholder="¿Qué quieres respaldar?" className={AREA} aria-label="Buscar" />
            <Boton type="submit" cargando={buscando} aria-label="Buscar">{!buscando && <Search className="h-4 w-4" />}</Boton>
          </form>
          <div className="grid max-h-[50vh] gap-2 overflow-y-auto">
            {r && r.resultados.length === 0 && <Vacio>No hay secciones que hablen de eso.</Vacio>}
            {r?.resultados.map((h) => (
              <button key={h.fragmento_id} onClick={() => { setElegida(h); setRespalda(""); }} className="rounded-xl border border-smn-gris-100 p-3 text-left hover:border-smn-naranja">
                <span className="flex flex-wrap items-center gap-2 font-semibold">{h.titulo} <ChipFuente estado={h.estado} /></span>
                <span className="block text-[13px] text-smn-gris-500">versión {h.version}{h.pagina ? ` · pág. ${h.pagina}` : ""}{h.seccion ? ` · ${h.seccion}` : ""}</span>
                <span className="mt-1 line-clamp-3 block text-sm text-smn-gris-700">{h.extracto}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="grid gap-3">
          <div className="rounded-xl bg-smn-gris-50 p-3 text-sm">
            <p className="font-semibold">{elegida.titulo} · versión {elegida.version}{elegida.pagina ? ` · pág. ${elegida.pagina}` : ""}</p>
            <p className="mt-1 text-smn-gris-700">{elegida.extracto}</p>
            {elegida.estado !== "revisado" && <p className="mt-1 text-amber-700 dark:text-amber-400">Esta fuente aún no está revisada: la cita queda, pero no respalda un dictamen hasta que se revise.</p>}
            <button className="mt-2 font-semibold text-smn-naranja" onClick={() => setElegida(null)}>Elegir otra</button>
          </div>
          <Texto etiqueta="¿Qué respalda para este producto?" valor={respalda} cambiar={setRespalda} filas={3} />
          <Texto etiqueta="Límites (opcional)" valor={limites} cambiar={setLimites} filas={2} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Selector etiqueta="¿Aplica a este producto?" valor={aplica} cambiar={setAplica} opciones={Object.entries(APLICA).map(([valor, texto]) => ({ valor, texto }))} />
            <Selector etiqueta="Sentido" valor={sentido} cambiar={setSentido} opciones={[{ valor: "a_favor", texto: "A favor" }, { valor: "contradictoria", texto: "En contra (contradictoria)" }]} />
          </div>
          <Boton onClick={guardar} cargando={enviando} disabled={respalda.trim().length < 3}>Guardar cita</Boton>
        </div>
      )}
    </Modal>
  );
}
