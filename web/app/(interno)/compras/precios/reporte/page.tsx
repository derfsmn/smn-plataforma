"use client";
// Radar de precios · Reporte a Excel (Diego, 2026-11-17: «un reporte donde seleccione varios productos, individualmente o por
// marca o por categoría y se bajaría en excel»). Se mezclan productos sueltos, marcas y categorías sin repetir; se eligen las
// hojas y la fecha de los precios; la selección se puede guardar para bajarla otra vez con un clic.

import { Download, Save, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import {
  descargar,
  descargarPost,
  type HojaReporte,
  type ModoReporte,
  type OpcionReporte,
  type SeleccionGuardada,
  type SeleccionReporte,
} from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";

const MODOS: { valor: ModoReporte; texto: string; buscar: string }[] = [
  { valor: "producto", texto: "Productos", buscar: "Buscar por SKU, código de barras, nombre o marca" },
  { valor: "marca", texto: "Por marca", buscar: "Buscar marca" },
  { valor: "categoria", texto: "Por categoría", buscar: "Buscar categoría" },
];
const HOJAS: { valor: HojaReporte; texto: string; detalle: string }[] = [
  { valor: "resumen", texto: "Resumen por marca y categoría", detalle: "Cuántos están más caros, parejos o más baratos" },
  { valor: "tiendas", texto: "Precio por tienda", detalle: "Walmart, Chedraui, San Pablo, Soriana y otras, con liga" },
  { valor: "accion", texto: "Qué conviene hacer", detalle: "Precio sugerido, margen y costo meta" },
  { valor: "historial", texto: "Historial de 8 semanas", detalle: "Cómo se ha movido el mercado" },
];

type Elegido = { modo: ModoReporte; clave: string; nombre: string };

export default function Reporte() {
  const avisar = useAvisos();
  const [modo, setModo] = useState<ModoReporte>("producto");
  const [q, setQ] = useState("");
  const [opciones, setOpciones] = useState<OpcionReporte[] | null>(null);
  const [elegidos, setElegidos] = useState<Elegido[]>([]);
  const [hojas, setHojas] = useState<HojaReporte[]>(["resumen", "tiendas", "accion"]);
  const [usarFecha, setUsarFecha] = useState(false);
  const [fecha, setFecha] = useState("");
  const [cuenta, setCuenta] = useState<number | null>(null);
  const [bajando, setBajando] = useState(false);
  const [nombre, setNombre] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [guardadas, setGuardadas] = useState<SeleccionGuardada[] | null>(null);
  const [bajandoId, setBajandoId] = useState<number | null>(null);

  useEffect(() => {
    setOpciones(null);
    const id = setTimeout(() => {
      api<OpcionReporte[]>(`/api/compras/precios/reporte/opciones?modo=${modo}&q=${encodeURIComponent(q.trim())}`)
        .then(setOpciones)
        .catch((e) => avisar(mensajeDe(e), "info"));
    }, 250);
    return () => clearTimeout(id);
  }, [modo, q, avisar]);

  const cargarGuardadas = useCallback(() => {
    api<SeleccionGuardada[]>("/api/compras/precios/selecciones").then(setGuardadas).catch(() => setGuardadas([]));
  }, []);
  useEffect(cargarGuardadas, [cargarGuardadas]);

  const seleccion: SeleccionReporte = useMemo(
    () => ({
      producto_ids: elegidos.filter((e) => e.modo === "producto").map((e) => Number(e.clave)),
      marcas: elegidos.filter((e) => e.modo === "marca").map((e) => e.clave),
      categorias: elegidos.filter((e) => e.modo === "categoria").map((e) => e.clave),
      hojas,
      fecha: usarFecha && fecha ? fecha : null,
    }),
    [elegidos, hojas, usarFecha, fecha],
  );

  useEffect(() => {
    if (!elegidos.length) return setCuenta(0);
    const id = setTimeout(() => {
      api<{ productos: number }>("/api/compras/precios/reporte/contar", { metodo: "POST", cuerpo: seleccion })
        .then((r) => setCuenta(r.productos))
        .catch(() => setCuenta(null));
    }, 250);
    return () => clearTimeout(id);
  }, [elegidos, seleccion]);

  const esta = (o: OpcionReporte) => elegidos.some((e) => e.modo === modo && e.clave === o.clave);
  const alternar = (o: OpcionReporte) =>
    setElegidos((l) => (esta(o) ? l.filter((e) => !(e.modo === modo && e.clave === o.clave)) : [...l, { modo, clave: o.clave, nombre: o.nombre }]));
  const quitar = (e: Elegido) => setElegidos((l) => l.filter((x) => !(x.modo === e.modo && x.clave === e.clave)));

  const bajar = async () => {
    setBajando(true);
    try {
      await descargarPost("/api/compras/precios/reporte/excel", seleccion, "Radar_de_precios.xlsx");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setBajando(false);
    }
  };

  const guardar = async () => {
    setGuardando(true);
    try {
      await api("/api/compras/precios/selecciones", { metodo: "POST", cuerpo: { nombre: nombre.trim(), seleccion } });
      setNombre("");
      avisar("Selección guardada", "exito");
      cargarGuardadas();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };

  const bajarGuardada = async (s: SeleccionGuardada) => {
    setBajandoId(s.id);
    try {
      await descargar(`/api/compras/precios/selecciones/${s.id}/excel`, `${s.nombre}.xlsx`);
      cargarGuardadas();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setBajandoId(null);
    }
  };

  const borrar = async (s: SeleccionGuardada) => {
    try {
      await api(`/api/compras/precios/selecciones/${s.id}`, { metodo: "DELETE" });
      cargarGuardadas();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const cargarEn = (s: SeleccionGuardada) => {
    // Al abrir una guardada para cambiarla, los productos sueltos se muestran por número (su nombre llega al buscar).
    setElegidos([
      ...s.seleccion.marcas.map((m) => ({ modo: "marca" as const, clave: m, nombre: m })),
      ...s.seleccion.categorias.map((c) => ({ modo: "categoria" as const, clave: c, nombre: c })),
      ...s.seleccion.producto_ids.map((id) => ({ modo: "producto" as const, clave: String(id), nombre: `Producto ${id}` })),
    ]);
    setHojas(s.seleccion.hojas);
    setNombre(s.nombre);
  };

  const modoActual = MODOS.find((m) => m.valor === modo)!;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Entrada>
        <section className="rounded-xl border border-smn-gris-100 bg-superficie">
          <div className="border-b border-smn-gris-100 p-4 sm:p-5">
            <h2 className="text-lg font-semibold">¿Qué productos van?</h2>
            <p className="text-[13px] text-smn-gris-500">Puedes mezclar productos sueltos, marcas y categorías; ninguno sale repetido.</p>
            <div className="mt-4 flex rounded-lg bg-smn-gris-100 p-0.5 text-[14px] sm:w-max">
              {MODOS.map((m) => (
                <button
                  key={m.valor}
                  type="button"
                  onClick={() => (setModo(m.valor), setQ(""))}
                  className={`flex-1 rounded-md px-3 py-1.5 sm:flex-none ${modo === m.valor ? "bg-tinta text-superficie" : "text-smn-gris-700"}`}
                >
                  {m.texto}
                </button>
              ))}
            </div>
            <label className="relative mt-3 block">
              <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={modoActual.buscar}
                aria-label={modoActual.buscar}
                className="h-11 w-full rounded-lg border border-smn-gris-100 bg-superficie pr-3 pl-9 text-[15px] outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
              />
            </label>
          </div>
          {!opciones ? (
            <div className="space-y-2 p-4">
              <Esqueleto className="h-12" />
              <Esqueleto className="h-12" />
              <Esqueleto className="h-12" />
            </div>
          ) : opciones.length === 0 ? (
            <p className="px-4 py-10 text-center text-smn-gris-500">No hay resultados.</p>
          ) : (
            <ul className="max-h-[520px] divide-y divide-smn-gris-100 overflow-y-auto">
              {opciones.map((o) => {
                const si = esta(o);
                return (
                  <li key={o.clave}>
                    <label className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-smn-gris-100/30">
                      <input type="checkbox" checked={si} onChange={() => alternar(o)} className="h-[18px] w-[18px] accent-smn-naranja" />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium">{o.nombre}</span>
                        {o.detalle && <span className="block text-[13px] text-smn-gris-500">{o.detalle}</span>}
                      </span>
                      <span className="shrink-0 text-[13px] text-smn-gris-500 tabular-nums">{o.cuenta}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </Entrada>

      <div className="space-y-6">
        <Entrada retraso={0.05}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5 lg:sticky lg:top-4">
            <h2 className="text-lg font-semibold">Tu reporte</h2>
            <p className="text-[13px] text-smn-gris-500">
              {elegidos.length === 0 ? "Elige productos, marcas o categorías." : `${cuenta === null ? "…" : cuenta.toLocaleString("es-MX")} productos`}
            </p>
            {elegidos.length > 0 && (
              <ul className="mt-3 flex flex-wrap gap-1.5">
                {elegidos.map((e) => (
                  <li key={`${e.modo}-${e.clave}`} className="max-w-full min-w-0">
                    <button
                      type="button"
                      onClick={() => quitar(e)}
                      className="inline-flex max-w-full items-center gap-1 rounded-full bg-smn-gris-100 px-2.5 py-1 text-[13px] hover:bg-smn-gris-300/50"
                      title="Quitar"
                    >
                      <span className="text-smn-gris-500">{e.modo === "marca" ? "Marca" : e.modo === "categoria" ? "Categoría" : "Producto"}:</span>
                      <span className="truncate">{e.nombre}</span>
                      <X className="h-3 w-3 shrink-0" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <h3 className="mt-5 mb-2 text-[15px] font-medium">Qué lleva el Excel</h3>
            <ul className="space-y-2">
              {HOJAS.map((h) => (
                <li key={h.valor}>
                  <label className="flex cursor-pointer items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={hojas.includes(h.valor)}
                      onChange={() => setHojas((l) => (l.includes(h.valor) ? l.filter((x) => x !== h.valor) : [...l, h.valor]))}
                      className="mt-0.5 h-[18px] w-[18px] accent-smn-naranja"
                    />
                    <span>
                      <span className="block text-[14px]">{h.texto}</span>
                      <span className="block text-[13px] text-smn-gris-500">{h.detalle}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>

            <h3 className="mt-5 mb-2 text-[15px] font-medium">Precios de</h3>
            <div className="space-y-2 text-[14px]">
              <label className="flex items-center gap-2.5">
                <input type="radio" checked={!usarFecha} onChange={() => setUsarFecha(false)} className="h-4 w-4 accent-smn-naranja" />
                La última actualización
              </label>
              <label className="flex flex-wrap items-center gap-2.5">
                <input type="radio" checked={usarFecha} onChange={() => setUsarFecha(true)} className="h-4 w-4 accent-smn-naranja" />
                Hasta el día
                <input
                  type="date"
                  value={fecha}
                  onChange={(e) => (setFecha(e.target.value), setUsarFecha(true))}
                  className="h-9 rounded-lg border border-smn-gris-100 bg-superficie px-2 text-[14px]"
                />
              </label>
            </div>

            <Boton onClick={bajar} cargando={bajando} disabled={!elegidos.length || !hojas.length || (usarFecha && !fecha)} className="mt-5 w-full">
              <Download className="h-4 w-4" /> Descargar Excel
            </Boton>

            <div className="mt-4 flex gap-2">
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                maxLength={120}
                placeholder="Nombre, p. ej. Proteínas AA"
                aria-label="Nombre de la selección"
                className="h-10 min-w-0 flex-1 rounded-lg border border-smn-gris-100 bg-superficie px-3 text-[14px] outline-none focus:border-smn-naranja"
              />
              <Boton variante="secundario" onClick={guardar} cargando={guardando} disabled={!elegidos.length || !nombre.trim()} title="Guardar esta selección">
                <Save className="h-4 w-4" /> Guardar
              </Boton>
            </div>
          </section>
        </Entrada>

        <Entrada retraso={0.1}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
            <h2 className="text-lg font-semibold">Tus selecciones guardadas</h2>
            <p className="mb-3 text-[13px] text-smn-gris-500">Se bajan con los precios del día.</p>
            {!guardadas ? (
              <Esqueleto className="h-16" />
            ) : guardadas.length === 0 ? (
              <p className="text-[14px] text-smn-gris-500">Todavía no guardas ninguna.</p>
            ) : (
              <ul className="divide-y divide-smn-gris-100">
                {guardadas.map((s) => (
                  <li key={s.id} className="flex items-center gap-2 py-2.5">
                    <button type="button" onClick={() => cargarEn(s)} className="min-w-0 flex-1 text-left" title="Abrir para cambiarla">
                      <span className="block truncate font-medium">{s.nombre}</span>
                      <span className="block text-[13px] text-smn-gris-500">
                        {s.productos.toLocaleString("es-MX")} productos{s.usado_en ? ` · bajado ${haceCuanto(s.usado_en).toLowerCase()}` : ""}
                      </span>
                    </button>
                    <Boton variante="secundario" onClick={() => bajarGuardada(s)} cargando={bajandoId === s.id} aria-label={`Descargar ${s.nombre}`}>
                      <Download className="h-4 w-4" />
                    </Boton>
                    <button
                      type="button"
                      onClick={() => borrar(s)}
                      className="rounded-lg p-2 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta"
                      aria-label={`Borrar ${s.nombre}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
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
