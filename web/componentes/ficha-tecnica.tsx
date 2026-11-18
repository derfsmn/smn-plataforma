"use client";

import { Flag } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";

export type CampoFicha = { campo: string; nombre: string; valor: string | null; origen: string | null; cita: string | null };
export type FichaTecnica = {
  estado: "lista" | "dudosa" | "fallida" | "mal";
  nota: string | null;
  extraida_en: string;
  con_ia: boolean;
  mal_motivo: string | null;
  mal_en: string | null;
  campos: CampoFicha[];
};

const ORIGEN: Record<string, string> = { reglas: "del texto", texto: "lo leyó la IA", foto: "de la foto", catalogo: "del catálogo" };

/** Ficha técnica estándar que llena la máquina (migración 0047). Nadie la aprueba: si algo está mal, se marca con
 * motivo y deja de usarse al momento (Diego, 17 nov 2026). `ruta` es la de la API que la regresa; la de «Está mal» es
 * la misma + «/esta-mal». */
export function FichaTecnicaTarjeta({ ruta }: { ruta: string }) {
  const avisar = useAvisos();
  const [ficha, setFicha] = useState<FichaTecnica | null | undefined>(undefined);
  const [marcando, setMarcando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(() => {
    api<FichaTecnica | null>(ruta).then(setFicha).catch(() => setFicha(null));
  }, [ruta]);
  useEffect(cargar, [cargar]);

  if (ficha === undefined || ficha === null) return null;
  const conValor = ficha.campos.filter((c) => c.valor);
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Ficha técnica</h2>
        {ficha.estado !== "mal" && (
          <button type="button" onClick={() => setMarcando(true)} className="inline-flex items-center gap-1 text-sm font-semibold text-naranja-tinta hover:underline">
            <Flag className="h-4 w-4" aria-hidden /> Está mal
          </button>
        )}
      </div>
      {ficha.estado === "mal" ? (
        <p className="rounded-xl bg-aviso-fondo px-3 py-2 text-sm text-aviso-texto">
          Marcada como mal: {ficha.mal_motivo}. Ya no se usa; se vuelve a leer al recalcular.
        </p>
      ) : ficha.estado !== "lista" ? (
        <p className="text-sm text-smn-gris-500">No se pudo saber qué es ni cuánto trae; no cuenta para comparar y se vuelve a intentar.</p>
      ) : null}
      {conValor.length > 0 && (
        <dl className="mt-1 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {conValor.map((c) => (
            <div key={c.campo} className="min-w-0">
              <dt className="text-[13px] text-smn-gris-500">{c.nombre}</dt>
              <dd className="font-semibold" title={c.cita ? `«${c.cita}»` : undefined}>
                {c.valor}
                {c.origen && <span className="ml-1 text-[13px] font-normal text-smn-gris-500">· {ORIGEN[c.origen] ?? c.origen}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-3 text-[13px] text-smn-gris-500">Leída el {fechaLocal(ficha.extraida_en)}. Cada dato sale del texto o la foto del producto; lo que no dice, se queda vacío.</p>
      {marcando && (
        <Modal titulo="¿Qué está mal en la ficha?" cerrar={() => setMarcando(false)}>
          <textarea
            value={motivo}
            onChange={(x) => setMotivo(x.target.value)}
            rows={3}
            maxLength={500}
            placeholder="Ej. son 20 sobres, no 25"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-sm outline-none focus:border-smn-naranja"
          />
          <div className="mt-3 flex justify-end gap-2">
            <Boton variante="secundario" onClick={() => setMarcando(false)}>Cancelar</Boton>
            <Boton
              cargando={enviando}
              disabled={motivo.trim().length < 3}
              onClick={async () => {
                setEnviando(true);
                try {
                  setFicha(await api<FichaTecnica>(`${ruta}/esta-mal`, { cuerpo: { motivo: motivo.trim() } }));
                  setMarcando(false);
                  setMotivo("");
                  avisar("Gracias. La ficha ya no se usa y se vuelve a leer.", "exito");
                } catch (e) {
                  avisar(mensajeDe(e), "info");
                } finally {
                  setEnviando(false);
                }
              }}
            >
              Marcar «Está mal»
            </Boton>
          </div>
        </Modal>
      )}
    </section>
  );
}
