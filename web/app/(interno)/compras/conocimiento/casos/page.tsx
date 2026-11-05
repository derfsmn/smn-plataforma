"use client";
// Base de conocimiento · Casos pasados: productos que Compras ya evaluó, para calibrar el semáforo.

import { AnimatePresence } from "motion/react";
import { History, Pencil, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_DECISION, TEXTO_RESULTADO, type Caso, type Decision, type Resultado } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { AreaTexto, CampoDepartamento, EDITAR, MensajeError, Vacio, useDepartamentos } from "../piezas";

type Forma = { producto: string; sku: string; proveedor: string; departamento: string; fecha_decision: string; decision: Decision; motivo: string; resultado: Resultado; notas: string };
const NUEVO: Forma = { producto: "", sku: "", proveedor: "", departamento: "", fecha_decision: "", decision: "aprobado", motivo: "", resultado: "sin_dato", notas: "" };
const opciones = <T extends string>(textos: Record<T, string>) => (Object.keys(textos) as T[]).map((valor) => ({ valor, texto: textos[valor] }));
const CLASE_DECISION: Record<Decision, string> = {
  aprobado: "bg-smn-naranja/15 text-aviso-texto",
  rechazado: "bg-tinta text-superficie",
  condicionado: "bg-smn-gris-100 text-smn-gris-700",
};

export default function Casos() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const editar = puede(EDITAR);
  const departamentos = useDepartamentos();
  const [lista, setLista] = useState<Caso[] | null>(null);
  const [abierto, setAbierto] = useState<{ id?: number; datos: Forma } | null>(null);
  const [borrar, setBorrar] = useState<Caso | null>(null);

  const cargar = useCallback(() => {
    api<Caso[]>("/api/compras/conocimiento/casos").then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const quitar = async () => {
    if (!borrar) return;
    try {
      await api(`/api/compras/conocimiento/casos/${borrar.id}`, { metodo: "DELETE" });
      avisar("Caso quitado", "exito");
      setBorrar(null);
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!lista) return <Esqueleto className="h-48" />;
  const aForma = (c: Caso): Forma => ({
    producto: c.producto,
    sku: c.sku ?? "",
    proveedor: c.proveedor ?? "",
    departamento: c.departamento ?? "",
    fecha_decision: c.fecha_decision ?? "",
    decision: c.decision,
    motivo: c.motivo ?? "",
    resultado: c.resultado,
    notas: c.notas ?? "",
  });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-smn-gris-500">
          Productos que Compras evaluó antes, aprobados y rechazados, con su motivo y cómo les fue. Con al menos 20 se puede comprobar que el semáforo sugiere lo mismo que habría decidido Compras. Sirven más si hay éxitos y fracasos.
        </p>
        {editar && (
          <Boton onClick={() => setAbierto({ datos: NUEVO })}>
            <Plus className="h-4 w-4" /> Agregar caso
          </Boton>
        )}
      </div>
      {!lista.length ? (
        <Vacio icono={<History className="h-10 w-10" />} titulo="Sin casos" texto={editar ? "Agrega los productos que mejor muestren cómo decide Compras." : "Compras todavía no los ha registrado."} />
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-smn-gris-100 bg-superficie">
          <table className="w-full text-sm">
            <thead className="bg-smn-gris-50 text-left text-[13px] font-medium text-smn-gris-500">
              <tr>
                <th className="px-4 py-3">Producto</th>
                <th className="px-4 py-3">Decisión</th>
                <th className="px-4 py-3">Motivo</th>
                <th className="px-4 py-3">Resultado</th>
                {editar && <th className="px-4 py-3" aria-label="Acciones" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-smn-gris-100">
              {lista.map((c) => (
                <tr key={c.id} className="align-top">
                  <td className="px-4 py-3">
                    <p className="font-semibold">{c.producto}</p>
                    <p className="text-[13px] text-smn-gris-500">{[c.sku, c.proveedor, c.departamento, c.fecha_decision].filter(Boolean).join(" · ")}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Insignia className={CLASE_DECISION[c.decision]}>{TEXTO_DECISION[c.decision]}</Insignia>
                  </td>
                  <td className="max-w-sm px-4 py-3 text-smn-gris-700">{c.motivo ?? "—"}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{TEXTO_RESULTADO[c.resultado]}</td>
                  {editar && (
                    <td className="px-2 py-2 whitespace-nowrap">
                      <button onClick={() => setAbierto({ id: c.id, datos: aForma(c) })} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${c.producto}`}>
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button onClick={() => setBorrar(c)} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Quitar ${c.producto}`}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[13px] text-smn-gris-500">{lista.length} caso{lista.length === 1 ? "" : "s"}</p>
      <AnimatePresence>
        {abierto && <VentanaCaso id={abierto.id} inicial={abierto.datos} departamentos={departamentos} cerrar={() => setAbierto(null)} alGuardar={cargar} />}
        {borrar && (
          <Modal titulo="Quitar caso" cerrar={() => setBorrar(null)}>
            <p>
              Se quitará <b>{borrar.producto}</b> de los casos pasados.
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

function VentanaCaso({ id, inicial, departamentos, cerrar, alGuardar }: { id?: number; inicial: Forma; departamentos: string[]; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [d, setD] = useState<Forma>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const cuerpo = {
        ...d,
        sku: d.sku || null,
        proveedor: d.proveedor || null,
        departamento: d.departamento || null,
        fecha_decision: d.fecha_decision || null,
        motivo: d.motivo || null,
        notas: d.notas || null,
      };
      await api(id ? `/api/compras/conocimiento/casos/${id}` : "/api/compras/conocimiento/casos", { metodo: id ? "PUT" : "POST", cuerpo });
      avisar(id ? "Caso actualizado" : "Caso agregado", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={id ? "Editar caso" : "Agregar caso"} cerrar={cerrar} ancho="max-w-2xl">
      <div className="space-y-4">
        <Campo etiqueta="Producto" value={d.producto} onChange={(e) => setD({ ...d, producto: e.target.value })} maxLength={300} autoFocus />
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo etiqueta="SKU (si se dio de alta)" value={d.sku} onChange={(e) => setD({ ...d, sku: e.target.value })} maxLength={60} />
          <Campo etiqueta="Proveedor" value={d.proveedor} onChange={(e) => setD({ ...d, proveedor: e.target.value })} maxLength={200} />
          <Campo etiqueta="Fecha aproximada" type="date" value={d.fecha_decision} onChange={(e) => setD({ ...d, fecha_decision: e.target.value })} />
        </div>
        <CampoDepartamento valor={d.departamento} cambiar={(v) => setD({ ...d, departamento: v })} departamentos={departamentos} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Selector etiqueta="Decisión" valor={d.decision} cambiar={(v) => setD({ ...d, decision: v as Decision })} opciones={opciones(TEXTO_DECISION)} />
          <Selector etiqueta="Cómo le fue" valor={d.resultado} cambiar={(v) => setD({ ...d, resultado: v as Resultado })} opciones={opciones(TEXTO_RESULTADO)} />
        </div>
        <AreaTexto etiqueta="Motivo de la decisión" valor={d.motivo} cambiar={(v) => setD({ ...d, motivo: v })} max={1000} filas={3} />
        <AreaTexto etiqueta="Notas (opcional): qué se aprendió" valor={d.notas} cambiar={(v) => setD({ ...d, notas: v })} max={1000} filas={2} />
      </div>
      <MensajeError texto={error} />
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando} disabled={d.producto.trim().length < 2}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}
