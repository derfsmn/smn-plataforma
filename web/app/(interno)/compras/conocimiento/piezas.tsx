"use client";
// Piezas compartidas de la base de conocimiento: vacío, área de texto, departamento, error y lista de reglas.

import { AnimatePresence } from "motion/react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { TIPOS_REGLA, rango, type Regla, type TipoRegla } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Esqueleto, Insignia } from "@/componentes/ui";

export const EDITAR = "compras.conocimiento.editar";

export function Vacio({ titulo, texto, icono }: { titulo: string; texto: React.ReactNode; icono: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-6 py-12 text-center">
      <span className="text-naranja-tinta">{icono}</span>
      <p className="mt-3 text-lg font-semibold">{titulo}</p>
      <div className="mt-1 max-w-md text-sm text-smn-gris-500">{texto}</div>
    </div>
  );
}

export function AreaTexto({ etiqueta, valor, cambiar, filas = 4, max, ayuda }: { etiqueta: string; valor: string; cambiar: (v: string) => void; filas?: number; max?: number; ayuda?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">{etiqueta}</span>
      <textarea
        value={valor}
        onChange={(e) => cambiar(e.target.value)}
        rows={filas}
        maxLength={max}
        className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
      />
      {ayuda && <span className="mt-1 block text-[13px] text-smn-gris-500">{ayuda}</span>}
    </label>
  );
}

// Departamentos del catálogo; si el catálogo no se ha cargado se puede escribir libre
export function useDepartamentos() {
  const [lista, setLista] = useState<string[]>([]);
  useEffect(() => {
    api<string[]>("/api/compras/conocimiento/departamentos").then(setLista).catch(() => setLista([]));
  }, []);
  return lista;
}

export function CampoDepartamento({ valor, cambiar, departamentos }: { valor: string; cambiar: (v: string) => void; departamentos: string[] }) {
  return (
    <>
      <Campo etiqueta="Departamento (vacío = aplica a todos)" value={valor} onChange={(e) => cambiar(e.target.value)} list="departamentos-catalogo" placeholder="Todos" />
      <datalist id="departamentos-catalogo">
        {departamentos.map((d) => (
          <option key={d} value={d} />
        ))}
      </datalist>
    </>
  );
}

export function MensajeError({ texto }: { texto: string | null }) {
  if (!texto) return null;
  return (
    <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-400">
      {texto}
    </p>
  );
}

export function Pie({ por, en }: { por: string | null; en: string | null }) {
  if (!en) return null;
  return (
    <span>
      {por ? `${por} · ` : ""}
      {fechaLocal(en)}
    </span>
  );
}

type FormaRegla = { criterio: string; departamento: string; minimo: string; maximo: string; unidad: string; periodo_meses: string; descripcion: string; activa: boolean };
const vacia: FormaRegla = { criterio: "", departamento: "", minimo: "", maximo: "", unidad: "", periodo_meses: "", descripcion: "", activa: true };

