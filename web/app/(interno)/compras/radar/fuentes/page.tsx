"use client";
// Radar · Fuentes y temas: la lista de sitios que se leen cada día y los temas de la búsqueda abierta.

import { AnimatePresence } from "motion/react";
import { CircleCheck, CircleX, ExternalLink, Pencil, Plus, Rss, Search, Globe2, FlaskConical } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_FUENTE_TIPO, TEXTO_METODO, fechaHora, type Fuente, type Tema } from "@/lib/radar";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Esqueleto, Insignia, Selector } from "@/componentes/ui";

type FuenteForma = Omit<Fuente, "id" | "ultima_lectura_en" | "ultimo_resultado" | "ultimos_articulos" | "articulos_total">;
const NUEVA: FuenteForma = { nombre: "", liga: "https://", tipo: "especializada", pais: "MX", idioma: "es", metodo: "rss", lectura: "", activa: true, notas: "" };
const ICONO_METODO = { rss: Rss, busqueda: Search, manual: Globe2 };

export default function Fuentes() {
  const avisar = useAvisos();
  const { puede } = useSesion();
  const admin = puede("compras.radar.administrar");
  const [fuentes, setFuentes] = useState<Fuente[] | null>(null);
  const [temas, setTemas] = useState<Tema[] | null>(null);
  const [editarFuente, setEditarFuente] = useState<{ id?: number; datos: FuenteForma } | null>(null);
  const [editarTema, setEditarTema] = useState<Tema | "nuevo" | null>(null);

  const cargar = useCallback(() => {
    api<Fuente[]>("/api/compras/radar/fuentes").then(setFuentes).catch((e) => avisar(mensajeDe(e), "info"));
    api<Tema[]>("/api/compras/radar/temas").then(setTemas).catch(() => {});
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const porTipo = useMemo(() => {
    const g: Record<string, Fuente[]> = {};
    (fuentes ?? []).forEach((f) => (g[f.tipo] ??= []).push(f));
    return g;
  }, [fuentes]);

  const cambiarActiva = async (f: Fuente) => {
    try {
      const { nombre, liga, tipo, pais, idioma, metodo, lectura, notas } = f;
      await api(`/api/compras/radar/fuentes/${f.id}`, { metodo: "PUT", cuerpo: { nombre, liga, tipo, pais, idioma, metodo, lectura, notas, activa: !f.activa } });
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  if (!fuentes || !temas) return <Esqueleto className="h-64" />;

  return (
    <div className="space-y-8">
      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Fuentes ({fuentes.filter((f) => f.activa).length} activas)</h2>
            <p className="text-sm text-smn-gris-500">
              Las de RSS se leen directo y sin costo. Las demás se leen con la búsqueda de la IA dentro de su sitio, una búsqueda por tipo de fuente.
            </p>
          </div>
          {admin && (
            <Boton onClick={() => setEditarFuente({ datos: NUEVA })}>
              <Plus className="h-4 w-4" /> Agregar fuente
            </Boton>
          )}
        </div>
        <div className="space-y-5">
          {Object.entries(porTipo).map(([tipo, lista]) => (
            <div key={tipo}>
              <h3 className="mb-2 text-[13px] font-medium text-smn-gris-500">{TEXTO_FUENTE_TIPO[tipo as Fuente["tipo"]]}</h3>
              <ul className="grid gap-2 md:grid-cols-2">
                {lista.map((f) => {
                  const Icono = ICONO_METODO[f.metodo];
                  const error = f.ultimo_resultado?.startsWith("Error");
                  return (
                    <li key={f.id} className={`rounded-2xl border border-smn-gris-100 bg-superficie p-4 ${f.activa ? "" : "opacity-60"}`}>
                      <div className="flex items-start gap-3">
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-smn-gris-50 text-smn-naranja">
                          <Icono className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <a href={f.liga} target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline">
                              {f.nombre}
                            </a>
                            <ExternalLink className="h-3.5 w-3.5 text-smn-gris-500" />
                            <Insignia className="bg-smn-gris-50 text-smn-gris-700">{f.pais}</Insignia>
                            {!f.activa && <Insignia className="bg-smn-gris-100 text-smn-gris-500">Pausada</Insignia>}
                          </div>
                          <p className="text-[13px] text-smn-gris-500">
                            {TEXTO_METODO[f.metodo]} · {f.articulos_total} notas guardadas
                          </p>
                          {f.ultimo_resultado && (
                            <p className={`mt-1 flex items-start gap-1 text-[13px] ${error ? "text-red-700 dark:text-red-400" : "text-smn-gris-700"}`}>
                              {error ? <CircleX className="mt-px h-3.5 w-3.5 shrink-0" /> : <CircleCheck className="mt-px h-3.5 w-3.5 shrink-0" />}
                              {f.ultimo_resultado} {f.ultima_lectura_en && `(${fechaHora(f.ultima_lectura_en)})`}
                            </p>
                          )}
                          {f.notas && <p className="mt-1 text-[13px] text-smn-gris-500">{f.notas}</p>}
                        </div>
                        {admin && (
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <button
                              role="switch"
                              aria-checked={f.activa}
                              aria-label={f.activa ? "Pausar fuente" : "Activar fuente"}
                              onClick={() => cambiarActiva(f)}
                              className={`relative h-6 w-11 rounded-full transition-colors ${f.activa ? "bg-smn-naranja" : "bg-smn-gris-300"}`}
                            >
                              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${f.activa ? "right-0.5" : "left-0.5"}`} />
                            </button>
                            <button onClick={() => setEditarFuente({ id: f.id, datos: { nombre: f.nombre, liga: f.liga, tipo: f.tipo, pais: f.pais, idioma: f.idioma, metodo: f.metodo, activa: f.activa, lectura: f.lectura ?? "", notas: f.notas ?? "" } })} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${f.nombre}`}>
                              <Pencil className="h-4 w-4" />
                            </button>
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Temas de la búsqueda abierta ({temas.filter((t) => t.activo).length} activos)</h2>
            <p className="text-sm text-smn-gris-500">Además de la lista de fuentes, la IA busca en todo internet cada uno de estos temas, todos los días. Cada búsqueda cuesta.</p>
          </div>
          {admin && (
            <Boton variante="secundario" onClick={() => setEditarTema("nuevo")}>
              <Plus className="h-4 w-4" /> Agregar tema
            </Boton>
          )}
        </div>
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {temas.map((t) => (
            <li key={t.id} className={`flex items-start gap-3 p-4 ${t.activo ? "" : "opacity-60"}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {t.nombre} {!t.activo && <Insignia className="ml-1 bg-smn-gris-100 text-smn-gris-500">Pausado</Insignia>}
                </p>
                <p className="text-sm text-smn-gris-500">{t.descripcion}</p>
              </div>
              {admin && (
                <button onClick={() => setEditarTema(t)} className="rounded-lg p-1.5 text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta" aria-label={`Editar ${t.nombre}`}>
                  <Pencil className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <AnimatePresence>
        {editarFuente && <VentanaFuente id={editarFuente.id} inicial={editarFuente.datos} cerrar={() => setEditarFuente(null)} alGuardar={cargar} />}
        {editarTema && <VentanaTema tema={editarTema === "nuevo" ? null : editarTema} cerrar={() => setEditarTema(null)} alGuardar={cargar} />}
      </AnimatePresence>
    </div>
  );
}

function VentanaFuente({ id, inicial, cerrar, alGuardar }: { id?: number; inicial: FuenteForma; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [d, setD] = useState<FuenteForma>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [probando, setProbando] = useState(false);
  const [prueba, setPrueba] = useState<{ ok: boolean; mensaje: string; ejemplos: { titulo: string; url: string; fecha: string | null }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poner = (c: Partial<FuenteForma>) => setD((x) => ({ ...x, ...c }));
  const cuerpo = { ...d, lectura: d.lectura || null, notas: d.notas || null };

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await api(id ? `/api/compras/radar/fuentes/${id}` : "/api/compras/radar/fuentes", { metodo: id ? "PUT" : "POST", cuerpo });
      avisar(id ? "Fuente actualizada" : "Fuente agregada", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  const probar = async () => {
    setProbando(true);
    setPrueba(null);
    try {
      setPrueba(await api("/api/compras/radar/fuentes/probar", { metodo: "POST", cuerpo }));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setProbando(false);
    }
  };

  return (
    <Modal titulo={id ? "Editar fuente" : "Agregar fuente"} cerrar={cerrar} ancho="sm:max-w-2xl">
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Nombre" value={d.nombre} onChange={(e) => poner({ nombre: e.target.value })} />
        <Campo etiqueta="Página del sitio" value={d.liga} onChange={(e) => poner({ liga: e.target.value })} />
        <Selector etiqueta="Tipo" valor={d.tipo} cambiar={(v) => poner({ tipo: v as FuenteForma["tipo"] })} opciones={Object.entries(TEXTO_FUENTE_TIPO).map(([valor, texto]) => ({ valor, texto }))} />
        <div className="grid grid-cols-2 gap-3">
          <Selector etiqueta="País" valor={d.pais} cambiar={(v) => poner({ pais: v })} opciones={["MX", "EUA", "UE", "global"].map((v) => ({ valor: v, texto: v }))} />
          <Selector etiqueta="Idioma" valor={d.idioma} cambiar={(v) => poner({ idioma: v as "es" | "en" })} opciones={[{ valor: "es", texto: "Español" }, { valor: "en", texto: "Inglés" }]} />
        </div>
        <Selector etiqueta="Cómo se lee" valor={d.metodo} cambiar={(v) => poner({ metodo: v as FuenteForma["metodo"] })} opciones={Object.entries(TEXTO_METODO).map(([valor, texto]) => ({ valor, texto }))} />
        {d.metodo !== "manual" && (
          <Campo
            etiqueta={d.metodo === "rss" ? "Dirección del RSS" : "Sitio(s) donde buscar"}
            placeholder={d.metodo === "rss" ? "https://sitio.com/feed" : "sitio.com (vacío = el de la página)"}
            value={d.lectura ?? ""}
            onChange={(e) => poner({ lectura: e.target.value })}
          />
        )}
        <div className="sm:col-span-2">
          <Campo etiqueta="Notas (opcional)" value={d.notas ?? ""} onChange={(e) => poner({ notas: e.target.value })} />
        </div>
      </div>
      {prueba && (
        <div className={`mt-4 rounded-xl p-3 text-sm ${prueba.ok ? "bg-smn-gris-50" : "bg-red-500/10 text-red-700 dark:text-red-400"}`}>
          <p className="font-semibold">{prueba.mensaje}</p>
          <ul className="mt-1 space-y-0.5">
            {prueba.ejemplos.map((e) => (
              <li key={e.url} className="truncate text-smn-gris-700">
                • {e.titulo} {e.fecha && <span className="text-smn-gris-500">({e.fecha})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        {d.metodo === "rss" && (
          <Boton variante="secundario" onClick={probar} cargando={probando} className="mr-auto">
            <FlaskConical className="h-4 w-4" /> Probar RSS
          </Boton>
        )}
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}

function VentanaTema({ tema, cerrar, alGuardar }: { tema: Tema | null; cerrar: () => void; alGuardar: () => void }) {
  const avisar = useAvisos();
  const [d, setD] = useState({ nombre: tema?.nombre ?? "", descripcion: tema?.descripcion ?? "", activo: tema?.activo ?? true, orden: tema?.orden ?? 100 });
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await api(tema ? `/api/compras/radar/temas/${tema.id}` : "/api/compras/radar/temas", { metodo: tema ? "PUT" : "POST", cuerpo: d });
      avisar(tema ? "Tema actualizado" : "Tema agregado", "exito");
      alGuardar();
      cerrar();
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };
  return (
    <Modal titulo={tema ? "Editar tema" : "Agregar tema"} cerrar={cerrar}>
      <div className="space-y-4">
        <Campo etiqueta="Nombre" value={d.nombre} onChange={(e) => setD({ ...d, nombre: e.target.value })} />
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Qué buscar (en palabras)</span>
          <textarea
            value={d.descripcion}
            onChange={(e) => setD({ ...d, descripcion: e.target.value })}
            rows={4}
            maxLength={600}
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={d.activo} onChange={(e) => setD({ ...d, activo: e.target.checked })} className="h-4 w-4 accent-[var(--color-smn-naranja)]" />
          Activo
        </label>
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <Boton variante="fantasma" onClick={cerrar}>
          Cancelar
        </Boton>
        <Boton onClick={guardar} cargando={guardando}>
          Guardar
        </Boton>
      </div>
    </Modal>
  );
}
