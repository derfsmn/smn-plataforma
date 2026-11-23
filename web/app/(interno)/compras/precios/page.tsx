"use client";
// Radar de precios · Resumen (Diego, 2026-11-17: «quiero que ese radar de precios sea muy fácil de ver»).
// Banda de avance de la noche, 4 cuadros de color, cómo estamos contra cada tienda y lo que pide acción, ordenado por venta.
// Compras no valida nada: si ve un precio que no es, lo marca con «Está mal».

import { ChevronLeft, ChevronRight, Flag, Moon, Search, TrendingDown, TrendingUp } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, haceCuanto, mensajeDe, pesos } from "@/lib/api";
import { SEMAFORO, pct, type Cuadro, type FilaTablero, type GrupoTablero, type Tablero } from "@/lib/precios";

type PrecioComparado = "lista" | "membresia";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { EstaMal } from "./esta-mal";
import { Miniatura, monto, precio } from "./piezas";

const GRUPOS: GrupoTablero[] = ["accion", "rojo", "amarillo", "verde", "sin_referencia", "subir", "todos"];
// Ligas viejas (avisos de la campana)
const ALIAS: Record<string, GrupoTablero> = { caros: "rojo", baratos: "verde", revisar: "sin_referencia", sin_precios: "sin_referencia" };
const CUADROS: { clave: Cuadro; titulo: string; texto: string; clase: string; punto: string }[] = [
  { clave: "rojo", titulo: "Más caros que el mercado", texto: "Conviene bajar o negociar", clase: "border-red-600/30 bg-red-600/[0.06]", punto: "bg-red-600" },
  { clave: "amarillo", titulo: "Un poco más caros", texto: "Vigilar", clase: "border-yellow-500/40 bg-yellow-500/[0.08]", punto: "bg-yellow-500" },
  { clave: "verde", titulo: "Igual o más baratos", texto: "Bien", clase: "border-green-600/30 bg-green-600/[0.06]", punto: "bg-green-600" },
  { clave: "sin_referencia", titulo: "Sin referencia", texto: "Todavía sin precios validados", clase: "border-smn-gris-100 bg-smn-gris-100/40", punto: "bg-smn-gris-300" },
];
const TITULO_GRUPO: Record<GrupoTablero, string> = {
  accion: "Lo que pide acción",
  rojo: "Más caros que el mercado",
  amarillo: "Un poco más caros",
  verde: "Igual o más baratos",
  sin_referencia: "Sin referencia",
  subir: "Se podrían subir",
  todos: "Todos los productos",
};
const CLASE_ACCION: Record<string, string> = {
  bajar: "text-red-700 dark:text-red-400",
  bajar_y_negociar: "text-red-700 dark:text-red-400",
  negociar: "text-naranja-tinta",
  subir: "text-green-700 dark:text-green-400",
  mantener: "text-smn-gris-700",
  sin_referencia: "text-smn-gris-500",
};
const POR_PAGINA = 25;
const n = (v: number) => v.toLocaleString("es-MX");

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-72" />}>
      <Resumen />
    </Suspense>
  );
}

