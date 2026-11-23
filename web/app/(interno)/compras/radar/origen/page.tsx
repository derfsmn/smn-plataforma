"use client";
// Radar · De dónde sale la información: lo mismo que «Fuentes y temas», pero de solo lectura para Compras.
// Sin interruptores ni lápices: solo qué se lee, de qué tipo es y cuándo se leyó por última vez.

import { ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_FUENTE_TIPO, fechaHora, type Fuente, type Tema } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { Esqueleto } from "@/componentes/ui";

const ORDEN: Fuente["tipo"][] = ["oficial", "especializada", "negocios", "estudios"];
const QUE_ES: Record<Fuente["tipo"], string> = {
  oficial: "Autoridades de salud y comercio: alertas, retiros y cambios de reglas.",
  especializada: "Medios del sector naturista y de suplementos.",
  negocios: "Prensa de negocios y consumo.",
  estudios: "Estudios de mercado y de tendencias.",
};

export default function Origen() {
  const avisar = useAvisos();
  const [fuentes, setFuentes] = useState<Fuente[] | null>(null);
  const [temas, setTemas] = useState<Tema[] | null>(null);

  useEffect(() => {
    api<Fuente[]>("/api/compras/radar/fuentes").then(setFuentes).catch((e) => avisar(mensajeDe(e), "info"));
    api<Tema[]>("/api/compras/radar/temas").then(setTemas).catch(() => setTemas([]));
  }, [avisar]);

  const grupos = useMemo(() => {
    const activas = (fuentes ?? []).filter((f) => f.activa);
    return ORDEN.map((t) => [t, activas.filter((f) => f.tipo === t)] as const).filter(([, l]) => l.length > 0);
  }, [fuentes]);

  if (!fuentes || !temas) return <Esqueleto className="h-64" />;
  const activos = temas.filter((t) => t.activo);

  return (
    <div className="space-y-8">
      <p className="max-w-2xl text-[15px] text-smn-gris-700">
        Cada mañana el radar lee <b className="text-tinta">{grupos.reduce((a, [, l]) => a + l.length, 0)} sitios</b> y busca{" "}
        <b className="text-tinta">{activos.length} temas</b>. Cada tendencia lleva la liga a su fuente para que la puedas abrir.
      </p>

      {activos.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">Temas que se buscan</h2>
          <ul className="flex flex-wrap gap-2">
            {activos.map((t) => (
              <li key={t.id} title={t.descripcion} className="rounded-full bg-smn-gris-100 px-3 py-1 text-sm font-medium text-smn-gris-700">
                {t.nombre}
              </li>
            ))}
          </ul>
        </section>
      )}

      {grupos.map(([tipo, lista]) => (
        <section key={tipo}>
          <h2 className="text-lg font-semibold">
            {TEXTO_FUENTE_TIPO[tipo]} <span className="font-normal text-smn-gris-500">({lista.length})</span>
          </h2>
          <p className="mb-3 text-sm text-smn-gris-500">{QUE_ES[tipo]}</p>
          <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
            {lista.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3">
                <a href={f.liga} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1.5 font-medium hover:text-naranja-tinta">
                  <span className="truncate">{f.nombre}</span>
                  <ExternalLink className="h-3.5 w-3.5 shrink-0 text-smn-gris-500" aria-hidden />
                </a>
                <span className="text-[13px] text-smn-gris-500">
                  {f.pais} · {f.idioma === "es" ? "español" : "inglés"}
                  {f.ultima_lectura_en ? ` · leída ${fechaHora(f.ultima_lectura_en)}` : " · aún no se lee"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
