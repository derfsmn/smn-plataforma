"use client";
// Ficha de una fuente: lectura en curso (con reintentos), datos sugeridos por la IA local para confirmar, revisión
// (qué respalda y sus límites), vínculos, archivos con descarga, versiones y dónde se usa.

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AnimatePresence } from "motion/react";
import { CheckCircle2, Download, FilePlus2, Loader2, RotateCw, Sparkles, X, XCircle } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Campo, Encabezado, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { api, haceCuanto, mensajeDe, tamanoLegible } from "@/lib/api";
import {
  CLASIFICACION, P, RUTA, TIPOS, descargar, enviarFuente, fecha,
  type Fuente, type Ingrediente, type Seccion, type TrabajoFuente, type VersionFuente,
} from "@/lib/innovacion";
import { ChipClasificacion, ChipFuente, ETIQUETA, MenuModulo, SinAcceso, TARJETA, Texto, Volver } from "../../comunes";

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-64" />}>
      <FichaFuente />
    </Suspense>
  );
}

function FichaFuente() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [f, setF] = useState<Fuente | null>(null);
  const [nueva, setNueva] = useState(false);
  const [seccion, setSeccion] = useState<Seccion | null>(null);
  const cargar = useCallback(
    () => api<Fuente>(`${RUTA}/recursos/${id}`).then(setF).catch((e) => avisar(mensajeDe(e), "info")),
    [id, avisar],
  );
  useEffect(() => {
    cargar();
  }, [cargar]);
  useEffect(() => {
    const s = params.get("seccion");
    if (s) api<Seccion>(`${RUTA}/secciones/${s}`).then(setSeccion).catch(() => {});
  }, [params]);

  // Mientras haya lectura en curso, la pantalla mueve la cola (en la laptop no hay programador) y se actualiza.
  const enCurso = f?.trabajos.some((t) => t.estado === "pendiente" || t.estado === "corriendo");
  useEffect(() => {
    if (!enCurso) return;
    const t = setInterval(async () => {
      try {
        const trabajos = await api<TrabajoFuente[]>(`${RUTA}/recursos/${id}/trabajos`);
        const sigue = trabajos.some((x) => x.estado === "pendiente" || x.estado === "corriendo");
        if (!sigue) cargar();
        else setF((x) => (x ? { ...x, trabajos } : x));
      } catch {}
    }, 3000);
    return () => clearInterval(t);
  }, [enCurso, id, cargar]);

  if (!puede(P.ver)) return <SinAcceso />;
  if (!f) return <Esqueleto className="h-64" />;
  const ultima = f.versiones[0];
  const anteriores = f.versiones.slice(1);
  return (
    <>
      <Volver href="/innovacion/fuentes" texto="Fuentes" />
      <Encabezado
        titulo={f.titulo}
        descripcion={`${TIPOS[f.tipo] ?? f.tipo}${f.folio ? ` · ${f.folio}` : ""} · responsable ${f.responsable ?? "—"}`}
        accion={
          f.puede_cargar && (
            <Boton variante="secundario" onClick={() => setNueva(true)}><FilePlus2 className="h-4 w-4" /> Versión nueva</Boton>
          )
        }
      />
      <MenuModulo />
      <div className="mb-4 flex flex-wrap gap-2">
        <ChipFuente estado={ultima.estado} />
        <ChipClasificacion valor={f.clasificacion} />
        {f.clasificacion !== "general" && <span className="text-[13px] text-smn-gris-500">{CLASIFICACION[f.clasificacion]?.ayuda}</span>}
      </div>

      {seccion && (
        <div className={`${TARJETA} mb-5 border-smn-naranja`}>
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-semibold">
              Sección citada · versión {seccion.version}{seccion.pagina ? ` · página ${seccion.pagina}` : ""}{seccion.seccion ? ` · ${seccion.seccion}` : ""}
            </p>
            <button aria-label="Cerrar sección" onClick={() => setSeccion(null)}><X className="h-4 w-4" /></button>
          </div>
          <p className="mt-2 whitespace-pre-line text-[15px] text-smn-gris-700">{seccion.texto}</p>
        </div>
      )}

      <Trabajos trabajos={f.trabajos} alCambiar={cargar} puedeReintentar={puede(P.cargar)} />

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="grid content-start gap-5">
          <Datos f={f} v={ultima} alCambiar={cargar} />
          <Revision f={f} v={ultima} alCambiar={cargar} />
        </div>
        <div className="grid content-start gap-5">
          <Archivos f={f} v={ultima} alCambiar={cargar} />
          <Vinculos f={f} v={ultima} alCambiar={cargar} />
          <Uso v={ultima} />
          {anteriores.length > 0 && (
            <div className={TARJETA}>
              <h2 className="mb-2 font-semibold">Versiones anteriores</h2>
              {anteriores.map((v) => (
                <div key={v.numero} className="flex items-center justify-between border-t border-smn-gris-100 py-2 text-sm first:border-0">
                  <span>Versión {v.numero} · {fecha(v.creado_en)}{v.revisado_por ? ` · revisó ${v.revisado_por}` : ""}</span>
                  <ChipFuente estado={v.estado} />
                </div>
              ))}
              <p className="mt-2 text-[13px] text-smn-gris-500">Las versiones anteriores se conservan: las citas de los expedientes siguen apuntando a la versión que se citó.</p>
            </div>
          )}
        </div>
      </div>
      <AnimatePresence>{nueva && <NuevaVersion f={f} cerrar={() => setNueva(false)} alGuardar={cargar} />}</AnimatePresence>
    </>
  );
}

