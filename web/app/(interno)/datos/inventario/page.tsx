"use client";
// Datos → Salud de inventario: dinero detenido en productos sin venta, exceso de más de 180 días y productos que se
// venden pero estaban en cero, por tienda y departamento. Foto de inventario de SMNBI contra 13 semanas de venta.

import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Ban, Boxes, PackageX, Store, Tags, Warehouse } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, mensajeDe, pesos } from "@/lib/api";
import { fechaDia } from "@/lib/etl";
import { RUTA, TIPO, type RenglonInventario, type ResumenInventario, type Sumas, type Tipo } from "@/lib/inventario";
import { Encabezado, Esqueleto, Selector } from "@/componentes/ui";

type Pestana = "tiendas" | "departamentos" | "productos";
const dinero = (n: number) => pesos(Math.round(n));
const entero = (n: number) => Math.round(n).toLocaleString("es-MX");
const pct = (a: number, b: number) => (b > 0 ? `${((a / b) * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })} %` : "—");

export default function SaludInventario() {
  const [r, setR] = useState<ResumenInventario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tienda, setTienda] = useState("");
  const [depto, setDepto] = useState("");
  const [pestana, setPestana] = useState<Pestana>("tiendas");
  const [tipo, setTipo] = useState<Tipo>("sin_venta");
  // Las opciones de los filtros salen de la primera carga, sin filtrar
  const [opciones, setOpciones] = useState<{ tiendas: { valor: string; texto: string }[]; deptos: string[] } | null>(null);

  useEffect(() => {
    setR(null);
    const p = new URLSearchParams({ tienda, departamento: depto });
    api<ResumenInventario>(`${RUTA}?${p}`)
      .then((x) => {
        setR(x);
        if (!tienda && !depto && x.por_tienda)
          setOpciones({
            tiendas: [...x.por_tienda].sort((a, b) => a.nombre.localeCompare(b.nombre)).map((t) => ({ valor: t.almacen, texto: t.nombre })),
            deptos: (x.por_departamento ?? []).map((d) => d.departamento).sort(),
          });
      })
      .catch((e) => setError(mensajeDe(e)));
  }, [tienda, depto]);

  if (error) return <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>;

  const desfase = r?.corte && r.venta ? Math.round((Date.parse(r.corte) - Date.parse(r.venta.hasta)) / 86400000) : 0;

  return (
    <>
      <Encabezado
        titulo="Salud de inventario"
        descripcion={
          r?.corte && r.venta
            ? `Foto de inventario del ${fechaDia(r.corte)} contra la venta del ${fechaDia(r.venta.desde)} al ${fechaDia(r.venta.hasta)} (13 semanas, sin mayoreo). Valores al costo, sin IVA.`
            : "Foto de inventario de SMNBI contra la venta de las últimas 13 semanas."
        }
      />

      {opciones && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
          <Selector etiqueta="Tienda" valor={tienda} cambiar={setTienda} opciones={[{ valor: "", texto: "Todas las tiendas" }, ...opciones.tiendas]} />
          <Selector
            etiqueta="Departamento"
            valor={depto}
            cambiar={setDepto}
            opciones={[{ valor: "", texto: "Todos los departamentos" }, ...opciones.deptos.map((d) => ({ valor: d, texto: d }))]}
          />
        </div>
      )}

      {r === null ? (
        <Esqueleto className="h-96" />
      ) : !r.corte || !r.total ? (
        <p className="rounded-2xl bg-smn-gris-50 px-4 py-10 text-center text-sm text-smn-gris-500">
          Falta cargar el inventario o la venta de SMNBI. Cárgalos en ETL de ventas y vuelve aquí.
        </p>
      ) : (
        <>
          {Math.abs(desfase) > 14 && (
            <p className="mb-4 flex items-start gap-2 rounded-xl bg-aviso-fondo px-4 py-2.5 text-sm text-aviso-texto">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              La foto de inventario y la venta están separadas {Math.abs(desfase)} días. Lo que se vendió o se surtió entre esas fechas no aparece, así que confirma en
              tienda antes de mover mercancía.
            </p>
          )}
          <Tarjetas t={r.total} />

          <div role="tablist" className="mt-6 mb-4 flex gap-1 overflow-x-auto border-b border-smn-gris-100">
            {(
              [
                ["tiendas", "Por tienda", Store],
                ["departamentos", "Por departamento", Tags],
                ["productos", "Productos", Boxes],
              ] as const
            ).map(([id, texto, Icono]) => (
              <button
                key={id}
                role="tab"
                aria-selected={pestana === id}
                onClick={() => setPestana(id)}
                className={`relative flex shrink-0 items-center gap-2 px-3.5 py-2.5 text-sm font-semibold ${pestana === id ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
              >
                <Icono className={`h-4 w-4 ${pestana === id ? "text-smn-naranja" : ""}`} /> {texto}
                {pestana === id && <motion.span layoutId="pestana-inv" className="absolute inset-x-0 -bottom-px h-[3px] rounded-full bg-smn-naranja" />}
              </button>
            ))}
          </div>

          {pestana === "tiendas" && (
            <TablaGrupos
              filas={(r.por_tienda ?? []).map((t) => ({ ...t, clave: t.almacen, sub: t.categoria ? `Categoría ${t.categoria}` : t.almacen }))}
              primera="Tienda"
              elegir={(k) => {
                setTienda(k);
                setPestana("productos");
              }}
            />
          )}
          {pestana === "departamentos" && (
            <TablaGrupos
              filas={(r.por_departamento ?? []).map((d) => ({ clave: d.departamento, nombre: d.departamento, sub: null, ...d }))}
              primera="Departamento"
              elegir={(k) => {
                setDepto(k);
                setPestana("productos");
              }}
            />
          )}
          {pestana === "productos" && <Productos tipo={tipo} setTipo={setTipo} tienda={tienda} depto={depto} total={r.total} />}

          {(r.otros_almacenes?.length ?? 0) > 0 && !tienda && (
            <details className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <summary className="flex cursor-pointer items-center gap-2 font-semibold">
                <Warehouse className="h-4 w-4 text-smn-naranja" /> {r.otros_almacenes!.length} {r.otros_almacenes!.length === 1 ? "almacén" : "almacenes"} con inventario que no vende en tienda ·{" "}
                {dinero(r.otros_almacenes!.reduce((s, a) => s + a.valor, 0))}
              </summary>
              <p className="mt-2 text-sm text-smn-gris-500">
                Mayoreo, CEDIS u otros almacenes sin venta en estas 13 semanas. No se cuentan como «sin venta» porque no venden al público.
              </p>
              <ul className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {r.otros_almacenes!.map((a) => (
                  <li key={a.almacen} className="flex justify-between gap-3">
                    <span className="truncate">
                      {a.nombre} <span className="font-mono text-[13px] text-smn-gris-500">{a.almacen}</span>
                    </span>
                    <span className="tabular-nums">{dinero(a.valor)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </>
  );
}

function Tarjetas({ t }: { t: Sumas }) {
  const datos = [
    { icono: Boxes, titulo: "Inventario en tiendas", valor: dinero(t.valor), nota: `${entero(t.existencia)} piezas · ${t.dias !== null ? `${entero(t.dias)} días de venta` : "sin venta"}` },
    { icono: Ban, titulo: "Sin venta en 13 semanas", valor: dinero(t.valor_sin_venta), nota: `${pct(t.valor_sin_venta, t.valor)} del inventario · ${entero(t.sin_venta)} renglones`, rojo: true },
    { icono: Warehouse, titulo: "Exceso (más de 180 días)", valor: dinero(t.valor_exceso), nota: `${pct(t.valor_exceso, t.valor)} del inventario · ${entero(t.exceso)} renglones` },
    { icono: PackageX, titulo: "En cero y sí se venden", valor: entero(t.en_cero), nota: "renglones tienda-producto a revisar" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {datos.map((d, i) => (
        <motion.div
          key={d.titulo}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3"
        >
          <p className="flex items-center gap-2 text-[13px] font-medium text-smn-gris-500">
            <d.icono className="h-4 w-4 text-smn-naranja" /> {d.titulo}
          </p>
          <p className={`mt-1 text-2xl font-semibold tabular-nums ${d.rojo ? "text-red-700 dark:text-red-400" : ""}`}>{d.valor}</p>
          <p className="text-[13px] text-smn-gris-500">{d.nota}</p>
        </motion.div>
      ))}
    </div>
  );
}

type Grupo = Sumas & { clave: string; nombre: string; sub: string | null };
type Orden = "valor_sin_venta" | "valor_exceso" | "valor" | "en_cero" | "dias";

function TablaGrupos({ filas, primera, elegir }: { filas: Grupo[]; primera: string; elegir: (clave: string) => void }) {
  const [orden, setOrden] = useState<Orden>("valor_sin_venta");
  const ordenadas = useMemo(() => [...filas].sort((a, b) => (b[orden] ?? -1) - (a[orden] ?? -1)), [filas, orden]);
  const cols: [Orden, string][] = [
    ["valor", "Inventario"],
    ["valor_sin_venta", "Sin venta"],
    ["valor_exceso", "Exceso"],
    ["dias", "Días"],
    ["en_cero", "En cero"],
  ];
  return (
    <div className="overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-smn-gris-100 text-left text-[13px] text-smn-gris-500">
            <th className="px-4 py-2.5">{primera}</th>
            {cols.map(([k, t]) => (
              <th key={k} className="px-3 py-2.5 text-right">
                <button onClick={() => setOrden(k)} className={` ${orden === k ? "text-naranja-tinta" : "hover:text-tinta"}`}>
                  {t}
                  {orden === k ? " ↓" : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-smn-gris-100">
          {ordenadas.map((f) => (
            <tr key={f.clave} onClick={() => elegir(f.clave)} className="cursor-pointer hover:bg-smn-gris-50" title="Ver sus productos">
              <td className="px-4 py-2">
                <span className="font-semibold">{f.nombre}</span>
                {f.sub && <span className="block text-[13px] text-smn-gris-500">{f.sub}</span>}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{dinero(f.valor)}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                <span className="font-semibold text-red-700 dark:text-red-400">{dinero(f.valor_sin_venta)}</span>
                <span className="block text-[13px] text-smn-gris-500">{pct(f.valor_sin_venta, f.valor)}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {dinero(f.valor_exceso)}
                <span className="block text-[13px] text-smn-gris-500">{pct(f.valor_exceso, f.valor)}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{f.dias !== null ? entero(f.dias) : "—"}</td>
              <td className="px-3 py-2 text-right tabular-nums">{entero(f.en_cero)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Productos({ tipo, setTipo, tienda, depto, total }: { tipo: Tipo; setTipo: (t: Tipo) => void; tienda: string; depto: string; total: Sumas }) {
  const [filas, setFilas] = useState<RenglonInventario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cargar = useCallback(() => {
    setFilas(null);
    const p = new URLSearchParams({ tipo, tienda, departamento: depto, limite: "300" });
    api<RenglonInventario[]>(`${RUTA}/productos?${p}`).then(setFilas).catch((e) => setError(mensajeDe(e)));
  }, [tipo, tienda, depto]);
  useEffect(cargar, [cargar]);
  const cuenta: Record<Tipo, number> = { sin_venta: total.sin_venta, exceso: total.exceso, en_cero: total.en_cero };

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        {(Object.keys(TIPO) as Tipo[]).map((t) => (
          <button
            key={t}
            aria-pressed={tipo === t}
            onClick={() => setTipo(t)}
            className={`rounded-full border px-3.5 py-1.5 text-[13px] font-semibold ${tipo === t ? "border-smn-naranja bg-aviso-fondo text-tinta" : "border-smn-gris-300 text-smn-gris-500 hover:text-tinta"}`}
          >
            {TIPO[t].texto} <span className="tabular-nums">· {entero(cuenta[t])}</span>
          </button>
        ))}
      </div>
      <p className="mb-3 text-sm text-smn-gris-500">
        {TIPO[tipo].explica} {tipo === "en_cero" ? "Ordenados por lo que venden." : "Ordenados por dinero detenido."} Se muestran hasta 300.
      </p>
      {error ? (
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>
      ) : !filas ? (
        <Esqueleto className="h-64" />
      ) : !filas.length ? (
        <p className="rounded-2xl bg-smn-gris-50 px-4 py-10 text-center text-sm text-smn-gris-500">No hay productos en este grupo con los filtros elegidos.</p>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={tipo} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-smn-gris-100 text-left text-[13px] text-smn-gris-500">
                  <th className="px-4 py-2.5">Producto</th>
                  {!tienda && <th className="px-3 py-2.5">Tienda</th>}
                  <th className="px-3 py-2.5 text-right">Existencia</th>
                  <th className="px-3 py-2.5 text-right">{tipo === "en_cero" ? "Costo" : "Valor"}</th>
                  <th className="px-3 py-2.5 text-right">Pzas/semana</th>
                  {tipo === "exceso" && <th className="px-3 py-2.5 text-right">Días</th>}
                  {tipo !== "en_cero" && <th className="px-3 py-2.5">En cero en</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-smn-gris-100">
                {filas.map((f) => (
                  <tr key={f.almacen + f.sku}>
                    <td className="max-w-xs px-4 py-2">
                      <span className="block truncate font-semibold">{f.descripcion ?? f.sku}</span>
                      <span className="block truncate text-[13px] text-smn-gris-500">
                        {f.sku}
                        {f.departamento ? ` · ${f.departamento}` : ""}
                        {f.proveedor ? ` · ${f.proveedor}` : ""}
                      </span>
                    </td>
                    {!tienda && <td className="px-3 py-2 whitespace-nowrap">{f.tienda}</td>}
                    <td className="px-3 py-2 text-right tabular-nums">{entero(f.existencia)}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">
                      {tipo === "en_cero" ? (f.costo !== null ? pesos(f.costo) : "—") : dinero(f.valor)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{f.por_semana.toLocaleString("es-MX", { maximumFractionDigits: 1 })}</td>
                    {tipo === "exceso" && <td className="px-3 py-2 text-right tabular-nums">{f.dias !== null ? entero(f.dias) : "—"}</td>}
                    {tipo !== "en_cero" && (
                      <td className="px-3 py-2 text-[13px]">
                        {f.en_cero_en?.length ? (
                          <span title={f.en_cero_en.join(", ")}>
                            <span className="font-semibold text-emerald-700 dark:text-emerald-400">{f.en_cero_en.length} {f.en_cero_en.length === 1 ? "tienda" : "tiendas"}</span>{" "}
                            <span className="text-smn-gris-500">
                              {f.en_cero_en.slice(0, 2).join(", ")}
                              {f.en_cero_en.length > 2 ? "…" : ""}
                            </span>
                          </span>
                        ) : (
                          <span className="text-smn-gris-500">Ninguna</span>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </motion.div>
        </AnimatePresence>
      )}
    </>
  );
}
