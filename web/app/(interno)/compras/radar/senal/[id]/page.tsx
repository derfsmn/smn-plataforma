"use client";
// Detalle de una señal: sus notas, en qué reportes salió y las decisiones. Los botones del correo llegan aquí con ?accion=.

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { History } from "lucide-react";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_ACCION, fechaCorta, fechaHora, type Accion, type SenalDetalle } from "@/lib/radar";
import { useSesion } from "@/componentes/sesion";
import { Entrada, Esqueleto } from "@/componentes/ui";
import { BotonesDecision, Etiquetas, Nota, VentanaDecision } from "../../piezas";

export default function PaginaSenal() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <DetalleSenal />
    </Suspense>
  );
}

function DetalleSenal() {
  const { id } = useParams<{ id: string }>();
  const pedida = useSearchParams().get("accion") as Accion | null;
  const router = useRouter();
  const { puede } = useSesion();
  const [s, setS] = useState<SenalDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accion, setAccion] = useState<Accion | null>(null);

  const cargar = useCallback(() => {
    api<SenalDetalle>(`/api/compras/radar/senales/${id}`).then(setS).catch((e) => setError(mensajeDe(e)));
  }, [id]);
  useEffect(cargar, [cargar]);
  useEffect(() => {
    if (pedida && ["iniciativa", "vigilar", "descartar"].includes(pedida) && puede("compras.radar.decidir")) setAccion(pedida);
  }, [pedida, puede]);

  if (error) return <p className="text-smn-gris-500">{error}</p>;
  if (!s) return <Esqueleto className="h-64" />;

  const cerrar = () => {
    setAccion(null);
    if (pedida) router.replace(`/compras/radar/senal/${id}`);
  };

  return (
    <div className="space-y-6">
      <Entrada className="rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-7">
        <Etiquetas nivel={s.nivel} tipo={s.tipo} estado={s.estado} area={s.area} paises={s.paises} />
        <h2 className="mt-3 text-2xl font-semibold">{s.titulo}</h2>
        {s.descripcion && <p className="mt-2 text-smn-gris-700">{s.descripcion}</p>}
        <p className="mt-3 text-sm text-smn-gris-500">
          Vista desde el {fechaCorta(s.primera_vez)} · última vez el {fechaCorta(s.ultima_vez)} · {s.articulos} nota{s.articulos === 1 ? "" : "s"} en{" "}
          {s.sitios_distintos} sitio{s.sitios_distintos === 1 ? "" : "s"} · salió en {s.veces_reportada} reporte{s.veces_reportada === 1 ? "" : "s"}
        </p>
        <p className="mt-1 text-[13px] text-smn-gris-500">
          Es tendencia cuando la respaldan 2 o más sitios distintos, o cuando aparece en EUA y en México; si no, es señal emergente.
        </p>
        {puede("compras.radar.decidir") && (
          <div className="mt-5">
            <BotonesDecision senalId={s.id} titulo={s.titulo} alDecidir={cargar} />
          </div>
        )}
      </Entrada>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Entrada retraso={0.05} className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h3 className="font-semibold">Notas que la respaldan</h3>
          <ul className="mt-2 divide-y divide-smn-gris-100">
            {s.lista_articulos.map((a) => (
              <Nota key={a.id} a={a} detalle />
            ))}
          </ul>
        </Entrada>
        <Entrada retraso={0.1} className="space-y-6">
          <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h3 className="flex items-center gap-2 font-semibold">
              <History className="h-4 w-4 text-smn-naranja" /> Decisiones
            </h3>
            {s.acciones.length === 0 ? (
              <p className="mt-2 text-sm text-smn-gris-500">Nadie ha decidido sobre esta señal.</p>
            ) : (
              <ol className="mt-2 space-y-3">
                {s.acciones.map((a, i) => (
                  <li key={i} className="text-sm">
                    <p className="font-semibold">{TEXTO_ACCION[a.accion]}</p>
                    <p className="text-[13px] text-smn-gris-500">
                      {a.usuario} · {fechaHora(a.ocurrido_en)}
                    </p>
                    {a.motivo && <p className="mt-0.5 text-smn-gris-700">“{a.motivo}”</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
          <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h3 className="font-semibold">Salió en los reportes</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {s.reportes.map((f) => (
                <li key={f}>
                  <Link href={`/compras/radar?fecha=${f}`} className="font-semibold hover:underline">
                    {fechaCorta(f)}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </Entrada>
      </div>
      <AnimatePresence>{accion && <VentanaDecision senalId={s.id} titulo={s.titulo} accion={accion} cerrar={cerrar} alDecidir={cargar} />}</AnimatePresence>
    </div>
  );
}