function Trabajos({ trabajos, alCambiar, puedeReintentar }: { trabajos: TrabajoFuente[]; alCambiar: () => void; puedeReintentar: boolean }) {
  const avisar = useAvisos();
  const ultimos = Object.values(Object.fromEntries(trabajos.map((t) => [`${t.version}-${t.tipo}`, t])));
  const visibles = ultimos.filter((t) => t.estado !== "listo" || t.version === Math.max(...trabajos.map((x) => x.version)));
  if (!visibles.length) return null;
  const reintentar = async (t: TrabajoFuente) => {
    try {
      await api(`${RUTA}/trabajos/${t.id}/reintentar`, { metodo: "POST", cuerpo: {} });
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  return (
    <div className={`${TARJETA} mb-5`}>
      <h2 className="mb-2 font-semibold">Lectura de la fuente</h2>
      <ul className="grid gap-1.5">
        {visibles.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="inline-flex items-center gap-2">
              {t.estado === "listo" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : t.estado === "error" ? <XCircle className="h-4 w-4 text-red-600" /> : <Loader2 className="h-4 w-4 animate-spin text-smn-naranja" />}
              {t.nombre}
              {t.estado === "pendiente" && t.intentos > 0 && t.siguiente_en && <span className="text-smn-gris-500">· reintento {t.intentos} a las {new Date(t.siguiente_en).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })}</span>}
            </span>
            {t.estado === "error" && (
              <span className="inline-flex items-center gap-2 text-red-700 dark:text-red-400">
                {t.error}
                {puedeReintentar && <Boton variante="fantasma" className="min-h-8 px-2" onClick={() => reintentar(t)}><RotateCw className="h-4 w-4" /> Reintentar</Boton>}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

const CAMPOS_DATOS = [
  ["autores", "Autores"], ["anio", "Año"], ["publicado_en", "Publicado en"], ["doi", "DOI"], ["pmid", "PMID"], ["url", "Enlace"], ["idioma", "Idioma"],
] as const;
const CAMPOS_ESTUDIO = [["poblacion", "Población"], ["cantidad", "Cantidad o dosis"], ["duracion", "Duración"], ["diseno", "Diseño del estudio"]] as const;

function Datos({ f, v, alCambiar }: { f: Fuente; v: VersionFuente; alCambiar: () => void }) {
  const avisar = useAvisos();
  const inicial = () => ({
    titulo: f.titulo,
    autores: v.autores ?? "", anio: v.anio ? String(v.anio) : "", publicado_en: v.publicado_en ?? "", doi: v.doi ?? "", pmid: v.pmid ?? "",
    url: v.url ?? "", idioma: v.idioma ?? "", resumen: v.resumen ?? "", vigente_desde: v.vigente_desde ?? "", vigente_hasta: v.vigente_hasta ?? "",
    poblacion: v.datos.poblacion ?? "", cantidad: v.datos.cantidad ?? "", duracion: v.datos.duracion ?? "", diseno: v.datos.diseno ?? "",
  });
  const [d, setD] = useState(inicial);
  const [guardando, setGuardando] = useState(false);
  const editable = v.estado === "pendiente" && f.puede_cargar;
  const sug = v.sugerencias as Record<string, string | number | null>;
  const haySug = Object.values(sug).some((x) => x !== null && x !== "" && !Array.isArray(x));
  useEffect(() => setD(inicial()), [v.version_id, v.procesado]); // eslint-disable-line react-hooks/exhaustive-deps

  const usarSugerencias = () =>
    setD((x) => {
      const y = { ...x } as Record<string, string>;
      for (const k of Object.keys(y)) if (!y[k] && sug[k] !== null && sug[k] !== undefined && typeof sug[k] !== "object") y[k] = String(sug[k]);
      return y as typeof x;
    });
  const guardar = async () => {
    setGuardando(true);
    try {
      await api(`${RUTA}/recursos/${f.id}/versiones/${v.numero}`, {
        metodo: "PATCH",
        cuerpo: Object.fromEntries(Object.entries(d).map(([k, x]) => [k, k === "anio" ? (x ? Number(x) : null) : x.trim() || null])),
      });
      avisar("Datos guardados.", "exito");
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setGuardando(false);
    }
  };
  const poner = (k: keyof ReturnType<typeof inicial>) => (e: React.ChangeEvent<HTMLInputElement>) => setD((x) => ({ ...x, [k]: e.target.value }));
  return (
    <div className={TARJETA}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Datos de la fuente · versión {v.numero}</h2>
        {editable && haySug && (
          <Boton variante="secundario" onClick={usarSugerencias}><Sparkles className="h-4 w-4" /> Llenar lo vacío con lo que sugirió la IA local</Boton>
        )}
      </div>
      {!editable ? (
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {[...CAMPOS_DATOS, ...CAMPOS_ESTUDIO].map(([k, t]) => {
            const valor = (k in v ? (v as unknown as Record<string, unknown>)[k] : v.datos[k]) as string | number | null;
            return valor ? (
              <div key={k}>
                <dt className="text-smn-gris-500">{t}</dt>
                <dd className="break-words">{k === "url" ? <a href={String(valor)} target="_blank" rel="noreferrer noopener" className="text-smn-naranja underline">{String(valor)}</a> : String(valor)}</dd>
              </div>
            ) : null;
          })}
          {v.resumen && <div className="sm:col-span-2"><dt className="text-smn-gris-500">Resumen</dt><dd className="whitespace-pre-line">{v.resumen}</dd></div>}
          {(v.vigente_desde || v.vigente_hasta) && <div><dt className="text-smn-gris-500">Vigencia</dt><dd>{fecha(v.vigente_desde)} a {v.vigente_hasta ? fecha(v.vigente_hasta) : "sin fecha"}</dd></div>}
          <div><dt className="text-smn-gris-500">Secciones leídas</dt><dd>{v.secciones}</dd></div>
        </dl>
      ) : (
        <div className="grid gap-3">
          <Campo etiqueta="Título" value={d.titulo} onChange={poner("titulo")} />
          <div className="grid gap-3 sm:grid-cols-2">
            {[...CAMPOS_DATOS, ...CAMPOS_ESTUDIO].map(([k, t]) => (
              <div key={k}>
                <Campo etiqueta={t} value={d[k]} onChange={poner(k)} type={k === "anio" ? "number" : "text"} />
                {!d[k] && sug[k] !== null && sug[k] !== undefined && typeof sug[k] !== "object" && (
                  <span className="mt-1 block text-[13px] text-smn-gris-500">IA local sugiere: {String(sug[k])}</span>
                )}
              </div>
            ))}
            <Campo etiqueta="Vigente desde" type="date" value={d.vigente_desde} onChange={poner("vigente_desde")} />
            <Campo etiqueta="Vigente hasta" type="date" value={d.vigente_hasta} onChange={poner("vigente_hasta")} />
          </div>
          <Texto etiqueta="Resumen" valor={d.resumen} cambiar={(x) => setD((y) => ({ ...y, resumen: x }))} filas={4}
            ayuda={!d.resumen && sug.resumen ? `IA local sugiere: ${String(sug.resumen)}` : undefined} />
          <p className="text-[13px] text-smn-gris-500">Lo que sugiere la IA local no se guarda solo: tú lo confirmas o lo corriges. Secciones leídas: {v.secciones}.</p>
          <Boton onClick={guardar} cargando={guardando} className="justify-self-start">Guardar datos</Boton>
        </div>
      )}
    </div>
  );
}

function Revision({ f, v, alCambiar }: { f: Fuente; v: VersionFuente; alCambiar: () => void }) {
  const avisar = useAvisos();
  const sug = v.sugerencias as Record<string, string | null>;
  const [respalda, setRespalda] = useState(sug.respalda ?? "");
  const [limites, setLimites] = useState(sug.limites ?? "");
  const [corresponde, setCorresponde] = useState("ingrediente");
  const [interpretacion, setInterpretacion] = useState("");
  const [enviando, setEnviando] = useState(false);
  if (v.estado !== "pendiente") {
    return v.respalda ? (
      <div className={TARJETA}>
        <h2 className="mb-2 font-semibold">Revisión</h2>
        <dl className="grid gap-2 text-sm">
          <div><dt className="text-smn-gris-500">Qué respalda</dt><dd className="whitespace-pre-line">{v.respalda}</dd></div>
          {v.limites && <div><dt className="text-smn-gris-500">Límites</dt><dd className="whitespace-pre-line">{v.limites}</dd></div>}
          {v.corresponde && <div><dt className="text-smn-gris-500">Corresponde al</dt><dd>{v.corresponde === "ambos" ? "ingrediente y producto" : v.corresponde}</dd></div>}
          {v.interpretacion && <div><dt className="text-smn-gris-500">Interpretación del equipo</dt><dd className="whitespace-pre-line">{v.interpretacion}</dd></div>}
          <div><dt className="text-smn-gris-500">Revisó</dt><dd>{v.revisado_por} · {fecha(v.revisado_en)} · revisión {v.tipo_revision}</dd></div>
        </dl>
      </div>
    ) : null;
  }
  if (!f.puede_revisar) {
    return (
      <div className={TARJETA}>
        <h2 className="mb-1 font-semibold">Pendiente de revisión {v.tipo_revision}</h2>
        <p className="text-sm text-smn-gris-500">Mientras no se revise, esta fuente no respalda reglas ni respuestas de la consulta.</p>
      </div>
    );
  }
  const revisar = async () => {
    if (respalda.trim().length < 3) return avisar("Escribe qué respalda la fuente.", "info");
    setEnviando(true);
    try {
      await api(`${RUTA}/recursos/${f.id}/versiones/${v.numero}/revision`, {
        cuerpo: { respalda: respalda.trim(), limites: limites.trim() || null, corresponde, interpretacion: interpretacion.trim() || null },
      });
      avisar("Fuente revisada: ya puede respaldar reglas y respuestas.", "exito");
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setEnviando(false);
    }
  };
  return (
    <div className={`${TARJETA} grid gap-3`}>
      <h2 className="font-semibold">Revisar · revisión {v.tipo_revision}</h2>
      <Texto etiqueta="¿Qué respalda esta fuente?" valor={respalda} cambiar={setRespalda} filas={3} ayuda={sug.respalda ? "Viene prellenado con la sugerencia de la IA local: corrígelo." : undefined} />
      <Texto etiqueta="Límites que reconoce (población, dosis, diseño…)" valor={limites} cambiar={setLimites} filas={2} />
      <Selector etiqueta="Corresponde al" valor={corresponde} cambiar={setCorresponde}
        opciones={[{ valor: "ingrediente", texto: "Ingrediente" }, { valor: "producto", texto: "Producto terminado" }, { valor: "ambos", texto: "Ambos" }]} />
      <Texto etiqueta="Interpretación del equipo (opcional)" valor={interpretacion} cambiar={setInterpretacion} filas={2} />
      <Boton onClick={revisar} cargando={enviando} className="justify-self-start">Marcar como revisada</Boton>
    </div>
  );
}

function Archivos({ f, v, alCambiar }: { f: Fuente; v: VersionFuente; alCambiar: () => void }) {
  const avisar = useAvisos();
  const [editando, setEditando] = useState<number | null>(null);
  const [texto, setTexto] = useState("");
  if (!v.archivos.length && !v.url) return null;
  const confirmar = async (archivo: number) => {
    try {
      await api(`${RUTA}/recursos/${f.id}/versiones/${v.numero}/archivos/${archivo}/descripcion`, { cuerpo: { descripcion: texto.trim() } });
      setEditando(null);
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  return (
    <div className={TARJETA}>
      <h2 className="mb-2 font-semibold">Archivos</h2>
      {v.url && <a href={v.url} target="_blank" rel="noreferrer noopener" className="mb-2 block break-all text-sm text-smn-naranja underline">{v.url}</a>}
      <ul className="grid gap-3">
        {v.archivos.map((a) => (
          <li key={a.id} className="text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="block truncate font-medium">{a.nombre}</span>
                <span className="block text-[13px] text-smn-gris-500">{a.rol} · {tamanoLegible(a.bytes)}{a.cifrado ? " · cifrado" : ""}</span>
              </span>
              <button aria-label={`Descargar ${a.nombre}`} className="rounded-lg p-2 hover:bg-smn-gris-50"
                onClick={() => descargar(`${RUTA}/recursos/${f.id}/archivos/${a.id}`, a.nombre).catch((e) => avisar(mensajeDe(e), "info"))}>
                <Download className="h-4 w-4" />
              </button>
            </div>
            {a.rol === "imagen" && (
              <div className="mt-1.5 rounded-lg bg-smn-gris-50 p-2.5">
                {editando === a.id ? (
                  <div className="grid gap-2">
                    <Texto etiqueta="Descripción de la imagen" valor={texto} cambiar={setTexto} filas={3} />
                    <div className="flex gap-2"><Boton onClick={() => confirmar(a.id)} disabled={texto.trim().length < 3}>Confirmar</Boton><Boton variante="fantasma" onClick={() => setEditando(null)}>Cancelar</Boton></div>
                  </div>
                ) : (
                  <>
                    <p className="text-[13px]">{a.descripcion ?? "Sin descripción todavía."}</p>
                    <p className="mt-1 flex items-center justify-between text-[13px] text-smn-gris-500">
                      {a.descripcion_confirmada ? "Confirmada: ya se puede encontrar." : a.descripcion ? "Sugerida por la IA local: confírmala para que se pueda encontrar." : ""}
                      {f.puede_cargar && <button className="font-semibold text-smn-naranja" onClick={() => { setEditando(a.id); setTexto(a.descripcion ?? ""); }}>{a.descripcion_confirmada ? "Corregir" : "Confirmar"}</button>}
                    </p>
                  </>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {f.clasificacion !== "general" && <p className="mt-2 text-[13px] text-smn-gris-500">Los PDF de esta fuente se descargan con tu nombre y la fecha como marca de agua, y queda registro.</p>}
    </div>
  );
}

function Vinculos({ f, v, alCambiar }: { f: Fuente; v: VersionFuente; alCambiar: () => void }) {
  const avisar = useAvisos();
  const [ingredientes, setIngredientes] = useState<Ingrediente[]>([]);
  const [elegido, setElegido] = useState("");
  const [categoria, setCategoria] = useState("");
  useEffect(() => {
    if (f.puede_cargar) api<Ingrediente[]>(`${RUTA}/ingredientes`).then(setIngredientes).catch(() => {});
  }, [f.puede_cargar]);
  const ligados = new Set(v.vinculos.map((x) => x.ingrediente_id).filter(Boolean));
  const agregar = async () => {
    try {
      await api(`${RUTA}/recursos/${f.id}/versiones/${v.numero}/vinculos`, {
        cuerpo: { ingredientes: elegido ? [Number(elegido)] : [], categorias: categoria.trim() ? [categoria.trim()] : [] },
      });
      setElegido("");
      setCategoria("");
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  const quitar = async (id: number) => {
    try {
      await api(`${RUTA}/vinculos/${id}`, { metodo: "DELETE" });
      alCambiar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };
  return (
    <div className={TARJETA}>
      <h2 className="mb-2 font-semibold">De qué habla</h2>
      <div className="flex flex-wrap gap-2">
        {v.vinculos.length === 0 && <span className="text-sm text-smn-gris-500">Sin vínculos.</span>}
        {v.vinculos.map((x) => (
          <Insignia key={x.id} className="bg-smn-gris-100 text-smn-gris-700">
            {x.ingrediente ?? x.categoria ?? x.folio}
            {f.puede_cargar && <button aria-label="Quitar" className="ml-1" onClick={() => quitar(x.id)}><X className="h-3 w-3" /></button>}
          </Insignia>
        ))}
      </div>
      {f.puede_cargar && (
        <div className="mt-3 grid gap-2">
          <Selector etiqueta="Ingrediente" valor={elegido} cambiar={setElegido}
            opciones={[{ valor: "", texto: "Elige uno" }, ...ingredientes.filter((i) => !ligados.has(i.id)).map((i) => ({ valor: String(i.id), texto: i.nombre }))]} />
          <Campo etiqueta="o una categoría" value={categoria} onChange={(e) => setCategoria(e.target.value)} />
          <Boton variante="secundario" onClick={agregar} disabled={!elegido && !categoria.trim()}>Agregar</Boton>
        </div>
      )}
    </div>
  );
}

function Uso({ v }: { v: VersionFuente }) {
  if (!v.uso.citas.length && !v.uso.reglas.length) return null;
  return (
    <div className={TARJETA}>
      <h2 className="mb-2 font-semibold">Dónde se usa esta versión</h2>
      <ul className="grid gap-1.5 text-sm">
        {v.uso.citas.map((c, i) => (
          <li key={i}><Link href={`/innovacion/expedientes/${c.folio}?vista=evidencia`} className="font-medium text-smn-naranja">{c.folio}</Link>{c.pagina ? ` · pág. ${c.pagina}` : ""} · {c.respalda}</li>
        ))}
        {v.uso.reglas.map((r) => <li key={`${r.codigo}-${r.version}`}>Regla {r.codigo} v{r.version} ({r.estado})</li>)}
      </ul>
    </div>
  );
}

function NuevaVersion({ f, cerrar, alGuardar }: { f: Fuente; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [url, setUrl] = useState("");
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const guardar = async () => {
    if (!archivos.length && !url.trim() && !texto.trim()) return avisar("Pon el archivo, el enlace o el texto de la versión nueva.", "info");
    setEnviando(true);
    try {
      await enviarFuente(`${RUTA}/recursos/${f.id}/versiones`, { url: url.trim() || null, texto: texto.trim() || null }, archivos);
      avisar("Versión nueva cargada. La anterior se conserva.", "exito");
      cerrar();
      alGuardar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
      setEnviando(false);
    }
  };
  return (
    <Modal titulo="Versión nueva de la fuente" cerrar={cerrar} ancho="max-w-lg">
      <div className="grid gap-3">
        <p className="text-sm text-smn-gris-500">La versión nueva pasa por lectura y revisión. Mientras tanto, la versión revisada anterior sigue vigente.</p>
        <span className={ETIQUETA}>Archivos</span>
        <input ref={entrada} type="file" multiple accept=".pdf,.docx,.pptx,.xlsx,.txt,.png,.jpg,.jpeg,.webp" onChange={(e) => setArchivos(Array.from(e.target.files ?? []).slice(0, 10))} />
        <Campo etiqueta="Enlace" value={url} onChange={(e) => setUrl(e.target.value)} />
        <Texto etiqueta="Texto" valor={texto} cambiar={setTexto} filas={4} />
        <Boton onClick={guardar} cargando={enviando}>Cargar versión</Boton>
      </div>
    </Modal>
  );
}
