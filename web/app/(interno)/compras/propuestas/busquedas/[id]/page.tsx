"use client";
// Una búsqueda de proveedor: por qué vale la pena, el semáforo, a quién se ha contactado y cómo se cierra.

import { Imagen } from "@/componentes/imagen";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { ArrowUpRight, CheckCircle2, Hand, PackageSearch, RotateCcw, Send, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { ElegirIntelisis, type Intelisis } from "@/componentes/proveedor-intelisis";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { abierta, ESTILO_ESTADO, PUERTA, RESULTADOS, RUTA, type BusquedaDetalle, type Resultado } from "@/lib/busquedas";
import { urlFoto } from "@/lib/productos";

const fecha = (f: string) => fechaLocal(f, { dateStyle: "medium" });
const fechaDia = (f: string) => new Date(`${f}T12:00:00`).toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long" });
const AREA = "w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 py-2.5 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15";

export default function Busqueda() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [b, setB] = useState<BusquedaDetalle | null>(null);
  const [ventana, setVentana] = useState<"encontrado" | "cerrar" | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(() => api<BusquedaDetalle>(`${RUTA}/${id}`).then(setB).catch((e) => avisar(mensajeDe(e), "info")), [id, avisar]);
  useEffect(() => {
    cargar();
  }, [cargar]);

  const accion = async (ruta: string, cuerpo?: unknown, exito?: string) => {
    setOcupado(true);
    try {
      setB(await api<BusquedaDetalle>(`${RUTA}/${id}/${ruta}`, { metodo: "POST", cuerpo: cuerpo ?? {} }));
      if (exito) avisar(exito);
      return true;
    } catch (e) {
      avisar(mensajeDe(e), "info");
      return false;
    } finally {
      setOcupado(false);
    }
  };

  const subirAlComite = async () => {
    if (!b?.reunion_abierta) return;
    setOcupado(true);
    try {
      await api(`/api/compras/comite/reuniones/${b.reunion_abierta.id}/productos`, { cuerpo: { idea_id: b.idea_id } });
      avisar("Se subió a la reunión del comité.");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };

  if (!b) return <Esqueleto className="h-96" />;
  const atiende = puede("compras.busquedas.atender");
  const s = b.semaforo;

  return (
    <>
      <Entrada className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Insignia className={ESTILO_ESTADO[b.estado]}>{b.estado_texto}</Insignia>
            {b.puertas.map((p) => (
              <Insignia key={p} className="bg-smn-gris-100 text-smn-gris-700">{PUERTA[p] ?? p}</Insignia>
            ))}
            <span className="text-sm text-smn-gris-500">
              {b.origen === "automatica" ? "Se abrió sola" : "La pidió Compras"} el {fecha(b.creada_en)}
              {b.color_inicial && ` · estaba en ${b.color_inicial}${b.puntaje_inicial !== null ? ` (${b.puntaje_inicial} de 100)` : ""}`}
            </span>
          </div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{b.nombre}</h2>
          <p className="mt-1 text-smn-gris-500">{[b.marca, b.departamento, b.contenido, b.forma].filter(Boolean).join(" · ") || "Sin marca ni departamento"}</p>
          <p className="mt-1 text-sm text-smn-gris-700">Responsable: <b className="text-tinta">{b.responsable?.nombre ?? "nadie todavía"}</b></p>
        </div>
        {atiende && (
          <div className="flex flex-wrap gap-2">
            {b.estado === "sin_tomar" && (
              <Boton onClick={() => accion("tomar", undefined, "La búsqueda es tuya.")} cargando={ocupado}>
                <Hand className="h-4 w-4" /> Tomarla
              </Boton>
            )}
            {abierta(b.estado) && (
              <>
                <Boton variante={b.estado === "sin_tomar" ? "secundario" : "primario"} onClick={() => setVentana("encontrado")}>
                  <CheckCircle2 className="h-4 w-4" /> Encontré proveedor
                </Boton>
                <Boton variante="secundario" onClick={() => setVentana("cerrar")}>
                  <XCircle className="h-4 w-4" /> Cerrar sin proveedor
                </Boton>
              </>
            )}
            {(b.estado === "sin_proveedor" || b.estado === "cancelada") && (
              <Boton variante="secundario" onClick={() => accion("reabrir", undefined, "Se reabrió la búsqueda.")} cargando={ocupado}>
                <RotateCcw className="h-4 w-4" /> Reabrir
              </Boton>
            )}
          </div>
        )}
      </Entrada>

      {b.estado === "encontrado" && (
        <Entrada className="mb-6 rounded-2xl border border-green-600/30 bg-green-600/5 p-5">
          <p className="font-semibold">Proveedor encontrado: {b.proveedor}</p>
          <p className="mt-1 text-sm text-smn-gris-700">
            {b.costo ? `Costo ${pesos(b.costo)} sin IVA. ` : "Sin costo todavía. "}
            {b.motivo_cierre && `${b.motivo_cierre.replace(/\.$/, "")}. `}Se volvió a evaluar con este proveedor.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {b.en_comite ? (
              <Link href={`/compras/propuestas/comite/${b.en_comite.id}`} className="inline-flex items-center gap-1 text-[15px] font-medium underline underline-offset-2">
                En el comité del {fechaDia(b.en_comite.fecha)} <ArrowUpRight className="h-4 w-4" />
              </Link>
            ) : b.reunion_abierta && puede("compras.comite.subir") ? (
              <Boton onClick={subirAlComite} cargando={ocupado}>
                <Send className="h-4 w-4" /> Subir al comité del {fechaDia(b.reunion_abierta.fecha)}
              </Boton>
            ) : (
              <p className="text-sm text-smn-gris-700">
                {b.reunion_abierta ? "Quien sube productos al comité ya recibió el aviso." : "Cuando Compras abra la siguiente reunión del comité, se sube desde ahí."}
              </p>
            )}
          </div>
        </Entrada>
      )}
      {(b.estado === "sin_proveedor" || b.estado === "cancelada") && b.motivo_cierre && (
        <Entrada className="mb-6 rounded-2xl border border-smn-gris-100 bg-smn-gris-50 p-5">
          <p className="font-semibold">{b.estado === "sin_proveedor" ? "Se cerró sin proveedor" : "Se canceló"}</p>
          <p className="mt-1 text-sm text-smn-gris-700">{b.motivo_cierre}</p>
        </Entrada>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <div className="space-y-6">
          <Entrada retraso={0.05} className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <h3 className="font-semibold">Por qué vale la pena</h3>
            {b.por_que ? <p className="mt-2 text-[15px] text-smn-gris-700">{b.por_que}</p> : b.nota ? (
              <p className="mt-2 text-[15px] text-smn-gris-700">{b.nota}</p>
            ) : (
              <p className="mt-2 text-[15px] text-smn-gris-700">{b.descripcion ?? "Compras la capturó como idea de producto."}</p>
            )}
            {b.evidencia.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-sm text-smn-gris-700">
                {b.evidencia.map((x, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="shrink-0 font-medium text-tinta">{x.fuente}:</span>
                    <span>{x.texto}</span>
                  </li>
                ))}
              </ul>
            )}
            {(b.precio_visto || b.donde_se_vio) && (
              <p className="mt-3 text-sm text-smn-gris-500">
                {b.precio_visto && `Se vio en ${pesos(b.precio_visto)}`}
                {b.donde_se_vio && ` (${b.donde_se_vio})`}
              </p>
            )}
            {(b.imagen || b.fotos.length > 0) && (
              <div className="mt-4 flex gap-2 overflow-x-auto">
                {b.fotos.map((f) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <Imagen key={f} src={urlFoto(b.idea_id, f, 160)} alt="Foto del producto" loading="lazy" decoding="async" className="h-24 w-24 shrink-0 rounded-xl bg-smn-gris-50 object-contain" />
                ))}
                {b.imagen && b.fotos.length === 0 && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <Imagen src={b.imagen} alt="Foto del producto" referrerPolicy="no-referrer" className="h-24 w-24 shrink-0 rounded-xl bg-smn-gris-50 object-contain" />
                )}
              </div>
            )}
          </Entrada>

          <Entrada retraso={0.1} className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Semáforo</h3>
              {s && (
                <Link href={`/compras/productos/${s.evaluacion_id}`} className="inline-flex items-center gap-1 text-sm font-medium underline underline-offset-2">
                  Ver evaluación completa <ArrowUpRight className="h-4 w-4" />
                </Link>
              )}
            </div>
            {!s ? (
              <p className="mt-2 text-sm text-smn-gris-500">Todavía no tiene evaluación.</p>
            ) : s.estado === "en_curso" ? (
              <p className="mt-2 text-sm text-smn-gris-500">Evaluando…</p>
            ) : (
              <>
                <div className="mt-3 flex items-center gap-3">
                  <InsigniaColor color={s.color} />
                  {s.puntaje !== null && <span className="text-xl font-semibold tabular-nums">{s.puntaje}<span className="text-sm font-normal text-smn-gris-500"> de 100</span></span>}
                  {s.confianza && <span className="text-sm text-smn-gris-500">confianza {s.confianza}</span>}
                </div>
                {s.explicacion && (
                  <p className="mt-3 line-clamp-6 text-sm whitespace-pre-line text-smn-gris-700">{s.explicacion.replaceAll("**", "")}</p>
                )}
              </>
            )}
          </Entrada>
        </div>

        <Entrada retraso={0.1} className="rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h3 className="font-semibold">Registro</h3>
          {atiende && abierta(b.estado) && <NuevoContacto enviar={(c) => accion("avances", c, "Quedó registrado.")} ocupado={ocupado} />}
          <ol className="mt-4 space-y-3">
            {b.avances.map((a) => (
              <li key={a.id} className="border-l-2 border-smn-gris-100 pl-3">
                <p className="text-[13px] text-smn-gris-500">
                  {fechaLocal(a.creado_en)}{a.quien && ` · ${a.quien}`}
                </p>
                {a.proveedor && a.tipo === "contacto" && (
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 font-medium">
                    {a.proveedor}
                    {a.resultado_texto && <Insignia className={a.resultado === "no_surte" ? "bg-smn-gris-100 text-smn-gris-700" : "bg-smn-naranja/15 text-tinta"}>{a.resultado_texto}</Insignia>}
                  </p>
                )}
                <p className={`text-[15px] ${a.tipo === "estado" ? "text-smn-gris-700 italic" : ""}`}>{a.texto}</p>
              </li>
            ))}
          </ol>
        </Entrada>
      </div>

      <AnimatePresence>
        {ventana === "encontrado" && (
          <Encontrado cerrar={() => setVentana(null)} enviar={async (c) => (await accion("encontrado", c, "Listo: se vuelve a evaluar con ese proveedor.")) && setVentana(null)} ocupado={ocupado} />
        )}
        {ventana === "cerrar" && (
          <Cerrar cerrar={() => setVentana(null)} enviar={async (c) => (await accion("cerrar", c, "Se cerró la búsqueda.")) && setVentana(null)} ocupado={ocupado} />
        )}
      </AnimatePresence>
    </>
  );
}

