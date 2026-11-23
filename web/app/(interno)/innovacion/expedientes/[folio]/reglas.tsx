"use client";
// Pestaña «Reglas»: la última evaluación, regla por regla, con su motivo, lo que falta, los datos que usó, la fuente
// y, si es manual, su revisión. Arriba, la compuerta para pasar a la etapa siguiente.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { ChevronDown, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { ETAPAS, RUTA, SEVERIDAD, fecha, type PropsPestana, type ResultadoRegla } from "@/lib/innovacion";
import { BarraResumen, ChipResultado, TARJETA, Texto, Vacio } from "../../comunes";

export function Reglas({ e, alCambiar }: PropsPestana) {
  const ev = e.evaluacion;
  const c = e.compuerta;
  const [pedir, setPedir] = useState<ResultadoRegla | null>(null);
  return (
    <div className="grid gap-5">
      <div className={`${TARJETA} ${c.puede_avanzar ? "" : "border-red-300 dark:border-red-500/40"}`}>
        <div className="flex flex-wrap items-center gap-2">
          {c.puede_avanzar ? <ShieldCheck className="h-5 w-5 text-emerald-600" /> : <ShieldAlert className="h-5 w-5 text-red-600" />}
          <h2 className="font-semibold">
            {c.puede_avanzar ? `Puede pasar a ${ETAPAS[c.etapa] ?? c.etapa}` : `No puede pasar a ${ETAPAS[c.etapa] ?? c.etapa}: ${c.motivo}`}
          </h2>
        </div>
        {c.bloqueantes_abiertos.length > 0 && (
          <ul className="mt-2 grid gap-1 text-sm">
            {c.bloqueantes_abiertos.map((b) => <li key={b.resultado_id}><b>{b.regla}</b> · {b.motivo}</li>)}
          </ul>
        )}
        {c.mayores_abiertos.length > 0 && (
          <p className="mt-2 text-sm text-smn-gris-700">{c.mayores_abiertos.length} reglas de severidad mayor siguen abiertas: se muestran en la decisión, pero no detienen.</p>
        )}
        {(c.pendientes_determinantes?.length ?? 0) > 0 && (
          <p className="mt-1 text-sm text-smn-gris-700">{c.pendientes_determinantes!.length} pendientes determinantes abiertos.</p>
        )}
        {(c.excepciones_vigentes?.length ?? 0) > 0 && (
          <p className="mt-1 text-sm text-smn-gris-700">Con excepción vigente: {c.excepciones_vigentes!.map((x) => `${x.regla} (vence ${fecha(x.vence_en)})`).join(", ")}.</p>
        )}
      </div>

      {!ev ? (
        <Vacio>Este expediente no se ha evaluado. Captura la ficha en «Composición» y se evalúa solo.</Vacio>
      ) : (
        <div className={TARJETA}>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Evaluación #{ev.numero}</h2>
            <span className="text-[13px] text-smn-gris-500">
              {fecha(ev.creada_en)} · {ev.motivo}{ev.regla ? ` (${ev.regla})` : ""} · ficha v{ev.ficha_version ?? "—"}{ev.formula_version ? ` · fórmula v${ev.formula_version}` : ""} · motor {ev.motor}
            </span>
          </div>
          <BarraResumen resumen={ev.resumen} />
          {ev.resultados.length === 0 ? (
            <p className="mt-3 text-sm text-smn-gris-500">No hay reglas publicadas que apliquen a este expediente. Se puede seguir trabajando.</p>
          ) : (
            <ul className="mt-3 divide-y divide-smn-gris-100">
              {ev.resultados.map((r) => <Renglon key={r.id} r={r} e={e} pedir={() => setPedir(r)} />)}
            </ul>
          )}
        </div>
      )}
      <AnimatePresence>{pedir && <PedirExcepcion r={pedir} cerrar={() => setPedir(null)} alCambiar={alCambiar} />}</AnimatePresence>
    </div>
  );
}

