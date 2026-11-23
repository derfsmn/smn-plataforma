"use client";
// Pestaña «Composición»: la ficha del producto (datos y tabla de ingredientes, versionada) y la fórmula técnica
// (cifrada; solo el equipo del folio con permiso la ve o la cambia). Guardar crea versión nueva y vuelve a evaluar.

import { Lock, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Campo, Selector } from "@/componentes/ui";
import { api, mensajeDe } from "@/lib/api";
import {
  CAMPOS_FICHA, RUTA, TIPO_INGREDIENTE, UNIDADES, fecha,
  type Componente, type Formula, type Ingrediente, type IngredienteFicha, type PropsPestana,
} from "@/lib/innovacion";
import { AREA, ETIQUETA, TARJETA, Texto, Vacio } from "../../comunes";

const VACIO: IngredienteFicha = {
  ingrediente_id: null, nombre: "", tipo: null, forma: null, en_compuesto: false, cantidad_compuesto: null, unidad_compuesto: "mg",
  cantidad_activa: null, unidad_activa: "mg", fraccion_activa: null, fuente_version_id: null, nota: null,
};
const numero = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

export function Composicion({ e, alCambiar }: PropsPestana) {
  return (
    <div className="grid gap-5">
      <FichaProducto e={e} alCambiar={alCambiar} />
      <FormulaTecnica e={e} alCambiar={alCambiar} />
    </div>
  );
}

