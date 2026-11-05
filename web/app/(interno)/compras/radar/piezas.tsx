"use client";
// Piezas compartidas del radar: tarjeta de hallazgo, nota y ventana para decidir.

import { AnimatePresence, motion } from "motion/react";
import { ExternalLink, Eye, Lightbulb, XCircle } from "lucide-react";
import { useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import {
  CLASE_ESTADO,
  CLASE_NIVEL,
  TEXTO_ACCION,
  TEXTO_ESTADO,
  TEXTO_TIPO,
  fechaCorta,
  fechaHora,
  type Accion,
  type AccionRadar,
  type ArticuloRadar,
  type EstadoSenal,
  type Nivel,
  type Senal,
} from "@/lib/radar";
import { Modal } from "@/componentes/modal";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Insignia } from "@/componentes/ui";

export function Etiquetas({ nivel, tipo, estado, area, paises }: { nivel: Nivel; tipo: "emergente" | "tendencia"; estado?: EstadoSenal; area?: string | null; paises?: string | null }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Insignia className={CLASE_NIVEL[nivel]}>{nivel}</Insignia>
      <Insignia className="border border-smn-gris-300 text-smn-gris-700">{TEXTO_TIPO[tipo]}</Insignia>
      {area && <Insignia className="bg-smn-gris-50 text-smn-gris-700">{area}</Insignia>}
      {paises && <Insignia className="bg-smn-gris-50 text-smn-gris-700">{paises}</Insignia>}
      {estado && <Insignia className={CLASE_ESTADO[estado]}>{TEXTO_ESTADO[estado]}</Insignia>}
    </div>
  );
}

export function Nota({ a, detalle = false }: { a: ArticuloRadar; detalle?: boolean }) {
  return (
    <li className="flex gap-2 py-2 text-sm">
      <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-smn-naranja" aria-hidden />
      <div className="min-w-0">
        <a href={a.url} target="_blank" rel="noopener noreferrer" className="font-semibold break-words hover:underline">
          {a.titulo}
        </a>
        <p className="text-[13px] text-smn-gris-500">
          {a.fuente ?? a.sitio} · {fechaCorta(a.publicado_en)}
          {a.origen === "busqueda" && " · búsqueda abierta"}
        </p>
        {detalle && a.por_que && <p className="mt-1 text-smn-gris-700">{a.por_que}</p>}
      </div>
    </li>
  );
}

export function UltimaAccion({ a }: { a: AccionRadar | null }) {
  if (!a) return null;
  return (
    <p className="text-[13px] text-smn-gris-500">
      {TEXTO_ACCION[a.accion]} · {a.usuario} · {fechaHora(a.ocurrido_en)}
      {a.motivo && <span className="block text-smn-gris-700">“{a.motivo}”</span>}
    </p>
  );
}

const ICONO_ACCION = { iniciativa: Lightbulb, vigilar: Eye, descartar: XCircle };

export function BotonesDecision({ senalId, titulo, alDecidir, compacto }: { senalId: number; titulo: string; alDecidir: (s: Senal) => void; compacto?: boolean }) {
  const [accion, setAccion] = useState<Accion | null>(null);
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {(["iniciativa", "vigilar", "descartar"] as Accion[]).map((a) => {
          const Icono = ICONO_ACCION[a];
          return (
            <Boton key={a} variante={a === "iniciativa" ? "primario" : a === "vigilar" ? "secundario" : "fantasma"} onClick={() => setAccion(a)} className={compacto ? "px-3 py-2" : ""}>
              <Icono className="h-4 w-4" /> {TEXTO_ACCION[a]}
            </Boton>
          );
        })}
      </div>
      <AnimatePresence>{accion && <VentanaDecision senalId={senalId} titulo={titulo} accion={accion} cerrar={() => setAccion(null)} alDecidir={alDecidir} />}</AnimatePresence>
    </>
  );
}

const EXPLICA: Record<Accion, string> = {
  iniciativa: "Queda registrado que Compras quiere evaluar esto como producto nuevo. Cuando exista el semáforo de producto nuevo, la idea pasará ahí.",
  vigilar: "La señal sigue en el radar y se marca para revisarla cuando vuelva a aparecer.",
  descartar: "La señal deja de proponerse. El motivo ayuda a que el radar y el equipo entiendan por qué no.",
};

export function VentanaDecision({ senalId, titulo, accion, cerrar, alDecidir }: { senalId: number; titulo: string; accion: Accion; cerrar: () => void; alDecidir: (s: Senal) => void }) {
  const avisar = useAvisos();
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const s = await api<Senal>(`/api/compras/radar/senales/${senalId}/accion`, { metodo: "POST", cuerpo: { accion, motivo: motivo || null } });
      avisar(`${TEXTO_ACCION[accion]}: registrado`, "exito");
      alDecidir(s);
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={TEXTO_ACCION[accion]} cerrar={cerrar}>
      <p className="font-semibold">{titulo}</p>
      <p className="mt-2 text-sm text-smn-gris-500">{EXPLICA[accion]}</p>
      <label className="mt-4 block">
        <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">
          Motivo o siguiente paso {accion === "descartar" ? "(obligatorio)" : "(opcional)"}
        </span>
        <textarea
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          maxLength={600}
          rows={3}
          autoFocus
          className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
        />
      </label>
      {error && (
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} role="alert" className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-400">
          {error}
        </motion.p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando} disabled={accion === "descartar" && !motivo.trim()}>
          Confirmar
        </Boton>
      </div>
    </Modal>
  );
}

export function Vacio({ titulo, texto, icono }: { titulo: string; texto: React.ReactNode; icono: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-6 py-12 text-center">
      <span className="text-naranja-tinta">{icono}</span>
      <p className="mt-3 text-lg font-semibold">{titulo}</p>
      <div className="mt-1 max-w-md text-sm text-smn-gris-500">{texto}</div>
    </div>
  );
}