function Renglon({ r, e, pedir }: { r: ResultadoRegla; e: PropsPestana["e"]; pedir: () => void }) {
  const [abierto, setAbierto] = useState(r.resultado === "incumple" || r.resultado === "pendiente");
  const usados = Object.entries(r.datos_usados ?? {});
  return (
    <li className="py-3">
      <button className="flex w-full items-start justify-between gap-3 text-left" aria-expanded={abierto} onClick={() => setAbierto(!abierto)}>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <ChipResultado valor={r.resultado} />
            <span className="font-semibold">{r.regla}</span>
            <span className="text-[13px] text-smn-gris-500">v{r.version} · {SEVERIDAD[r.severidad] ?? r.severidad} · {r.modo}</span>
            {r.excepcion && <Insignia className="bg-smn-gris-100 text-smn-gris-700">Excepción hasta {fecha(r.excepcion.vence_en)}</Insignia>}
          </span>
          <span className="mt-1 block text-[15px]">{r.proposito}</span>
        </span>
        <ChevronDown className={`mt-1 h-4 w-4 shrink-0 transition ${abierto ? "rotate-180" : ""}`} />
      </button>
      {abierto && (
        <div className="mt-2 grid gap-2 rounded-lg bg-smn-gris-50 p-3 text-sm">
          <p><b>Por qué:</b> {r.motivo}</p>
          {r.faltantes.length > 0 && <p><b>Falta capturar:</b> {r.faltantes.join(", ")}</p>}
          {r.aviso_fuente && <p className="text-amber-700 dark:text-amber-400">{r.aviso_fuente}</p>}
          {usados.length > 0 && (
            <p><b>Datos que usó:</b> {usados.map(([k, v]) => `${k} = ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}</p>
          )}
          {r.fuente && (
            <p><b>Fuente:</b> <Link href={`/innovacion/fuentes/${r.fuente.recurso_id}`} className="text-smn-naranja underline">{r.fuente.titulo} v{r.fuente.version}</Link>{r.fuente.ubicacion ? ` · ${r.fuente.ubicacion}` : ""}</p>
          )}
          <div className="flex flex-wrap gap-2">
            {r.revision && (
              <Link href={`/innovacion/revisiones/${r.revision.id}`} className="font-semibold text-smn-naranja">
                {r.revision.estado === "asignada" ? `Dictaminar (le toca a ${r.revision.rol ?? "revisión"})` : "Ver dictamen"}
              </Link>
            )}
            {r.admite_excepcion && !r.excepcion && r.resultado !== "cumple" && r.resultado !== "no_aplica" && e.puede.editar && (
              <button className="font-semibold text-smn-naranja" onClick={pedir}>Pedir excepción</button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function PedirExcepcion({ r, cerrar, alCambiar }: { r: ResultadoRegla; cerrar: () => void; alCambiar: () => Promise<void> }) {
  const avisar = useAvisos();
  const manana = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const [justificacion, setJustificacion] = useState("");
  const [vence, setVence] = useState(new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10));
  const [enviando, setEnviando] = useState(false);
  const enviar = async () => {
    setEnviando(true);
    try {
      await api(`${RUTA}/resultados/${r.id}/excepcion`, { cuerpo: { justificacion: justificacion.trim(), vence_en: vence } });
      avisar("Excepción pedida. La aprueba otra persona con ese permiso.", "exito");
      cerrar();
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
      setEnviando(false);
    }
  };
  return (
    <Modal titulo={`Excepción a ${r.regla}`} cerrar={cerrar}>
      <div className="grid gap-3">
        <p className="text-sm text-smn-gris-500">Quien pide la excepción no puede aprobarla. Vence sola en la fecha que pongas.</p>
        <Texto etiqueta="Justificación" valor={justificacion} cambiar={setJustificacion} filas={4} />
        <Campo etiqueta="Vence el" type="date" min={manana} value={vence} onChange={(x) => setVence(x.target.value)} />
        <Boton onClick={enviar} cargando={enviando} disabled={justificacion.trim().length < 10}>Pedir excepción</Boton>
      </div>
    </Modal>
  );
}
