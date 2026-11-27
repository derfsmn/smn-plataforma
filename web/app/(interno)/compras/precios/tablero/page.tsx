"use client";
// Radar de precios · Tablero al día (Diego, 26 nov 2026). Solo radar de precios, sin costos («no metamos costos»): cuántos
// productos ya se comparan, cuántos están más caros o más baratos, el dinero en juego al mes, lo que pide acción por agente,
// los precios del mercado que se movieron y cómo va la revisión de noche.

import { ArrowDownRight, ArrowUpRight, Moon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, dolares, haceCuanto, mensajeDe } from "@/lib/api";
import { SEMAFORO, pct, type TableroDia } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Entrada, Esqueleto } from "@/componentes/ui";
import { Miniatura, monto } from "../piezas";
import { dinero } from "../tabla-filas";

const n = (v: number) => v.toLocaleString("es-MX");
const diaCorto = (f: string) => new Date(`${f}T12:00:00`).toLocaleDateString("es-MX", { weekday: "short", day: "numeric" });

export default function TableroAlDia() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [t, setT] = useState<TableroDia | null>(null);
  const [falla, setFalla] = useState<string | null>(null);
  useEffect(() => {
    api<TableroDia>("/api/compras/precios/tablero/dia")
      .then(setT)
      .catch((e) => {
        setFalla(mensajeDe(e));
        avisar(mensajeDe(e), "info");
      });
  }, [avisar]);
  // Si la consulta falla no se queda el esqueleto para siempre (revisión de usabilidad, 26 nov 2026)
  if (!t && falla) return <p className="rounded-xl border border-smn-gris-100 bg-superficie p-5 text-[15px] text-smn-gris-700">No se pudo cargar el tablero: {falla} Vuelve a abrir la página en un momento.</p>;
  if (!t) return <Esqueleto className="h-96" />;

  const caros = t.mas_caros + t.un_poco_caros;
  const pctComparados = t.catalogo ? Math.round((t.comparados / t.catalogo) * 100) : 0;
  const tramos = [
    { k: "rojo" as const, v: t.mas_caros, texto: "Más caros" },
    { k: "amarillo" as const, v: t.un_poco_caros, texto: "Un poco más caros" },
    { k: "verde" as const, v: t.mas_baratos, texto: "Igual o más baratos" },
  ];
  const a = t.avance;
  const maxDia = Math.max(1, ...t.dias.map((d) => d.productos));

  return (
    <div className="space-y-5">
      <p className="text-[13px] text-smn-gris-500">
        {t.actualizado ? `Precios actualizados ${haceCuanto(t.actualizado).toLowerCase()}` : "Todavía no hay precios"}
        {t.en_curso && ` · ${t.en_curso.toLowerCase()}`}. Precios en MXN con impuestos.
      </p>

      <Entrada>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Cuadro titulo="Productos comparados" valor={n(t.comparados)} pie={`de ${n(t.catalogo)} en el radar (${pctComparados} %)`} />
          <Cuadro titulo="Más caros que el mercado" valor={n(caros)} pie={`${n(t.mas_caros)} muy caros · ${n(t.un_poco_caros)} un poco`} punto="bg-red-600" liga="/compras/precios?grupo=rojo" />
          <Cuadro titulo="Igual o más baratos" valor={n(t.mas_baratos)} pie={t.comparados ? `${Math.round((t.mas_baratos / t.comparados) * 100)} % de los comparados` : ""} punto="bg-green-600" liga="/compras/precios?grupo=verde" />
          <Cuadro
            titulo="Dinero en juego al mes"
            valor={dinero(t.en_juego_caros)}
            pie={Number(t.en_juego_subir) > 0 ? `por estar más caros · ${dinero(t.en_juego_subir)} donde se podría subir` : "por estar más caros"}
          />
        </div>
      </Entrada>

      {t.comparados > 0 && (
        <Entrada retraso={0.04}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
            <h2 className="text-[15px] font-semibold">Cómo estamos contra el mercado</h2>
            <div className="mt-3 flex h-3 gap-0.5 overflow-hidden rounded-full" role="img" aria-label={tramos.map((x) => `${x.texto}: ${x.v}`).join(", ")}>
              {tramos
                .filter((x) => x.v)
                .map((x) => (
                  <span key={x.k} className={`${SEMAFORO[x.k].punto} first:rounded-l-full last:rounded-r-full`} style={{ flexGrow: x.v }} title={`${x.texto}: ${n(x.v)}`} />
                ))}
            </div>
            <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
              {tramos.map((x) => (
                <li key={x.k} className="flex items-center gap-1.5">
                  <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[x.k].punto}`} aria-hidden />
                  {x.texto} <b className="tabular-nums">{n(x.v)}</b>
                </li>
              ))}
              <li className="flex items-center gap-1.5 text-smn-gris-500">
                <span className="h-2.5 w-2.5 rounded-full bg-smn-gris-300" aria-hidden />
                Sin comparar <b className="tabular-nums">{n(t.sin_comparar)}</b>
              </li>
            </ul>
          </section>
        </Entrada>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-2">
        <Entrada retraso={0.08}>
          <section className="h-full rounded-xl border border-smn-gris-100 bg-superficie">
            <div className="border-b border-smn-gris-100 px-4 py-3 sm:px-5">
              <h2 className="text-[15px] font-semibold">Acciones pendientes por agente</h2>
              <p className="text-[13px] text-smn-gris-500">Productos que piden bajar precio, negociar costo o revisar si se sube.</p>
            </div>
            {t.agentes.length === 0 ? (
              <p className="px-4 py-8 text-center text-smn-gris-500">Todavía no hay productos en el radar.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[14px]">
                  <thead className="text-left text-[13px] text-smn-gris-500">
                    <tr className="border-b border-smn-gris-100">
                      <th className="px-4 py-2 font-medium sm:px-5">Agente</th>
                      <th className="px-2 py-2 text-right font-medium">Bajar</th>
                      <th className="px-2 py-2 text-right font-medium">Negociar</th>
                      <th className="px-2 py-2 text-right font-medium">Subir</th>
                      <th className="px-4 py-2 text-right font-medium sm:px-5">En juego al mes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-smn-gris-100">
                    {t.agentes.map((g) => (
                      <tr key={g.agente} className="hover:bg-smn-gris-100/40">
                        <td className="px-4 py-2.5 sm:px-5">
                          <Link
                            href={`/compras/precios?agente=${encodeURIComponent(g.agente === "Sin agente" ? "sin_agente" : g.agente)}`}
                            className="font-medium hover:underline"
                          >
                            {g.agente}
                          </Link>
                          <span className="block text-[13px] text-smn-gris-500">
                            {n(g.comparados)} de {n(g.productos)} comparados
                          </span>
                        </td>
                        <td className="px-2 py-2.5 text-right tabular-nums">{g.bajar || "—"}</td>
                        <td className="px-2 py-2.5 text-right tabular-nums">{g.negociar || "—"}</td>
                        <td className="px-2 py-2.5 text-right tabular-nums">{g.subir || "—"}</td>
                        <td className="px-4 py-2.5 text-right font-semibold whitespace-nowrap tabular-nums sm:px-5">{Number(g.en_juego) > 0 ? dinero(g.en_juego) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </Entrada>

        <Entrada retraso={0.1}>
          <section className="h-full rounded-xl border border-smn-gris-100 bg-superficie">
            <div className="border-b border-smn-gris-100 px-4 py-3 sm:px-5">
              <h2 className="text-[15px] font-semibold">Precios del mercado que se movieron</h2>
              <p className="text-[13px] text-smn-gris-500">
                Cambios de 5 % o más en las últimas dos semanas · <span className="tabular-nums">{n(t.subieron)}</span> subieron,{" "}
                <span className="tabular-nums">{n(t.bajaron)}</span> bajaron
              </p>
            </div>
            {t.movimientos.length === 0 ? (
              <p className="px-4 py-8 text-center text-[14px] text-smn-gris-500">Ningún precio del mercado se movió 5 % o más en las últimas dos semanas.</p>
            ) : (
              <ul className="divide-y divide-smn-gris-100">
                {t.movimientos.map((m) => {
                  const sube = Number(m.cambio_pct) > 0;
                  const Flecha = sube ? ArrowUpRight : ArrowDownRight;
                  return (
                    <li key={m.producto_id}>
                      <Link href={`/compras/precios?producto=${m.producto_id}&q=${encodeURIComponent(m.sku)}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-smn-gris-100/40 sm:px-5">
                        <Miniatura liga={m.imagen} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{m.descripcion ?? m.sku}</span>
                          <span className="block text-[13px] text-smn-gris-500 tabular-nums">
                            Mercado {monto(m.antes)} → {monto(m.ahora)} · nuestro {monto(m.nuestro)}
                          </span>
                        </span>
                        <span className="flex shrink-0 items-center gap-0.5 font-semibold tabular-nums">
                          <Flecha className="h-4 w-4" aria-label={sube ? "Subió" : "Bajó"} />
                          {pct(m.cambio_pct)}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </Entrada>
      </div>

      <Entrada retraso={0.12}>
        <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-[15px] font-semibold">
                <Moon className="h-4 w-4" /> Revisión de noche
              </h2>
              <p className="text-[13px] text-smn-gris-500">
                {a.activo ? `De ${a.desde}:00 a ${a.hasta}:00, lotes de ${a.lote} productos` : "Está apagada en Configuración"}
                {a.texto && ` · ${a.texto}`}
              </p>
            </div>
            <p className="text-right text-[14px]">
              <b className="text-xl tabular-nums">{n(a.validados)}</b> de {n(a.total)} validados
              <span className="block text-[13px] text-smn-gris-500">{a.total ? Math.round((a.validados / a.total) * 100) : 0} % del radar</span>
            </p>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-smn-gris-100">
            <span className="block h-full rounded-full bg-smn-naranja" style={{ width: `${a.total ? Math.max(1, (a.validados / a.total) * 100) : 0}%` }} />
          </div>
          <div className="mt-4 grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            <dl className="grid grid-cols-2 gap-3 text-[14px]">
              <Dato t="Última noche" v={t.noche.lotes ? `${n(t.noche.productos)} productos en ${t.noche.lotes} lotes` : "Sin lotes"} />
              <Dato t="Con precios" v={n(t.noche.con_precios)} />
              {/* El gasto en dólares solo lo ve quien administra (criterio de Diego) */}
              {puede("compras.precios.administrar") && <Dato t="Búsquedas de la noche" v={dolares(t.noche.costo_usd)} />}
              <Dato t="Por revisar" v={`${n(a.sin_revisar + a.dudosos)}${a.noches_faltan ? ` · unas ${a.noches_faltan} noches` : ""}`} />
            </dl>
            <div>
              <p className="text-[13px] text-smn-gris-500">Productos revisados por día (últimos 14)</p>
              <div className="mt-2 flex h-24 items-end gap-0.5" role="img" aria-label="Productos revisados por día">
                {t.dias.map((d) => (
                  <span key={d.fecha} className="group relative flex h-full flex-1 items-end" title={`${diaCorto(d.fecha)}: ${n(d.productos)} productos`}>
                    <span
                      className="block w-full rounded-t-[4px] bg-smn-naranja group-hover:brightness-90"
                      style={{ height: d.productos ? `${Math.max(4, (d.productos / maxDia) * 100)}%` : "2px", opacity: d.productos ? 1 : 0.25 }}
                    />
                  </span>
                ))}
              </div>
              <div className="mt-1 flex justify-between text-[12px] text-smn-gris-500">
                <span>{diaCorto(t.dias[0].fecha)}</span>
                <span>hoy</span>
              </div>
            </div>
          </div>
        </section>
      </Entrada>
    </div>
  );
}

function Cuadro({ titulo, valor, pie, punto, liga }: { titulo: string; valor: string; pie: string; punto?: string; liga?: string }) {
  const cuerpo = (
    <>
      <p className="flex items-center gap-1.5 text-[13px] text-smn-gris-700">
        {punto && <span className={`h-2.5 w-2.5 rounded-full ${punto}`} aria-hidden />}
        {titulo}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums sm:text-[28px]">{valor}</p>
      {pie && <p className="text-[13px] text-smn-gris-500">{pie}</p>}
    </>
  );
  const clase = "block h-full rounded-xl border border-smn-gris-100 bg-superficie p-4";
  return liga ? (
    <Link href={liga} className={`${clase} hover:border-smn-gris-300`}>
      {cuerpo}
    </Link>
  ) : (
    <div className={clase}>{cuerpo}</div>
  );
}

function Dato({ t, v }: { t: string; v: string }) {
  return (
    <div>
      <dt className="text-[13px] text-smn-gris-500">{t}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}
