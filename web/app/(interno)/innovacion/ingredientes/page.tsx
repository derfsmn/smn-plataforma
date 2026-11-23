"use client";
// Catálogo de ingredientes: nombre, tipo, forma química y sinónimos (la búsqueda los usa: «piridoxina» encuentra
// «Vitamina B6»). El factor UI→µg solo se acepta con una fuente revisada que lo respalde.

import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import { P, RUTA, TIPO_INGREDIENTE, type FilaRecurso, type Ingrediente } from "@/lib/innovacion";
import { AREA, MenuModulo, SinAcceso, TARJETA, Vacio } from "../comunes";

type Forma = { id: number | null; nombre: string; tipo: string; forma_quimica: string; sinonimos: string; factor_ui_ug: string; factor_version_id: number | null; factor_fuente: string };
const VACIA: Forma = { id: null, nombre: "", tipo: "mineral", forma_quimica: "", sinonimos: "", factor_ui_ug: "", factor_version_id: null, factor_fuente: "" };

export default function Ingredientes() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [filas, setFilas] = useState<Ingrediente[] | null>(null);
  const [q, setQ] = useState("");
  const [f, setF] = useState<Forma>(VACIA);
  const [fuentes, setFuentes] = useState<FilaRecurso[]>([]);
  const [buscaFuente, setBuscaFuente] = useState("");
  const [guardando, setGuardando] = useState(false);
  const cargar = useCallback(() => api<Ingrediente[]>(`${RUTA}/ingredientes`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    if (puede(P.ver)) cargar();
  }, [puede, cargar]);
  useEffect(() => {
    if (buscaFuente.trim().length < 2) return setFuentes([]);
    const t = setTimeout(() => api<{ recursos: FilaRecurso[] }>(`${RUTA}/recursos?estado=revisado&q=${encodeURIComponent(buscaFuente.trim())}`).then((x) => setFuentes(x.recursos.slice(0, 6))).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [buscaFuente]);

  if (!puede(P.ver)) return <SinAcceso />;
  const editar = (i: Ingrediente) =>
    setF({ id: i.id, nombre: i.nombre, tipo: i.tipo, forma_quimica: i.forma_quimica ?? "", sinonimos: i.sinonimos.join(", "),
      factor_ui_ug: i.factor_ui_ug != null ? String(i.factor_ui_ug) : "", factor_version_id: i.factor_version_id, factor_fuente: i.factor_version_id ? "fuente revisada ligada" : "" });
  const elegirFuente = async (r: FilaRecurso) => {
    const d = await api<{ versiones: { version_id: number; numero: number; estado: string }[] }>(`${RUTA}/recursos/${r.id}`);
    const v = d.versiones.find((x) => x.estado === "revisado");
    if (v) setF({ ...f, factor_version_id: v.version_id, factor_fuente: `${r.titulo} v${v.numero}` });
    setBuscaFuente("");
  };
  const guardar = async () => {
    setGuardando(true);
    try {
      const cuerpo = {
        nombre: f.nombre.trim(), tipo: f.tipo, forma_quimica: f.forma_quimica.trim() || null,
        sinonimos: f.sinonimos.split(",").map((s) => s.trim()).filter(Boolean),
        factor_ui_ug: f.factor_ui_ug.trim() ? Number(f.factor_ui_ug.replace(",", ".")) : null,
        factor_version_id: f.factor_ui_ug.trim() ? f.factor_version_id : null,
      };
      await api(f.id ? `${RUTA}/ingredientes/${f.id}` : `${RUTA}/ingredientes`, { metodo: f.id ? "PUT" : "POST", cuerpo });
      avisar(f.id ? "Ingrediente actualizado." : "Ingrediente agregado.", "exito");
      setF(VACIA);
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  const visibles = (filas ?? []).filter((i) => !q || `${i.nombre} ${i.sinonimos.join(" ")} ${i.forma_quimica ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <Encabezado titulo="Ingredientes" descripcion="El catálogo con sinónimos y formas químicas que usan la búsqueda, la ficha y las reglas." />
      <MenuModulo />
      <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <div>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrar" aria-label="Filtrar ingredientes" className={`${AREA} mb-3`} />
          {!filas ? <Esqueleto className="h-40" /> : visibles.length === 0 ? <Vacio>Sin ingredientes todavía.</Vacio> : (
            <div className={`${TARJETA} divide-y divide-smn-gris-100 p-0`}>
              {visibles.map((i) => (
                <button key={i.id} onClick={() => puede(P.cargar) && editar(i)} className="block w-full px-5 py-3 text-left hover:bg-smn-gris-50">
                  <span className="block font-medium">{i.nombre} <span className="text-[13px] font-normal text-smn-gris-500">· {TIPO_INGREDIENTE[i.tipo] ?? i.tipo}{i.forma_quimica ? ` · ${i.forma_quimica}` : ""}</span></span>
                  {i.sinonimos.length > 0 && <span className="block text-[13px] text-smn-gris-500">También: {i.sinonimos.join(", ")}</span>}
                  {i.factor_ui_ug != null && <span className="block text-[13px] text-smn-gris-500">1 UI = {i.factor_ui_ug} µg (con fuente)</span>}
                </button>
              ))}
            </div>
          )}
        </div>
        {puede(P.cargar) && (
          <div className={`${TARJETA} grid content-start gap-3`}>
            <h2 className="font-semibold">{f.id ? `Editar ${f.nombre}` : "Agregar ingrediente"}</h2>
            <Campo etiqueta="Nombre" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} />
            <Selector etiqueta="Tipo" valor={f.tipo} cambiar={(v) => setF({ ...f, tipo: v })} opciones={Object.entries(TIPO_INGREDIENTE).map(([valor, texto]) => ({ valor, texto }))} />
            <Campo etiqueta="Forma química principal" value={f.forma_quimica} onChange={(e) => setF({ ...f, forma_quimica: e.target.value })} />
            <Campo etiqueta="Sinónimos (separados por coma)" value={f.sinonimos} onChange={(e) => setF({ ...f, sinonimos: e.target.value })} placeholder="magnesium, Mg" />
            <Campo etiqueta="Factor UI → µg (solo vitaminas que lo usan)" inputMode="decimal" value={f.factor_ui_ug} onChange={(e) => setF({ ...f, factor_ui_ug: e.target.value })} placeholder="0.025" />
            {f.factor_ui_ug.trim() && (
              f.factor_version_id ? (
                <p className="text-sm">Respaldo: {f.factor_fuente} <button className="ml-1 font-semibold text-smn-naranja" onClick={() => setF({ ...f, factor_version_id: null, factor_fuente: "" })}>Cambiar</button></p>
              ) : (
                <div>
                  <input value={buscaFuente} onChange={(e) => setBuscaFuente(e.target.value)} placeholder="Fuente revisada que respalda el factor" className={AREA} />
                  {fuentes.map((r) => <button key={r.id} onClick={() => elegirFuente(r)} className="mt-1 block w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-smn-gris-50">{r.titulo}</button>)}
                </div>
              )
            )}
            <div className="flex gap-2">
              <Boton onClick={guardar} cargando={guardando} disabled={f.nombre.trim().length < 2 || (!!f.factor_ui_ug.trim() && !f.factor_version_id)}>Guardar</Boton>
              {f.id && <Boton variante="fantasma" onClick={() => setF(VACIA)}>Cancelar</Boton>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
