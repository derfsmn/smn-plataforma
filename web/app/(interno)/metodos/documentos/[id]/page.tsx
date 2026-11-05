"use client";
// Un documento: sus secciones (como las lee la búsqueda), versiones, avisos y acciones del área dueña.

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { AlertTriangle, ArrowLeft, Download, FileText, RefreshCw, Sparkles, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { ESTADOS_DOC, ORIGENES, PERMISO_APROBAR, PERMISO_CARGAR, RUTA, TIPOS, fecha, type DocumentoDetalle, type Estado } from "@/lib/metodos";
import { descargar } from "@/lib/precios";
import { PedirBorradorVentana, type PedirBorrador } from "../../borradores";
import { VerDiagrama } from "../../diagrama";
import { TARJETA } from "../../estilos";

export default function VerDocumento() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [d, setD] = useState<DocumentoDetalle | null>(null);
  const [estado, setEstado] = useState<Estado | null>(null);
  const [pedir, setPedir] = useState<PedirBorrador | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const cargar = useCallback(() => api<DocumentoDetalle>(`${RUTA}/documentos/${id}`).then(setD).catch((e) => avisar(mensajeDe(e), "info")), [id, avisar]);
  useEffect(() => {
    cargar();
    api<Estado>(`${RUTA}/estado`).then(setEstado).catch(() => {});
  }, [cargar]);
  // al llegar desde una cita, baja a la sección
  useEffect(() => {
    if (d && window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [d]);

  if (!d) return <Esqueleto className="h-64" />;
  const propio = d.origen === "cargado" || d.origen === "ia";
  const accion = async (ruta: string, cuerpo: unknown, exito: string) => {
    setOcupado(true);
    try {
      await api(`${RUTA}/documentos/${d.id}/${ruta}`, { cuerpo });
      avisar(exito, "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  const marcado = typeof window !== "undefined" ? window.location.hash.replace("#seccion-", "") : "";

  return (
    <>
      <Link href="/metodos?vista=documentos" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Documentos
      </Link>
      <Encabezado
        titulo={d.titulo}
        descripcion={[d.clave, TIPOS[d.tipo], d.area, `versión ${d.version}`, d.vigente_desde ? `vigente desde ${fecha(d.vigente_desde)}` : null].filter(Boolean).join(" · ")}
        accion={<Insignia className={ESTADOS_DOC[d.estado]?.clase}>{ESTADOS_DOC[d.estado]?.texto}</Insignia>}
      />
      {(d.viejo || d.avisos.length > 0) && (
        <Entrada className="mb-4 grid gap-1 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          {[d.viejo, ...d.avisos].filter(Boolean).map((a, i) => (
            <p key={i} className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {a}</p>
          ))}
        </Entrada>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="grid min-w-0 content-start gap-3 lg:col-span-2">
          {d.diagrama_svg && (
            <div className={`${TARJETA} min-w-0`}>
              <p className="mb-2 flex items-center gap-2 font-semibold"><Workflow className="h-4 w-4 text-smn-naranja" /> Diagrama de flujo</p>
              <VerDiagrama svg={d.diagrama_svg} />
            </div>
          )}
          {d.secciones.length === 0 && <div className={`${TARJETA} text-sm text-smn-gris-500`}>No se leyó texto de este documento.</div>}
          {d.secciones.map((s) => (
            <section key={s.id} id={`seccion-${s.id}`} className={`${TARJETA} scroll-mt-24 ${marcado === String(s.id) ? "ring-2 ring-smn-naranja" : ""}`}>
              {s.seccion && <p title={s.seccion} className="mb-1 text-[13px] font-medium text-smn-gris-500">{s.seccion.split(" > ").slice(-1)[0]}{s.pagina ? ` · página ${s.pagina}` : ""}</p>}
              <p className="whitespace-pre-line text-sm leading-relaxed">{s.texto}</p>
            </section>
          ))}
        </div>
        <div className="grid content-start gap-4">
          <div className={`${TARJETA} text-sm`}>
            <p className="font-semibold">Datos del documento</p>
            <dl className="mt-2 grid gap-1 text-smn-gris-500">
              <div>Origen: {ORIGENES[d.origen]}</div>
              {d.sistema && <div>Sistema: {d.sistema}</div>}
              <div>Lo ven: {d.roles.length ? d.roles.map((r) => estado?.roles.find((x) => x.codigo === r)?.nombre ?? r).join(", ") : "todos los que consultan manuales"}</div>
              {d.revisar_antes && <div>Revisar antes de: {fecha(d.revisar_antes)}</div>}
              <div>Cargado por {d.cargado_por ?? "—"} el {fechaLocal(d.cargado_en)}</div>
              {d.aprobado_por && d.aprobado_en && <div>Aprobado por {d.aprobado_por} el {fechaLocal(d.aprobado_en)}</div>}
              <div>{d.secciones.length} secciones, {d.con_huella} con huella de significado</div>
            </dl>
          </div>
          <div className={`${TARJETA} grid gap-2`}>
            {d.pdf && (
              <Boton onClick={() => descargar(`${RUTA}/documentos/${d.id}/pdf`, `${d.titulo} v${d.version}.pdf`).catch((e) => avisar(mensajeDe(e), "info"))}>
                <FileText className="h-4 w-4" /> Descargar en PDF
              </Boton>
            )}
            {d.archivo && (
              <Boton variante={d.pdf ? "fantasma" : "secundario"} onClick={() => descargar(`${RUTA}/documentos/${d.id}/archivo`, d.archivo!).catch((e) => avisar(mensajeDe(e), "info"))}>
                <Download className="h-4 w-4" /> Descargar {d.origen === "ia" ? "en Word" : "el original"}
              </Boton>
            )}
            {!propio && <p className="text-[13px] text-smn-gris-500">Este documento se carga y se cambia en su módulo de origen; aquí solo se usa para contestar.</p>}
            {propio && d.estado === "vigente" && puede(PERMISO_CARGAR) && estado?.ollama && (
              <>
                <Boton variante="secundario" onClick={() => setPedir({ tipo: "actualizacion", documento_id: d.id })}>
                  <Sparkles className="h-4 w-4" /> Pedir versión actualizada a la IA
                </Boton>
                <Boton variante="secundario" onClick={() => setPedir({ tipo: "formato", documento_id: d.id })}>
                  <Sparkles className="h-4 w-4" /> Pasar al formato estándar
                </Boton>
              </>
            )}
            {propio && puede(PERMISO_CARGAR) && (
              <Boton variante="fantasma" cargando={ocupado} onClick={() => accion("releer", {}, "Se volvió a leer el documento.")}>
                <RefreshCw className="h-4 w-4" /> Volver a leer
              </Boton>
            )}
            {propio && d.estado === "vigente" && puede(PERMISO_APROBAR) && (
              <Boton variante="fantasma" cargando={ocupado} onClick={() => {
                const nota = window.prompt("¿Por qué se retira? Ya no se usará para contestar.");
                if (nota !== null) accion("retirar", { nota }, "Documento retirado.");
              }}>
                <Trash2 className="h-4 w-4" /> Retirar
              </Boton>
            )}
          </div>
          {d.versiones.length > 0 && (
            <div className={`${TARJETA} text-sm`}>
              <p className="font-semibold">Otras versiones</p>
              <ul className="mt-2 space-y-1">
                {d.versiones.map((v) => (
                  <li key={v.id}>
                    <Link href={`/metodos/documentos/${v.id}`} className="hover:underline">Versión {v.version}</Link>
                    <span className="text-smn-gris-500"> · {ESTADOS_DOC[v.estado]?.texto} · {fecha(v.vigente_desde)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      <AnimatePresence>
        {pedir && estado && (
          <PedirBorradorVentana estado={estado} inicial={pedir} cerrar={() => setPedir(null)} listo={(b) => {
            setPedir(null);
            avisar("La IA está redactando. Te aviso en la campana cuando esté listo.", "exito");
            window.location.href = `/metodos/borradores/${b.id}`;
          }} />
        )}
      </AnimatePresence>
    </>
  );
}
