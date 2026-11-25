"use client";
// Radar de precios · Precios contra el mercado (plan «Radar de precios para Compras: una sola vista», aprobado por Diego el
// 2026-11-25). Lo único que ve Compras: de inicio los 20 productos con más dinero en juego al mes, filtros por agente, clase y
// marca, y un buscador para abrir cualquier producto con su historial. Lista y membresía se comparan las dos. Compras no
// valida nada: si ve un precio que no es, lo marca con «Algo está mal» en el detalle.

import { Download, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { SEMAFORO, descargar, pct, type Color, type FilaTablero, type GrupoTablero, type Tablero } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { Detalle } from "./detalle";
import { Miniatura, monto } from "./piezas";

const GRUPOS: GrupoTablero[] = ["accion", "rojo", "amarillo", "verde", "sin_referencia", "subir", "todos"];
// Ligas viejas (avisos de la campana)
const ALIAS: Record<string, GrupoTablero> = { caros: "rojo", baratos: "verde", revisar: "sin_referencia", sin_precios: "sin_referencia" };
const BOTONES: { clave: GrupoTablero; texto: string; punto?: string; cuenta: (t: Tablero) => number | null }[] = [
  { clave: "accion", texto: "Piden acción", cuenta: (t) => Object.values(t.acciones).reduce((a, b) => a + b, 0) },
  { clave: "rojo", texto: "Más caros", punto: "bg-red-600", cuenta: (t) => t.cuadros.rojo ?? 0 },
  { clave: "amarillo", texto: "Un poco más caros", punto: "bg-yellow-500", cuenta: (t) => t.cuadros.amarillo ?? 0 },
  { clave: "verde", texto: "Igual o más baratos", punto: "bg-green-600", cuenta: (t) => t.cuadros.verde ?? 0 },
  { clave: "sin_referencia", texto: "Sin comparar", punto: "bg-smn-gris-300", cuenta: (t) => t.cuadros.sin_referencia ?? 0 },
  { clave: "todos", texto: "Todo el catálogo", cuenta: (t) => t.catalogo },
];
const CLASE_ACCION: Record<string, string> = {
  bajar: "text-red-700 dark:text-red-400",
  bajar_y_negociar: "text-red-700 dark:text-red-400",
  negociar: "text-naranja-tinta",
  subir: "text-green-700 dark:text-green-400",
  mantener: "text-smn-gris-700",
  sin_referencia: "text-smn-gris-500",
};
const POR_PAGINA = 20;
const n = (v: number) => v.toLocaleString("es-MX");
const dinero = (v: string | number) => Number(v).toLocaleString("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-72" />}>
      <PreciosContraMercado />
    </Suspense>
  );
}

