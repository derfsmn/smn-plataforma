"use client";
// Comité de producto nuevo: las reuniones (cada una abre un ciclo), las peticiones de los asistentes por atender y los
// productos aceptados con su revisión de inventario y regulación.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { CalendarPlus, CheckCircle2, ChevronRight, MessageSquare } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { InsigniaColor } from "@/componentes/semaforo-producto";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import {
  fechaReunion, RESULTADO_REVISION, RUTA, type Aceptado, type Peticion, type Reunion, type ReunionBreve,
} from "@/lib/comite";
import { Atender } from "./piezas";

type Vista = "reuniones" | "peticiones" | "aceptados";
const VISTAS: { valor: Vista; texto: string }[] = [
  { valor: "reuniones", texto: "Reuniones" },
  { valor: "peticiones", texto: "Peticiones" },
  { valor: "aceptados", texto: "Aceptados" },
];

const ESTILO_ESTADO: Record<string, string> = {
  abierta: "bg-smn-naranja/15 text-tinta",
  prefiltro: "bg-smn-naranja/15 text-tinta",
  comite: "bg-tinta text-superficie",
  cerrada: "bg-smn-gris-100 text-smn-gris-700",
};

export default function Comite() {
  const [vista, setVista] = useState<Vista>("reuniones");

  useEffect(() => {
    const v = new URLSearchParams(window.location.search).get("vista");
    if (v === "peticiones" || v === "aceptados" || v === "revisiones") setVista(v === "revisiones" ? "aceptados" : v);
  }, []);

  const cambiar = (v: Vista) => {
    setVista(v);
    window.history.replaceState(null, "", v === "reuniones" ? "/compras/propuestas/comite" : `/compras/propuestas/comite?vista=${v}`);
  };

  return (
    <>
      <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Secciones del comité">
        {VISTAS.map((v) => (
          <button
            key={v.valor}
            role="tab"
            aria-selected={vista === v.valor}
            onClick={() => cambiar(v.valor)}
            className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition-colors ${vista === v.valor ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700 hover:text-tinta"}`}
          >
            {v.texto}
          </button>
        ))}
      </div>
      {vista === "reuniones" && <Reuniones />}
      {vista === "peticiones" && <Peticiones />}
      {vista === "aceptados" && <Aceptados />}
    </>
  );
}

function Reuniones() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [lista, setLista] = useState<ReunionBreve[] | null>(null);
  const [abriendo, setAbriendo] = useState(false);

  useEffect(() => {
    api<ReunionBreve[]>(`${RUTA}/reuniones`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  const sinCerrar = lista?.find((r) => r.estado !== "cerrada");

  return (
    <>
      <Entrada className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-smn-gris-500">
          Cada reunión abre un ciclo: el equipo de producto sube los productos, el semáforo los evalúa, Compras hace el pre-filtro y al comité llega solo lo que pasó.
        </p>
        {puede("compras.comite.prefiltrar") && !sinCerrar && lista && (
          <Boton onClick={() => setAbriendo(true)}>
            <CalendarPlus className="h-4 w-4" /> Nueva reunión
          </Boton>
        )}
      </Entrada>

      {lista === null ? (
        <div className="space-y-2">
          <Esqueleto className="h-24" />
          <Esqueleto className="h-24" />
        </div>
      ) : lista.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">
          Todavía no hay reuniones. {puede("compras.comite.prefiltrar") ? "Registra la fecha de la siguiente para abrir el ciclo." : "Compras abre la primera."}
        </p>
      ) : (
        <ul className="space-y-2">
          {lista.map((r, i) => (
            <motion.li key={r.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
              <Link
                href={`/compras/propuestas/comite/${r.id}`}
                className={`group flex items-center gap-4 rounded-2xl border bg-superficie p-4 transition hover:border-smn-naranja ${r.estado !== "cerrada" ? "border-smn-naranja/60" : "border-smn-gris-100"}`}
              >
                <div className="min-w-0 flex-1">
                  <p className="font-semibold first-letter:uppercase">{fechaReunion(r.fecha)}</p>
                  <p className="text-sm text-smn-gris-500">
                    {r.embudo.subidos} subidos · {r.embudo.evaluados} evaluados · {r.embudo.pasan} al comité
                    {r.estado === "cerrada" && ` · ${r.embudo.aceptados} aceptados`}
                    {r.embudo.en_espera > 0 && ` · ${r.embudo.en_espera} en espera`}
                  </p>
                  {r.peticiones_abiertas > 0 && (
                    <p className="mt-0.5 flex items-center gap-1 text-[13px] text-smn-gris-700">
                      <MessageSquare className="h-3.5 w-3.5" /> {r.peticiones_abiertas} {r.peticiones_abiertas === 1 ? "petición sin atender" : "peticiones sin atender"}
                    </p>
                  )}
                </div>
                <Insignia className={ESTILO_ESTADO[r.estado]}>{r.estado_texto}</Insignia>
                <ChevronRight className="h-5 w-5 shrink-0 text-smn-gris-500 transition group-hover:translate-x-0.5 group-hover:text-smn-naranja" />
              </Link>
            </motion.li>
          ))}
        </ul>
      )}
      <AnimatePresence>{abriendo && <NuevaReunion cerrar={() => setAbriendo(false)} />}</AnimatePresence>
    </>
  );
}

function NuevaReunion({ cerrar }: { cerrar: () => void }) {
  const router = useRouter();
  const avisar = useAvisos();
  const [fecha, setFecha] = useState("");
  const [notas, setNotas] = useState("");
  const [guardando, setGuardando] = useState(false);

  const abrir = async (e: React.FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    try {
      const r = await api<Reunion>(`${RUTA}/reuniones`, { cuerpo: { fecha, notas: notas.trim() || null } });
      const llevados = r.productos.filter((p) => p.origen === "espera").length;
      avisar(llevados ? `Reunión abierta; entraron ${llevados} producto(s) que quedaron en espera` : "Reunión abierta");
      router.push(`/compras/propuestas/comite/${r.id}`);
    } catch (err) {
      avisar(mensajeDe(err), "info");
      setGuardando(false);
    }
  };

  return (
    <Modal titulo="Nueva reunión del comité" cerrar={cerrar}>
      <form onSubmit={abrir} className="space-y-4">
        <p className="text-sm text-smn-gris-700">Al registrar la fecha se abre el ciclo. Lo que quedó «En espera» en la reunión anterior entra solo.</p>
        <Campo etiqueta="Fecha de la reunión" type="date" required value={fecha} onChange={(e) => setFecha(e.target.value)} />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-smn-gris-700">Notas (opcional)</span>
          <textarea
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            rows={3}
            maxLength={2000}
            className="w-full rounded-lg border border-smn-gris-100 bg-superficie px-3.5 py-2.5 text-[15px] outline-none hover:border-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/15"
          />
        </label>
        <div className="flex justify-end gap-2">
          <Boton type="button" variante="fantasma" onClick={cerrar}>Cancelar</Boton>
          <Boton type="submit" cargando={guardando} disabled={!fecha}>Abrir reunión</Boton>
        </div>
      </form>
    </Modal>
  );
}

function Peticiones() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [lista, setLista] = useState<Peticion[] | null>(null);
  const [todas, setTodas] = useState(false);
  const [atendiendo, setAtendiendo] = useState<Peticion | null>(null);

  const cargar = useCallback(() => {
    api<Peticion[]>(`${RUTA}/peticiones${todas ? "" : "?estado=abierta"}`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [todas, avisar]);
  useEffect(cargar, [cargar]);
  const atender = puede("compras.comite.prefiltrar") || puede("compras.comite.decidir");

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-smn-gris-500">Lo que pidieron los asistentes en las reuniones, con quién lo pidió y su puesto, para verificar que se atienda.</p>
        <label className="flex items-center gap-2 text-sm text-smn-gris-700">
          <input type="checkbox" checked={todas} onChange={(e) => setTodas(e.target.checked)} className="h-4 w-4 accent-[var(--resalte)]" />
          Ver también las atendidas
        </label>
      </div>
      {lista === null ? (
        <Esqueleto className="h-24" />
      ) : lista.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">{todas ? "No hay peticiones registradas." : "No hay peticiones sin atender."}</p>
      ) : (
        <ul className="space-y-2">
          {lista.map((p) => (
            <li key={p.id} className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{p.texto}</p>
                  <p className="text-sm text-smn-gris-500">
                    {p.asistente ? `${p.asistente}${p.puesto ? ` (${p.puesto})` : ""}` : "Sin asistente"}
                    {p.producto && ` · ${p.producto}`} ·{" "}
                    <Link href={`/compras/propuestas/comite/${p.reunion_id}`} className="underline-offset-2 hover:underline">
                      reunión del {fechaReunion(p.fecha_reunion, { day: "numeric", month: "short", year: "numeric" })}
                    </Link>
                  </p>
                  {p.estado === "atendida" && (
                    <p className="mt-1 text-sm text-smn-gris-700">
                      <CheckCircle2 className="mr-1 inline h-4 w-4 text-green-600" />
                      {p.respuesta || "Atendida"} · {p.atendida_por}, {p.atendida_en && fechaLocal(p.atendida_en, { dateStyle: "medium" })}
                    </p>
                  )}
                </div>
                {atender && p.estado === "abierta" && (
                  <Boton variante="secundario" onClick={() => setAtendiendo(p)}>Marcar atendida</Boton>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <AnimatePresence>
        {atendiendo && <Atender p={atendiendo} cerrar={() => setAtendiendo(null)} listo={() => { setAtendiendo(null); cargar(); }} />}
      </AnimatePresence>
    </>
  );
}

function Aceptados() {
  const avisar = useAvisos();
  const [lista, setLista] = useState<Aceptado[] | null>(null);
  useEffect(() => {
    api<Aceptado[]>(`${RUTA}/aceptados`).then(setLista).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  return (
    <>
      <p className="mb-4 max-w-2xl text-smn-gris-500">
        Los productos que aceptó el comité. Algunos pasan antes por una revisión de espacio en inventario y después de regulación; luego siguen con el proceso de alta, que va aparte.
      </p>
      {lista === null ? (
        <Esqueleto className="h-24" />
      ) : lista.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 p-10 text-center text-smn-gris-500">Todavía no hay productos aceptados.</p>
      ) : (
        <ul className="space-y-2">
          {lista.map(({ producto: i, reunion_id, fecha_reunion }) => (
            <li key={i.id}>
              <Link href={`/compras/propuestas/comite/${reunion_id}#producto-${i.id}`} className="flex flex-wrap items-center gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-4 hover:border-smn-naranja">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">{i.nombre}</p>
                  <p className="truncate text-sm text-smn-gris-500">
                    {i.proveedor ?? "Sin proveedor"} · reunión del {fechaReunion(fecha_reunion, { day: "numeric", month: "short", year: "numeric" })}
                  </p>
                </div>
                {i.revisiones.map((r) => (
                  <Insignia key={r.tipo} className={RESULTADO_REVISION[r.resultado].clase}>
                    {r.nombre}: {RESULTADO_REVISION[r.resultado].texto.toLowerCase()}
                  </Insignia>
                ))}
                <InsigniaColor color={i.decision_color} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
