"use client";
// Pestaña «Filtro»: la decisión la toma un usuario directivo (Diego, 2026-11-21). Muestra la compuerta para pasar a
// desarrollo, lo que sigue abierto, la evidencia y los escenarios; «Avanzar» no procede con bloqueantes abiertos.

import { Gavel } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton } from "@/componentes/ui";
import { api, mensajeDe, pesos } from "@/lib/api";
import { DECISION, ETAPAS, RUTA, postConDetalle, type Compuerta, type PropsPestana } from "@/lib/innovacion";
import { BarraResumen, TARJETA, Texto, Vacio } from "../../comunes";

export function Filtro({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const [c, setC] = useState<Compuerta | null>(null);
  const [resultado, setResultado] = useState("");
  const [motivo, setMotivo] = useState("");
  const [condiciones, setCondiciones] = useState("");
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    api<Compuerta>(`${RUTA}/expedientes/${e.folio}/compuerta?etapa=desarrollo`).then(setC).catch(() => {});
  }, [e.folio, e.evaluacion?.numero]);

  const esperando = e.etapa === "filtro" && e.estado === "activo";
  const decidir = async () => {
    setEnviando(true);
    const r = await postConDetalle(`${RUTA}/expedientes/${e.folio}/decisiones`, { resultado, motivo: motivo.trim(), condiciones: condiciones.trim() || null });
    setEnviando(false);
    if (!r.ok) return avisar(r.mensaje, "info");
    avisar("Decisión guardada con lo que se vio hoy.", "exito");
    setResultado("");
    setMotivo("");
    setCondiciones("");
    await alCambiar();
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
      <div className="grid content-start gap-5">
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Lo que se decide</h2>
          <p className="text-sm text-smn-gris-700">{e.descripcion ?? "Sin descripción."}</p>
          <div className="mt-3"><BarraResumen resumen={e.evaluacion?.resumen} /></div>
          {c && (
            <div className="mt-3 text-sm">
              {c.puede_avanzar ? (
                <p className="text-emerald-700 dark:text-emerald-400">Sin bloqueantes abiertos para pasar a desarrollo.</p>
              ) : (
                <>
                  <p className="font-semibold text-red-700 dark:text-red-400">{c.motivo} No se puede avanzar hasta cerrarlos o tener excepción aprobada.</p>
                  <ul className="mt-1 list-disc pl-5">{c.bloqueantes_abiertos.map((b) => <li key={b.resultado_id}>{b.regla}: {b.motivo}</li>)}</ul>
                </>
              )}
              {c.mayores_abiertos.length > 0 && (
                <>
                  <p className="mt-2 font-semibold">Mayores abiertas (no detienen, pero cuentan):</p>
                  <ul className="list-disc pl-5">{c.mayores_abiertos.map((b) => <li key={b.resultado_id}>{b.regla}: {b.motivo}</li>)}</ul>
                </>
              )}
              {(c.pendientes_determinantes?.length ?? 0) > 0 && (
                <>
                  <p className="mt-2 font-semibold">Pendientes determinantes:</p>
                  <ul className="list-disc pl-5">{c.pendientes_determinantes!.map((p) => <li key={p.id}>{p.descripcion}</li>)}</ul>
                </>
              )}
            </div>
          )}
        </div>
        <div className={TARJETA}>
          <h2 className="mb-2 font-semibold">Evidencia y escenarios</h2>
          <p className="text-sm">{e.evidencia.length} citas ({e.evidencia.filter((x) => x.sentido === "contradictoria").length} en contra).</p>
          {e.escenarios.map((s) => (
            <p key={s.id} className="text-sm">{s.nombre}: precio {s.precio != null ? pesos(s.precio) : "—"}, margen {s.margen_pct != null ? `${s.margen_pct} %` : "—"}</p>
          ))}
        </div>
      </div>

      <div className={`${TARJETA} grid content-start gap-3`}>
        <h2 className="inline-flex items-center gap-2 font-semibold"><Gavel className="h-4 w-4 text-smn-naranja" /> Decisión del Filtro</h2>
        {!esperando ? (
          <Vacio>Este expediente está en {ETAPAS[e.etapa]}{e.estado !== "activo" ? ` (${e.estado})` : ""}. La decisión se toma cuando lo envían al Filtro.</Vacio>
        ) : !e.puede.filtro ? (
          <Vacio>La decisión del Filtro la toma un usuario directivo.</Vacio>
        ) : (
          <>
            {Object.entries(DECISION).map(([valor, texto]) => {
              const bloqueado = valor === "avanzar" && c !== null && !c.puede_avanzar;
              return (
                <label key={valor} className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-[15px] ${resultado === valor ? "border-smn-naranja" : "border-smn-gris-100"} ${bloqueado ? "opacity-50" : ""}`}>
                  <input type="radio" name="decision" disabled={bloqueado} checked={resultado === valor} onChange={() => setResultado(valor)} /> {texto}
                </label>
              );
            })}
            <Texto etiqueta="Motivo" valor={motivo} cambiar={setMotivo} filas={4} />
            <Texto etiqueta="Condiciones (opcional)" valor={condiciones} cambiar={setCondiciones} filas={2} />
            <Boton onClick={decidir} cargando={enviando} disabled={!resultado || motivo.trim().length < 10}>Guardar decisión</Boton>
            <p className="text-[13px] text-smn-gris-500">Se guarda con la evaluación, la ficha y la evidencia de hoy, aunque después cambien.</p>
          </>
        )}
      </div>
    </div>
  );
}
