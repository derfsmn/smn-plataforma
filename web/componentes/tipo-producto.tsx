"use client";
// Tipo de producto (lista de márgenes A–F de Compras) y precio de membresía (Diego, 22 nov 2026). Rentabilidad se mide
// contra el mínimo de esa lista, al precio de lista y al de membresía. Lo usa la revisión de propuestas y el detalle del
// radar. El proveedor nunca lo ve.

import { Percent } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Campo, Selector } from "@/componentes/ui";
import { mensajeDe } from "@/lib/api";
import { LISTAS_MARGEN } from "@/lib/productos";

const comoTexto = (v: string | number | null | undefined) => (v != null && v !== "" ? String(Number(v)) : "");

export function TipoProducto({
  lista,
  membresia,
  guardar,
  editable,
  nota,
}: {
  lista: string | null | undefined;
  membresia: string | number | null | undefined;
  guardar: (lista: string, membresia: string | null) => Promise<void>;
  editable: boolean;
  nota?: string;
}) {
  const avisar = useAvisos();
  const [l, setL] = useState(lista ?? "");
  const [m, setM] = useState(comoTexto(membresia));
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    setL(lista ?? "");
    setM(comoTexto(membresia));
  }, [lista, membresia]);
  const nombre = LISTAS_MARGEN.find((x) => x.valor === lista)?.texto;
  const limpio = m.trim().replace(/[$,\s]/g, "");
  const cambio = l !== (lista ?? "") || (limpio ? String(Number(limpio)) : "") !== comoTexto(membresia);

  const enviar = async () => {
    setOcupado(true);
    try {
      await guardar(l, limpio || null);
      avisar("Tipo de producto guardado; cuenta en la siguiente evaluación");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-3 flex items-center gap-2 font-semibold">
        <Percent className="h-4 w-4 text-smn-naranja" aria-hidden /> Tipo de producto
      </h2>
      {editable ? (
        <div className="space-y-3">
          <Selector etiqueta="Lista de márgenes" valor={l} cambiar={setL} opciones={[{ valor: "", texto: "Elige uno" }, ...LISTAS_MARGEN]} />
          <Campo
            etiqueta="Precio de membresía con IVA (si lo sabes)"
            value={m}
            onChange={(e) => setM(e.target.value)}
            inputMode="decimal"
            placeholder="Si no, se calcula con su lista"
          />
          <Boton variante="secundario" cargando={ocupado} disabled={!l || !cambio} onClick={enviar}>
            Guardar
          </Boton>
        </div>
      ) : (
        <dl className="space-y-1 text-sm">
          <div>
            <dt className="inline text-smn-gris-500">Lista: </dt>
            <dd className="inline font-semibold">{nombre ?? "Sin elegir (se usa la A)"}</dd>
          </div>
          <div>
            <dt className="inline text-smn-gris-500">Membresía: </dt>
            <dd className="inline font-semibold">
              {membresia ? `$${Number(membresia).toLocaleString("es-MX", { minimumFractionDigits: 2 })}` : "Se calcula con su lista"}
            </dd>
          </div>
        </dl>
      )}
      <p className="mt-3 text-[13px] text-smn-gris-500">
        {nota ?? "Rentabilidad pide el margen mínimo de esta lista al precio de lista y al de membresía. Sin elegir, se evalúa con la lista A."}
      </p>
    </section>
  );
}
