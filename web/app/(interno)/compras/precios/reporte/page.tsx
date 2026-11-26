"use client";
// Radar de precios · Reporte a Excel (Diego, 2026-11-17: «un reporte donde seleccione varios productos, individualmente o por
// marca o por categoría y se bajaría en excel»). Se mezclan productos sueltos, marcas y categorías sin repetir; se eligen las
// hojas y la fecha de los precios; la selección se puede guardar para bajarla otra vez con un clic. Desde el 26 nov también por
// clasificación (AA–E) y con una lista de SKU pegada o en Excel (componente Selector).

import { Download, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { descargar, descargarPost, type HojaReporte, type SeleccionGuardada, type SeleccionReporte } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { aSeleccion, Elegidos, Selector, type Elegido } from "../selector";
const HOJAS: { valor: HojaReporte; texto: string; detalle: string }[] = [
  { valor: "resumen", texto: "Resumen por marca y categoría", detalle: "Cuántos están más caros, parejos o más baratos" },
  { valor: "tiendas", texto: "Precio por tienda", detalle: "Walmart, Chedraui, San Pablo, Soriana y otras, con liga" },
  { valor: "accion", texto: "Qué conviene hacer", detalle: "Precio sugerido, margen y costo meta" },
  { valor: "historial", texto: "Historial de 8 semanas", detalle: "Cómo se ha movido el mercado" },
];

export default function Reporte() {
  const avisar = useAvisos();
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

  const cargarGuardadas = useCallback(() => {
    api<SeleccionGuardada[]>("/api/compras/precios/selecciones").then(setGuardadas).catch(() => setGuardadas([]));
  }, []);
  useEffect(cargarGuardadas, [cargarGuardadas]);

  const seleccion: SeleccionReporte = useMemo(
    () => ({
      ...aSeleccion(elegidos),
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
      ...(s.seleccion.clasificaciones ?? []).map((c) => ({ modo: "clasificacion" as const, clave: c, nombre: c === "Sin clase" ? c : `Clase ${c}` })),
      ...s.seleccion.producto_ids.map((id) => ({ modo: "producto" as const, clave: String(id), nombre: `Producto ${id}` })),
    ]);
    setHojas(s.seleccion.hojas);
    setNombre(s.nombre);
  };

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <Entrada>
        <Selector elegidos={elegidos} setElegidos={setElegidos} />
      </Entrada>

      <div className="space-y-6">
        <Entrada retraso={0.05}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5 lg:sticky lg:top-4">
            <h2 className="text-lg font-semibold">Tu reporte</h2>
            <p className="text-[13px] text-smn-gris-500">
              {elegidos.length === 0 ? "Elige productos, marcas, clasificaciones, categorías o una lista de SKU." : `${cuenta === null ? "…" : cuenta.toLocaleString("es-MX")} productos`}
            </p>
            <Elegidos elegidos={elegidos} setElegidos={setElegidos} />

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
                placeholder="Nombre, p. ej. Vidanat AA"
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
