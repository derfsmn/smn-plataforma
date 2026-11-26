"use client";
// Radar de precios · una corrida: mientras corre, en qué va; al terminar, el resumen de lo que encontró (con precio confirmado,
// más caros, igual o más baratos, sin comparar), qué conviene con cada producto y su Excel. Al picar un producto se abre su
// detalle (tiendas, historial y «Algo está mal») sin salir de la corrida.

import { ArrowLeft, Download, Square } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, dolares, mensajeDe } from "@/lib/api";
import { descargar, hora, type DetallePedido } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { Detalle } from "../../detalle";
import { TablaPrecios, dinero } from "../../tabla-filas";
import { Avance, Estado } from "../piezas-corrida";

const cuando = (iso: string) =>
  new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long" }) + ", " + hora(iso);
const n = (v: number) => v.toLocaleString("es-MX");

const CUADROS: { clave: keyof DetallePedido["cuadros"]; texto: string; punto?: string }[] = [
  { clave: "con_precio", texto: "Con precio confirmado" },
  { clave: "mas_caros", texto: "Más caros que el mercado", punto: "bg-red-600" },
  { clave: "mas_baratos", texto: "Igual o más baratos", punto: "bg-green-600" },
  { clave: "sin_comparar", texto: "Sin comparar", punto: "bg-smn-gris-300" },
];
const ACCIONES: { clave: string; texto: string }[] = [
  { clave: "bajar", texto: "Bajar precio" },
  { clave: "bajar_y_negociar", texto: "Bajar y negociar costo" },
  { clave: "negociar", texto: "Negociar costo" },
  { clave: "subir", texto: "Revisar si se sube" },
];

