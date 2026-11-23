"use client";
// Pestaña «Mercado y pendientes»: productos comparables (cada uno con su fuente), escenarios de costo y precio con
// margen calculado, y pendientes del expediente (los determinantes se muestran en la compuerta).

import { CheckCircle2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Campo, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe, pesos } from "@/lib/api";
import { RUTA, fecha, type PropsPestana } from "@/lib/innovacion";
import { TARJETA, Vacio } from "../../comunes";

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

export function Mercado({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const enviar = async (ruta: string, cuerpo: unknown, listo: () => void) => {
    try {
      await api(ruta, { cuerpo });
      listo();
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  const [c, setC] = useState({ producto: "", marca: "", presentacion: "", precio: "", fuente: "", url: "" });
  const [s, setS] = useState({ nombre: "", costo_unitario: "", precio: "", supuestos: "", confianza: "media" });
  const [p, setP] = useState({ descripcion: "", fecha_limite: "", responsable_id: "", determinante: false });
  const ed = e.puede.editar;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className={TARJETA}>
        <h2 className="mb-1 font-semibold">Productos comparables</h2>
        <p className="mb-3 text-[13px] text-smn-gris-500">Para el análisis comercial que hace Marketing. Un comparable capturado a mano lleva su fuente o enlace.</p>
        {e.comparables.length === 0 ? <Vacio>Sin comparables.</Vacio> : (
          <ul className="divide-y divide-smn-gris-100 text-sm">
            {e.comparables.map((x) => (
              <li key={x.id} className="flex items-start justify-between gap-2 py-2">
                <span>
                  <span className="block font-medium">{x.producto}{x.marca ? ` · ${x.marca}` : ""}</span>
                  <span className="block text-[13px] text-smn-gris-500">
                    {x.presentacion ?? ""}{x.precio != null ? ` · ${pesos(x.precio)}` : ""}{x.fuente ? ` · ${x.fuente}` : ""}
                    {x.url && <> · <a href={x.url} target="_blank" rel="noreferrer noopener" className="text-smn-naranja underline">enlace</a></>}
                  </span>
                </span>
                {ed && <button aria-label="Quitar comparable" onClick={() => api(`${RUTA}/comparables/${x.id}`, { metodo: "DELETE" }).then(alCambiar).catch((y) => avisar(mensajeDe(y), "info"))}><Trash2 className="h-4 w-4" /></button>}
              </li>
            ))}
          </ul>
        )}
        {ed && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Campo etiqueta="Producto" value={c.producto} onChange={(x) => setC({ ...c, producto: x.target.value })} />
            <Campo etiqueta="Marca" value={c.marca} onChange={(x) => setC({ ...c, marca: x.target.value })} />
            <Campo etiqueta="Presentación" value={c.presentacion} onChange={(x) => setC({ ...c, presentacion: x.target.value })} />
            <Campo etiqueta="Precio (MXN)" inputMode="decimal" value={c.precio} onChange={(x) => setC({ ...c, precio: x.target.value })} />
            <Campo etiqueta="Fuente (tienda, catálogo…)" value={c.fuente} onChange={(x) => setC({ ...c, fuente: x.target.value })} />
            <Campo etiqueta="Enlace" value={c.url} onChange={(x) => setC({ ...c, url: x.target.value })} />
            <Boton variante="secundario" className="sm:col-span-2" disabled={c.producto.trim().length < 2 || (!c.fuente.trim() && !c.url.trim())}
              onClick={() => enviar(`${RUTA}/expedientes/${e.folio}/comparables`,
                { origen: "manual", producto: c.producto.trim(), marca: c.marca.trim() || null, presentacion: c.presentacion.trim() || null, precio: num(c.precio), fuente: c.fuente.trim() || null, url: c.url.trim() || null },
                () => setC({ producto: "", marca: "", presentacion: "", precio: "", fuente: "", url: "" }))}>
              <Plus className="h-4 w-4" /> Agregar comparable
            </Boton>
          </div>
        )}
      </div>

      <div className={TARJETA}>
        <h2 className="mb-1 font-semibold">Escenarios de costo y precio</h2>
        <p className="mb-3 text-[13px] text-smn-gris-500">El margen se calcula sobre el precio. Anota de dónde sale cada supuesto.</p>
        {e.escenarios.length === 0 ? <Vacio>Sin escenarios.</Vacio> : (
          <ul className="divide-y divide-smn-gris-100 text-sm">
            {e.escenarios.map((x) => (
              <li key={x.id} className="py-2">
                <span className="flex flex-wrap items-center gap-2 font-medium">{x.nombre}{x.confianza && <Insignia className="bg-smn-gris-100 text-smn-gris-700">confianza {x.confianza}</Insignia>}</span>
                <span className="block text-[13px] text-smn-gris-500">
                  Costo {x.costo_unitario != null ? pesos(x.costo_unitario) : "—"} · precio {x.precio != null ? pesos(x.precio) : "—"} · margen {x.margen_pct != null ? `${x.margen_pct} %` : "—"}
                </span>
                {x.supuestos && <span className="block text-[13px]">{x.supuestos}</span>}
              </li>
            ))}
          </ul>
        )}
        {ed && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Campo etiqueta="Nombre" value={s.nombre} onChange={(x) => setS({ ...s, nombre: x.target.value })} placeholder="Base, optimista…" />
            <Selector etiqueta="Confianza" valor={s.confianza} cambiar={(v) => setS({ ...s, confianza: v })} opciones={["alta", "media", "baja"].map((v) => ({ valor: v, texto: v }))} />
            <Campo etiqueta="Costo unitario (MXN)" inputMode="decimal" value={s.costo_unitario} onChange={(x) => setS({ ...s, costo_unitario: x.target.value })} />
            <Campo etiqueta="Precio (MXN)" inputMode="decimal" value={s.precio} onChange={(x) => setS({ ...s, precio: x.target.value })} />
            <div className="sm:col-span-2"><Campo etiqueta="Supuestos" value={s.supuestos} onChange={(x) => setS({ ...s, supuestos: x.target.value })} /></div>
            <Boton variante="secundario" className="sm:col-span-2" disabled={s.nombre.trim().length < 2}
              onClick={() => enviar(`${RUTA}/expedientes/${e.folio}/escenarios`,
                { nombre: s.nombre.trim(), costo_unitario: num(s.costo_unitario), precio: num(s.precio), supuestos: s.supuestos.trim() || null, confianza: s.confianza },
                () => setS({ nombre: "", costo_unitario: "", precio: "", supuestos: "", confianza: "media" }))}>
              <Plus className="h-4 w-4" /> Agregar escenario
            </Boton>
          </div>
        )}
      </div>

      <div className={`${TARJETA} lg:col-span-2`}>
        <h2 className="mb-3 font-semibold">Pendientes</h2>
        {e.pendientes.length === 0 ? <Vacio>Sin pendientes.</Vacio> : (
          <ul className="divide-y divide-smn-gris-100 text-sm">
            {e.pendientes.map((x) => (
              <li key={x.id} className="flex items-center justify-between gap-2 py-2">
                <span className={x.estado === "cerrado" ? "text-smn-gris-500 line-through" : ""}>
                  {x.descripcion}
                  <span className="ml-2 text-[13px] text-smn-gris-500">{x.responsable ?? "sin responsable"}{x.fecha_limite ? ` · ${fecha(x.fecha_limite)}` : ""}</span>
                  {x.determinante && <Insignia className="ml-2 bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">Determinante</Insignia>}
                </span>
                {ed && x.estado !== "cerrado" && (
                  <Boton variante="fantasma" className="min-h-8 px-2" onClick={() => api(`${RUTA}/pendientes/${x.id}/cerrar`, { metodo: "POST", cuerpo: {} }).then(alCambiar).catch((y) => avisar(mensajeDe(y), "info"))}>
                    <CheckCircle2 className="h-4 w-4" /> Cerrar
                  </Boton>
                )}
              </li>
            ))}
          </ul>
        )}
        {ed && (
          <div className="mt-3 grid gap-2 sm:grid-cols-4">
            <div className="sm:col-span-2"><Campo etiqueta="Pendiente" value={p.descripcion} onChange={(x) => setP({ ...p, descripcion: x.target.value })} /></div>
            <Selector etiqueta="Responsable" valor={p.responsable_id} cambiar={(v) => setP({ ...p, responsable_id: v })}
              opciones={[{ valor: "", texto: "—" }, ...e.equipo.map((m) => ({ valor: String(m.usuario_id), texto: m.nombre }))]} />
            <Campo etiqueta="Fecha límite" type="date" value={p.fecha_limite} onChange={(x) => setP({ ...p, fecha_limite: x.target.value })} />
            <label className="flex items-center gap-2 text-sm sm:col-span-3"><input type="checkbox" checked={p.determinante} onChange={(x) => setP({ ...p, determinante: x.target.checked })} /> Determinante para la decisión del Filtro</label>
            <Boton variante="secundario" disabled={p.descripcion.trim().length < 3}
              onClick={() => enviar(`${RUTA}/expedientes/${e.folio}/pendientes`,
                { descripcion: p.descripcion.trim(), responsable_id: p.responsable_id ? Number(p.responsable_id) : null, fecha_limite: p.fecha_limite || null, determinante: p.determinante },
                () => setP({ descripcion: "", fecha_limite: "", responsable_id: "", determinante: false }))}>
              <Plus className="h-4 w-4" /> Agregar
            </Boton>
          </div>
        )}
      </div>
    </div>
  );
}
