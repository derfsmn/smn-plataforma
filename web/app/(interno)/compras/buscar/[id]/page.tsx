"use client";
// Ficha completa de un producto del catálogo (buscador de Compras, 22 nov 2026). Junta en una pantalla lo que antes
// estaba repartido en cuatro: precio y membresía, venta de SMNBI, inventario del último corte, costo y margen,
// proveedor con su calificación y nuestro precio contra el mercado. Solo consulta.

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowUpRight, ExternalLink, Search, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { RUTA_BUSCADOR, hrefDe, piezas, type Ficha } from "@/lib/buscador";
import { SEMAFORO, dia, pct } from "@/lib/precios";
import { Miniatura, precio } from "../../precios/piezas";

const porcentaje = (n: number | null | undefined) => (n == null ? "—" : `${n.toLocaleString("es-MX", { maximumFractionDigits: 1 })} %`);
const semanaCorta = (f: string) => new Date(`${f}T12:00:00`).toLocaleDateString("es-MX", { day: "numeric", month: "short" });

export default function FichaProducto() {
  const { id } = useParams<{ id: string }>();
  const avisar = useAvisos();
  const { puede } = useSesion();
  const [f, setF] = useState<Ficha | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Ficha>(`${RUTA_BUSCADOR}/producto/${id}`).then(setF).catch((e) => {
      setError(mensajeDe(e));
      avisar(mensajeDe(e), "info");
    });
  }, [id, avisar]);

  const volver = (
    <Link href="/compras/buscar" className="mb-4 inline-flex items-center gap-1 text-[15px] text-smn-gris-500 hover:text-tinta">
      <ArrowLeft className="h-4 w-4" /> Buscar productos
    </Link>
  );
  if (error) return <>{volver}<p className="text-smn-gris-500">{error}</p></>;
  if (!f)
    return (
      <div className="space-y-4">
        <Esqueleto className="h-40" />
        <div className="grid gap-3 sm:grid-cols-4"><Esqueleto className="h-24" /><Esqueleto className="h-24" /><Esqueleto className="h-24" /><Esqueleto className="h-24" /></div>
        <Esqueleto className="h-64" />
      </div>
    );

  const v = f.venta;
  const inv = f.inventario;
  const tendencia = v?.tendencia_pct ?? null;

  return (
    <>
      {volver}
      {/* Encabezado: foto, nombre y precios */}
      <Entrada className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <div className="hidden sm:block"><Miniatura liga={f.imagen} grande /></div>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-naranja-tinta">
            SKU {f.sku}
            {f.codigo_barras && <span className="font-normal text-smn-gris-500"> · código de barras {f.codigo_barras}</span>}
          </p>
          <h1 className="mt-0.5 text-[28px] leading-tight font-semibold tracking-tight sm:text-[32px]">{f.descripcion ?? f.sku}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {!f.activo && <Insignia className="bg-smn-gris-100 text-smn-gris-700">Inactivo</Insignia>}
            {f.clasificacion && <Insignia className="bg-smn-naranja/15 text-aviso-texto">Clase {f.clasificacion}</Insignia>}
            {[f.marca, f.departamento, f.subcategoria].filter(Boolean).map((t) => (
              <Insignia key={t} className="bg-smn-gris-100 text-smn-gris-700">{t}</Insignia>
            ))}
          </div>
          <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2">
            <div>
              <dt className="text-[13px] text-smn-gris-500">Precio de lista</dt>
              <dd className="text-2xl font-semibold tabular-nums">{precio(f.precio_lista)}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-smn-gris-500">Membresía</dt>
              <dd className="text-2xl font-semibold tabular-nums">{precio(f.precio_membresia)}</dd>
            </div>
            {f.precio_tienda_en_linea && (
              <div>
                <dt className="text-[13px] text-smn-gris-500">Tienda en línea</dt>
                <dd className="text-2xl font-semibold tabular-nums">
                  {f.liga_producto ? (
                    <a href={f.liga_producto} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-naranja-tinta">
                      {precio(f.precio_tienda_en_linea)} <ExternalLink className="h-4 w-4 text-smn-gris-500" />
                    </a>
                  ) : (
                    precio(f.precio_tienda_en_linea)
                  )}
                </dd>
              </div>
            )}
          </dl>
          <p className="mt-1 text-[13px] text-smn-gris-500">Con impuestos.</p>
        </div>
      </Entrada>

      {/* Los cuatro números que más se preguntan */}
      <Entrada retraso={0.04} className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Cifra titulo="Venta al mes" valor={v?.al_mes != null ? `${piezas(v.al_mes)} pzas` : "Sin venta"}
          nota={tendencia == null ? (v ? `${piezas(v.piezas)} piezas en 26 semanas` : "Sin venta cargada") : (
            <span className={`inline-flex items-center gap-1 ${tendencia >= 0 ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}>
              {tendencia >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {tendencia >= 0 ? "+" : ""}{porcentaje(tendencia)} contra las 13 semanas anteriores
            </span>
          )} />
        <Cifra titulo="Inventario" valor={inv ? `${piezas(inv.existencia)} pzas` : "—"}
          nota={inv ? (inv.dias != null ? `Alcanza para ${piezas(inv.dias)} días` : `En ${inv.tiendas_con} tiendas`) : "Sin inventario cargado"} />
        <Cifra titulo="Margen" valor={porcentaje(f.costo?.margen_pct ?? v?.margen_real_pct)}
          nota={f.costo?.margen_pct != null ? "Precio de lista sin IVA contra el último costo" : v?.margen_real_pct != null ? "Real, de lo vendido" : "Sin costo cargado"} />
        <Cifra titulo="Contra el mercado" valor={f.mercado ? pct(f.mercado.diferencia_pct) : "—"}
          nota={f.mercado ? (f.mercado.color ? <ColorPrecio color={f.mercado.color} /> : "Sin comparación") : "No está en el radar de precios"} />
      </Entrada>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Tarjeta titulo="Venta por semana" nota={v ? v.nota.charAt(0).toUpperCase() + v.nota.slice(1) + ". Piezas netas (vendidas menos devueltas)." : undefined}>
            {v && v.piezas > 0 ? <GraficaSemanas semanas={v.semanas} /> : <Vacio texto="Este producto no tiene venta en las últimas 26 semanas." />}
            {v && v.mejores.length > 0 && (
              <>
                <h3 className="mt-5 mb-2 text-sm font-semibold">Dónde se vende más</h3>
                <Barras filas={v.mejores.map((t) => ({ clave: t.almacen, texto: t.nombre, valor: t.piezas }))} unidad="pzas" />
                <p className="mt-2 text-[13px] text-smn-gris-500">
                  Vendió en {v.tiendas} {v.tiendas === 1 ? "tienda" : "tiendas"} · {v.importe.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 })} MXN sin IVA en 26 semanas
                </p>
              </>
            )}
          </Tarjeta>

          <Tarjeta titulo="Inventario" nota={inv ? `Corte del ${dia(inv.corte)}.` : undefined}>
            {!inv ? (
              <Vacio texto="Todavía no hay inventario cargado." />
            ) : (
              <>
                <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                  <p><b className="text-lg tabular-nums">{inv.tiendas_con}</b> <span className="text-smn-gris-500">tiendas con existencia</span></p>
                  <p className={inv.tiendas_en_cero ? "text-red-700 dark:text-red-400" : ""}>
                    <b className="text-lg tabular-nums">{inv.tiendas_en_cero}</b> <span className={inv.tiendas_en_cero ? "" : "text-smn-gris-500"}>en cero donde sí se vende</span>
                  </p>
                </div>
                {inv.mayores.length > 0 && (
                  <>
                    <h3 className="mt-5 mb-2 text-sm font-semibold">Dónde hay más</h3>
                    <Barras filas={inv.mayores.map((t) => ({ clave: t.almacen, texto: t.nombre, valor: t.existencia }))} unidad="pzas" />
                  </>
                )}
              </>
            )}
          </Tarjeta>
        </div>

        <aside className="space-y-4">
          <Tarjeta titulo="Proveedor y costo">
            {!f.proveedor && !f.costo ? (
              <Vacio texto="Sin proveedor ni costo cargados." />
            ) : (
              <dl className="space-y-3 text-sm">
                {f.proveedor && (
                  <div>
                    <dt className="text-[13px] text-smn-gris-500">Proveedor</dt>
                    <dd className="flex flex-wrap items-center gap-2 font-medium">
                      {f.proveedor.nombre ?? f.proveedor.codigo}
                      {f.proveedor.puntaje != null && (
                        <span className="text-[13px] font-normal text-smn-gris-500">{f.proveedor.puntaje} de 100</span>
                      )}
                      {f.proveedor.color && <InsigniaColor color={f.proveedor.color} />}
                    </dd>
                  </div>
                )}
                {f.proveedor && (f.proveedor.dias_entrega != null || f.proveedor.dias_reales != null) && (
                  <Par titulo="Días de entrega" valor={[
                    f.proveedor.dias_entrega != null && `promete ${f.proveedor.dias_entrega}`,
                    f.proveedor.dias_reales != null && `cumple en ${piezas(f.proveedor.dias_reales)}`,
                  ].filter(Boolean).join(" · ")} />
                )}
                {f.proveedor?.surtido_pct != null && <Par titulo="Surte" valor={`${porcentaje(f.proveedor.surtido_pct)} de lo pedido`} />}
                {f.proveedor?.condicion && <Par titulo="Condición" valor={f.proveedor.condicion} />}
                {f.costo && (
                  <>
                    <Par titulo="Último costo, sin IVA" valor={`${precio(f.costo.ultimo)}${f.costo.fecha_ultima ? ` · ${dia(f.costo.fecha_ultima, "medium")}` : ""}`} />
                    {f.costo.promedio_12m && <Par titulo="Costo promedio en 12 meses" valor={precio(f.costo.promedio_12m)} />}
                  </>
                )}
                {f.proveedor && puede("datos.proveedores.ver") && (
                  <Link href={`/datos/proveedores?codigo=${encodeURIComponent(f.proveedor.codigo)}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-naranja-tinta hover:underline">
                    Ver al proveedor <ArrowUpRight className="h-3.5 w-3.5" />
                  </Link>
                )}
              </dl>
            )}
          </Tarjeta>

          <Tarjeta titulo="Contra el mercado" nota={f.mercado ? `Radar de precios del ${dia(f.mercado.fecha)}.` : undefined}>
            {!f.mercado ? (
              <Vacio texto="Este producto no está en el radar de precios." />
            ) : (
              <dl className="space-y-3 text-sm">
                <Par titulo="Mediana de la competencia" valor={precio(f.mercado.mediana)} />
                <Par titulo="Más barato y más caro" valor={`${precio(f.mercado.minimo)} a ${precio(f.mercado.maximo)}`} />
                <Par titulo="Tiendas comparadas" valor={String(f.mercado.vendedores)} />
                <Link href={`/compras/precios/producto/${f.id}`} className="inline-flex items-center gap-1 text-[13px] font-medium text-naranja-tinta hover:underline">
                  Ver la comparación completa <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </dl>
            )}
          </Tarjeta>

          {f.relacionados.length > 0 && (
            <Tarjeta titulo="En el radar de productos" nota="Ideas o propuestas con el mismo código de barras.">
              <ul className="space-y-2">
                {f.relacionados.map((r) => (
                  <li key={`${r.tipo}-${r.id}`}>
                    <Link href={hrefDe(r)} className="flex items-center gap-2 rounded-xl p-2 text-sm hover:bg-smn-gris-50">
                      <span className="min-w-0 flex-1 truncate font-medium">{r.titulo}</span>
                      <InsigniaColor color={r.color} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Tarjeta>
          )}

          <Link href="/compras/buscar" className="flex items-center justify-center gap-2 rounded-2xl border border-dashed border-smn-gris-300 p-4 text-sm font-medium text-smn-gris-700 hover:border-smn-naranja hover:text-tinta">
            <Search className="h-4 w-4" /> Buscar otro producto
          </Link>
        </aside>
      </div>
    </>
  );
}

function Cifra({ titulo, valor, nota }: { titulo: string; valor: string; nota: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <p className="text-[13px] text-smn-gris-500">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{valor}</p>
      <p className="mt-1 text-[13px] leading-snug text-smn-gris-500">{nota}</p>
    </div>
  );
}

function ColorPrecio({ color }: { color: "verde" | "amarillo" | "rojo" }) {
  const s = SEMAFORO[color];
  const texto = color === "verde" ? "Igual o más barato" : color === "amarillo" ? "Un poco más caro" : "Más caro que el mercado";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${s.punto}`} aria-hidden /> {texto}
    </span>
  );
}

function Tarjeta({ titulo, nota, children }: { titulo: string; nota?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="font-semibold">{titulo}</h2>
      {nota && <p className="mt-0.5 mb-4 text-[13px] text-smn-gris-500">{nota}</p>}
      {!nota && <div className="mb-4" />}
      {children}
    </section>
  );
}

function Par({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-[13px] text-smn-gris-500">{titulo}</dt>
      <dd className="font-medium tabular-nums">{valor}</dd>
    </div>
  );
}

function Vacio({ texto }: { texto: string }) {
  return <p className="rounded-xl bg-smn-gris-50 p-4 text-sm text-smn-gris-500">{texto}</p>;
}

/** Barras horizontales: el nombre a la izquierda, el número a la derecha y la barra debajo. */
function Barras({ filas, unidad }: { filas: { clave: string; texto: string; valor: number }[]; unidad: string }) {
  const max = Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="space-y-2.5">
      {filas.map((f) => (
        <li key={f.clave} className="text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="truncate">{f.texto}</span>
            <span className="shrink-0 tabular-nums text-smn-gris-700">{piezas(f.valor)} {unidad}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-smn-gris-100">
            <div className="h-full rounded-full bg-smn-naranja" style={{ width: `${Math.max(2, (f.valor / max) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Barras de 26 semanas. Al pasar el ratón (o tocar) cada barra dice su semana, piezas e importe. */
function GraficaSemanas({ semanas }: { semanas: Ficha["venta"] extends infer V ? (V extends { semanas: infer S } ? S : never) : never }) {
  const [activa, setActiva] = useState<number | null>(null);
  const max = Math.max(...semanas.map((s) => s.piezas), 1);
  const alto = 160;
  const s = activa != null ? semanas[activa] : null;
  return (
    <div>
      <div className="mb-2 h-5 text-[13px] text-smn-gris-700" aria-live="polite">
        {s ? (
          <>
            Semana del <b>{semanaCorta(s.semana)}</b>: <b className="tabular-nums">{piezas(s.piezas)}</b> pzas ·{" "}
            {s.importe.toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 })} MXN
          </>
        ) : (
          <span className="text-smn-gris-500">Toca o pasa el ratón sobre una barra para ver la semana.</span>
        )}
      </div>
      <div className="relative" onMouseLeave={() => setActiva(null)}>
        {/* línea del máximo, discreta */}
        <div className="pointer-events-none absolute inset-x-0 top-0 border-t border-dashed border-smn-gris-100" />
        <span className="pointer-events-none absolute -top-2 right-0 bg-superficie pl-1 text-[11px] text-smn-gris-500 tabular-nums">{piezas(max)}</span>
        <div className="flex items-end gap-[2px]" style={{ height: alto }} role="img" aria-label={`Venta de las últimas ${semanas.length} semanas, máximo ${piezas(max)} piezas`}>
          {semanas.map((x, i) => (
            <button
              key={x.semana}
              type="button"
              onMouseEnter={() => setActiva(i)}
              onFocus={() => setActiva(i)}
              onClick={() => setActiva(i)}
              aria-label={`Semana del ${semanaCorta(x.semana)}: ${piezas(x.piezas)} piezas`}
              className="group flex h-full min-w-0 flex-1 items-end"
            >
              <span
                className={`block w-full rounded-t-[4px] transition-colors ${activa === i ? "bg-tinta" : "bg-smn-naranja group-hover:bg-tinta"}`}
                style={{ height: x.piezas > 0 ? `${Math.max(2, (x.piezas / max) * 100)}%` : 0 }}
              />
            </button>
          ))}
        </div>
        <div className="mt-1.5 flex justify-between border-t border-smn-gris-100 pt-1 text-[11px] text-smn-gris-500">
          <span>{semanaCorta(semanas[0].semana)}</span>
          <span>{semanaCorta(semanas[Math.floor(semanas.length / 2)].semana)}</span>
          <span>{semanaCorta(semanas[semanas.length - 1].semana)}</span>
        </div>
      </div>
    </div>
  );
}
