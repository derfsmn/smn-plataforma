"use client";
// Datos → Proveedores: cada proveedor con su calificación de 0 a 100 armada con compras, venta, costo e inventario de SMNBI.
// Los pesos son provisionales hasta que Compras los ponga en la Base de conocimiento.

import { AnimatePresence } from "motion/react";
import { AlertTriangle, Calculator, FileSpreadsheet, Info, Search, Truck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { descargar } from "@/lib/precios";
import { COLOR, CONFIANZA, RUTA, type ColorProveedor, type FichaProveedor, type FilaProveedor, type ListaProveedores } from "@/lib/proveedores";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";

type FiltroColor = "" | ColorProveedor | "sin_datos";
const dinero = (v: string | number | null) => (v === null ? "—" : pesos(Math.round(Number(v))));
const num = (v: number | null | undefined, sufijo = "") => (v === null || v === undefined ? "—" : `${v.toLocaleString("es-MX", { maximumFractionDigits: 1 })}${sufijo}`);

function Puntaje({ valor, color }: { valor: number | null; color: FiltroColor | null }) {
  const c = COLOR[color || "sin_datos"];
  return (
    <span className="inline-flex items-center gap-2 font-semibold tabular-nums">
      <span className={`h-2.5 w-2.5 rounded-full ${c.punto}`} aria-hidden />
      {valor ?? "—"}
    </span>
  );
}

function Barra({ valor }: { valor: number | null }) {
  if (valor === null) return <span className="text-smn-gris-500">—</span>;
  return (
    <span className="inline-flex items-center gap-2 tabular-nums" title={`${valor} de 100`}>
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-smn-gris-100">
        <span className={`block h-full rounded-full ${valor > 80 ? "bg-emerald-500" : valor >= 60 ? "bg-amber-400" : "bg-red-500"}`} style={{ width: `${valor}%` }} />
      </span>
      {valor}
    </span>
  );
}

export default function Proveedores() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const calcula = puede("datos.proveedores.calcular");
  const [l, setL] = useState<ListaProveedores | null>(null);
  const [texto, setTexto] = useState("");
  const [q, setQ] = useState("");
  const [color, setColor] = useState<FiltroColor>("");
  const [orden, setOrden] = useState("venta");
  const [agente, setAgente] = useState("");
  const [rfc, setRfc] = useState("");
  const [ficha, setFicha] = useState<string | null>(null);
  const [lanzando, setLanzando] = useState(false);
  const corria = useRef(false);

  const cargar = useCallback(() => {
    const p = new URLSearchParams({ q, color, orden, agente, rfc });
    api<ListaProveedores>(`${RUTA}?${p}`).then(setL).catch((e) => avisar(mensajeDe(e), "info"));
  }, [q, color, orden, agente, rfc, avisar]);
  useEffect(cargar, [cargar]);

  useEffect(() => {
    const t = setTimeout(() => setQ(texto.trim()), 300);
    return () => clearTimeout(t);
  }, [texto]);

  // Mientras se calcula se revisa cada 2 segundos; al terminar se avisa
  const enCurso = l?.en_curso;
  useEffect(() => {
    if (enCurso) {
      corria.current = true;
      const t = setTimeout(cargar, 2000);
      return () => clearTimeout(t);
    }
    if (corria.current && l) {
      corria.current = false;
      const ok = l.evaluacion?.estado === "completa";
      avisar(ok ? "Calificación lista" : "El cálculo no terminó; revisa el detalle", ok ? "exito" : "info");
    }
  }, [enCurso, l, cargar, avisar]);

  const [bajando, setBajando] = useState(false);
  const bajarExcel = async () => {
    setBajando(true);
    try {
      const sufijo = agente ? ` - ${agente}` : "";
      await descargar(`${RUTA}/excel?${new URLSearchParams({ agente })}`, `Proveedores en alta con agente${sufijo} - ${new Date().toLocaleDateString("en-CA")}.xlsx`);
    } catch (err) {
      avisar(mensajeDe(err), "info");
    } finally {
      setBajando(false);
    }
  };
  const calcular = async () => {
    setLanzando(true);
    try {
      await api(`${RUTA}/calcular`, { metodo: "POST" });
      avisar("Calculando la calificación de los proveedores", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(false);
    }
  };

  const ev = l?.evaluacion;
  const tarjetas: { id: FiltroColor; texto: string }[] = [
    { id: "", texto: "Todos" },
    { id: "verde", texto: "Verde" },
    { id: "amarillo", texto: "Amarillo" },
    { id: "rojo", texto: "Rojo" },
    { id: "sin_datos", texto: "Sin datos suficientes" },
  ];
  const total = l ? Object.values(l.conteo).reduce((s, n) => s + (n ?? 0), 0) : 0;

  return (
    <>
      <Encabezado
        titulo="Proveedores"
        descripcion="Cada proveedor con una calificación de 0 a 100 armada con lo que ya tenemos en SMNBI: órdenes de compra, venta, costo e inventario."
        accion={
          <div className="flex flex-wrap gap-2">
            {l?.evaluacion && (
              <Boton
                variante="secundario"
                onClick={bajarExcel}
                cargando={bajando}
                disabled={agente === "-" || !l.reporte?.proveedores}
                title={agente === "-" ? "El reporte es de proveedores con agente" : undefined}
              >
                <FileSpreadsheet className="h-4 w-4" /> Excel para Compras
              </Boton>
            )}
            {calcula && (
              <Boton onClick={calcular} cargando={lanzando || !!enCurso} disabled={!l || !!enCurso}>
                <Calculator className="h-4 w-4" /> {enCurso ? "Calculando…" : "Calcular"}
              </Boton>
            )}
          </div>
        }
      />

      {!l ? (
        <Esqueleto className="h-72" />
      ) : (
        <>
          {l.evaluacion && l.reporte?.desactualizada && (
            <p className="mb-4 flex items-start gap-2 rounded-xl bg-aviso-fondo px-4 py-3 text-sm text-aviso-texto">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              Después de la última calificación se volvió a cargar: {l.reporte.desactualizada}. Pulsa «Calcular» antes de bajar el Excel para que salga al día.
            </p>
          )}
          <Entrada className="mb-5 rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-sm">
            <p className="flex items-center gap-2 font-semibold">
              <Info className="h-4 w-4 text-smn-naranja" /> Cómo se califica
              <Insignia className={l.pesos_de === "compras" ? "bg-emerald-100 text-emerald-700" : "bg-aviso-fondo text-aviso-texto"}>
                {l.pesos_de === "compras" ? "Pesos de Compras" : "Pesos provisionales"}
              </Insignia>
            </p>
            <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {l.bloques.map((b) => (
                <li key={b.clave} className="rounded-xl bg-smn-gris-100/50 p-3">
                  <p className="flex items-baseline justify-between gap-2 font-semibold">
                    {b.nombre} <span className="text-lg font-semibold tabular-nums">{b.peso}</span>
                  </p>
                  <p className="mt-1 text-[13px] text-smn-gris-500">{b.que_mide}</p>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-smn-gris-500">
              Verde arriba de 80, amarillo de 60 a 80, rojo abajo de 60. Si a un proveedor le falta un bloque, se califica con los que sí tiene y baja la confianza.{" "}
              {l.pesos_de === "provisionales" ? "Los pesos y las escalas son una propuesta inicial de Transformación Digital; " : ""}
              Compras puede cambiar los pesos en{" "}
              <Link href="/compras/conocimiento/pesos" className="font-semibold text-naranja-tinta hover:underline">
                Base de conocimiento → Peso de cada factor
              </Link>
              ; cuentan desde el siguiente cálculo.
            </p>
          </Entrada>

          {ev ? (
            <p className="mb-4 text-sm text-smn-gris-500">
              {ev.estado === "fallida" ? (
                <span className="text-red-700 dark:text-red-400">
                  <AlertTriangle className="mr-1 inline h-4 w-4" />
                  El último cálculo falló: {ev.error}
                </span>
              ) : (
                <>
                  Calculado el {fechaLocal(ev.terminada_en ?? ev.iniciada_en)}
                  {ev.iniciada_por && ` por ${ev.iniciada_por}`} · {ev.calificados ?? 0} de {ev.proveedores ?? 0} proveedores con calificación.
                  {[ev.contexto.venta, ev.contexto.compras, ev.contexto.inventario, ev.contexto.precios].filter(Boolean).length > 0 &&
                    ` Datos: ${[ev.contexto.venta, ev.contexto.compras, ev.contexto.inventario, ev.contexto.precios].filter(Boolean).join("; ")}.`}
                  {ev.contexto.margen_empresa != null && ` Margen de toda la empresa: ${num(ev.contexto.margen_empresa, " %")}.`}
                </>
              )}
            </p>
          ) : null}

          {!ev ? (
            <div className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-6 py-12 text-center">
              <Truck className="mx-auto mb-3 h-10 w-10 text-smn-gris-500" />
              <p className="font-semibold">{enCurso ? "Calculando la primera calificación…" : "Todavía no hay calificación"}</p>
              <p className="mt-1 text-sm text-smn-gris-500">
                {calcula ? "Da clic en «Calcular» para calificar a los proveedores con los datos cargados de SMNBI." : "Alguien de Compras debe dar clic en «Calcular»."}
              </p>
            </div>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap gap-2">
                {tarjetas.map((t) => {
                  const n = t.id === "" ? total : l.conteo[t.id] ?? 0;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setColor(t.id)}
                      aria-pressed={color === t.id}
                      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors ${color === t.id ? "border-smn-naranja bg-smn-naranja/10" : "border-smn-gris-100 bg-superficie hover:border-smn-gris-300"}`}
                    >
                      {t.id && <span className={`h-2.5 w-2.5 rounded-full ${COLOR[t.id].punto}`} aria-hidden />}
                      {t.texto} <span className="tabular-nums text-smn-gris-500">{n.toLocaleString("es-MX")}</span>
                    </button>
                  );
                })}
              </div>

              <div className="mb-4 grid gap-3 sm:grid-cols-2 sm:items-end lg:grid-cols-[1fr_auto_auto_auto]">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Buscar</span>
                  <span className="relative block">
                    <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
                    <input
                      value={texto}
                      onChange={(e) => setTexto(e.target.value)}
                      placeholder="Nombre, código o RFC del proveedor"
                      className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 outline-none placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                    />
                  </span>
                </label>
                <Selector
                  etiqueta="Ordenar por"
                  valor={orden}
                  cambiar={setOrden}
                  opciones={[
                    { valor: "venta", texto: "Más venta" },
                    { valor: "compra", texto: "Más compra" },
                    { valor: "puntaje", texto: "Peor calificación" },
                    { valor: "nombre", texto: "Nombre" },
                  ]}
                  className="lg:w-52"
                />
                <Selector
                  etiqueta="Agente"
                  valor={agente}
                  cambiar={setAgente}
                  opciones={[{ valor: "", texto: "Todos" }, { valor: "-", texto: "Sin agente" }, ...(l.agentes ?? []).map((a) => ({ valor: a, texto: a }))]}
                  className="lg:w-44"
                />
                <Selector
                  etiqueta="RFC"
                  valor={rfc}
                  cambiar={setRfc}
                  opciones={[{ valor: "", texto: "Todos" }, { valor: "con", texto: "Con RFC" }, { valor: "sin", texto: "Sin RFC" }]}
                  className="lg:w-40"
                />
              </div>

              {!l.filas.length ? (
                <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">Ningún proveedor coincide.</p>
              ) : (
                <Tabla filas={l.filas} bloques={l.bloques} abrir={setFicha} />
              )}
            </>
          )}
        </>
      )}

      <AnimatePresence>{ficha && <Ficha codigo={ficha} cerrar={() => setFicha(null)} />}</AnimatePresence>
    </>
  );
}

function Tabla({ filas, bloques, abrir }: { filas: FilaProveedor[]; bloques: ListaProveedores["bloques"]; abrir: (c: string) => void }) {
  return (
    <>
      <div className="hidden overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie md:block">
        <table className="w-full text-sm">
          <thead className="bg-smn-gris-100/60 text-left text-[13px] font-medium text-smn-gris-500">
            <tr>
              <th className="px-4 py-3">Proveedor</th>
              <th className="px-4 py-3">Calificación</th>
              {bloques.map((b) => (
                <th key={b.clave} className="hidden px-3 py-3 lg:table-cell">
                  {b.nombre}
                </th>
              ))}
              <th className="px-4 py-3 text-right">Venta 26 sem.</th>
              <th className="hidden px-4 py-3 text-right xl:table-cell">Compra 12 m.</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-smn-gris-100">
            {filas.map((f) => (
              <tr key={f.proveedor} onClick={() => abrir(f.proveedor)} className="cursor-pointer transition-colors hover:bg-smn-gris-100/50">
                <td className="px-4 py-3">
                  <p className="font-semibold">{f.nombre ?? "Sin nombre"}</p>
                  <p className="text-[13px] text-smn-gris-500">
                    {f.proveedor} · {f.skus_activos} SKU activos{f.agente && ` · Agente ${f.agente}`}
                  </p>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <Puntaje valor={f.puntaje} color={f.color} />
                  <p className="text-[13px] text-smn-gris-500">{CONFIANZA[f.confianza]}</p>
                </td>
                {bloques.map((b) => (
                  <td key={b.clave} className="hidden px-3 py-3 lg:table-cell">
                    <Barra valor={f[b.clave]} />
                  </td>
                ))}
                <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">{dinero(f.venta)}</td>
                <td className="hidden px-4 py-3 text-right whitespace-nowrap tabular-nums xl:table-cell">{dinero(f.compra)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-2 md:hidden">
        {filas.map((f) => (
          <li key={f.proveedor}>
            <button onClick={() => abrir(f.proveedor)} className="w-full rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-left">
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="block font-semibold">{f.nombre ?? "Sin nombre"}</span>
                  <span className="block text-[13px] text-smn-gris-500">
                    {f.proveedor} · {f.skus_activos} SKU activos{f.agente && ` · Agente ${f.agente}`}
                  </span>
                </span>
                <Puntaje valor={f.puntaje} color={f.color} />
              </span>
              <span className="mt-2 block text-sm text-smn-gris-500 tabular-nums">
                Venta {dinero(f.venta)} · {CONFIANZA[f.confianza]}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[13px] text-smn-gris-500">Venta sin IVA de las últimas 26 semanas; arriba dice de qué fechas y qué incluye. Da clic en un proveedor para ver su ficha.</p>
    </>
  );
}

function Dato({ titulo, valor, nota }: { titulo: string; valor: React.ReactNode; nota?: string }) {
  return (
    <div className="rounded-xl bg-smn-gris-100/50 p-3">
      <p className="text-[13px] text-smn-gris-500">{titulo}</p>
      <p className="text-lg font-semibold tabular-nums">{valor}</p>
      {nota && <p className="text-[13px] text-smn-gris-500">{nota}</p>}
    </div>
  );
}

function Seccion({ titulo, valor, children }: { titulo: string; valor: number | null; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 flex items-center justify-between gap-2 font-semibold">
        {titulo} <Barra valor={valor} />
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{children}</div>
    </section>
  );
}

function Ficha({ codigo, cerrar }: { codigo: string; cerrar: () => void }) {
  const avisar = useAvisos();
  const [f, setF] = useState<FichaProveedor | null>(null);
  useEffect(() => {
    api<FichaProveedor>(`${RUTA}/${encodeURIComponent(codigo)}`).then(setF).catch((e) => avisar(mensajeDe(e), "info"));
  }, [codigo, avisar]);
  const m = f?.metricas;
  const maxPedidas = f ? Math.max(1, ...f.ordenes_por_mes.map((o) => o.pedidas)) : 1;

  return (
    <Modal titulo={f ? f.nombre ?? f.proveedor : "Proveedor"} cerrar={cerrar} ancho="max-w-3xl">
      {!f || !m ? (
        <Esqueleto className="h-64" />
      ) : (
        <div className="space-y-6 text-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-3xl">
              <Puntaje valor={f.puntaje} color={f.color} />
            </span>
            <Insignia className={COLOR[f.color ?? "sin_datos"].insignia}>{COLOR[f.color ?? "sin_datos"].texto}</Insignia>
            <span className="text-smn-gris-500">{CONFIANZA[f.confianza]}</span>
            <span className="text-smn-gris-500">
              · Código {f.proveedor}
              {f.estatus && ` · ${f.estatus}`} · Agente {f.agente ?? "sin capturar"} · RFC {f.rfc ?? "sin capturar"}
            </span>
          </div>
          {m.notas.length > 0 && (
            <ul className="space-y-1 rounded-xl bg-aviso-fondo p-3 text-aviso-texto">
              {m.notas.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}

          <Seccion titulo="Cumplimiento" valor={f.cumplimiento}>
            {m.cumplimiento ? (
              <>
                <Dato titulo="Órdenes en 12 meses" valor={m.cumplimiento.ordenes} />
                <Dato titulo="Piezas surtidas" valor={num(m.cumplimiento.surtido_pct, " %")} nota="de lo pedido" />
                <Dato titulo="Perdidas o rechazadas" valor={num(m.cumplimiento.perdidas_rechazadas_pct, " %")} nota="de lo pedido" />
                <Dato titulo="Días hábiles a la primera entrada" valor={num(m.cumplimiento.dias_reales)} nota={m.cumplimiento.dias_prometidos ? `promete ${m.cumplimiento.dias_prometidos}` : "sin días prometidos"} />
                <Dato titulo="Retraso" valor={m.cumplimiento.retraso_dias === null ? "—" : `${num(m.cumplimiento.retraso_dias)} días hábiles`} />
              </>
            ) : (
              <p className="col-span-full text-smn-gris-500">Sin órdenes suficientes.</p>
            )}
          </Seccion>

          <Seccion titulo="Desempeño comercial" valor={f.comercial}>
            {m.comercial ? (
              <>
                <Dato titulo="SKU activos" valor={m.comercial.skus_activos} />
                <Dato titulo="Con buena rotación" valor={m.comercial.buena_rotacion} nota={`${num(m.comercial.buena_rotacion_pct, " %")} de sus activos`} />
                <Dato titulo="Abajo de la permanencia" valor={m.comercial.debajo_permanencia} nota={`${num(m.comercial.debajo_permanencia_pct, " %")} de sus activos`} />
                <Dato titulo="Margen" valor={num(m.comercial.margen_pct, " %")} nota={m.comercial.margen_empresa_pct != null ? `empresa ${num(m.comercial.margen_empresa_pct, " %")}` : undefined} />
              </>
            ) : (
              <p className="col-span-full text-smn-gris-500">Sin venta de sus productos activos.</p>
            )}
          </Seccion>

          <Seccion titulo="Costo y condiciones" valor={f.costo}>
            <Dato titulo="Alza de costo" valor={num(m.costo?.alza_costo_pct, " %")} nota="último costo contra el promedio de 12 meses" />
            <Dato titulo="Condición de pago" valor={f.condicion ?? "—"} nota={m.costo?.dias_credito != null ? `${m.costo.dias_credito} días de crédito` : undefined} />
            <Dato titulo="Descuento" valor={f.descuento ?? "—"} />
          </Seccion>

          <Seccion titulo="Inventario" valor={f.inventario}>
            {m.inventario ? (
              <>
                <Dato titulo="Piezas en existencia" valor={m.inventario.existencia.toLocaleString("es-MX")} />
                <Dato titulo="Días de inventario" valor={num(m.inventario.dias)} nota="al ritmo de las últimas 13 semanas" />
                <Dato titulo="SKU con exceso" valor={m.inventario.skus_exceso} nota={`más de 180 días · ${num(m.inventario.skus_exceso_pct, " %")}`} />
              </>
            ) : (
              <p className="col-span-full text-smn-gris-500">Sin existencia en la última foto de inventario.</p>
            )}
          </Seccion>

          {m.precio_mercado && (
            <p className="rounded-xl border border-smn-gris-100 p-3">
              <b>Precio contra el mercado (solo informativo):</b> en {m.precio_mercado.productos} productos del último Radar de precios, la diferencia mediana es{" "}
              {num(m.precio_mercado.mediana_dif_pct, " %")}; {m.precio_mercado.mas_caros} están más caros que la competencia.
            </p>
          )}

          {f.ordenes_por_mes.length > 0 && (
            <section>
              <h3 className="mb-2 font-semibold">Órdenes por mes</h3>
              <ul className="space-y-1">
                {f.ordenes_por_mes.map((o) => (
                  <li key={o.mes} className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2 text-[13px] tabular-nums">
                    <span>{o.mes}</span>
                    <span className="relative h-3 overflow-hidden rounded-full bg-smn-gris-100">
                      <span className="absolute inset-y-0 left-0 rounded-full bg-smn-gris-300" style={{ width: `${(o.pedidas / maxPedidas) * 100}%` }} />
                      <span className="absolute inset-y-0 left-0 rounded-full bg-smn-naranja" style={{ width: `${(Math.min(o.recibidas, o.pedidas) / maxPedidas) * 100}%` }} />
                    </span>
                    <span className="text-smn-gris-500">
                      {o.ordenes} órd. · {Math.round(o.recibidas).toLocaleString("es-MX")} de {Math.round(o.pedidas).toLocaleString("es-MX")} pz
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[13px] text-smn-gris-500">Gris: piezas pedidas. Naranja: piezas recibidas.</p>
            </section>
          )}

          {m.skus && m.skus.length > 0 && (
            <section>
              <h3 className="mb-2 font-semibold">Sus productos con más venta</h3>
              <div className="overflow-x-auto rounded-xl border border-smn-gris-100">
                <table className="w-full text-[13px]">
                  <thead className="bg-smn-gris-100/60 text-left font-semibold text-smn-gris-500">
                    <tr>
                      <th className="px-3 py-2">Producto</th>
                      <th className="px-3 py-2 text-right">Pz por tienda al mes</th>
                      <th className="px-3 py-2 text-right">Venta</th>
                      <th className="px-3 py-2 text-right">Margen</th>
                      <th className="px-3 py-2 text-right">Días inv.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-smn-gris-100">
                    {m.skus.map((s) => (
                      <tr key={s.sku} className={s.activo ? "" : "opacity-60"}>
                        <td className="px-3 py-2">
                          <p className="font-semibold">{s.descripcion ?? s.sku}</p>
                          <p className="text-smn-gris-500">
                            {s.sku}
                            {s.departamento && ` · ${s.departamento}`}
                            {!s.activo && " · inactivo"}
                          </p>
                        </td>
                        <td className={`px-3 py-2 text-right tabular-nums ${s.activo && s.por_tienda_mes < s.permanencia ? "text-red-700 dark:text-red-400" : ""}`} title={`Meta ${s.meta} · permanencia ${s.permanencia}`}>
                          {num(s.por_tienda_mes)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{dinero(s.venta)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{num(s.margen_pct, " %")}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{s.sin_venta_con_existencia ? "sin venta" : num(s.dias_inventario)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-1 text-[13px] text-smn-gris-500">En rojo, los que venden menos que la permanencia mínima de la Base de conocimiento.</p>
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
