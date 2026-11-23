"use client";
// Expedientes de producto nuevo (folio VID-AAAA-NNNN): lista por etapa y alta con su equipo.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { FolderPlus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe } from "@/lib/api";
import { ESTADO_EXP, ETAPAS, P, RUTA, type FilaExpediente } from "@/lib/innovacion";
import { BarraResumen, ETIQUETA, MenuModulo, SinAcceso, TARJETA, Texto, Vacio } from "../comunes";

export default function Expedientes() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [filas, setFilas] = useState<FilaExpediente[] | null>(null);
  const [etapa, setEtapa] = useState("");
  const [solo, setSolo] = useState(false);
  const [alta, setAlta] = useState(false);
  const cargar = useCallback(() => api<FilaExpediente[]>(`${RUTA}/expedientes`).then(setFilas).catch((e) => avisar(mensajeDe(e), "info")), [avisar]);
  useEffect(() => {
    if (puede(P.expVer)) cargar();
  }, [puede, cargar]);

  if (!puede(P.expVer)) return <SinAcceso />;
  const visibles = (filas ?? []).filter((e) => (!etapa || e.etapa === etapa) && (!solo || e.soy_del_equipo));
  return (
    <>
      <Encabezado
        titulo="Expedientes"
        descripcion="Un folio por producto nuevo de Vidanat: ficha, fórmula, evidencia citada, reglas y la decisión del Filtro."
        accion={puede(P.expEditar) && <Boton onClick={() => setAlta(true)}><FolderPlus className="h-4 w-4" /> Nuevo expediente</Boton>}
      />
      <MenuModulo />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {["", "investigacion", "filtro", "desarrollo", "salida_comercial", "validacion"].map((e) => (
          <button key={e} onClick={() => setEtapa(e)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${etapa === e ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}`}>
            {e ? ETAPAS[e] : "Todas"}
          </button>
        ))}
        <label className="ml-auto inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={solo} onChange={(e) => setSolo(e.target.checked)} /> Solo donde soy del equipo</label>
      </div>
      {!filas ? (
        <Esqueleto className="h-48" />
      ) : visibles.length === 0 ? (
        <Vacio>No hay expedientes {etapa ? `en ${ETAPAS[etapa]}` : "todavía"}.</Vacio>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {visibles.map((e) => (
            <Link key={e.folio} href={`/innovacion/expedientes/${e.folio}`} className={`${TARJETA} block hover:border-smn-gris-300`}>
              <div className="flex items-start justify-between gap-3">
                <span>
                  <span className="block font-mono text-[13px] text-smn-gris-500">{e.folio}</span>
                  <span className="block text-[17px] font-semibold">{e.nombre}</span>
                </span>
                <Insignia className="bg-smn-gris-100 text-smn-gris-700">{ETAPAS[e.etapa] ?? e.etapa}{e.estado !== "activo" ? ` · ${ESTADO_EXP[e.estado]}` : ""}</Insignia>
              </div>
              <p className="mt-1 text-[13px] text-smn-gris-500">
                {e.categoria_comercial ? `${e.categoria_comercial} · ` : ""}Responsable {e.responsable ?? "—"} · {haceCuanto(e.actualizado_en)}
                {e.soy_del_equipo && <span className="ml-2 inline-flex items-center gap-1"><Users className="h-3 w-3" /> tu equipo</span>}
              </p>
              <div className="mt-3"><BarraResumen resumen={e.resumen} /></div>
            </Link>
          ))}
        </div>
      )}
      <AnimatePresence>{alta && <Alta cerrar={() => setAlta(false)} />}</AnimatePresence>
    </>
  );
}

function Alta({ cerrar }: { cerrar: () => void }) {
  const avisar = useAvisos();
  const router = useRouter();
  const { yo } = useSesion();
  const [d, setD] = useState({ nombre: "", descripcion: "", categoria_sanitaria: "", categoria_comercial: "", presentacion: "", jurisdiccion: "MX" });
  const [disponibles, setDisponibles] = useState<{ usuario_id: number; nombre: string; roles: string[] }[]>([]);
  const [equipo, setEquipo] = useState<number[]>([]);
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    api<typeof disponibles>(`${RUTA}/equipo-disponible`).then(setDisponibles).catch(() => {});
  }, []);
  const crear = async () => {
    if (d.nombre.trim().length < 3) return avisar("Ponle nombre al producto.", "info");
    setEnviando(true);
    try {
      const r = await api<{ folio: string }>(`${RUTA}/expedientes`, {
        cuerpo: { ...Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim() || null])), jurisdiccion: d.jurisdiccion || "MX", equipo },
      });
      router.push(`/innovacion/expedientes/${r.folio}`);
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setEnviando(false);
    }
  };
  const poner = (k: keyof typeof d) => (e: React.ChangeEvent<HTMLInputElement>) => setD((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Modal titulo="Nuevo expediente" cerrar={cerrar} ancho="max-w-lg">
      <div className="grid gap-3">
        <Campo etiqueta="Nombre del producto" value={d.nombre} onChange={poner("nombre")} placeholder="Magnesio para relajación" />
        <Texto etiqueta="Idea en dos o tres frases" valor={d.descripcion} cambiar={(v) => setD((x) => ({ ...x, descripcion: v }))} filas={3} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Categoría sanitaria" value={d.categoria_sanitaria} onChange={poner("categoria_sanitaria")} placeholder="suplemento" />
          <Campo etiqueta="Categoría comercial" value={d.categoria_comercial} onChange={poner("categoria_comercial")} placeholder="sueño" />
          <Campo etiqueta="Presentación" value={d.presentacion} onChange={poner("presentacion")} placeholder="capsula" />
          <Campo etiqueta="Jurisdicción" value={d.jurisdiccion} onChange={poner("jurisdiccion")} maxLength={10} />
        </div>
        <div>
          <span className={ETIQUETA}>Equipo (tú quedas como responsable)</span>
          <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto">
            {disponibles.filter((u) => u.nombre !== yo.usuario.nombre).map((u) => {
              const si = equipo.includes(u.usuario_id);
              return (
                <button key={u.usuario_id} type="button" aria-pressed={si} title={u.roles.join(", ")}
                  onClick={() => setEquipo((x) => (si ? x.filter((y) => y !== u.usuario_id) : [...x, u.usuario_id]))}
                  className={`rounded-full px-3 py-1 text-[13px] font-semibold ${si ? "bg-tinta text-superficie" : "bg-smn-gris-100 text-smn-gris-700"}`}>
                  {u.nombre}
                </button>
              );
            })}
            {disponibles.length === 0 && <span className="text-sm text-smn-gris-500">Nadie más tiene roles de Innovación todavía.</span>}
          </div>
          <p className="mt-1 text-[13px] text-smn-gris-500">Solo el equipo del folio con permiso de fórmula puede ver la fórmula técnica.</p>
        </div>
        <Boton onClick={crear} cargando={enviando}>Crear expediente</Boton>
      </div>
    </Modal>
  );
}
