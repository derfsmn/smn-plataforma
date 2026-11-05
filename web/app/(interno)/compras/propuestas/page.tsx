"use client";
// Bandeja de Compras: propuestas que ya envió algún proveedor y las que Compras captura por él (proveedor actual o nuevo). Las «listas para evaluar» son la entrada del radar de productos.

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, ChevronRight, PenLine, Search, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { estiloEstado, RUTA, type Bandeja, type Estado } from "@/lib/propuestas";
import { Capturar } from "./capturar";
import { Invitar } from "./invitar";

const FILTROS: { valor: Estado | ""; texto: string }[] = [
  { valor: "", texto: "Todas" },
  { valor: "recibida", texto: "Recibidas" },
  { valor: "en_revision", texto: "En revisión" },
  { valor: "devuelta", texto: "Con el proveedor" },
  { valor: "lista", texto: "Listas para evaluar" },
  { valor: "rechazada", texto: "Rechazadas" },
  { valor: "borrador", texto: "Capturas sin enviar" },
];

export default function BandejaPropuestas() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [datos, setDatos] = useState<Bandeja | null>(null);
  const [estado, setEstado] = useState<Estado | "">("");
  const [q, setQ] = useState("");
  const [invitando, setInvitando] = useState(false);
  const [capturando, setCapturando] = useState(false);

  const cargar = useCallback(() => {
    const params = new URLSearchParams();
    if (estado) params.set("estado", estado);
    if (q.trim()) params.set("q", q.trim());
    api<Bandeja>(`${RUTA}?${params}`).then(setDatos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [estado, q, avisar]);

  useEffect(() => {
    const t = setTimeout(cargar, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [cargar, q]);

  // «Todas» no cuenta los borradores: tienen su propio filtro
  const total = Object.entries(datos?.por_estado ?? {}).reduce((a, [k, b]) => a + (k === "borrador" ? 0 : b ?? 0), 0);

  return (
    <>
      <Entrada className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-smn-gris-500">
          Lo que los proveedores proponen desde su portal y lo que Compras captura por ellos. Revisa cada propuesta, regrésala si le falta algo y marca como lista la que pasa a evaluación.
        </p>
        <div className="flex flex-wrap gap-2">
          {puede("compras.propuestas.revisar") && (
            <Boton onClick={() => setCapturando(true)}>
              <PenLine className="h-4 w-4" /> Capturar producto
            </Boton>
          )}
          {puede("compras.proveedores.invitar") && (
            <Boton variante="secundario" onClick={() => setInvitando(true)}>
              <UserPlus className="h-4 w-4" /> Invitar proveedor
            </Boton>
          )}
        </div>
      </Entrada>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTROS.filter((f) => f.valor !== "borrador" || datos?.por_estado.borrador || estado === "borrador").map((f) => {
          const n = f.valor ? datos?.por_estado[f.valor] ?? 0 : total;
          return (
            <button
              key={f.valor}
              onClick={() => setEstado(f.valor)}
              className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition-colors ${estado === f.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:text-tinta"}`}
            >
              {f.texto} <span className="opacity-60">{n}</span>
            </button>
          );
        })}
        <label className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Folio, producto o proveedor"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
      </div>

      {datos === null ? (
        <div className="space-y-2">
          <Esqueleto className="h-20" />
          <Esqueleto className="h-20" />
          <Esqueleto className="h-20" />
        </div>
      ) : datos.propuestas.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          {total === 0 && !estado ? "Todavía no hay propuestas. Invita a un proveedor o captura un producto para empezar." : "No hay propuestas con este filtro."}
        </p>
      ) : (
        <ul className="space-y-2">
          {datos.propuestas.map((p, i) => (
            <motion.li key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.3) }}>
              <Link href={p.capturada_por_compras && (p.estado === "borrador" || p.estado === "devuelta") ? `/compras/propuestas/captura/${p.id}` : `/compras/propuestas/${p.id}`} className="group flex items-center gap-4 rounded-2xl border border-smn-gris-100 bg-superficie p-4 transition hover:border-smn-naranja">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{p.producto ?? "Producto sin nombre"}</p>
                  <p className="truncate text-sm text-smn-gris-500">
                    {p.folio ?? "Sin folio"} · {p.empresa}{p.capturada_por_compras && " · captura de Compras"} · {p.departamento ?? "Sin departamento"} · {p.presentaciones} {p.presentaciones === 1 ? "presentación" : "presentaciones"}
                  </p>
                  {p.enviada_en ? (
                    <p className="text-[13px] text-smn-gris-500">Enviada el {fechaLocal(p.enviada_en)}</p>
                  ) : (
                    <p className="text-[13px] text-smn-gris-500">Guardada el {fechaLocal(p.actualizada_en)}</p>
                  )}
                </div>
                {p.alertas > 0 && (
                  <span className="flex items-center gap-1 text-[13px] font-semibold text-aviso-texto" title="Revisiones automáticas en alerta">
                    <AlertTriangle className="h-4 w-4" /> {p.alertas}
                  </span>
                )}
                <Insignia className={estiloEstado[p.estado]}>{p.estado_texto}</Insignia>
                <ChevronRight className="h-5 w-5 shrink-0 text-smn-gris-500 transition group-hover:translate-x-0.5 group-hover:text-smn-naranja" />
              </Link>
            </motion.li>
          ))}
        </ul>
      )}

      <AnimatePresence>{invitando && <Invitar cerrar={() => setInvitando(false)} listo={() => {}} />}</AnimatePresence>
      <AnimatePresence>{capturando && <Capturar cerrar={() => setCapturando(false)} />}</AnimatePresence>
    </>
  );
}