function PreciosContraMercado() {
  const avisar = useAvisos();
  const parametros = useSearchParams();
  const router = useRouter();
  const ruta = usePathname();
  const crudo = parametros.get("grupo") ?? "accion";
  const grupo: GrupoTablero = ALIAS[crudo] ?? (GRUPOS.includes(crudo as GrupoTablero) ? (crudo as GrupoTablero) : "accion");
  const clase = parametros.get("clase") ?? "";
  const agente = parametros.get("agente") ?? "";
  const q = parametros.get("q") ?? "";
  const abierto = Number(parametros.get("producto")) || null;
  const [t, setT] = useState<Tablero | null>(null);
  const [filas, setFilas] = useState<FilaTablero[]>([]);
  const [pagina, setPagina] = useState(1);
  const [texto, setTexto] = useState(q);
  const [cargando, setCargando] = useState(false);
  const [bajando, setBajando] = useState(false);

  const cambiar = useCallback(
    (cambios: Record<string, string>) => {
      const p = new URLSearchParams(parametros.toString());
      for (const [k, v] of Object.entries(cambios)) (v ? p.set(k, v) : p.delete(k));
      router.replace(`${ruta}${p.size ? `?${p}` : ""}`, { scroll: false });
    },
    [parametros, router, ruta],
  );

  const filtros = useCallback(() => {
    const p = new URLSearchParams({ grupo });
    if (clase) p.set("clase", clase);
    if (agente) p.set("agente", agente);
    if (q) p.set("q", q);
    return p;
  }, [grupo, clase, agente, q]);

  const cargar = useCallback(
    (num = 1) => {
      const p = filtros();
      p.set("pagina", String(num));
      p.set("por_pagina", String(POR_PAGINA));
      setCargando(true);
      api<Tablero>(`/api/compras/precios/tablero?${p}`)
        .then((r) => {
          setT(r);
          setPagina(num);
          setFilas((antes) => (num === 1 ? r.filas : [...antes, ...r.filas]));
        })
        .catch((e) => avisar(mensajeDe(e), "info"))
        .finally(() => setCargando(false));
    },
    [filtros, avisar],
  );
  useEffect(() => cargar(1), [cargar]);

  useEffect(() => {
    const id = setTimeout(() => texto !== q && cambiar({ q: texto.trim() }), 350);
    return () => clearTimeout(id);
  }, [texto, q, cambiar]);

  const bajar = async () => {
    setBajando(true);
    try {
      await descargar(`/api/compras/precios/tablero/excel?${filtros()}`, `Precios contra el mercado ${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setBajando(false);
    }
  };

  if (!t) return <Esqueleto className="h-96" />;
  const buscando = !!q;
  const titulo = buscando
    ? `Productos que dicen «${q}»`
    : grupo === "accion"
      ? `Los ${Math.min(POR_PAGINA, t.total)} con más dinero en juego`
      : BOTONES.find((b) => b.clave === grupo)?.texto ?? "Productos";

  return (
    <div className="space-y-5">
      <Entrada>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <p className="text-[15px] text-smn-gris-700">
            <b className="text-tinta tabular-nums">{n(t.catalogo)}</b> productos ·{" "}
            <b className="text-tinta tabular-nums">{n(t.comparados)}</b> ya comparados contra el mercado
            {agente && <span className="text-smn-gris-500"> · agente {agente === "sin_agente" ? "sin asignar" : agente}</span>}
          </p>
          <div className="flex flex-wrap gap-2">
            <select
              value={agente}
              onChange={(e) => cambiar({ agente: e.target.value })}
              aria-label="Agente"
              className="h-10 rounded-lg border border-smn-gris-100 bg-superficie px-2.5 text-[15px]"
            >
              <option value="">Todos los agentes</option>
              {t.agentes.map((a) => (
                <option key={a} value={a}>
                  Agente {a}
                </option>
              ))}
              <option value="sin_agente">Sin agente</option>
            </select>
            <select
              value={clase}
              onChange={(e) => cambiar({ clase: e.target.value })}
              aria-label="Clase"
              className="h-10 rounded-lg border border-smn-gris-100 bg-superficie px-2.5 text-[15px]"
            >
              <option value="">Todas las clases</option>
              {t.clases.map((c) => (
                <option key={c} value={c}>
                  Clase {c}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Entrada>

      <Entrada retraso={0.05}>
        <label className="relative block">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 h-5 w-5 -translate-y-1/2 text-smn-gris-500" />
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Busca cualquier producto por nombre, SKU, marca o código de barras para ver su historial"
            aria-label="Buscar producto"
            className="h-12 w-full rounded-xl border border-smn-gris-100 bg-superficie pr-10 pl-11 text-[16px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
          />
          {texto && (
            <button type="button" onClick={() => setTexto("")} aria-label="Borrar búsqueda" className="absolute top-1/2 right-3 -translate-y-1/2 rounded-full p-1 text-smn-gris-500 hover:bg-smn-gris-100">
              <X className="h-4 w-4" />
            </button>
          )}
        </label>
      </Entrada>

      {!buscando && (
        <Entrada retraso={0.1}>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Qué productos ver">
            {BOTONES.map((b) => {
              const activo = grupo === b.clave;
              const c = b.cuenta(t);
              return (
                <button
                  key={b.clave}
                  type="button"
                  onClick={() => cambiar({ grupo: b.clave === "accion" ? "" : b.clave })}
                  aria-pressed={activo}
                  className={`inline-flex h-10 items-center gap-2 rounded-full border px-4 text-[15px] transition ${
                    activo ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 bg-superficie hover:border-smn-gris-300"
                  }`}
                >
                  {b.punto && <span className={`h-2.5 w-2.5 rounded-full ${b.punto}`} aria-hidden />}
                  {b.texto}
                  {c !== null && <span className={`tabular-nums ${activo ? "" : "text-smn-gris-500"}`}>{n(c)}</span>}
                </button>
              );
            })}
          </div>
        </Entrada>
      )}

      <Entrada retraso={0.15}>
        <section className="rounded-xl border border-smn-gris-100 bg-superficie">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-smn-gris-100 px-4 py-3.5 sm:px-5">
            <div>
              <h2 className="text-lg font-semibold">{titulo}</h2>
              <p className="text-[13px] text-smn-gris-500">
                {buscando
                  ? `${n(t.total)} encontrados · pica uno para ver su historial de precios`
                  : `${n(t.total)} productos · ordenados por el dinero en juego al mes`}
              </p>
            </div>
            <Boton variante="secundario" onClick={bajar} cargando={bajando} disabled={!t.total}>
              <Download className="h-4 w-4" /> Descargar Excel
            </Boton>
          </div>

          {filas.length === 0 ? (
            <p className="px-4 py-10 text-center text-smn-gris-500">
              {buscando ? "Ningún producto del radar coincide con esa búsqueda." : grupo === "accion" ? "Nada pide acción con estos filtros." : "No hay productos con estos filtros."}
            </p>
          ) : (
            <>
              <table className="hidden w-full text-[14px] lg:table">
                <thead className="text-left text-[13px] text-smn-gris-500">
                  <tr className="border-b border-smn-gris-100">
                    <th className="w-[32%] px-4 py-2.5 font-medium">Producto</th>
                    <th className="px-2 py-2.5 text-right font-medium">Nuestro <span className="font-normal">(MXN)</span></th>
                    <th className="px-2 py-2.5 text-right font-medium">Mercado <span className="font-normal">(MXN)</span></th>
                    <th className="px-3 py-2.5 font-medium">Diferencia</th>
                    <th className="px-2 py-2.5 font-medium">Qué conviene</th>
                    <th className="px-4 py-2.5 text-right font-medium">En juego al mes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-smn-gris-100">
                  {filas.map((f) => (
                    <tr
                      key={f.producto_id}
                      onClick={() => cambiar({ producto: String(f.producto_id) })}
                      className={`cursor-pointer align-top hover:bg-smn-gris-100/40 ${abierto === f.producto_id ? "bg-smn-gris-100/60" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <Producto f={f} />
                      </td>
                      <td className="px-2 py-3 text-right whitespace-nowrap tabular-nums">
                        <span className="block font-semibold">{monto(f.nuestro)}</span>
                        {f.membresia && <span className="block text-[13px] text-smn-gris-500">Memb. {monto(f.membresia)}</span>}
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums">
                        <span className="block whitespace-nowrap font-semibold">{monto(f.mercado)}</span>
                        <DeTiendas f={f} />
                      </td>
                      <td className="px-3 py-3">
                        <Difs f={f} />
                      </td>
                      <td className="max-w-[260px] px-2 py-3">
                        <Accion f={f} />
                      </td>
                      <td className="px-4 py-3 text-right font-semibold whitespace-nowrap tabular-nums">{Number(f.en_juego) > 0 ? dinero(f.en_juego) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="divide-y divide-smn-gris-100 lg:hidden">
                {filas.map((f) => (
                  <li key={f.producto_id}>
                    <button type="button" onClick={() => cambiar({ producto: String(f.producto_id) })} className="block w-full space-y-2 p-4 text-left">
                      <Producto f={f} />
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px]">
                        <span>Nuestro <b className="tabular-nums">{monto(f.nuestro)}</b></span>
                        <span>Mercado <b className="tabular-nums">{monto(f.mercado)}</b> <DeTiendas f={f} enLinea /></span>
                        <Difs f={f} />
                      </div>
                      <div className="flex items-start justify-between gap-3">
                        <Accion f={f} />
                        {Number(f.en_juego) > 0 && <span className="shrink-0 text-[14px] font-semibold tabular-nums">{dinero(f.en_juego)}/mes</span>}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          {filas.length < t.total && (
            <div className="border-t border-smn-gris-100 px-4 py-3 text-center">
              <Boton variante="secundario" onClick={() => cargar(pagina + 1)} cargando={cargando}>
                Ver {Math.min(POR_PAGINA, t.total - filas.length)} más
              </Boton>
              <p className="mt-1.5 text-[13px] text-smn-gris-500 tabular-nums">
                {n(filas.length)} de {n(t.total)}
              </p>
            </div>
          )}
        </section>
      </Entrada>

      {abierto && <Detalle productoId={abierto} cerrar={() => cambiar({ producto: "" })} cambio={() => cargar(1)} />}
    </div>
  );
}

function Producto({ f }: { f: FilaTablero }) {
  return (
    <span className="flex min-w-0 items-start gap-3">
      <Miniatura liga={f.imagen} />
      <span className="min-w-0">
        <span className="block font-medium">{f.descripcion ?? f.sku}</span>
        <span className="block text-[13px] text-smn-gris-500">
          {f.sku}
          {f.marca && ` · ${f.marca}`}
          {f.clase && ` · clase ${f.clase}`}
          {f.agente && ` · agente ${f.agente}`}
        </span>
      </span>
    </span>
  );
}

function DeTiendas({ f, enLinea }: { f: FilaTablero; enLinea?: boolean }) {
  const cuantas = Object.keys(f.tiendas).length + f.otras;
  if (!f.mercado || !cuantas) return null;
  const texto = `de ${cuantas} ${cuantas === 1 ? "tienda" : "tiendas"}`;
  return enLinea ? <span className="text-[13px] text-smn-gris-500">{texto}</span> : <span className="block text-[13px] text-smn-gris-500">{texto}</span>;
}

function Difs({ f }: { f: FilaTablero }) {
  if (!f.color || f.dif_pct === null) return <span className="text-[13px] text-smn-gris-500">Sin comparar</span>;
  return (
    <span className="inline-flex flex-wrap gap-x-3 gap-y-1 lg:flex-col">
      <Dif color={f.color} valor={f.dif_pct} etiqueta="Lista" />
      {f.color_membresia && f.dif_membresia_pct !== null && <Dif color={f.color_membresia} valor={f.dif_membresia_pct} etiqueta="Memb." />}
    </span>
  );
}

function Dif({ color, valor, etiqueta }: { color: Color; valor: string; etiqueta: string }) {
  const s = SEMAFORO[color];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap tabular-nums">
      <span className={`h-2.5 w-2.5 rounded-full ${s.punto}`} aria-hidden />
      <span className="sr-only">{s.texto}: </span>
      <span className="text-[13px] text-smn-gris-500">{etiqueta}</span> <b className="font-semibold">{pct(valor)}</b>
    </span>
  );
}

function Accion({ f }: { f: FilaTablero }) {
  const texto = f.accion === "sin_referencia" ? "Sin comparar" : f.accion_texto;
  return <b className={`font-semibold ${CLASE_ACCION[f.accion] ?? ""}`}>{texto}</b>;
}
