"use client";
// Base de conocimiento · Avance: qué secciones ya llenó Compras y qué falta para que el semáforo las use.

import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import { useEffect, useState } from "react";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { type Resumen } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { Entrada, Esqueleto } from "@/componentes/ui";

const LIGA: Record<string, string> = {
  politicas: "/compras/conocimiento/politicas",
  rechazo: "/compras/conocimiento/rechazo",
  criterios: "/compras/conocimiento/criterios",
  pesos: "/compras/conocimiento/pesos",
  exito: "/compras/conocimiento/exito",
  casos: "/compras/conocimiento/casos",
  proceso: "/compras/conocimiento/proceso",
};

const CUANTOS: Record<string, (n: number) => string> = {
  politicas: (n) => `${n} vigente${n === 1 ? "" : "s"}`,
  rechazo: (n) => `${n} motivo${n === 1 ? "" : "s"}`,
  criterios: (n) => `${n} criterio${n === 1 ? "" : "s"}`,
  pesos: (n) => `${n} de 100 puntos`,
  exito: (n) => `${n} meta${n === 1 ? "" : "s"}`,
  casos: (n) => `${n} caso${n === 1 ? "" : "s"}`,
  proceso: (n) => (n ? "Descrito" : "Sin describir"),
};

export default function Avance() {
  const avisar = useAvisos();
  const [r, setR] = useState<Resumen | null>(null);
  useEffect(() => {
    api<Resumen>("/api/compras/conocimiento/resumen").then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  if (!r) return <Esqueleto className="h-64" />;
  const pct = Math.round((r.listas / r.total) * 100);

  return (
    <div className="space-y-6">
      <Entrada className="rounded-2xl border border-smn-gris-100 bg-superficie p-6">
        <p className="text-[13px] font-medium text-naranja-tinta">Para el semáforo de productos</p>
        <p className="mt-1 max-w-3xl text-smn-gris-700">
          Aquí Compras deja por escrito cómo decide hoy si un producto entra: sus políticas, lo que rechaza de inmediato, los valores que revisa, cuánto pesa cada factor, qué es un lanzamiento exitoso y casos pasados. El semáforo usará esto para sugerir un color con su explicación; la decisión sigue siendo de Compras.
        </p>
        <div className="mt-5 flex items-center gap-4">
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-smn-gris-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Avance">
            <div className="h-full rounded-full bg-smn-naranja transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="shrink-0 font-semibold">
            {r.listas} de {r.total} secciones
          </p>
        </div>
        {r.actualizado_en && <p className="mt-2 text-[13px] text-smn-gris-500">Último cambio: {fechaLocal(r.actualizado_en)}</p>}
      </Entrada>

      <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
        {r.secciones.map((s, i) => (
          <li key={s.clave}>
            <Link href={LIGA[s.clave]} className="group flex items-center gap-4 p-4 transition-colors hover:bg-smn-gris-50">
              {s.lista ? <CheckCircle2 className="h-6 w-6 shrink-0 text-smn-naranja" aria-label="Lista" /> : <Circle className="h-6 w-6 shrink-0 text-smn-gris-500" aria-label="Pendiente" />}
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {i + 1}. {s.titulo} <span className="ml-1 text-sm font-semibold text-smn-gris-500">· {CUANTOS[s.clave]?.(s.cuantos) ?? s.cuantos}</span>
                </p>
                {s.falta && <p className="text-sm text-smn-gris-500">{s.falta}</p>}
              </div>
              <ArrowRight className="h-5 w-5 shrink-0 text-smn-gris-500 transition group-hover:translate-x-1 group-hover:text-smn-naranja" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
