"use client";
// Pestaña «Historial»: evaluaciones (inmutables) con comparación entre dos, decisiones con lo que se vio ese día,
// excepciones (pedirla y aprobarla son personas distintas) y versiones de la ficha.

import { AnimatePresence } from "motion/react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { DECISION, P, RUTA, fecha, type Decision, type Evaluacion, type Ficha, type PropsPestana } from "@/lib/innovacion";
import { BarraResumen, ChipResultado, TARJETA, Vacio } from "../../comunes";

type FilaEv = { numero: number; motivo: string; creada_en: string; creada_por: string | null; resumen: Record<string, number>; ficha_version: number | null; regla: string | null; decision: { etapa: string; resultado: string } | null };
type Cambio = { regla: string; antes: { version: number; resultado: string; motivo: string } | null; despues: { version: number; resultado: string; motivo: string } | null };
type Excepcion = { id: number; regla: string; estado: string; justificacion: string; vence_en: string; solicitada_por: string | null; resuelta_por: string | null; nota: string | null };
type Congelada = Decision & { congelado: { evaluacion: number | null; evidencia: { id: number; version_id: number; pagina: number | null }[]; excepciones: unknown[]; etapa: string; en: string }; evaluacion_detalle: Evaluacion | null; ficha: Ficha | null };

export function Historial({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [evs, setEvs] = useState<FilaEv[] | null>(null);
  const [exc, setExc] = useState<Excepcion[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [cambios, setCambios] = useState<Cambio[] | null>(null);
  const [decision, setDecision] = useState<Congelada | null>(null);
  const cargar = useCallback(() => {
    api<FilaEv[]>(`${RUTA}/expedientes/${e.folio}/evaluaciones`).then((x) => {
      setEvs(x);
      if (x.length > 1) {
        setA(String(x[1].numero));
        setB(String(x[0].numero));
      }
    }).catch((x) => avisar(mensajeDe(x), "info"));
    api<Excepcion[]>(`${RUTA}/expedientes/${e.folio}/excepciones`).then(setExc).catch(() => {});
  }, [e.folio, avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);

  const comparar = async () => {
    try {
      setCambios((await api<{ cambios: Cambio[] }>(`${RUTA}/expedientes/${e.folio}/comparar?a=${a}&b=${b}`)).cambios);
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  const resolver = async (id: number, aprobar: boolean) => {
    try {
      await api(`${RUTA}/excepciones/${id}/resolver`, { cuerpo: { aprobar } });
      cargar();
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  const verDecision = async (id: number) => {
    try {
      setDecision(await api<Congelada>(`${RUTA}/expedientes/${e.folio}/decisiones/${id}`));
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  if (!evs) return <Esqueleto className="h-48" />;
  const opciones = evs.map((x) => ({ valor: String(x.numero), texto: `#${x.numero} · ${fecha(x.creada_en)}` }));
  return (
    <div className="grid gap-5">
      {e.decisiones.length > 0 && (
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Decisiones</h2>
          <ul className="divide-y divide-smn-gris-100 text-sm">
            {e.decisiones.map((d) => (
              <li key={d.id} className="flex flex-wrap items-start justify-between gap-2 py-2">
                <span>
                  <b>{DECISION[d.resultado] ?? d.resultado}</b> · {d.etapa} · {d.decidida_por} · {fecha(d.decidida_en)}
                  <span className="block text-smn-gris-700">{d.motivo}{d.condiciones ? ` Condiciones: ${d.condiciones}` : ""}</span>
                </span>
                <button className="font-semibold text-smn-naranja" onClick={() => verDecision(d.id)}>Ver lo que se vio ese día</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className={TARJETA}>
        <h2 className="mb-2 font-semibold">Evaluaciones</h2>
        {evs.length === 0 ? <Vacio>Sin evaluaciones.</Vacio> : (
          <>
            <ul className="divide-y divide-smn-gris-100 text-sm">
              {evs.map((x) => (
                <li key={x.numero} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>#{x.numero} · {fecha(x.creada_en)} · {x.motivo}{x.regla ? ` (${x.regla})` : ""} · ficha v{x.ficha_version ?? "—"} · {x.creada_por ?? "sistema"}
                    {x.decision && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">usada en {x.decision.etapa}: {x.decision.resultado}</Insignia>}
                  </span>
                  <BarraResumen resumen={x.resumen} />
                </li>
              ))}
            </ul>
            {evs.length > 1 && (
              <div className="mt-4 grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <Selector etiqueta="Antes" valor={a} cambiar={setA} opciones={opciones} />
                <Selector etiqueta="Después" valor={b} cambiar={setB} opciones={opciones} />
                <Boton variante="secundario" onClick={comparar} disabled={!a || !b || a === b}>Comparar</Boton>
              </div>
            )}
            {cambios && (
              <div className="mt-3 rounded-lg bg-smn-gris-50 p-3 text-sm">
                {cambios.length === 0 ? "Nada cambió entre esas dos evaluaciones." : (
                  <ul className="grid gap-2">
                    {cambios.map((c) => (
                      <li key={c.regla}>
                        <b>{c.regla}</b>: {c.antes ? <ChipResultado valor={c.antes.resultado} /> : "no estaba"} → {c.despues ? <ChipResultado valor={c.despues.resultado} /> : "ya no está"}
                        {c.despues && <span className="block text-smn-gris-700">{c.despues.motivo}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {exc.length > 0 && (
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Excepciones</h2>
          <ul className="divide-y divide-smn-gris-100 text-sm">
            {exc.map((x) => (
              <li key={x.id} className="py-2">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span><b>{x.regla}</b> · {x.estado} · vence {fecha(x.vence_en)} · pidió {x.solicitada_por}{x.resuelta_por ? ` · resolvió ${x.resuelta_por}` : ""}</span>
                  {x.estado === "solicitada" && puede(P.excepcion) && (
                    <span className="flex gap-2">
                      <Boton variante="secundario" className="min-h-8" onClick={() => resolver(x.id, true)}>Aprobar</Boton>
                      <Boton variante="fantasma" className="min-h-8" onClick={() => resolver(x.id, false)}>Rechazar</Boton>
                    </span>
                  )}
                </span>
                <span className="block text-smn-gris-700">{x.justificacion}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e.fichas.length > 1 && (
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Versiones de la ficha</h2>
          <ul className="text-sm">{e.fichas.map((f) => <li key={f.numero}>v{f.numero} · {fecha(f.creado_en)} · {f.creado_por}</li>)}</ul>
        </div>
      )}

      <AnimatePresence>
        {decision && (
          <Modal titulo={`Decisión del ${fecha(decision.decidida_en)}`} cerrar={() => setDecision(null)} ancho="max-w-2xl">
            <div className="grid max-h-[70vh] gap-3 overflow-y-auto text-sm">
              <p><b>{DECISION[decision.resultado]}</b> · {decision.decidida_por}</p>
              <p>{decision.motivo}</p>
              {decision.condiciones && <p>Condiciones: {decision.condiciones}</p>}
              <p className="text-smn-gris-500">
                Con la evaluación #{decision.congelado.evaluacion ?? "—"}, ficha v{decision.ficha?.numero ?? "—"} y {decision.congelado.evidencia.length} citas, tal como estaban ese día.
              </p>
              {decision.evaluacion_detalle?.resultados.map((r) => (
                <p key={r.id} className="flex flex-wrap items-center gap-2"><ChipResultado valor={r.resultado} /> <b>{r.regla}</b> v{r.version} · {r.motivo}</p>
              ))}
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </div>
  );
}
