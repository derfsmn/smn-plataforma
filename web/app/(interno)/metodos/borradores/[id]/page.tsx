"use client";
// Revisar un borrador de la IA: aceptar o rechazar cada cambio, contestar sus preguntas y aprobarlo como versión nueva.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { ArrowLeft, Check, Download, FileText, HelpCircle, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import { ESTADOS_BORRADOR, PERMISO_APROBAR, PERMISO_CARGAR, RUTA, TIPOS, TIPOS_BORRADOR, type BorradorDetalle, type Cambio, type Estado, type TipoDoc } from "@/lib/metodos";
import { descargar } from "@/lib/precios";
import { DiagramaBorrador } from "../../diagrama";
import { AREA, TARJETA } from "../../estilos";
import { Markdown } from "../../markdown";

const PREGUNTA = /\[PREGUNTA:\s*([^\]]+)\]/g;

export default function RevisarBorrador() {
  const { id } = useParams<{ id: string }>();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const router = useRouter();
  const [b, setB] = useState<BorradorDetalle | null>(null);
  const [rechazados, setRechazados] = useState<Set<number>>(new Set());
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState("");
  const [aprobar, setAprobar] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [estado, setEstado] = useState<Estado | null>(null);

  const cargar = useCallback(
    () =>
      api<BorradorDetalle>(`${RUTA}/borradores/${id}`)
        .then((x) => {
          setB(x);
          setTexto(x.texto ?? "");
        })
        .catch((e) => avisar(mensajeDe(e), "info")),
    [id, avisar],
  );
  useEffect(() => {
    cargar();
    api<Estado>(`${RUTA}/estado`).then(setEstado).catch(() => {});
  }, [cargar]);
  useEffect(() => {
    if (b?.estado !== "generando") return;
    const t = setInterval(cargar, 5000);
    return () => clearInterval(t);
  }, [b?.estado, cargar]);

  if (!puede(PERMISO_CARGAR)) return <p className="text-smn-gris-500">No tienes acceso a los borradores.</p>;
  if (!b) return <Esqueleto className="h-64" />;

  const accion = async (ruta: string, cuerpo: unknown, exito: string) => {
    setOcupado(true);
    try {
      await api(`${RUTA}/borradores/${b.id}/${ruta}`, { cuerpo });
      avisar(exito, "exito");
      await cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(false);
    }
  };
  const editable = b.estado === "listo";
  const preguntasEnTexto = [...(editando ? texto : b.texto ?? "").matchAll(PREGUNTA)].map((m) => m[1]);
  const usaCambios = b.tipo !== "nuevo" && b.cambios.length > 0 && !editando;

  return (
    <>
      <Link href="/metodos?vista=borradores" className="mb-6 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
        <ArrowLeft className="h-4 w-4" /> Borradores con IA
      </Link>
      <Encabezado
        titulo={b.titulo}
        descripcion={`${TIPOS_BORRADOR[b.tipo]}${b.version_anterior ? ` de la versión ${b.version_anterior}` : ""} · ${b.area} · pedido por ${b.creado_por ?? "—"} el ${fechaLocal(b.creado_en)}`}
        accion={<Insignia className={ESTADOS_BORRADOR[b.estado].clase}>{ESTADOS_BORRADOR[b.estado].texto}</Insignia>}
      />
      {b.estado === "generando" && <div className={`${TARJETA} text-sm text-smn-gris-500`}>La IA local está redactando. Esta página se actualiza sola; también te aviso en la campana.</div>}
      {b.error && <p className="mb-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">{b.error}</p>}
      {b.estado === "aprobado" && b.publicado_id && (
        <p className="mb-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
          Aprobado por {b.revisado_por} el {fechaLocal(b.revisado_en!)}. <Link href={`/metodos/documentos/${b.publicado_id}`} className="font-semibold underline">Ver el documento publicado</Link>
        </p>
      )}

      {b.texto && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="grid min-w-0 gap-4 lg:col-span-2">
            {usaCambios ? (
              <Entrada className={TARJETA}>
                <p className="font-semibold">Cambios contra la versión {b.version_anterior}</p>
                <p className="mb-3 text-sm text-smn-gris-500">Por omisión se aceptan todos. Rechaza los que no quieras: en esos se queda lo que decía antes.</p>
                <ul className="grid gap-3">
                  {b.cambios.map((c) => (
                    <CambioFila key={c.n} c={c} rechazado={rechazados.has(c.n)} editable={editable}
                      alternar={() => setRechazados((r) => { const n = new Set(r); if (n.has(c.n)) n.delete(c.n); else n.add(c.n); return n; })} />
                  ))}
                </ul>
              </Entrada>
            ) : (
              <Entrada className={TARJETA}>
                <div className="mb-2 flex items-center gap-2">
                  <p className="font-semibold">{editando ? "Corrige el borrador" : "Borrador"}</p>
                  {editable && !editando && <Boton variante="fantasma" className="ml-auto !px-3 !py-1.5 text-[13px]" onClick={() => setEditando(true)}>Corregir el texto</Boton>}
                </div>
                {editando ? (
                  <textarea rows={28} value={texto} onChange={(e) => setTexto(e.target.value)} className={`${AREA} font-mono text-[13px]`} />
                ) : (
                  <Markdown texto={b.texto} />
                )}
              </Entrada>
            )}
            {b.estado !== "generando" && (
              <DiagramaBorrador borradorId={b.id} flujo={b.flujo} svg={b.diagrama_svg} editable={editable}
                iaPrendida={Boolean(estado?.ollama)} alCambiar={cargar} />
            )}
            {usaCambios && editable && (
              <button className="text-left text-sm font-semibold text-naranja-tinta hover:underline" onClick={() => setEditando(true)}>
                Prefiero corregir el texto completo a mano
              </button>
            )}
          </div>
          <div className="grid content-start gap-4">
            {preguntasEnTexto.length > 0 && (
              <div className={TARJETA}>
                <p className="flex items-center gap-2 font-semibold"><HelpCircle className="h-4 w-4 text-smn-naranja" /> La IA no supo esto</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{preguntasEnTexto.map((p, i) => <li key={i}>{p}</li>)}</ul>
                <p className="mt-2 text-[13px] text-smn-gris-500">Contéstalas en el texto con «Corregir el texto» (cambia cada «[PREGUNTA: …]» por la respuesta) antes de aprobar.</p>
              </div>
            )}
            <div className={`${TARJETA} text-sm`}>
              <p className="font-semibold">De dónde salió</p>
              <ul className="mt-1 space-y-1 text-smn-gris-500">
                {b.documento && <li>Manual base: {b.documento} (versión {b.version_anterior})</li>}
                {b.fuentes.map((f) => <li key={f.id}>Apoyo: {f.titulo} (versión {f.version})</li>)}
                {b.archivos.map((a) => <li key={a.id}>Archivo de apoyo: {a.nombre}</li>)}
                {b.instrucciones && <li className="whitespace-pre-line">Lo que se pidió: {b.instrucciones}</li>}
                <li>Redactado con la IA local de SMN; ningún texto salió de la empresa.</li>
              </ul>
            </div>
            <div className={`${TARJETA} grid gap-2`}>
              <Boton variante="secundario" onClick={() => descargar(`${RUTA}/borradores/${b.id}/pdf`, `Borrador - ${b.titulo}.pdf`).catch((e) => avisar(mensajeDe(e), "info"))}>
                <FileText className="h-4 w-4" /> Ver en PDF (con marca de borrador)
              </Boton>
              <Boton variante="fantasma" onClick={() => descargar(`${RUTA}/borradores/${b.id}/word`, `Borrador - ${b.titulo}.docx`).catch((e) => avisar(mensajeDe(e), "info"))}>
                <Download className="h-4 w-4" /> Descargar en Word
              </Boton>
              {editable && puede(PERMISO_APROBAR) && (
                <Boton onClick={() => setAprobar(true)} disabled={preguntasEnTexto.length > 0}>
                  <Check className="h-4 w-4" /> Aprobar y publicar
                </Boton>
              )}
              {editable && !puede(PERMISO_APROBAR) && <p className="text-[13px] text-smn-gris-500">Lo aprueba alguien de {b.area} con permiso de aprobar manuales.</p>}
              {(b.estado === "listo" || b.estado === "error") && (
                <Boton variante="secundario" cargando={ocupado} onClick={() => accion("reintentar", {}, "La IA lo está volviendo a redactar.")}>
                  <RotateCcw className="h-4 w-4" /> Volver a redactar
                </Boton>
              )}
              {(b.estado === "listo" || b.estado === "error") && (
                <Boton variante="fantasma" cargando={ocupado} onClick={() => { const nota = window.prompt("¿Por qué se descarta? (opcional)"); if (nota !== null) accion("descartar", { nota }, "Borrador descartado."); }}>
                  <X className="h-4 w-4" /> Descartar
                </Boton>
              )}
            </div>
          </div>
        </div>
      )}
      {!b.texto && b.estado === "error" && (
        <Boton variante="secundario" cargando={ocupado} onClick={() => accion("reintentar", {}, "La IA lo está volviendo a redactar.")}>
          <RotateCcw className="h-4 w-4" /> Volver a intentar
        </Boton>
      )}

      <AnimatePresence>
        {aprobar && (
          <AprobarVentana
            b={b}
            cerrar={() => setAprobar(false)}
            enviar={async (version, tipo, nota) => {
              setOcupado(true);
              try {
                const r = await api<{ publicado_id: number }>(`${RUTA}/borradores/${b.id}/aprobar`, {
                  cuerpo: { version, tipo, nota, rechazados: [...rechazados], texto: editando ? texto : null },
                });
                avisar("Publicado. Desde ahora se usa para contestar.", "exito");
                router.push(`/metodos/documentos/${r.publicado_id}`);
              } catch (e) {
                avisar(mensajeDe(e), "info");
              } finally {
                setOcupado(false);
              }
            }}
            ocupado={ocupado}
            rechazados={rechazados.size}
            editado={editando}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function CambioFila({ c, rechazado, editable, alternar }: { c: Cambio; rechazado: boolean; editable: boolean; alternar: () => void }) {
  return (
    <li className={`rounded-2xl border px-3 py-2 text-sm ${rechazado ? "border-smn-gris-100 opacity-60" : "border-smn-naranja/40"}`}>
      <div className="mb-1 flex items-center gap-2 text-[13px] text-smn-gris-500">
        <span className="font-semibold">{c.tipo === "cambia" ? "Cambia" : c.tipo === "agrega" ? "Agrega" : "Quita"}</span>
        {c.seccion && <span>· {c.seccion}</span>}
        {editable && (
          <button onClick={alternar} className={`ml-auto rounded-full px-3 py-1 font-semibold ${rechazado ? "bg-smn-gris-100 text-smn-gris-700" : "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300"}`}>
            {rechazado ? "Rechazado: queda lo anterior" : "Aceptado"}
          </button>
        )}
      </div>
      {c.antes.map((p, i) => <p key={`a${i}`} className="rounded bg-red-50 px-2 py-0.5 text-red-800 line-through decoration-red-400/60 dark:bg-red-500/10 dark:text-red-300">{p.replace(/^#+\s/, "")}</p>)}
      {c.despues.map((p, i) => <p key={`d${i}`} className="mt-0.5 rounded bg-emerald-50 px-2 py-0.5 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200">{p.replace(/^#+\s/, "")}</p>)}
    </li>
  );
}

function AprobarVentana({ b, cerrar, enviar, ocupado, rechazados, editado }: {
  b: BorradorDetalle; cerrar: () => void; enviar: (version: string, tipo: TipoDoc, nota: string) => void; ocupado: boolean; rechazados: number; editado: boolean;
}) {
  const [version, setVersion] = useState(b.version_sugerida);
  const [tipo, setTipo] = useState<TipoDoc>("manual");
  const [nota, setNota] = useState("");
  return (
    <Modal titulo="Aprobar y publicar" cerrar={cerrar}>
      <div className="grid gap-3 text-sm">
        <p>
          Al aprobar, «{b.titulo}» vale desde hoy y se usa para contestar.
          {b.documento ? ` La versión ${b.version_anterior} queda como reemplazada en el historial.` : ""}
          {rechazados ? ` Rechazaste ${rechazados} cambios: en esos se queda lo anterior.` : ""}
          {editado ? " Se publica el texto como lo corregiste." : ""}
        </p>
        <Campo etiqueta="Versión" value={version} onChange={(e) => setVersion(e.target.value)} />
        {!b.documento && <Selector etiqueta="Tipo" valor={tipo} cambiar={(v) => setTipo(v as TipoDoc)} opciones={Object.entries(TIPOS).map(([valor, texto]) => ({ valor, texto }))} />}
        <Campo etiqueta="Nota (opcional)" value={nota} onChange={(e) => setNota(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={cerrar}>Cancelar</Boton>
          <Boton cargando={ocupado} disabled={!version.trim()} onClick={() => enviar(version.trim(), tipo, nota)}>
            <Check className="h-4 w-4" /> Aprobar
          </Boton>
        </div>
      </div>
    </Modal>
  );
}