function Resumen() {
  const avisar = useAvisos();
  const parametros = useSearchParams();
  const router = useRouter();
  const ruta = usePathname();
  const crudo = parametros.get("grupo") ?? "accion";
  const grupo: GrupoTablero = ALIAS[crudo] ?? (GRUPOS.includes(crudo as GrupoTablero) ? (crudo as GrupoTablero) : "accion");
  const clase = parametros.get("clase") ?? "";
  const q = parametros.get("q") ?? "";
  const pagina = Math.max(1, Number(parametros.get("p")) || 1);
  const conPrecio: PrecioComparado = parametros.get("precio") === "membresia" ? "membresia" : "lista";
  const [t, setT] = useState<Tablero | null>(null);
  const [texto, setTexto] = useState(q);
  const [mal, setMal] = useState<FilaTablero | null>(null);

  const cambiar = useCallback(
    (cambios: Record<string, string>) => {
      const p = new URLSearchParams(parametros.toString());
      for (const [k, v] of Object.entries(cambios)) (v ? p.set(k, v) : p.delete(k));
      if (!("p" in cambios)) p.delete("p");
      router.replace(`${ruta}${p.size ? `?${p}` : ""}`, { scroll: false });
    },
    [parametros, router, ruta],
  );

  const cargar = useCallback(() => {
    const p = new URLSearchParams({ grupo, pagina: String(pagina), por_pagina: String(POR_PAGINA) });
    if (clase) p.set("clase", clase);
    if (q) p.set("q", q);
    if (conPrecio === "membresia") p.set("precio", "membresia");
    api<Tablero>(`/api/compras/precios/tablero?${p}`).then(setT).catch((e) => avisar(mensajeDe(e), "info"));
  }, [grupo, clase, q, pagina, conPrecio, avisar]);
  useEffect(cargar, [cargar]);

  useEffect(() => {
    const id = setTimeout(() => texto !== q && cambiar({ q: texto }), 350);
    return () => clearTimeout(id);
  }, [texto, q, cambiar]);

  if (!t) return <Esqueleto className="h-96" />;
  const paginas = Math.max(1, Math.ceil(t.total / t.por_pagina));

  return (
    <div className="space-y-6">
      <BandaAvance t={t} />

      <Entrada retraso={0.05}>
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-[14px] font-medium text-smn-gris-700">Comparar nuestro</span>
          <div className="flex rounded-lg bg-smn-gris-100 p-0.5 text-[14px]" role="group" aria-label="Precio que se compara">
            {(["lista", "membresia"] as PrecioComparado[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => cambiar({ precio: v === "lista" ? "" : v })}
                aria-pressed={conPrecio === v}
                className={`rounded-md px-3 py-1.5 ${conPrecio === v ? "bg-tinta text-superficie" : "text-smn-gris-700"}`}
              >
                {v === "lista" ? "Precio lista" : "Precio membresía"}
              </button>
            ))}
          </div>
          <span className="text-[13px] text-smn-gris-500">contra el mercado</span>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {CUADROS.map((c) => {
            const activo = grupo === c.clave;
            return (
              <button
                key={c.clave}
                type="button"
                onClick={() => cambiar({ grupo: activo ? "accion" : c.clave })}
                aria-pressed={activo}
                className={`rounded-xl border p-4 text-left transition hover:-translate-y-0.5 ${c.clase} ${activo ? "ring-2 ring-tinta" : ""}`}
              >
                <span className="flex items-center gap-2 text-[15px] font-medium">
                  <span className={`h-2.5 w-2.5 rounded-full ${c.punto}`} aria-hidden />
                  {c.titulo}
                </span>
                <span className="mt-2 block text-3xl font-semibold tabular-nums">{n(t.cuadros[c.clave] ?? 0)}</span>
                <span className="mt-0.5 block text-[13px] text-smn-gris-700">{c.texto}</span>
              </button>
            );
          })}
        </div>
      </Entrada>

      {t.tiendas.length > 0 && (
        <Entrada retraso={0.1}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
            <h2 className="text-lg font-semibold">Contra cada tienda</h2>
            <p className="mb-4 text-[13px] text-smn-gris-500">En los productos que tenemos en común. Parejos = ±2 %.</p>
            <ul className="grid gap-x-8 gap-y-4 md:grid-cols-2">
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

      <Entrada retraso={0.15}>
        <section className="rounded-xl border border-smn-gris-100 bg-superficie">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-smn-gris-100 p-4 sm:p-5">
            <div>
              <h2 className="text-lg font-semibold">{TITULO_GRUPO[grupo]}</h2>
              <p className="text-[13px] text-smn-gris-500">
                {n(t.total)} productos · ordenados por lo que venden
                {grupo === "accion" && " · bajar, negociar costo o revisar si se suben"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="flex rounded-lg bg-smn-gris-100 p-0.5 text-[13px]">
                {(["accion", "subir", "todos"] as GrupoTablero[]).map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => cambiar({ grupo: g })}
                    className={`rounded-md px-2.5 py-1.5 ${grupo === g ? "bg-tinta text-superficie" : "text-smn-gris-700"}`}
                  >
                    {g === "accion" ? "Pide acción" : g === "subir" ? "Se podrían subir" : "Todos"}
                  </button>
                ))}
              </div>
              <select
                value={clase}
                onChange={(e) => cambiar({ clase: e.target.value })}
                aria-label="Clase"
                className="h-9 rounded-lg border border-smn-gris-100 bg-superficie px-2 text-[14px]"
              >
                <option value="">Todas las clases</option>
                {t.clases.map((c) => (
                  <option key={c} value={c}>
                    Clase {c}
                  </option>
                ))}
              </select>
              <label className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
                <input
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder="Buscar SKU, nombre o marca"
                  aria-label="Buscar"
                  className="h-9 w-64 rounded-lg border border-smn-gris-100 bg-superficie pr-2 pl-8 text-[14px] outline-none focus:border-smn-naranja"
                />
              </label>
            </div>
          </div>

          {t.filas.length === 0 ? (
            <p className="px-4 py-10 text-center text-smn-gris-500">
              {grupo === "accion" ? "Nada pide acción con estos filtros." : "No hay productos con estos filtros."}
            </p>
          ) : (
            <>
              {/* Escritorio */}
              <table className="hidden w-full text-[14px] lg:table">
                <thead className="text-left text-[13px] text-smn-gris-500">
                  <tr className="border-b border-smn-gris-100">
                    <th className="w-[34%] px-4 py-2.5 font-medium">Producto</th>
                    <th className="px-2 py-2.5 text-right font-medium">Nuestro <span className="font-normal">(MXN)</span></th>
                    <th className="px-2 py-2.5 text-right font-medium">Mercado <span className="font-normal">(MXN)</span></th>
                    <th className="px-3 py-2.5 font-medium">Diferencia</th>
                    <th className="px-2 py-2.5 font-medium">Qué conviene</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-smn-gris-100">
                  {t.filas.map((f) => (
                    <tr key={f.producto_id} className="align-top hover:bg-smn-gris-100/30">
                      <td className="px-4 py-3">
                        <Producto f={f} />
                      </td>
                      <td className="px-2 py-3 text-right whitespace-nowrap tabular-nums">
                        <span className="block font-semibold">{monto(f.nuestro)}</span>
                        {f.membresia && <span className="block text-[13px] text-smn-gris-500">Memb. {monto(f.membresia)}</span>}
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums">
                        <span className="whitespace-nowrap font-semibold">{monto(f.mercado)}</span>
                        <Tiendas f={f} />
                      </td>
                      <td className="px-3 py-3">
                        <Difs f={f} />
                      </td>
                      <td className="max-w-[300px] px-2 py-3">
                        <Accion f={f} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <BotonMal f={f} abrir={setMal} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {/* Celular y tableta: tarjetas */}
              <ul className="divide-y divide-smn-gris-100 lg:hidden">
                {t.filas.map((f) => (
                  <li key={f.producto_id} className="space-y-2.5 p-4">
                    <Producto f={f} />
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px]">
                      <span>Nuestro <b className="tabular-nums">{precio(f.nuestro)}</b></span>
                      {f.membresia && <span>Membresía <b className="tabular-nums">{precio(f.membresia)}</b></span>}
                      <span>Mercado <b className="tabular-nums">{precio(f.mercado)}</b></span>
                      <Difs f={f} />
                    </div>
                    <Accion f={f} />
                    <div className="flex items-center justify-between gap-2">
                      <Tiendas f={f} />
                      <BotonMal f={f} abrir={setMal} />
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}

          {paginas > 1 && (
            <div className="flex items-center justify-between border-t border-smn-gris-100 px-4 py-3 text-[14px]">
              <span className="text-smn-gris-500">
                Página {pagina} de {paginas}
              </span>
              <div className="flex gap-2">
                <Boton variante="secundario" disabled={pagina <= 1} onClick={() => cambiar({ p: String(pagina - 1) })} aria-label="Página anterior">
                  <ChevronLeft className="h-4 w-4" />
                </Boton>
                <Boton variante="secundario" disabled={pagina >= paginas} onClick={() => cambiar({ p: String(pagina + 1) })} aria-label="Página siguiente">
                  <ChevronRight className="h-4 w-4" />
                </Boton>
              </div>
            </div>
          )}
        </section>
      </Entrada>

      {mal && <EstaMal productoId={mal.producto_id} nombre={mal.descripcion ?? mal.sku} cerrar={() => setMal(null)} listo={cargar} />}
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
          <span className="text-2xl font-semibold tabular-nums">{hecho} %</span>
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

function Producto({ f }: { f: FilaTablero }) {
  return (
    <Link href={`/compras/precios/producto/${f.producto_id}`} className="group flex min-w-0 items-start gap-3">
      <Miniatura liga={f.imagen} />
      <span className="min-w-0">
        <span className="block font-medium group-hover:underline">{f.descripcion ?? f.sku}</span>
        <span className="block text-[13px] text-smn-gris-500">
          {f.sku}
          {f.clase && ` · ${f.clase}`}
          {Number(f.venta_importe) > 0 && ` · vende ${pesos(f.venta_importe)} en 26 sem`}
          {f.tendencia && f.tendencia !== "estable" && (
            <span className="ml-1 inline-flex items-center gap-0.5">
              · {f.tendencia === "sube" ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />} mercado {pct(f.tendencia_pct)}
            </span>
          )}
        </span>
      </span>
    </Link>
  );
}

function Tiendas({ f }: { f: FilaTablero }) {
  const lista = Object.entries(f.tiendas);
  if (!lista.length && !f.otras) return null;
  return (
    <span className="mt-1 block text-[12.5px] font-normal text-smn-gris-500">
      {lista.slice(0, 2).map(([k, v]) => `${k} ${monto(v)}`).join(" · ")}
      {lista.length + f.otras > 2 && ` · +${lista.length + f.otras - 2} más`}
    </span>
  );
}

function Difs({ f }: { f: FilaTablero }) {
  if (!f.color || f.dif_pct === null) return <span className="text-[13px] text-smn-gris-500">Sin referencia</span>;
  return (
    <span className="inline-flex flex-wrap gap-1.5 lg:flex-col lg:items-start">
      <Dif color={f.color} valor={f.dif_pct} etiqueta="Lista" />
      {f.color_membresia && f.dif_membresia_pct !== null && <Dif color={f.color_membresia} valor={f.dif_membresia_pct} etiqueta="Memb." />}
    </span>
  );
}

function Dif({ color, valor, etiqueta }: { color: NonNullable<FilaTablero["color"]>; valor: string; etiqueta: string }) {
  const s = SEMAFORO[color];
  return (
    <Insignia className={`gap-1.5 whitespace-nowrap tabular-nums ${s.insignia}`}>
      <span className={`h-2 w-2 rounded-full ${s.punto}`} aria-hidden />
      <span className="font-normal">{etiqueta}</span> {pct(valor)}
    </Insignia>
  );
}

function Accion({ f }: { f: FilaTablero }) {
  return (
    <div>
      <b className={`font-semibold ${CLASE_ACCION[f.accion] ?? ""}`}>{f.accion_texto}</b>
      {f.detalle && <p title={f.detalle} className="line-clamp-2 text-[13px] leading-snug text-smn-gris-700">{f.detalle}</p>}
    </div>
  );
}

function BotonMal({ f, abrir }: { f: FilaTablero; abrir: (f: FilaTablero) => void }) {
  if (!f.mercado) return null;
  return (
    <button
      type="button"
      onClick={() => abrir(f)}
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[13px] whitespace-nowrap text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta"
    >
      <Flag className="h-3.5 w-3.5" /> Está mal
    </button>
  );
}
