"use client";
// Radar de precios · Nueva corrida: elegir los productos (Excel de SKU, pegados, o marca, clasificación y categoría), ver cuánto
// costaría en búsquedas antes de lanzarla y lanzarla. Si otra corrida está corriendo, la nueva se forma y arranca sola.

import { ArrowLeft, Play, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, dolares, mensajeDe } from "@/lib/api";
import type { EstimadoPedido, Pedido } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Entrada, Esqueleto } from "@/componentes/ui";
import { aSeleccion, Elegidos, Selector, type Elegido, type UltimaLista } from "../../selector";

export default function NuevaCorrida() {
  const avisar = useAvisos();
  const router = useRouter();
  const [elegidos, setElegidos] = useState<Elegido[]>([]);
  const [lista, setLista] = useState<UltimaLista | null>(null);
  const [e, setE] = useState<EstimadoPedido | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [lanzando, setLanzando] = useState(false);

  const cuerpo = useMemo(() => {
    const s = aSeleccion(elegidos);
    // El nombre del Excel solo se guarda si la corrida es justo esa lista
    const soloLista = lista && !s.marcas.length && !s.categorias.length && !s.clasificaciones.length;
    return { ...s, archivo: soloLista ? lista.archivo : null, no_encontrados: lista?.no_encontrados ?? [] };
  }, [elegidos, lista]);

  useEffect(() => {
    if (!elegidos.length) return setE(null);
    setCalculando(true);
    const id = setTimeout(() => {
      api<EstimadoPedido>("/api/compras/precios/pedidos/estimar", { metodo: "POST", cuerpo })
        .then(setE)
        .catch((x) => avisar(mensajeDe(x), "info"))
        .finally(() => setCalculando(false));
    }, 300);
    return () => clearTimeout(id);
  }, [elegidos, cuerpo, avisar]);

  const lanzar = async () => {
    setLanzando(true);
    try {
      const p = await api<Pedido>("/api/compras/precios/pedidos", { metodo: "POST", cuerpo });
      avisar(p.estado === "en_espera" ? "Corrida formada; arranca sola en cuanto termine la que va" : "Corrida lanzada", "exito");
      router.push(`/compras/precios/pedidos/${p.id}`);
    } catch (x) {
      avisar(mensajeDe(x), "info");
      setLanzando(false);
    }
  };

  return (
    <div className="space-y-4">
      <Link href="/compras/precios/pedidos" className="inline-flex items-center gap-1.5 text-[14px] text-smn-gris-700 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Corridas
      </Link>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Entrada>
          <Selector elegidos={elegidos} setElegidos={setElegidos} alLeerLista={setLista} titulo="¿Qué productos buscamos?" />
        </Entrada>
        <Entrada retraso={0.05}>
          <section className="rounded-xl border border-smn-gris-100 bg-superficie p-4 sm:p-5 lg:sticky lg:top-4">
            <h2 className="text-lg font-semibold">Nueva corrida</h2>
            {!elegidos.length ? (
              <p className="text-[14px] text-smn-gris-500">Elige productos, marcas, clasificaciones, categorías o sube tu lista de SKU.</p>
            ) : !e || calculando ? (
              <Esqueleto className="mt-3 h-24" />
            ) : (
              <>
                <p className="text-[14px] text-smn-gris-500">
                  <b className="text-[22px] text-tinta tabular-nums">{e.productos.toLocaleString("es-MX")}</b> productos
                  {e.productos > e.maximo && ` (máximo ${e.maximo})`}
                </p>
                <Elegidos elegidos={elegidos} setElegidos={setElegidos} />
                <dl className="mt-4 space-y-1.5 text-[14px]">
                  <div className="flex justify-between gap-3">
                    <dt className="text-smn-gris-700">Costo de las búsquedas</dt>
                    <dd className="font-semibold tabular-nums">hasta {dolares(e.estimado_usd)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-smn-gris-700">Queda este mes</dt>
                    <dd className="tabular-nums">
                      {dolares(e.disponible_usd)} de {dolares(e.tope_mes_usd)}
                    </dd>
                  </div>
                </dl>
                {e.motivo ? (
                  <p className="mt-3 flex gap-2 rounded-lg bg-aviso-fondo p-3 text-[14px] text-aviso-texto">
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {e.motivo}
                  </p>
                ) : (
                  <>
                    {!e.cabe && (
                      <p className="mt-3 rounded-lg bg-aviso-fondo p-3 text-[14px] text-aviso-texto">
                        Puede que no alcance lo que queda del mes; los productos que falten quedan para la revisión de noche.
                      </p>
                    )}
                    {(e.ocupado || e.en_espera > 0) && (
                      <p className="mt-3 rounded-lg bg-smn-gris-100/60 p-3 text-[14px]">
                        {e.ocupado ?? "Hay corridas formadas"}
                        {e.en_espera > 0 && ` y ${e.en_espera === 1 ? "hay 1 corrida formada" : `hay ${e.en_espera} corridas formadas`}`}. La tuya arranca sola en cuanto
                        termine.
                      </p>
                    )}
                  </>
                )}
                <Boton onClick={lanzar} cargando={lanzando} disabled={!e.puede} className="mt-4 w-full">
                  <Play className="h-4 w-4" /> Lanzar corrida
                </Boton>
                <p className="mt-2 text-[13px] text-smn-gris-500">Al terminar te avisamos en la campana. Los productos quedan en el radar y la revisión de noche los mantiene al día.</p>
              </>
            )}
          </section>
        </Entrada>
      </div>
    </div>
  );
}
