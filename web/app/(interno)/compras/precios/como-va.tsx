"use client";
// Radar de precios · Cómo va el radar (solo administración; plan del 25 nov, pantalla 3): avance de la revisión de noche,
// cómo estamos contra cada tienda y por qué hay productos sin comparar. Compras no ve esta pantalla.

import { Moon } from "lucide-react";
import { useEffect, useState } from "react";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { type Tablero } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Entrada, Esqueleto, Insignia } from "@/componentes/ui";

const n = (v: number) => v.toLocaleString("es-MX");

export function ComoVa() {
  const avisar = useAvisos();
  const [t, setT] = useState<Tablero | null>(null);
  useEffect(() => {
    api<Tablero>("/api/compras/precios/tablero?grupo=todos&por_pagina=1").then(setT).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  if (!t) return <Esqueleto className="mb-6 h-48" />;
  const sin = Object.entries(t.sin_comparar);
  const totalSin = sin.reduce((a, [, v]) => a + v, 0);
  return (
    <div className="mb-8 space-y-5">
      <BandaAvance t={t} />
      <div className="grid gap-5 lg:grid-cols-2">
        {t.tiendas.length > 0 && (
          <Entrada retraso={0.05}>
            <section className="h-full rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
              <h2 className="text-lg font-semibold">Contra cada tienda</h2>
              <p className="mb-4 text-[13px] text-smn-gris-500">En los productos que tenemos en común. Parejos = ±2 %.</p>
              <ul className="space-y-4">
                {t.tiendas.map((s) => (
                  <li key={s.nombre}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2 text-[15px]">
                      <b className="font-medium">{s.nombre}</b>
                      <span className="text-[13px] text-smn-gris-700">
                        {s.frase}
                        {s.productos > 0 && <span className="text-smn-gris-500"> · {n(s.productos)} productos</span>}
                      </span>
                    </div>
                    <Barra s={s} />
                  </li>
                ))}
              </ul>
              <p className="mt-3 flex flex-wrap gap-4 text-[13px] text-smn-gris-500">
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-600" /> Estamos más caros</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-smn-gris-300" /> Parejos</span>
                <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-green-600" /> Estamos más baratos</span>
              </p>
            </section>
          </Entrada>
        )}
        <Entrada retraso={0.1}>
          <section className="h-full rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
            <h2 className="text-lg font-semibold">Por qué hay productos sin comparar</h2>
            <p className="mb-4 text-[13px] text-smn-gris-500">
              {n(totalSin)} de {n(t.catalogo)} productos con resultado todavía no tienen un precio del mercado firme.
            </p>
            {sin.length === 0 ? (
              <p className="text-[14px] text-smn-gris-500">Todos los productos con resultado ya se comparan.</p>
            ) : (
              <ul className="space-y-2.5">
                {sin.map(([motivo, cuantos]) => (
                  <li key={motivo}>
                    <div className="mb-1 flex items-baseline justify-between gap-3 text-[14px]">
                      <span>{motivo}</span>
                      <b className="tabular-nums">{n(cuantos)}</b>
                    </div>
                    <div className="h-2 rounded-full bg-smn-gris-100">
                      <div className="h-2 rounded-full bg-smn-gris-500" style={{ width: `${(cuantos * 100) / Math.max(1, totalSin)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </Entrada>
      </div>
    </div>
  );
}

function BandaAvance({ t }: { t: Tablero }) {
  const a = t.avance;
  const hecho = a.total ? Math.round((a.validados * 100) / a.total) : 0;
  return (
    <Entrada>
      <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tinta text-superficie">
              <Moon className="h-4 w-4" />
            </span>
            <div>
              <p className="text-[15px] font-medium">Revisión de precios de noche <span className="font-normal text-smn-gris-700">· {a.texto}</span></p>
              <p className="text-[13px] text-smn-gris-500">
                {a.activo ? `Se revisa cada noche de ${a.desde}:00 a ${a.hasta}:00, primero los AA.` : "La revisión de noche está apagada en Configuración."}
                {t.actualizado && ` Última actualización: ${haceCuanto(t.actualizado).toLowerCase()}.`}
              </p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-2xl font-semibold tabular-nums">
              {n(a.validados)} <span className="text-[15px] font-normal text-smn-gris-500">de {n(a.total)}</span>
            </span>
            <p className="text-[13px] text-smn-gris-500 tabular-nums">productos ya validados ({hecho} %)</p>
          </div>
        </div>
        <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-smn-gris-100" role="img" aria-label={`${n(a.validados)} de ${n(a.total)} con precios validados`}>
          <span className="bg-green-600" style={{ width: `${a.total ? (a.validados * 100) / a.total : 0}%` }} />
          <span className="bg-yellow-500" style={{ width: `${a.total ? (a.dudosos * 100) / a.total : 0}%` }} />
          <span className="bg-smn-gris-300" style={{ width: `${a.total ? (a.sin_referencia * 100) / a.total : 0}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-smn-gris-700">
          <span><b className="tabular-nums">{n(a.validados)}</b> validados</span>
          <span><b className="tabular-nums">{n(a.dudosos)}</b> se revisan otra noche</span>
          <span><b className="tabular-nums">{n(a.sin_referencia)}</b> sin referencia en internet</span>
          <span><b className="tabular-nums">{n(a.sin_revisar)}</b> por revisar</span>
        </div>
        {Object.keys(a.por_clase).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {Object.entries(a.por_clase).map(([c, v]) => (
              <Insignia key={c} className="bg-smn-gris-100 text-smn-gris-700 tabular-nums">
                {c} {n(v.validados)}/{n(v.total)}
              </Insignia>
            ))}
          </div>
        )}
      </section>
    </Entrada>
  );
}

function Barra({ s }: { s: Tablero["tiendas"][number] }) {
  if (!s.productos) return <div className="h-2.5 rounded-full bg-smn-gris-100" />;
  const w = (v: number) => `${(v * 100) / s.productos}%`;
  return (
    <div className="flex h-2.5 overflow-hidden rounded-full" role="img" aria-label={`${s.mas_caros} más caros, ${s.parejos} parejos, ${s.mas_baratos} más baratos`}>
      <span className="bg-red-600" style={{ width: w(s.mas_caros) }} />
      <span className="bg-smn-gris-300" style={{ width: w(s.parejos) }} />
      <span className="bg-green-600" style={{ width: w(s.mas_baratos) }} />
    </div>
  );
}

