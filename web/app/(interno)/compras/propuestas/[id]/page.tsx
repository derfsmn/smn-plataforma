"use client";
// Detalle de una propuesta para Compras: lo capturado, revisiones automáticas, historia y cambio de estado.

import { useParams } from "next/navigation";
import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, Info, PenLine, Search, Undo2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { ResumenPropuesta } from "@/componentes/propuesta-resumen";
import { TarjetaEvaluacion } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { estiloEstado, RUTA, type Catalogos, type Estado, type Propuesta } from "@/lib/propuestas";

// Desde cada estado, qué puede hacer Compras (igual que TRANSICIONES en el servidor)
const ACCIONES: Record<string, Estado[]> = {
  recibida: ["en_revision", "lista", "devuelta", "rechazada"],
  en_revision: ["lista", "devuelta", "rechazada"],
  lista: ["en_revision", "devuelta", "rechazada"],
  rechazada: ["en_revision"],
  devuelta: ["en_revision"],
};
const BOTON: Partial<Record<Estado, { texto: string; icono: typeof Search; variante: "primario" | "secundario" | "fantasma" }>> = {
  en_revision: { texto: "Pasar a revisión", icono: Search, variante: "secundario" },
  lista: { texto: "Lista para evaluar", icono: CheckCircle2, variante: "primario" },
  devuelta: { texto: "Regresar al proveedor", icono: Undo2, variante: "secundario" },
  rechazada: { texto: "Rechazar", icono: XCircle, variante: "fantasma" },
};