export default function UnaCorrida() {
  const { id } = useParams<{ id: string }>();
  const avisar = useAvisos();
  const { yo, puede } = useSesion();
  const [d, setD] = useState<DetallePedido | null>(null);
  const [abierto, setAbierto] = useState<number | null>(null);
  const [bajando, setBajando] = useState(false);
  const [deteniendo, setDeteniendo] = useState(false);
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cargar = useCallback(() => {
    if (espera.current) clearTimeout(espera.current);
    api<DetallePedido>(`/api/compras/precios/pedidos/${id}`)
      .then((x) => {
        setD(x);
        if (x.pedido.estado === "en_curso" || x.pedido.estado === "en_espera") espera.current = setTimeout(cargar, 5000);
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);
  useEffect(() => {
    cargar();
    return () => {
      if (espera.current) clearTimeout(espera.current);
    };
  }, [cargar]);

  if (!d) return <Esqueleto className="h-72" />;
  const p = d.pedido;
  const corre = p.estado === "en_curso" || p.estado === "en_espera";
  const suya = p.usuario_id === yo.usuario.id || puede("compras.precios.administrar");

  const excel = async () => {
    setBajando(true);
    try {
      await descargar(`/api/compras/precios/pedidos/${p.id}/excel`, `Radar_de_precios_corrida_${p.id}.xlsx`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setBajando(false);
    }
  };
  const detener = async () => {
    setDeteniendo(true);
    try {
      await api(`/api/compras/precios/pedidos/${p.id}/detener`, { metodo: "POST" });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setDeteniendo(false);
    }
  };
  const acciones = ACCIONES.filter((a) => d.acciones[a.clave]);

  return (
    <div className="space-y-5">
      <Link href="/compras/precios/pedidos" className="inline-flex items-center gap-1.5 text-[14px] text-smn-gris-700 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Corridas
      </Link>

      <Entrada>
        <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold">{p.nombre}</h2>
                <Estado p={p} />
              </div>
              <p className="mt-0.5 text-[14px] text-smn-gris-500">
                {cuando(p.creado_en)}
                {p.usuario && ` · la pidió ${p.usuario}`} · {n(p.productos)} productos
                {Number(p.costo_usd) > 0 && ` · búsquedas ${dolares(p.costo_usd)}`}
              </p>
            </div>
            <div className="flex gap-2">
              {corre && suya && p.origen === "pedido" && (
                <Boton variante="secundario" onClick={detener} cargando={deteniendo}>
                  <Square className="h-4 w-4" /> {p.estado === "en_espera" ? "Quitar de la fila" : "Detener"}
                </Boton>
              )}
              {!corre && d.filas.length > 0 && (
                <Boton onClick={excel} cargando={bajando}>
                  <Download className="h-4 w-4" /> Descargar Excel
                </Boton>
              )}
            </div>
          </div>
          {corre && (
            <div className="mt-4 max-w-md">
              <Avance p={p} />
              <p className="mt-1 text-[13px] text-smn-gris-500">{p.estado === "en_espera" ? "Te avisamos en la campana cuando termine." : p.fase ?? "Buscando precios…"}</p>
            </div>
          )}
          {p.estado === "fallida" && p.error && <p className="mt-3 text-[14px] text-smn-gris-700">{p.error}</p>}
          {p.no_encontrados.length > 0 && (
            <p className="mt-3 text-[13px] text-smn-gris-500">
              {p.no_encontrados.length === 1 ? "1 SKU del Excel no está" : `${n(p.no_encontrados.length)} SKU del Excel no están`} en el catálogo:{" "}
              {p.no_encontrados.slice(0, 15).join(", ")}
              {p.no_encontrados.length > 15 && "…"}
            </p>
          )}
        </section>
      </Entrada>

      {!corre && d.filas.length > 0 && (
        <>
          <Entrada retraso={0.04}>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {CUADROS.map((c) => (
                <div key={c.clave} className="rounded-xl border border-smn-gris-100 bg-superficie p-4">
                  <p className="flex items-center gap-1.5 text-[13px] text-smn-gris-700">
                    {c.punto && <span className={`h-2.5 w-2.5 rounded-full ${c.punto}`} aria-hidden />}
                    {c.texto}
                  </p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums">{n(d.cuadros[c.clave])}</p>
                  {c.clave === "con_precio" && <p className="text-[13px] text-smn-gris-500">de {n(d.filas.length)}</p>}
                </div>
              ))}
            </div>
          </Entrada>

          <Entrada retraso={0.08}>
            <section className="grid gap-4 rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5 md:grid-cols-2">
              <div>
                <h3 className="text-[15px] font-semibold">Qué conviene</h3>
                {acciones.length === 0 ? (
                  <p className="mt-1 text-[14px] text-smn-gris-500">Ningún producto pide acción: los precios están en línea con el mercado.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-[14px]">
                    {acciones.map((a) => (
                      <li key={a.clave} className="flex justify-between gap-3">
                        <span>{a.texto}</span>
                        <b className="tabular-nums">{n(d.acciones[a.clave])}</b>
                      </li>
                    ))}
                  </ul>
                )}
                {Number(d.en_juego) > 0 && (
                  <p className="mt-3 text-[14px]">
                    En juego: <b className="tabular-nums">{dinero(d.en_juego)}</b> al mes
                  </p>
                )}
              </div>
              {Object.keys(d.sin_comparar).length > 0 && (
                <div>
                  <h3 className="text-[15px] font-semibold">Por qué no se compararon</h3>
                  <ul className="mt-2 space-y-1 text-[14px]">
                    {Object.entries(d.sin_comparar).map(([motivo, c]) => (
                      <li key={motivo} className="flex justify-between gap-3">
                        <span className="text-smn-gris-700">{motivo}</span>
                        <b className="tabular-nums">{n(c)}</b>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </Entrada>

          <Entrada retraso={0.12}>
            <section className="rounded-xl border border-smn-gris-100 bg-superficie">
              <div className="border-b border-smn-gris-100 px-4 py-3 sm:px-5">
                <h3 className="text-[15px] font-semibold">Producto por producto</h3>
                <p className="text-[13px] text-smn-gris-500">Primero lo que pide acción, con más dinero en juego. Pica un producto para ver sus tiendas.</p>
              </div>
              <TablaPrecios filas={d.filas} abierto={abierto} abrir={setAbierto} />
            </section>
          </Entrada>
        </>
      )}

      {abierto && <Detalle productoId={abierto} cerrar={() => setAbierto(null)} cambio={cargar} />}
    </div>
  );
}
