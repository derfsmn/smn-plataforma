"use client";
// Radar de precios · piezas de las corridas a pedido: avance y estado.

import { CLASE_CORRIDA, textoCorrida, type Pedido } from "@/lib/precios";
import { Insignia } from "@/componentes/ui";

export function Avance({ p }: { p: Pedido }) {
  if (p.estado === "en_espera") return <span className="text-[13px] text-smn-gris-500">Arranca al terminar la corrida que va</span>;
  const total = p.productos || 1;
  const hechos = p.estado === "en_curso" ? Math.min(p.hechos, total) : total;
  const porc = Math.round((hechos / total) * 100);
  if (p.estado !== "en_curso")
    return (
      <span className="text-[13px] text-smn-gris-700 tabular-nums">
        {p.con_precios.toLocaleString("es-MX")} de {p.productos.toLocaleString("es-MX")} con precios
      </span>
    );
  return (
    <span className="block">
      <span className="block h-1.5 overflow-hidden rounded-full bg-smn-gris-100">
        <span className="block h-full rounded-full bg-smn-naranja transition-[width] duration-300" style={{ width: `${Math.max(4, porc)}%` }} />
      </span>
      <span className="mt-1 block text-[13px] text-smn-gris-500 tabular-nums">
        {hechos.toLocaleString("es-MX")} de {p.productos.toLocaleString("es-MX")} revisados
      </span>
    </span>
  );
}

export function Estado({ p }: { p: Pedido }) {
  return <Insignia className={`shrink-0 ${CLASE_CORRIDA[p.estado]}`}>{textoCorrida(p)}</Insignia>;
}
