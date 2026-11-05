"use client";
// Documentos vigentes por área, cargar uno nuevo o una versión nueva, y traer los de Compras y Fiscal.

import Link from "next/link";
import { AnimatePresence } from "motion/react";
import { AlertTriangle, Cpu, FileUp, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { SubirArchivo } from "@/componentes/subir-archivo";
import { Boton, Campo, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, mensajeDe, type Archivo } from "@/lib/api";
import { ESTADOS_DOC, ORIGENES, PERMISO_CARGAR, RUTA, TIPOS, fecha, type Cargado, type Documento, type Estado, type TipoDoc } from "@/lib/metodos";
import { TARJETA } from "./estilos";

export function Documentos({ estado, alCambiar }: { estado: Estado; alCambiar: () => void }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const carga = puede(PERMISO_CARGAR);
  const [docs, setDocs] = useState<Documento[] | null>(null);
  const [todos, setTodos] = useState(false);
  const [filtro, setFiltro] = useState("");
  const [area, setArea] = useState("");
  const [nuevo, setNuevo] = useState<{ reemplaza?: Documento } | null>(null);
  const [ocupado, setOcupado] = useState("");

  const cargar = useCallback(
    () => api<Documento[]>(`${RUTA}/documentos${todos ? "?todos=true" : ""}`).then(setDocs).catch((e) => avisar(mensajeDe(e), "info")),
    [avisar, todos],
  );
  useEffect(() => {
    cargar();
  }, [cargar]);

  const vistos = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    return (docs ?? []).filter((d) => (!area || d.area === area) && (!f || `${d.titulo} ${d.clave ?? ""}`.toLowerCase().includes(f)));
  }, [docs, filtro, area]);
  const grupos = useMemo(() => {
    const g: Record<string, Documento[]> = {};
    vistos.forEach((d) => (g[d.area] ??= []).push(d));
    return g;
  }, [vistos]);

  const accion = async (nombre: string, ruta: string, exito: (r: Record<string, number>) => string) => {
    setOcupado(nombre);
    try {
      const r = await api<Record<string, number>>(ruta, { metodo: "POST" });
      avisar(exito(r), "exito");
      cargar();
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado("");
    }
  };

  if (!docs) return <Esqueleto className="h-64" />;
  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-64">
          <Campo etiqueta="Buscar por título o clave" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        </div>
        <Selector etiqueta="Área dueña" valor={area} cambiar={setArea} opciones={[{ valor: "", texto: "Todas" }, ...estado.areas.map((a) => ({ valor: a, texto: a }))]} />
        {carga && (
          <label className="flex items-center gap-2 pb-3 text-sm font-semibold text-smn-gris-700">
            <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} /> Ver también reemplazados y retirados
          </label>
        )}
        {carga && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Boton variante="secundario" cargando={ocupado === "sinc"} onClick={() => accion("sinc", `${RUTA}/sincronizar`, (r) => `Listo: ${r.nuevo ?? 0} nuevos, ${r.actualizado ?? 0} actualizados, ${r.retirado ?? 0} retirados.`)}>
              <RefreshCw className="h-4 w-4" /> Traer de Compras y Fiscal
            </Boton>
            {estado.ollama && estado.con_huella < estado.fragmentos && (
              <Boton variante="secundario" cargando={ocupado === "huellas" || estado.huellas_en_curso} onClick={() => accion("huellas", `${RUTA}/huellas`, () => "Sacando la huella de significado en segundo plano.")}>
                <Cpu className="h-4 w-4" /> Sacar huellas pendientes
              </Boton>
            )}
            <Boton onClick={() => setNuevo({})}>
              <FileUp className="h-4 w-4" /> Cargar documento
            </Boton>
          </div>
        )}
      </div>

      {vistos.length === 0 && (
        <div className={`${TARJETA} mt-4 text-sm text-smn-gris-500`}>
          {docs.length === 0 ? "Todavía no hay documentos. Carga el primer manual con «Cargar documento»." : "Ningún documento coincide con el filtro."}
        </div>
      )}
      {Object.entries(grupos).map(([nombre, lista]) => (
        <section key={nombre} className="mt-6">
          <h2 className="mb-2 text-sm font-medium text-smn-gris-500">{nombre}</h2>
          <ul className="grid gap-2">
            {lista.map((d) => (
              <li key={d.id} className={`${TARJETA} flex flex-wrap items-center gap-3 !py-3`}>
                <div className="min-w-0 flex-1">
                  <Link href={`/metodos/documentos/${d.id}`} className="font-semibold hover:underline">
                    {d.titulo}
                  </Link>
                  <p className="text-[13px] text-smn-gris-500">
                    {[d.clave, TIPOS[d.tipo], `versión ${d.version}`, d.vigente_desde ? `vigente desde ${fecha(d.vigente_desde)}` : null, ORIGENES[d.origen], d.roles.length ? `solo ${d.roles.length} roles` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {(d.viejo || d.avisos.length > 0) && (
                    <p className="mt-1 flex items-start gap-1 text-[13px] text-amber-700 dark:text-amber-400">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {d.viejo ?? d.avisos[0]}
                    </p>
                  )}
                </div>
                {d.estado !== "vigente" && <Insignia className={ESTADOS_DOC[d.estado]?.clase}>{ESTADOS_DOC[d.estado]?.texto}</Insignia>}
                <span className="text-[13px] text-smn-gris-500 tabular-nums">{d.fragmentos} {d.fragmentos === 1 ? "sección" : "secciones"}</span>
                {carga && d.estado === "vigente" && (d.origen === "cargado" || d.origen === "ia") && (
                  <Boton variante="fantasma" className="!px-3 !py-1.5 text-[13px]" onClick={() => setNuevo({ reemplaza: d })}>
                    Cargar versión nueva
                  </Boton>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      <AnimatePresence>
        {nuevo && (
          <CargarDocumento
            estado={estado}
            reemplaza={nuevo.reemplaza}
            cerrar={() => setNuevo(null)}
            listo={(r) => {
              setNuevo(null);
              const personales = Object.values(r.datos_personales).reduce((a, b) => a + b, 0);
              avisar(
                r.fragmentos === 0
                  ? "Se cargó, pero no se pudo leer texto (¿PDF escaneado?). No se usará para contestar."
                  : `Listo: ${r.fragmentos} secciones${personales ? `; se ocultaron ${personales} datos de personas` : ""}${r.con_huella ? "" : "; sin huella de significado porque la IA local está apagada"}.`,
                personales || !r.fragmentos ? "info" : "exito",
              );
              cargar();
              alCambiar();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function CargarDocumento({ estado, reemplaza, cerrar, listo }: { estado: Estado; reemplaza?: Documento; cerrar: () => void; listo: (r: Cargado) => void }) {
  const avisar = useAvisos();
  const [archivo, setArchivo] = useState<Archivo | null>(null);
  const [titulo, setTitulo] = useState(reemplaza?.titulo ?? "");
  const [tipo, setTipo] = useState<TipoDoc>(reemplaza?.tipo ?? "manual");
  const [area, setArea] = useState(reemplaza?.area ?? "");
  const [version, setVersion] = useState(reemplaza ? siguiente(reemplaza.version) : "1.0");
  const [vigente, setVigente] = useState(new Date().toISOString().slice(0, 10));
  const [revisar, setRevisar] = useState(reemplaza?.revisar_antes ?? "");
  const [clave, setClave] = useState(reemplaza?.clave ?? "");
  const [sistema, setSistema] = useState(reemplaza?.sistema ?? "");
  const [roles, setRoles] = useState<string[]>(reemplaza?.roles ?? []);
  const [guardando, setGuardando] = useState(false);

  const guardar = async () => {
    if (!archivo) return;
    setGuardando(true);
    try {
      const r = await api<Cargado>(`${RUTA}/documentos`, {
        cuerpo: {
          archivo_id: archivo.id, titulo, tipo, area, version, vigente_desde: vigente || null, revisar_antes: revisar || null,
          clave: clave || null, sistema: sistema || null, roles, reemplaza_a: reemplaza?.id ?? null,
        },
      });
      listo(r);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <Modal titulo={reemplaza ? `Versión nueva de «${reemplaza.titulo}»` : "Cargar documento"} cerrar={cerrar} ancho="max-w-2xl">
      <div className="grid gap-4">
        {reemplaza && <p className="text-sm text-smn-gris-500">La versión {reemplaza.version} queda como reemplazada: se guarda en el historial, pero ya no se usa para contestar.</p>}
        {!archivo ? (
          <SubirArchivo modulo="metodos" entidad="metodos_documento" maximoMb={20} alSubir={(a) => {
            setArchivo(a);
            if (!titulo) setTitulo(a.nombre.replace(/\.[^.]+$/, ""));
          }} />
        ) : (
          <p className="rounded-xl bg-smn-gris-50 px-3 py-2 text-sm dark:bg-white/5">
            Archivo: <span className="font-semibold">{archivo.nombre}</span>{" "}
            <button className="ml-2 text-[13px] font-semibold text-naranja-tinta hover:underline" onClick={() => setArchivo(null)}>Cambiar</button>
          </p>
        )}
        <p className="text-[13px] text-smn-gris-500">PDF con texto, Word, Excel o CSV. No cargues documentos con datos de personas (nombres, teléfonos, correos), nóminas ni datos fiscales de proveedores; si los trae, la plataforma los oculta y te avisa.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2"><Campo etiqueta="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)} /></div>
          <Selector etiqueta="Tipo" valor={tipo} cambiar={(v) => setTipo(v as TipoDoc)} opciones={Object.entries(TIPOS).map(([valor, texto]) => ({ valor, texto }))} />
          <label className="block">
            <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Área dueña</span>
            <input list="areas-metodos" value={area} onChange={(e) => setArea(e.target.value)} placeholder="Compras, Tiendas, Contraloría…" className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20" />
            <datalist id="areas-metodos">{estado.areas.map((a) => <option key={a} value={a} />)}</datalist>
          </label>
          <Campo etiqueta="Versión" value={version} onChange={(e) => setVersion(e.target.value)} />
          <Campo etiqueta="Clave del área (opcional)" value={clave} onChange={(e) => setClave(e.target.value)} placeholder="MP-COM-001" />
          <Campo etiqueta="Vigente desde" type="date" value={vigente} onChange={(e) => setVigente(e.target.value)} />
          <Campo etiqueta="Revisar antes de (opcional)" type="date" value={revisar} onChange={(e) => setRevisar(e.target.value)} />
          <div className="sm:col-span-2"><Campo etiqueta="Sistema al que aplica (opcional)" value={sistema} onChange={(e) => setSistema(e.target.value)} placeholder="Intelisis, plataforma…" /></div>
        </div>
        <details className="rounded-xl border border-smn-gris-100 px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold">Quién lo puede ver: {roles.length ? `${roles.length} roles` : "todos los que consultan manuales"}</summary>
          <div className="mt-2 grid gap-1 sm:grid-cols-2">
            {estado.roles.map((r) => (
              <label key={r.codigo} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={roles.includes(r.codigo)} onChange={(e) => setRoles((x) => (e.target.checked ? [...x, r.codigo] : x.filter((c) => c !== r.codigo)))} />
                {r.nombre}
              </label>
            ))}
          </div>
        </details>
        <div className="flex justify-end gap-2">
          <Boton variante="secundario" onClick={cerrar}>Cancelar</Boton>
          <Boton onClick={guardar} cargando={guardando} disabled={!archivo || titulo.trim().length < 3 || area.trim().length < 2 || !version.trim()}>
            Cargar y leer
          </Boton>
        </div>
      </div>
    </Modal>
  );
}

function siguiente(v: string) {
  const entero = v.replace(/^[vV]/, "").split(".")[0];
  return /^\d+$/.test(entero) ? (v.includes(".") ? `${Number(entero) + 1}.0` : String(Number(entero) + 1)) : `${v}.1`;
}