export default function DetallePropuesta() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const revisa = puede("compras.propuestas.revisar");
  const [p, setP] = useState<Propuesta | null>(null);
  const [cat, setCat] = useState<Catalogos | null>(null);
  const [pide, setPide] = useState<Estado | null>(null);
  const [comentario, setComentario] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [recarga, setRecarga] = useState(0);

  useEffect(() => {
    Promise.all([api<Propuesta>(`${RUTA}/${id}`), api<Catalogos>(`${RUTA}/catalogos`)])
      .then(([prop, c]) => {
        setP(prop);
        setCat(c);
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);

  if (!p || !cat) return <Esqueleto className="h-96" />;

  const mover = async (estado: Estado, texto?: string) => {
    setOcupado(true);
    try {
      setP(await api<Propuesta>(`${RUTA}/${id}/estado`, { cuerpo: { estado, comentario: texto || null } }));
      avisar(estado === "devuelta" ? "Se le avisó al proveedor para que la corrija" : `Quedó como «${cat.estados.find((e) => e.valor === estado)?.texto}»`);
      setPide(null);
      setComentario("");
      if (estado === "lista") setRecarga((n) => n + 1);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };

  const departamento = async (valor: string) => {
    try {
      setP(await api<Propuesta>(`${RUTA}/${id}/departamento`, { metodo: "PATCH", cuerpo: { departamento: valor } }));
      avisar("Departamento actualizado");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const departamentos = [...new Set([...(p.departamento ? [p.departamento] : []), ...cat.departamentos])];

  return (
    <>
      <Entrada className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-naranja-tinta">{p.folio} · {p.empresa}</p>
          <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{p.producto}</h1>
          <p className="mt-1 text-sm text-smn-gris-500">
            {p.capturada_por_compras ? "Capturó en Compras" : "Envió"} {p.creada_por}
            {p.enviada_en && ` el ${fechaLocal(p.enviada_en)}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Insignia className={estiloEstado[p.estado]}>{p.estado_texto}</Insignia>
          {p.editable && (
            <Link href={`/compras/propuestas/captura/${p.id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-smn-gris-100 px-3 py-1.5 text-sm font-medium hover:border-smn-gris-300">
              <PenLine className="h-4 w-4" /> Corregir captura
            </Link>
          )}
        </div>
      </Entrada>

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="order-2 lg:order-1">
          <ResumenPropuesta p={p} cat={cat} />
        </div>

        <aside className="order-1 space-y-4 lg:order-2">
          {revisa && (ACCIONES[p.estado] ?? []).length > 0 && (
            <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
              <h2 className="mb-3 font-semibold">Decidir</h2>
              <div className="flex flex-col gap-2">
                {ACCIONES[p.estado].map((e) => {
                  const b = BOTON[e]!;
                  const Icono = b.icono;
                  return (
                    <Boton key={e} variante={b.variante} cargando={ocupado && pide === null} className="justify-start"
                      onClick={() => (e === "devuelta" || e === "rechazada" ? setPide(e) : mover(e))}>
                      <Icono className="h-4 w-4" /> {e === "devuelta" && p.capturada_por_compras ? "Regresar para corregir" : b.texto}
                    </Boton>
                  );
                })}
              </div>
              <p className="mt-3 text-[13px] text-smn-gris-500">
                {p.capturada_por_compras
                  ? "«Lista para evaluar» la manda al radar de productos. Como la capturó Compras, regresarla la deja para corregir aquí mismo y no se avisa a nadie fuera."
                  : "«Lista para evaluar» la manda al radar de productos. Regresar o rechazar le avisa al proveedor por correo."}
              </p>
            </section>
          )}

          {puede("compras.productos.ver") && <TarjetaEvaluacion propuestaId={p.id} recarga={recarga} />}

          <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h2 className="mb-3 font-semibold">Revisiones automáticas</h2>
            {p.revisiones.length === 0 ? (
              <p className="text-sm text-smn-gris-500">Sin observaciones.</p>
            ) : (
              <ul className="space-y-2">
                {p.revisiones.map((r, i) => (
                  <li key={i} className={`flex gap-2 rounded-xl p-2.5 text-sm ${r.nivel === "alerta" ? "bg-aviso-fondo text-aviso-texto" : "bg-smn-gris-50"}`}>
                    {r.nivel === "alerta" ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> : <Info className="mt-0.5 h-4 w-4 shrink-0 text-smn-gris-500" />}
                    {r.texto}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-[13px] text-smn-gris-500">Se calculan al enviar. Son avisos: la decisión es de Compras.</p>
          </section>

          <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h2 className="mb-3 font-semibold">Departamento</h2>
            {revisa ? (
              <select value={p.departamento ?? ""} onChange={(e) => e.target.value && departamento(e.target.value)}
                className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-sm outline-none focus:border-smn-naranja">
                {!p.departamento && <option value="">Sin departamento</option>}
                {departamentos.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            ) : (
              <p className="text-sm">{p.departamento ?? "Sin departamento"}</p>
            )}
            <p className="mt-2 text-[13px] text-smn-gris-500">El proveedor propuso «{p.respuestas.general.departamento ?? "—"}».</p>
          </section>

          <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h2 className="mb-3 font-semibold">Historia</h2>
            <ol className="space-y-3 border-l-2 border-smn-gris-100 pl-4">
              {[...p.eventos].reverse().map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute top-1.5 -left-[1.4rem] h-2.5 w-2.5 rounded-full bg-smn-naranja" />
                  <p className="text-sm font-semibold">{cat.estados.find((x) => x.valor === e.estado_despues)?.texto}</p>
                  <p className="text-[13px] text-smn-gris-500">{e.usuario} · {fechaLocal(e.ocurrido_en)}</p>
                  {e.comentario && <p className="mt-0.5 text-sm">{e.comentario}</p>}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>

      <AnimatePresence>
        {pide && (
          <Modal titulo={pide === "devuelta" ? (p.capturada_por_compras ? "Regresar para corregir" : "Regresar al proveedor") : "Rechazar la propuesta"} cerrar={() => setPide(null)}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                mover(pide, comentario);
              }}
            >
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">
                  {pide === "devuelta" ? "¿Qué tiene que corregir?" : "Motivo"} <span className="text-naranja-tinta">*</span>
                </span>
                <textarea value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={1000} rows={4} required autoFocus
                  className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20" />
              </label>
              <p className="mt-1 text-[13px] text-smn-gris-500">El proveedor lo lee tal cual en su correo y en el portal.</p>
              <div className="mt-5 flex justify-end gap-2">
                <Boton type="button" variante="fantasma" onClick={() => setPide(null)}>Cancelar</Boton>
                <Boton type="submit" cargando={ocupado} disabled={!comentario.trim()}>{pide === "devuelta" ? "Regresar" : "Rechazar"}</Boton>
              </div>
            </form>
          </Modal>
        )}
      </AnimatePresence>
    </>
  );
}