function FichaProducto({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const f = e.ficha;
  const [editando, setEditando] = useState(!f && e.puede.editar);
  const [datos, setDatos] = useState<Record<string, string>>({});
  const [filas, setFilas] = useState<IngredienteFicha[]>([]);
  const [nota, setNota] = useState("");
  const [catalogo, setCatalogo] = useState<Ingrediente[]>([]);
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    setDatos(Object.fromEntries(Object.entries(f?.datos ?? { categoria_comercial: e.categoria_comercial ?? "", categoria_sanitaria: e.categoria_sanitaria ?? "", presentacion: e.presentacion ?? "" }).map(([k, v]) => [k, String(v ?? "")])));
    setFilas(f?.ingredientes.length ? f.ingredientes.map((i) => ({ ...i })) : [{ ...VACIO }]);
  }, [f, e.categoria_comercial, e.categoria_sanitaria, e.presentacion]);
  useEffect(() => {
    if (editando) api<Ingrediente[]>(`${RUTA}/ingredientes`).then(setCatalogo).catch(() => {});
  }, [editando]);

  const cambiarFila = (i: number, cambio: Partial<IngredienteFicha>) => setFilas((x) => x.map((y, j) => (j === i ? { ...y, ...cambio } : y)));
  const elegirCatalogo = (i: number, id: string) => {
    const c = catalogo.find((x) => String(x.id) === id);
    cambiarFila(i, c ? { ingrediente_id: c.id, nombre: c.nombre, tipo: c.tipo, forma: filas[i].forma || c.forma_quimica } : { ingrediente_id: null });
  };
  const guardar = async () => {
    const ingredientes = filas.filter((x) => x.nombre.trim());
    setGuardando(true);
    try {
      const r = await api<{ numero: number; evaluacion: number }>(`${RUTA}/expedientes/${e.folio}/fichas`, {
        cuerpo: { datos: Object.fromEntries(Object.entries(datos).filter(([, v]) => v.trim())), ingredientes, nota: nota.trim() || null },
      });
      avisar(`Ficha v${r.numero} guardada y evaluada (#${r.evaluacion}).`, "exito");
      setEditando(false);
      setNota("");
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className={TARJETA}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Ficha del producto{f ? ` · versión ${f.numero}` : ""}</h2>
        {f && <span className="text-[13px] text-smn-gris-500">{fecha(f.creado_en)} · {f.creado_por}</span>}
        {!editando && e.puede.editar && e.estado !== "cerrado" && <Boton variante="secundario" onClick={() => setEditando(true)}>{f ? "Cambiar (versión nueva)" : "Capturar ficha"}</Boton>}
      </div>
      {!editando ? (
        !f ? (
          <Vacio>Sin ficha capturada.</Vacio>
        ) : (
          <>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {CAMPOS_FICHA.filter((c) => f.datos[c.clave]).map((c) => (
                <div key={c.clave} className={c.largo ? "sm:col-span-2" : ""}><dt className="text-smn-gris-500">{c.texto}</dt><dd className="whitespace-pre-line">{f.datos[c.clave]}</dd></div>
              ))}
            </dl>
            <TablaIngredientes filas={f.ingredientes} />
          </>
        )
      ) : (
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {CAMPOS_FICHA.filter((c) => !c.largo).map((c) => (
              <Campo key={c.clave} etiqueta={c.texto} value={datos[c.clave] ?? ""} onChange={(x) => setDatos((d) => ({ ...d, [c.clave]: x.target.value }))} />
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {CAMPOS_FICHA.filter((c) => c.largo).map((c) => (
              <Texto key={c.clave} etiqueta={c.texto} valor={datos[c.clave] ?? ""} cambiar={(v) => setDatos((d) => ({ ...d, [c.clave]: v }))} filas={2} />
            ))}
          </div>
          <div>
            <span className={ETIQUETA}>Ingredientes</span>
            <p className="mb-2 text-[13px] text-smn-gris-500">
              Si el ingrediente viene en un compuesto (p. ej. bisglicinato de magnesio), captura la cantidad del compuesto y la cantidad del activo (magnesio elemental). Las reglas leen la cantidad activa.
            </p>
            <div className="grid gap-3">
              {filas.map((x, i) => (
                <div key={i} className="grid gap-2 rounded-xl border border-smn-gris-100 p-3 md:grid-cols-6">
                  <Selector className="md:col-span-2" etiqueta="Del catálogo" valor={x.ingrediente_id ? String(x.ingrediente_id) : ""} cambiar={(v) => elegirCatalogo(i, v)}
                    opciones={[{ valor: "", texto: "— (escribe el nombre)" }, ...catalogo.map((c) => ({ valor: String(c.id), texto: c.nombre }))]} />
                  <Campo etiqueta="Nombre" value={x.nombre} onChange={(v) => cambiarFila(i, { nombre: v.target.value })} />
                  <Selector etiqueta="Tipo" valor={x.tipo ?? ""} cambiar={(v) => cambiarFila(i, { tipo: v || null })}
                    opciones={[{ valor: "", texto: "—" }, ...Object.entries(TIPO_INGREDIENTE).map(([valor, texto]) => ({ valor, texto }))]} />
                  <div className="md:col-span-2"><Campo etiqueta="Forma química" value={x.forma ?? ""} onChange={(v) => cambiarFila(i, { forma: v.target.value || null })} /></div>
                  <label className="flex items-center gap-2 text-sm md:col-span-6"><input type="checkbox" checked={x.en_compuesto} onChange={(v) => cambiarFila(i, { en_compuesto: v.target.checked })} /> Viene en un compuesto</label>
                  {x.en_compuesto && (
                    <>
                      <Cantidad etiqueta="Cantidad del compuesto" valor={x.cantidad_compuesto} unidad={x.unidad_compuesto}
                        cambiar={(c, u) => cambiarFila(i, { cantidad_compuesto: c, unidad_compuesto: u })} />
                      <Campo etiqueta="Fracción activa (0 a 1)" value={x.fraccion_activa ?? ""} inputMode="decimal"
                        onChange={(v) => cambiarFila(i, { fraccion_activa: numero(v.target.value) })} />
                    </>
                  )}
                  <Cantidad etiqueta={x.en_compuesto ? "Cantidad activa (elemental)" : "Cantidad por porción"} valor={x.cantidad_activa} unidad={x.unidad_activa}
                    cambiar={(c, u) => cambiarFila(i, { cantidad_activa: c, unidad_activa: u })} />
                  <div className="flex items-end md:col-span-1">
                    <Boton variante="fantasma" aria-label="Quitar ingrediente" onClick={() => setFilas((y) => y.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Boton>
                  </div>
                </div>
              ))}
            </div>
            <Boton variante="fantasma" className="mt-2" onClick={() => setFilas((y) => [...y, { ...VACIO }])}><Plus className="h-4 w-4" /> Agregar ingrediente</Boton>
          </div>
          <Campo etiqueta="¿Qué cambió en esta versión?" value={nota} onChange={(x) => setNota(x.target.value)} />
          <div className="flex gap-2">
            <Boton onClick={guardar} cargando={guardando}>Guardar ficha y evaluar</Boton>
            {f && <Boton variante="fantasma" onClick={() => setEditando(false)}>Cancelar</Boton>}
          </div>
        </div>
      )}
    </div>
  );
}

function Cantidad({ etiqueta, valor, unidad, cambiar }: { etiqueta: string; valor: number | null; unidad: string | null; cambiar: (c: number | null, u: string) => void }) {
  return (
    <label className="block md:col-span-2">
      <span className={ETIQUETA}>{etiqueta}</span>
      <div className="flex gap-2">
        <input inputMode="decimal" value={valor ?? ""} onChange={(x) => cambiar(numero(x.target.value), unidad ?? "mg")} className={`${AREA} h-11`} />
        <select value={unidad ?? "mg"} onChange={(x) => cambiar(valor, x.target.value)} className={`${AREA} h-11 w-28`}>
          {UNIDADES.map((u) => <option key={u}>{u}</option>)}
        </select>
      </div>
    </label>
  );
}

function TablaIngredientes({ filas }: { filas: IngredienteFicha[] }) {
  if (!filas.length) return null;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-[13px] text-smn-gris-500">
          <tr><th className="py-1.5 pr-3 font-medium">Ingrediente</th><th className="pr-3 font-medium">Forma</th><th className="pr-3 font-medium">Compuesto</th><th className="font-medium">Activo</th></tr>
        </thead>
        <tbody className="divide-y divide-smn-gris-100">
          {filas.map((i, n) => (
            <tr key={n}>
              <td className="py-2 pr-3 font-medium">{i.nombre}</td>
              <td className="pr-3">{i.forma ?? "—"}</td>
              <td className="pr-3">{i.en_compuesto ? `${i.cantidad_compuesto ?? "—"} ${i.unidad_compuesto ?? ""}` : "—"}</td>
              <td>{i.cantidad_activa ?? "—"} {i.unidad_activa ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const COMPONENTE: Componente = { nombre: "", funcion: "activo", cantidad: null, unidad: "mg", proveedor: null, especificacion: null };

function FormulaTecnica({ e, alCambiar }: PropsPestana) {
  const avisar = useAvisos();
  const fx = e.formula;
  const [formula, setFormula] = useState<Formula | null>(null);
  const [editando, setEditando] = useState(false);
  const [componentes, setComponentes] = useState<Componente[]>([{ ...COMPONENTE }]);
  const [proceso, setProceso] = useState("");
  const [lote, setLote] = useState("");
  const [nota, setNota] = useState("");
  const [guardando, setGuardando] = useState(false);

  if (!fx.puede_ver) {
    return (
      <div className={`${TARJETA} flex items-start gap-3`}>
        <Lock className="mt-0.5 h-5 w-5 text-smn-gris-500" />
        <div>
          <h2 className="font-semibold">Fórmula técnica restringida</h2>
          <p className="text-sm text-smn-gris-500">
            {fx.numero ? `Hay una fórmula (versión ${fx.numero}). ` : ""}Solo la ve el equipo de este folio con permiso de fórmula. Las reglas que la usan te muestran «dato restringido».
          </p>
        </div>
      </div>
    );
  }
  const abrir = async () => {
    if (!fx.numero) return;
    try {
      setFormula(await api<Formula>(`${RUTA}/expedientes/${e.folio}/formulas/${fx.numero}`));
    } catch (x) {
      avisar(mensajeDe(x), "info");
    }
  };
  const empezar = () => {
    setComponentes(formula?.contenido.componentes.length ? formula.contenido.componentes.map((c) => ({ ...c })) : [{ ...COMPONENTE }]);
    setProceso(formula?.contenido.proceso ?? "");
    setLote(formula?.contenido.lote_teorico ?? "");
    setEditando(true);
  };
  const guardar = async () => {
    setGuardando(true);
    try {
      const r = await api<{ numero: number }>(`${RUTA}/expedientes/${e.folio}/formulas`, {
        cuerpo: { componentes: componentes.filter((c) => c.nombre.trim()), proceso: proceso.trim() || null, lote_teorico: lote.trim() || null, nota: nota.trim() || null },
      });
      avisar(`Fórmula v${r.numero} guardada cifrada.`, "exito");
      setEditando(false);
      setFormula(null);
      await alCambiar();
    } catch (x) {
      avisar(mensajeDe(x), "info");
    } finally {
      setGuardando(false);
    }
  };
  const cambiar = (i: number, c: Partial<Componente>) => setComponentes((x) => x.map((y, j) => (j === i ? { ...y, ...c } : y)));
  return (
    <div className={`${TARJETA} border-red-200 dark:border-red-500/30`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 font-semibold"><Lock className="h-4 w-4 text-red-600" /> Fórmula técnica{fx.numero ? ` · versión ${fx.numero}` : ""}</h2>
        <div className="flex gap-2">
          {fx.numero && !formula && !editando && <Boton variante="secundario" onClick={abrir}>Ver fórmula</Boton>}
          {fx.puede_editar && !editando && (fx.numero === null || formula) && <Boton variante="secundario" onClick={empezar}>{fx.numero ? "Cambiar (versión nueva)" : "Capturar fórmula"}</Boton>}
        </div>
      </div>
      <p className="mb-3 text-[13px] text-smn-gris-500">Se guarda cifrada. Verla queda en la bitácora. Nunca entra a la búsqueda general ni sale del servidor.</p>
      {!editando ? (
        formula ? (
          <div className="grid gap-3">
            <table className="w-full text-left text-sm">
              <thead className="text-[13px] text-smn-gris-500"><tr><th className="py-1.5 font-medium">Componente</th><th className="font-medium">Función</th><th className="font-medium">Cantidad</th><th className="font-medium">Proveedor</th></tr></thead>
              <tbody className="divide-y divide-smn-gris-100">
                {formula.contenido.componentes.map((c, i) => (
                  <tr key={i}><td className="py-2 font-medium">{c.nombre}</td><td>{c.funcion ?? "—"}</td><td>{c.cantidad ?? "—"} {c.unidad ?? ""}</td><td>{c.proveedor ?? "—"}</td></tr>
                ))}
              </tbody>
            </table>
            {formula.contenido.proceso && <p className="whitespace-pre-line text-sm"><b>Proceso:</b> {formula.contenido.proceso}</p>}
            {formula.contenido.lote_teorico && <p className="text-sm"><b>Lote teórico:</b> {formula.contenido.lote_teorico}</p>}
            <p className="text-[13px] text-smn-gris-500">{fecha(formula.creado_en)} · {formula.creado_por}{formula.nota ? ` · ${formula.nota}` : ""}</p>
          </div>
        ) : !fx.numero ? (
          <Vacio>Sin fórmula capturada.</Vacio>
        ) : null
      ) : (
        <div className="grid gap-3">
          {componentes.map((c, i) => (
            <div key={i} className="grid gap-2 rounded-xl border border-smn-gris-100 p-3 md:grid-cols-6">
              <div className="md:col-span-2"><Campo etiqueta="Componente" value={c.nombre} onChange={(x) => cambiar(i, { nombre: x.target.value })} /></div>
              <Selector etiqueta="Función" valor={c.funcion ?? ""} cambiar={(v) => cambiar(i, { funcion: v || null })}
                opciones={["activo", "excipiente", "recubrimiento", "capsula", "saborizante", "otro"].map((v) => ({ valor: v, texto: v }))} />
              <Campo etiqueta="Cantidad" inputMode="decimal" value={c.cantidad ?? ""} onChange={(x) => cambiar(i, { cantidad: numero(x.target.value) })} />
              <Selector etiqueta="Unidad" valor={c.unidad ?? "mg"} cambiar={(v) => cambiar(i, { unidad: v })} opciones={UNIDADES.map((u) => ({ valor: u, texto: u }))} />
              <Campo etiqueta="Proveedor" value={c.proveedor ?? ""} onChange={(x) => cambiar(i, { proveedor: x.target.value || null })} />
              <div className="flex items-end"><Boton variante="fantasma" aria-label="Quitar componente" onClick={() => setComponentes((x) => x.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Boton></div>
            </div>
          ))}
          <Boton variante="fantasma" className="justify-self-start" onClick={() => setComponentes((x) => [...x, { ...COMPONENTE }])}><Plus className="h-4 w-4" /> Agregar componente</Boton>
          <Texto etiqueta="Proceso" valor={proceso} cambiar={setProceso} filas={4} />
          <Campo etiqueta="Lote teórico" value={lote} onChange={(x) => setLote(x.target.value)} />
          <Campo etiqueta="¿Qué cambió en esta versión?" value={nota} onChange={(x) => setNota(x.target.value)} />
          <div className="flex gap-2">
            <Boton onClick={guardar} cargando={guardando} disabled={!componentes.some((c) => c.nombre.trim())}>Guardar fórmula y evaluar</Boton>
            <Boton variante="fantasma" onClick={() => setEditando(false)}>Cancelar</Boton>
          </div>
        </div>
      )}
    </div>
  );
}
