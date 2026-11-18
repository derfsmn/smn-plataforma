"use client";
// «Está mal» (Diego, 2026-11-17): Compras no valida nada; si ve un precio que no es, lo marca con motivo. Sale al momento,
// no se vuelve a elegir y queda como caso de prueba. Aquí también se ve cómo se validó cada precio.

import { Check, CircleHelp, ExternalLink, Minus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { MOTIVOS_MAL, type Comprobacion, type ValidacionProducto } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Esqueleto } from "@/componentes/ui";
import { precio } from "./piezas";

const ICONO = { ok: Check, no: X, sin_dato: CircleHelp, no_aplica: Minus };
const CLASE = {
  ok: "text-green-700 dark:text-green-400",
  no: "text-red-700 dark:text-red-400",
  sin_dato: "text-yellow-800 dark:text-yellow-300",
  no_aplica: "text-smn-gris-500",
};

export function Comprobaciones({ lista }: { lista: Comprobacion[] }) {
  if (!lista.length) return <p className="text-[13px] text-smn-gris-500">De antes de la validación automática.</p>;
  return (
    <ul className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
      {lista.map((c) => {
        const Icono = ICONO[c.estado];
        return (
          <li key={c.clave} className="flex items-start gap-1.5 text-[13px]">
            <Icono className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${CLASE[c.estado]}`} aria-hidden />
            <span>
              <b className="font-medium">{c.nombre}:</b> <span className="text-smn-gris-700">{c.texto}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function EstaMal({ productoId, nombre, cerrar, listo }: { productoId: number; nombre: string; cerrar: () => void; listo?: () => void }) {
  const avisar = useAvisos();
  const [v, setV] = useState<ValidacionProducto | null>(null);
  const [elegidos, setElegidos] = useState<number[]>([]);
  const [motivo, setMotivo] = useState<string>("otro_producto");
  const [nota, setNota] = useState("");
  const [abierto, setAbierto] = useState<number | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    api<ValidacionProducto>(`/api/compras/precios/productos/${productoId}/validacion`).then(setV).catch((e) => avisar(mensajeDe(e), "info"));
  }, [productoId, avisar]);

  const cuentan = v?.precios.filter((p) => p.cuenta) ?? [];
  const fuera = v?.precios.filter((p) => !p.cuenta && !p.marcado_mal) ?? [];
  const cambiar = (id: number) => setElegidos((e) => (e.includes(id) ? e.filter((x) => x !== id) : [...e, id]));

  const guardar = async () => {
    setGuardando(true);
    try {
      const r = await api<ValidacionProducto>(`/api/compras/precios/productos/${productoId}/esta-mal`, {
        metodo: "POST",
        cuerpo: { observacion_ids: elegidos, motivo, nota: nota.trim() || null },
      });
      setV(r);
      setElegidos([]);
      setNota("");
      avisar(elegidos.length > 1 ? "Listo: esos precios ya no cuentan" : "Listo: ese precio ya no cuenta", "exito");
      listo?.();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <Modal titulo="¿Qué precio está mal?" cerrar={cerrar} ancho="max-w-2xl">
      <p className="-mt-2 mb-4 text-sm text-smn-gris-500">{nombre}</p>
      {!v ? (
        <Esqueleto className="h-40" />
      ) : (
        <>
          {cuentan.length === 0 ? (
            <p className="rounded-xl bg-smn-gris-100/60 px-4 py-6 text-center text-sm text-smn-gris-500">Ningún precio cuenta hoy para este producto.</p>
          ) : (
            <ul className="divide-y divide-smn-gris-100 rounded-xl border border-smn-gris-100">
              {cuentan.map((p) => (
                <li key={p.observacion_id} className="px-3 py-2.5">
                  <label className="flex cursor-pointer items-start gap-3">
                    <input
                      type="checkbox"
                      checked={elegidos.includes(p.observacion_id)}
                      onChange={() => cambiar(p.observacion_id)}
                      className="mt-1 h-[18px] w-[18px] accent-smn-naranja"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-baseline justify-between gap-2">
                        <b className="font-semibold">{p.vendedor}</b>
                        <span className="font-semibold tabular-nums">{precio(p.precio)}</span>
                      </span>
                      <span className="block text-[13px] text-smn-gris-700">{p.titulo ?? "Sin título"}</span>
                      <span className="mt-0.5 flex flex-wrap gap-3 text-[13px]">
                        {p.liga && (
                          <a href={p.liga} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-naranja-tinta underline underline-offset-2">
                            Ver en la tienda <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                        <button type="button" onClick={(e) => (e.preventDefault(), setAbierto(abierto === p.observacion_id ? null : p.observacion_id))} className="text-smn-gris-500 underline underline-offset-2">
                          {abierto === p.observacion_id ? "Ocultar" : "Cómo se validó"}
                        </button>
                      </span>
                    </span>
                  </label>
                  {abierto === p.observacion_id && (
                    <div className="mt-2 ml-8 rounded-lg bg-smn-gris-100/50 p-2.5">
                      <Comprobaciones lista={p.comprobaciones} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {cuentan.length > 0 && (
            <div className="mt-4 grid gap-3 sm:grid-cols-[220px_1fr]">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Qué está mal</span>
                <select
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
                >
                  {MOTIVOS_MAL.map((m) => (
                    <option key={m.valor} value={m.valor}>
                      {m.texto}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Nota {motivo === "otro" ? "" : "(opcional)"}</span>
                <input
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  maxLength={400}
                  placeholder="Ej. es la presentación de 1 kg"
                  className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
                />
              </label>
            </div>
          )}

          {fuera.length > 0 && (
            <details className="mt-4 text-sm">
              <summary className="cursor-pointer text-smn-gris-500">{fuera.length === 1 ? "1 precio que no cuenta y por qué" : `${fuera.length} precios que no cuentan y por qué`}</summary>
              <ul className="mt-2 space-y-1.5">
                {fuera.map((p) => (
                  <li key={p.observacion_id} className="text-[13px]">
                    <b>{p.vendedor}</b> {precio(p.precio)} · <span className="text-smn-gris-500">{p.motivo}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {v.marcas.some((m) => m.activo) && (
            <div className="mt-4 text-[13px] text-smn-gris-500">
              Ya marcados:{" "}
              {v.marcas
                .filter((m) => m.activo)
                .map((m) => `${m.vendedor} (${m.motivo_texto.toLowerCase()}${m.usuario ? `, ${m.usuario}` : ""})`)
                .join(" · ")}
            </div>
          )}

          <div className="mt-5 flex justify-end gap-2">
            <Boton variante="fantasma" onClick={cerrar}>
              Cerrar
            </Boton>
            {cuentan.length > 0 && (
              <Boton onClick={guardar} cargando={guardando} disabled={!elegidos.length || (motivo === "otro" && !nota.trim())}>
                Marcar {elegidos.length > 1 ? `${elegidos.length} precios` : "precio"}
              </Boton>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