// Rechazo directo, criterios y lanzamiento exitoso comparten la misma lista; cambia qué se pide
export function ListaReglas({ tipo, icono }: { tipo: TipoRegla; icono: React.ReactNode }) {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const editar = puede(EDITAR);
  const textos = TIPOS_REGLA[tipo];
  const departamentos = useDepartamentos();
  const [lista, setLista] = useState<Regla[] | null>(null);
  const [abierta, setAbierta] = useState<{ id?: number; datos: FormaRegla } | null>(null);
  const [borrar, setBorrar] = useState<Regla | null>(null);

  const cargar = useCallback(() => {
    api<Regla[]>(`/api/compras/conocimiento/reglas?tipo=${tipo}`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar, tipo]);
  useEffect(cargar, [cargar]);

  const quitar = async () => {
    if (!borrar) return;
    try {
      await api(`/api/compras/conocimiento/reglas/${borrar.id}`, { metodo: "DELETE" });
      avisar("Quitado", "exito");
      setBorrar(null);
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!lista) return <Esqueleto className="h-48" />;
  const aForma = (r: Regla): FormaRegla => ({
    criterio: r.criterio,
    departamento: r.departamento ?? "",
    minimo: r.minimo ?? "",
    maximo: r.maximo ?? "",
    unidad: r.unidad ?? "",
    periodo_meses: r.periodo_meses ? String(r.periodo_meses) : "",
    descripcion: r.descripcion ?? "",
    activa: r.activa,
  });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-smn-gris-500">{textos.explicacion}</p>
        {editar && (
          <Boton onClick={() => setAbierta({ datos: vacia })}>
            <Plus className="h-4 w-4" /> {textos.nuevo}
          </Boton>
        )}
      </div>
      {!lista.length ? (
        <Vacio icono={icono} titulo="Todavía no hay nada aquí" texto={editar ? `Usa «${textos.nuevo}» para escribir el primero.` : "Compras todavía no lo ha llenado."} />
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {lista.map((r) => (
            <li key={r.id} className={`flex items-start gap-3 p-4 ${r.activa ? "" : "opacity-60"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {r.criterio}
                  {rango(r) && <span className="ml-2 font-semibold text-naranja-tinta">{rango(r)}</span>}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <Insignia className="bg-smn-gris-50 text-smn-gris-700">{r.departamento ?? "Todos los departamentos"}</Insignia>
                  {!r.activa && <Insignia className="bg-smn-gris-100 text-smn-gris-500">No se usa</Insignia>}
                </div>
                {r.descripcion && <p className="mt-1.5 text-sm whitespace-pre-line text-smn-gris-700">{r.descripcion}</p>}
                <p className="mt-1 text-[13px] text-smn-gris-500">
                  <Pie por={r.actualizado_por} en={r.actualizado_en} />
                </p>
              </div>
              {editar && (
                <>
                  <button onClick={() => setAbierta({ id: r.id, datos: aForma(r) })} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${r.criterio}`}>
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button onClick={() => setBorrar(r)} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Quitar ${r.criterio}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <AnimatePresence>
        {abierta && <VentanaRegla tipo={tipo} id={abierta.id} inicial={abierta.datos} departamentos={departamentos} cerrar={() => setAbierta(null)} alGuardar={cargar} />}
        {borrar && (
          <Modal titulo="Quitar" cerrar={() => setBorrar(null)}>
            <p>
              Se quitará <b>{borrar.criterio}</b> de la base de conocimiento.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => setBorrar(null)}>
                Cancelar
              </Boton>
              <Boton onClick={quitar}>Quitar</Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </div>
  );
}

function VentanaRegla({ tipo, id, inicial, departamentos, cerrar, alGuardar }: { tipo: TipoRegla; id?: number; inicial: FormaRegla; departamentos: string[]; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const textos = TIPOS_REGLA[tipo];
  const [d, setD] = useState<FormaRegla>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const cuerpo = {
        tipo,
        criterio: d.criterio,
        departamento: d.departamento || null,
        minimo: num(d.minimo),
        maximo: num(d.maximo),
        unidad: d.unidad || null,
        periodo_meses: num(d.periodo_meses),
        descripcion: d.descripcion || null,
        activa: d.activa,
      };
      await api(id ? `/api/compras/conocimiento/reglas/${id}` : "/api/compras/conocimiento/reglas", { metodo: id ? "PUT" : "POST", cuerpo });
      avisar("Guardado", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={id ? "Editar" : textos.nuevo} cerrar={cerrar} ancho="max-w-lg">
      <div className="space-y-4">
        <Campo etiqueta={textos.criterio} value={d.criterio} onChange={(e) => setD({ ...d, criterio: e.target.value })} placeholder={textos.ejemplo} maxLength={200} autoFocus />
        {tipo !== "rechazo" && (
          <div className="grid grid-cols-3 gap-3">
            <Campo etiqueta={tipo === "exito" ? "Meta" : "Mínimo"} inputMode="decimal" value={d.minimo} onChange={(e) => setD({ ...d, minimo: e.target.value })} />
            {tipo === "umbral" ? (
              <Campo etiqueta="Máximo" inputMode="decimal" value={d.maximo} onChange={(e) => setD({ ...d, maximo: e.target.value })} />
            ) : (
              <Campo etiqueta="En cuántos meses" inputMode="numeric" value={d.periodo_meses} onChange={(e) => setD({ ...d, periodo_meses: e.target.value })} />
            )}
            <Campo etiqueta="Unidad" value={d.unidad} onChange={(e) => setD({ ...d, unidad: e.target.value })} placeholder="%, días, piezas" maxLength={40} />
          </div>
        )}
        <CampoDepartamento valor={d.departamento} cambiar={(v) => setD({ ...d, departamento: v })} departamentos={departamentos} />
        <AreaTexto
          etiqueta={tipo === "rechazo" ? "Explicación (opcional)" : "Notas o excepciones (opcional)"}
          valor={d.descripcion}
          cambiar={(v) => setD({ ...d, descripcion: v })}
          max={1000}
          filas={3}
        />
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={d.activa} onChange={(e) => setD({ ...d, activa: e.target.checked })} className="h-4 w-4 accent-[var(--color-smn-naranja)]" />
          Se usa hoy
        </label>
      </div>
      <MensajeError texto={error} />
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando} disabled={d.criterio.trim().length < 2}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}