function NuevoContacto({ enviar, ocupado }: { enviar: (c: { texto: string; proveedor: string | null; resultado: Resultado | null }) => Promise<boolean>; ocupado: boolean }) {
  const [proveedor, setProveedor] = useState("");
  const [resultado, setResultado] = useState<Resultado | "">("");
  const [texto, setTexto] = useState("");
  const listo = texto.trim().length >= 3 && (!resultado || proveedor.trim().length >= 2);

  return (
    <form
      className="mt-3 space-y-3 rounded-xl bg-smn-gris-50 p-4"
      onSubmit={async (ev) => {
        ev.preventDefault();
        if (await enviar({ texto, proveedor: proveedor.trim() || null, resultado: resultado || null })) {
          setProveedor("");
          setResultado("");
          setTexto("");
        }
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Proveedor que contactaste (opcional)" value={proveedor} onChange={(e) => setProveedor(e.target.value)} maxLength={200} />
        <Selector
          etiqueta="Qué dijo"
          valor={resultado}
          cambiar={(v) => setResultado(v as Resultado | "")}
          opciones={[{ valor: "", texto: proveedor.trim() ? "Elige…" : "Solo una nota" }, ...RESULTADOS]}
        />
      </div>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Qué pasó</span>
        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} maxLength={1000} className={AREA} placeholder="Ej. Le mandé la ficha; queda de cotizar el viernes." />
      </label>
      <div className="flex justify-end">
        <Boton type="submit" disabled={!listo} cargando={ocupado}>Registrar</Boton>
      </div>
    </form>
  );
}

function Encontrado({ cerrar, enviar, ocupado }: {
  cerrar: () => void;
  enviar: (c: { proveedor_codigo: string | null; proveedor_nuevo: string | null; costo: string | null; nota: string | null }) => void;
  ocupado: boolean;
}) {
  const [modo, setModo] = useState<"intelisis" | "nuevo">("intelisis");
  const [elegido, setElegido] = useState<Intelisis | null>(null);
  const [nuevo, setNuevo] = useState("");
  const [costo, setCosto] = useState("");
  const [nota, setNota] = useState("");
  const listo = modo === "intelisis" ? !!elegido : nuevo.trim().length >= 2;

  return (
    <Modal titulo="Encontré proveedor" cerrar={cerrar} ancho="max-w-lg">
      <p className="mb-4 text-sm text-smn-gris-700">El proveedor queda en la idea y se vuelve a evaluar con él (con rentabilidad si das el costo). Luego puede subir al comité.</p>
      <div className="mb-4 flex gap-1 rounded-xl bg-smn-gris-100 p-1" role="tablist">
        {(["intelisis", "nuevo"] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={modo === m} onClick={() => setModo(m)}
            className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium ${modo === m ? "bg-superficie shadow-sm" : "text-smn-gris-500"}`}>
            {m === "intelisis" ? "Ya está en Intelisis" : "Proveedor nuevo"}
          </button>
        ))}
      </div>
      {modo === "intelisis" ? (
        <ElegirIntelisis elegido={elegido} elegir={setElegido} altura="max-h-48" />
      ) : (
        <Campo etiqueta="Nombre del proveedor" value={nuevo} onChange={(e) => setNuevo(e.target.value)} maxLength={200} autoFocus />
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Costo sin IVA (opcional)" inputMode="decimal" value={costo} onChange={(e) => setCosto(e.target.value.replace(/[^\d.]/g, ""))} placeholder="0.00" />
      </div>
      <label className="mt-3 block">
        <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Nota (opcional)</span>
        <textarea value={nota} onChange={(e) => setNota(e.target.value)} rows={2} maxLength={1000} className={AREA} placeholder="Ej. Entrega en 10 días, pedido mínimo 50 piezas." />
      </label>
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>Cancelar</Boton>
        <Boton
          disabled={!listo}
          cargando={ocupado}
          onClick={() => enviar({
            proveedor_codigo: modo === "intelisis" ? elegido?.codigo ?? null : null,
            proveedor_nuevo: modo === "nuevo" ? nuevo.trim() : null,
            costo: costo ? costo : null,
            nota: nota.trim() || null,
          })}
        >
          <CheckCircle2 className="h-4 w-4" /> Guardar proveedor
        </Boton>
      </div>
    </Modal>
  );
}

function Cerrar({ cerrar, enviar, ocupado }: { cerrar: () => void; enviar: (c: { estado: "sin_proveedor" | "cancelada"; motivo: string }) => void; ocupado: boolean }) {
  const [estado, setEstado] = useState<"sin_proveedor" | "cancelada">("sin_proveedor");
  const [motivo, setMotivo] = useState("");
  return (
    <Modal titulo="Cerrar la búsqueda" cerrar={cerrar}>
      <Selector
        etiqueta="Cómo terminó"
        valor={estado}
        cambiar={(v) => setEstado(v as "sin_proveedor" | "cancelada")}
        opciones={[
          { valor: "sin_proveedor", texto: "Se buscó y no hay proveedor" },
          { valor: "cancelada", texto: "Ya no nos interesa" },
        ]}
      />
      <label className="mt-3 block">
        <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Motivo</span>
        <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} maxLength={1000} className={AREA} placeholder="Ej. Ningún distribuidor lo trae a México." />
      </label>
      <p className="mt-2 text-[13px] text-smn-gris-500">Se puede reabrir después si aparece un proveedor.</p>
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>Cancelar</Boton>
        <Boton disabled={motivo.trim().length < 10} cargando={ocupado} onClick={() => enviar({ estado, motivo })}>
          <PackageSearch className="h-4 w-4" /> Cerrar
        </Boton>
      </div>
    </Modal>
  );
}

