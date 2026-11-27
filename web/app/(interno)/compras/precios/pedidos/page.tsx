"use client";
// Radar de precios · Corridas (Diego, 26 nov 2026: «una pantalla donde tengamos listado de corridas y cada corrida deberíamos
// poder subir un excel con los skus o seleccionar marca, clasificación, categorías e irlos a buscar»). Cada corrida dice
// cuándo, quién la pidió, qué se buscó, cómo va y su estado; al abrirla se ve el resumen con acciones y su Excel.

import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { ORIGEN, hora, type Corrida, type Pedido } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Esqueleto, Entrada } from "@/componentes/ui";
import { Avance, Estado } from "./piezas-corrida";

const fecha = (iso: string) =>
  new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleDateString("es-MX", { day: "numeric", month: "short" }) + " · " + hora(iso);

export default function Corridas() {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Pedido[] | null>(null);
  const [todas, setTodas] = useState(false);
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let vivo = true;
    const cargar = () =>
      api<Pedido[]>(`/api/compras/precios/pedidos?todas=${todas}`)
        .then((l) => {
          if (!vivo) return;
          setLista(l);
          // Mientras alguna corre o espera turno, se revisa otra vez (sin encimar peticiones)
          if (l.some((p) => p.estado === "en_curso" || p.estado === "en_espera")) espera.current = setTimeout(cargar, 5000);
        })
        .catch((e) => {
          if (!vivo) return;
          avisar(mensajeDe(e), "info");
          espera.current = setTimeout(cargar, 10000); // una falla no deja la lista cargando para siempre (26 nov 2026)
        });
    setLista(null);
    cargar();
    return () => {
      vivo = false;
      if (espera.current) clearTimeout(espera.current);
    };
  }, [todas, avisar]);

  return (
    <Entrada>
      <section className="rounded-xl border border-smn-gris-100 bg-superficie">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-smn-gris-100 p-4 sm:p-5">
          <div>
            <h2 className="text-lg font-semibold">Corridas</h2>
            <p className="text-[13px] text-smn-gris-500">Busca los precios de los productos que elijas: sube un Excel de SKU o elige marca, clasificación y categoría.</p>
          </div>
          <Link
            href="/compras/precios/pedidos/nueva"
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-smn-naranja px-4 text-[15px] font-medium text-smn-negro hover:brightness-95"
          >
            <Plus className="h-4 w-4" /> Nueva corrida
          </Link>
        </div>
        <label className="flex items-center gap-2 border-b border-smn-gris-100 px-4 py-2.5 text-[14px] sm:px-5">
          <input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} className="h-4 w-4 accent-smn-naranja" />
          Ver también las de la revisión de noche
        </label>
        {!lista ? (
          <div className="space-y-2 p-4">
            <Esqueleto className="h-14" />
            <Esqueleto className="h-14" />
          </div>
        ) : lista.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="font-medium">Todavía no hay corridas.</p>
            <p className="text-[14px] text-smn-gris-500">Con «Nueva corrida» eliges los productos y ves cuánto cuesta antes de lanzarla.</p>
          </div>
        ) : (
          <>
            <table className="hidden w-full text-[14px] md:table">
              <thead className="text-left text-[13px] text-smn-gris-500">
                <tr className="border-b border-smn-gris-100">
                  <th className="px-4 py-2.5 font-medium sm:px-5">Fecha</th>
                  <th className="px-2 py-2.5 font-medium">Qué se buscó</th>
                  <th className="px-2 py-2.5 font-medium">Pidió</th>
                  <th className="w-[200px] px-2 py-2.5 font-medium">Avance</th>
                  <th className="px-2 py-2.5 font-medium">Estado</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-smn-gris-100">
                {lista.map((p) => (
                  <tr key={p.id} className="group relative hover:bg-smn-gris-100/40">
                    <td className="px-4 py-3 whitespace-nowrap tabular-nums sm:px-5">
                      <Link href={`/compras/precios/pedidos/${p.id}`} className="after:absolute after:inset-0">
                        {fecha(p.creado_en)}
                      </Link>
                    </td>
                    <td className="px-2 py-3">
                      <span className="block font-medium">{p.nombre}</span>
                      <span className="block text-[13px] text-smn-gris-500">
                        {p.productos.toLocaleString("es-MX")} productos{p.origen !== "pedido" && ` · ${ORIGEN[p.origen as Corrida["origen"]] ?? p.origen}`}
                      </span>
                    </td>
                    <td className="px-2 py-3">{p.usuario ?? "Programada"}</td>
                    <td className="px-2 py-3">
                      <Avance p={p} />
                    </td>
                    <td className="px-2 py-3">
                      <Estado p={p} />
                    </td>
                    <td className="pr-3">
                      <ChevronRight className="h-4 w-4 text-smn-gris-500 group-hover:text-tinta" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-smn-gris-100 md:hidden">
              {lista.map((p) => (
                <li key={p.id}>
                  <Link href={`/compras/precios/pedidos/${p.id}`} className="block space-y-1.5 p-4">
                    <span className="flex items-start justify-between gap-3">
                      <span className="min-w-0 font-medium">{p.nombre}</span>
                      <Estado p={p} />
                    </span>
                    <span className="block text-[13px] text-smn-gris-500">
                      {fecha(p.creado_en)} · {p.usuario ?? "Programada"} · {p.productos.toLocaleString("es-MX")} productos
                    </span>
                    <Avance p={p} />
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </Entrada>
  );
}
