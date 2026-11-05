"use client";
// Base de conocimiento · Políticas: lo que Compras aplica hoy para aceptar productos y proveedores, escrito aquí.

import { AnimatePresence } from "motion/react";
import { ChevronDown, FileText, Pencil, Plus, ScrollText, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { CLASE_ESTADO, TEMAS, TEXTO_ESTADO, TEXTO_TEMA, type Politica } from "@/lib/conocimiento";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";
import { EDITAR, Pie, Vacio, useDepartamentos } from "../piezas";
import { VentanaPolitica, aFormaPolitica, type FormaPolitica } from "../politica";

const NUEVA: FormaPolitica = { tema: "alta_productos", titulo: "", contenido: "", departamento: "", estado: "borrador" };

export default function Politicas() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const editar = puede(EDITAR);
  const departamentos = useDepartamentos();
  const [lista, setLista] = useState<Politica[] | null>(null);
  const [abierta, setAbierta] = useState<{ id?: number; datos: FormaPolitica } | null>(null);
  const [leyendo, setLeyendo] = useState<number | null>(null);
  const [borrar, setBorrar] = useState<Politica | null>(null);

  const cargar = useCallback(() => {
    api<Politica[]>("/api/compras/conocimiento/politicas")
      .then((l) => setLista(l.filter((p) => p.tema !== "proceso")))
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const quitar = async () => {
    if (!borrar) return;
    try {
      await api(`/api/compras/conocimiento/politicas/${borrar.id}`, { metodo: "DELETE" });
      avisar("Política quitada", "exito");
      setBorrar(null);
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!lista) return <Esqueleto className="h-48" />;
  const grupos = TEMAS.map((t) => ({ ...t, politicas: lista.filter((p) => p.tema === t.valor) })).filter((g) => g.politicas.length);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-smn-gris-500">
          Lo que Compras aplica hoy para aceptar o rechazar un producto o un proveedor: alta de productos, requisitos a proveedores, regulatorio y etiquetado, precio y margen, y cómo aprueba el comité.
          Solo las vigentes cuentan para el semáforo.
        </p>
        {editar && (
          <Boton onClick={() => setAbierta({ datos: NUEVA })}>
            <Plus className="h-4 w-4" /> Escribir política
          </Boton>
        )}
      </div>
      {!grupos.length ? (
        <Vacio icono={<ScrollText className="h-10 w-10" />} titulo="Sin políticas escritas" texto={editar ? "Empieza por la de alta de productos nuevos; puedes dejarla en borrador mientras se revisa." : "Compras todavía no las ha escrito."} />
      ) : (
        <div className="space-y-6">
          {grupos.map((g) => (
            <section key={g.valor}>
              <h2 className="mb-2 text-sm font-medium text-smn-gris-500">{g.texto}</h2>
              <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
                {g.politicas.map((p) => (
                  <li key={p.id} className={p.estado === "archivada" ? "opacity-60" : ""}>
                    <div className="flex items-start gap-3 p-4">
                      <FileText className="mt-0.5 h-5 w-5 shrink-0 text-smn-naranja" />
                      <button onClick={() => setLeyendo(leyendo === p.id ? null : p.id)} className="min-w-0 flex-1 text-left" aria-expanded={leyendo === p.id}>
                        <p className="font-semibold">
                          {p.titulo} <Insignia className={`ml-1 ${CLASE_ESTADO[p.estado]}`}>{TEXTO_ESTADO[p.estado]}</Insignia>
                          {p.departamento && <Insignia className="ml-1 bg-smn-gris-50 text-smn-gris-700">{p.departamento}</Insignia>}
                        </p>
                        <p className="mt-0.5 flex items-center gap-1 text-[13px] text-smn-gris-500">
                          Versión {p.version} · <Pie por={p.actualizado_por} en={p.actualizado_en} />
                          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${leyendo === p.id ? "rotate-180" : ""}`} />
                        </p>
                      </button>
                      {editar && (
                        <>
                          <button onClick={() => setAbierta({ id: p.id, datos: aFormaPolitica(p) })} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${p.titulo}`}>
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button onClick={() => setBorrar(p)} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Quitar ${p.titulo}`}>
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                    {leyendo === p.id && (
                      <div className="border-t border-smn-gris-100 px-12 py-4 text-sm whitespace-pre-line text-smn-gris-700">{p.contenido || "Sin texto todavía."}</div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
      <AnimatePresence>
        {abierta && <VentanaPolitica id={abierta.id} inicial={abierta.datos} departamentos={departamentos} cerrar={() => setAbierta(null)} alGuardar={cargar} />}
        {borrar && (
          <Modal titulo="Quitar política" cerrar={() => setBorrar(null)}>
            <p>
              Se quitará <b>{borrar.titulo}</b> ({TEXTO_TEMA[borrar.tema]}). Si solo ya no se aplica, mejor márcala como archivada.
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
