"use client";
// Radar de precios · Productos: un renglón por producto de la última corrida (filtrado y paginado por la API, pensado para 4,000);
// al picarle se abre la página del producto.

import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, CircleSlash, Clock, Download, FlaskConical, Play, Search, Settings, Square, Tags, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { api, dolares, haceCuanto, mensajeDe } from "@/lib/api";
import { SEMAFORO, TEXTO_FILA, csvTabla, dia, hora, nuestroPrecio, textoCorrida, type Color, type Fila, type Grupo, type Lista, type Orden, type Resumen, type TablaPrecios } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";
import { Diferencia, ICONO_COINCIDENCIA, Miniatura, precio } from "./piezas";
import { PruebaExcel, UltimaPrueba } from "./prueba";

// Ligas viejas de avisos y de la pantalla anterior
const ALIAS: Record<string, Grupo> = { caros: "rojo", baratos: "verde", sin_coincidencia: "revisar" };
const GRUPOS: Grupo[] = ["todos", "verde", "amarillo", "rojo", "revisar", "sin_precios"];
const POR_PAGINA = 50;

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-72" />}>
      <Productos />
    </Suspense>
  );
}

function Productos() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const parametros = useSearchParams();
  const administra = puede("compras.precios.administrar");
  const router = useRouter();
  const ruta = usePathname();
  const [r, setR] = useState<Resumen | null>(null);
  const [l, setL] = useState<Lista | null>(null);
  // Filtros en la dirección: al regresar del detalle de un producto se conserva la página y el grupo
  const crudo = parametros.get("grupo") ?? parametros.get("filtro") ?? "todos";
  const grupo: Grupo = ALIAS[crudo] ?? (GRUPOS.includes(crudo as Grupo) ? (crudo as Grupo) : "todos");
  const q = parametros.get("q") ?? "";
  const marca = parametros.get("marca") ?? "";
  const orden = (parametros.get("orden") ?? "diferencia") as Orden;
  const num = Math.max(1, Number(parametros.get("p")) || 1);
  const [texto, setTexto] = useState(q);
  const [descargando, setDescargando] = useState(false);
  const [lanzando, setLanzando] = useState(false);
  const [deteniendo, setDeteniendo] = useState(false);
  const [preguntaDetener, setPreguntaDetener] = useState(false);
  const [probando, setProbando] = useState(false);
  const enCursoAntes = useRef(false);
  const eraPrueba = useRef(false);

  const cargar = useCallback(() => {
    api<Resumen>("/api/compras/precios/resumen").then(setR).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  useEffect(cargar, [cargar]);

  const poner = useCallback(
    (cambios: Record<string, string | number | null>) => {
      const p = new URLSearchParams(parametros.toString());
      p.delete("filtro");
      for (const [k, v] of Object.entries(cambios)) {
        if (v === null || v === "" || (k === "grupo" && v === "todos") || (k === "orden" && v === "diferencia") || (k === "p" && v === 1)) p.delete(k);
        else p.set(k, String(v));
      }
      const t = p.toString();
      router.replace(t ? `${ruta}?${t}` : ruta, { scroll: false });
    },
    [parametros, router, ruta],
  );

  const cargarLista = useCallback(() => {
    const p = new URLSearchParams({ grupo, orden, pagina: String(num), por_pagina: String(POR_PAGINA) });
    if (q) p.set("q", q);
    if (marca) p.set("marca", marca);
    api<Lista>(`/api/compras/precios/lista?${p}`).then(setL).catch((e) => avisar(mensajeDe(e), "info"));
  }, [grupo, orden, num, q, marca, avisar]);
  useEffect(cargarLista, [cargarLista]);

  // La búsqueda se manda a la API al dejar de escribir
  useEffect(() => {
    if (texto.trim() === q) return;
    const t = setTimeout(() => poner({ q: texto.trim(), p: 1 }), 350);
    return () => clearTimeout(t);
  }, [texto, q, poner]);

  const enCurso = r?.en_curso;
  useEffect(() => {
    if (enCurso) {
      enCursoAntes.current = true;
      eraPrueba.current = enCurso.origen === "prueba";
      const t = setTimeout(cargar, 4000);
      return () => clearTimeout(t);
    }
    if (enCursoAntes.current && eraPrueba.current) {
      enCursoAntes.current = false;
      avisar("La prueba con Excel terminó; ya puedes descargar el resultado", "exito");
      return;
    }
    if (enCursoAntes.current && r?.ultima) {
      enCursoAntes.current = false;
      cargarLista();
      avisar(r.ultima.estado === "completa" ? "Corrida terminada" : "La corrida terminó incompleta; revisa Corridas y gasto", r.ultima.estado === "completa" ? "exito" : "info");
    }
  }, [enCurso, r, cargar, cargarLista, avisar]);

  const detener = async () => {
    setPreguntaDetener(false);
    if (!enCurso) return;
    setDeteniendo(true);
    try {
      await api(`/api/compras/precios/corridas/${enCurso.id}/detener`, { metodo: "POST" });
      enCursoAntes.current = false;
      avisar("Corrida detenida", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setDeteniendo(false);
    }
  };

  const correr = async () => {
    setLanzando(true);
    try {
      await api("/api/compras/precios/corridas", { metodo: "POST" });
      avisar("Corrida iniciada", "exito");
      cargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(false);
    }
  };

  const alerta = r?.alerta_pct ?? 10;
  const descargar = async () => {
    setDescargando(true);
    try {
      const t = await api<TablaPrecios>("/api/compras/precios/tabla");
      const liga = URL.createObjectURL(new Blob([csvTabla(t.renglones)], { type: "text/csv;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = liga;
      a.download = `precios-${t.corrida?.fecha ?? "radar"}.csv`;
      a.click();
      URL.revokeObjectURL(liga);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setDescargando(false);
    }
  };

  if (!r) return <Esqueleto className="h-72" />;

  const tarjetas: { id: Grupo; texto: string; icono?: typeof Tags; color?: Color }[] = [
    { id: "todos", texto: "Todos", icono: Tags },
    { id: "verde", texto: "Igual o más baratos", color: "verde" },
    { id: "amarillo", texto: "Más caros, dentro del límite", color: "amarillo" },
    { id: "rojo", texto: "Más caros, arriba del límite", color: "rojo" },
    { id: "revisar", texto: "Necesitan revisión", icono: CircleSlash },
    { id: "sin_precios", texto: "Sin precios", icono: TriangleAlert },
  ];
  const paginas = l ? Math.max(1, Math.ceil(l.total / l.por_pagina)) : 1;
  const abrir = (id: number) => router.push(`/compras/precios/producto/${id}`);
  const proxima = r.proxima ? new Date(r.proxima).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" }) : null;

  return (
    <>
      <Entrada className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl text-sm text-smn-gris-500">
          <p>
            Nuestro precio lista con impuestos contra la mediana de la competencia en Google Shopping y en los sitios de las tiendas clave. Todo corre solo: lo que no tiene una coincidencia confiable se deja fuera de
            la comparación.
          </p>
          <p className="mt-1">
            <Clock className="mr-1 inline h-3.5 w-3.5" />
            {(r.automatico ? `${r.frecuencia} a las ${r.hora}:00.${proxima ? ` Próxima: ${proxima}` : ""}` : "La corrida automática está apagada").replace(/\.?$/, ".")} Gasto del mes{" "}
            <b className="text-tinta">{dolares(r.gasto_mes_usd, 3)}</b> de {dolares(r.tope_mes_usd)} · siguiente corrida hasta {dolares(r.estimado_usd, 3)}.
          </p>
        </div>
        {administra && (
          <div className="flex flex-wrap gap-2">
            <Boton variante="secundario" onClick={() => setProbando(true)} disabled={!!enCurso}>
              <FlaskConical className="h-4 w-4" /> Prueba con Excel
            </Boton>
            <Boton onClick={correr} cargando={lanzando || !!enCurso} disabled={r.falta_configurar.length > 0 || !r.vigilados}>
              <Play className="h-4 w-4" /> Correr ahora
            </Boton>
          </div>
        )}
      </Entrada>

      {r.falta_configurar.length > 0 && (
        <Entrada className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-smn-naranja bg-aviso-fondo px-4 py-3 text-sm text-aviso-texto">
          <Settings className="h-5 w-5 shrink-0" />
          <p className="min-w-0 flex-1">
            Para correr el radar falta capturar en Configuración, sección «Radar de precios»: <b>{r.falta_configurar.join(", ")}</b>.
          </p>
          {puede("nucleo.configuracion.administrar") && (
            <Link href="/admin/configuracion" className="font-semibold underline underline-offset-2">
              Ir a Configuración
            </Link>
          )}
        </Entrada>
      )}
      {!r.vigilados && (
        <Entrada className="mb-5 rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-4 text-sm">
          Todavía no se vigila ningún producto.{" "}
          <Link href="/compras/precios/productos" className="font-semibold underline underline-offset-2">
            Elige qué productos vigilar
          </Link>
          .
        </Entrada>
      )}

      <AnimatePresence>
        {enCurso && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-5 overflow-hidden">
            <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 text-sm">
                  <p className="font-semibold">
                    {enCurso.origen === "prueba" ? `Corriendo la prueba con Excel${enCurso.archivo ? ` (${enCurso.archivo})` : ""}.` : `Corriendo el radar con ${enCurso.productos || r.vigilados} productos.`} Puedes salir de esta pantalla.
                  </p>
                  {enCurso.avance?.paso && (
                    <p className="mt-2 font-semibold text-naranja-tinta">
                      Paso {enCurso.avance.paso} de {enCurso.avance.pasos}: {enCurso.avance.titulo}
                    </p>
                  )}
                  <p className="text-tinta">{enCurso.avance?.texto ?? enCurso.fase ?? "Preparando"}</p>
                  <p className="mt-1 text-[13px] text-smn-gris-500">
                    Inició {haceCuanto(enCurso.iniciado_en).toLowerCase()}.
                    {(enCurso.avance?.paso === 1 || enCurso.avance?.paso === 3) && " DataForSEO suele tardar unos minutos en contestar; cada espera tiene un límite de 15 minutos."}
                  </p>
                </div>
                {administra && (
                  <Boton variante="secundario" onClick={() => setPreguntaDetener(true)} cargando={deteniendo} className="px-3 py-1.5">
                    <Square className="h-4 w-4" /> Detener
                  </Boton>
                )}
              </div>
              {(() => {
                const a = enCurso.avance;
                const pct = a?.total ? Math.min(100, Math.round(((a.hechos ?? 0) / a.total) * 100)) : null;
                return (
                  <>
                    <div className="h-2 overflow-hidden rounded-full bg-smn-gris-100">
                      {pct === null ? (
                        <div className="h-full w-1/3 animate-pulse rounded-full bg-smn-naranja" />
                      ) : (
                        <div className="h-full rounded-full bg-smn-naranja transition-all duration-700" style={{ width: `${Math.max(pct, 2)}%` }} />
                      )}
                    </div>
                    {a?.total ? (
                      <p className="mt-1 text-right text-[13px] text-smn-gris-500 tabular-nums">
                        {a.hechos ?? 0} de {a.total} en este paso
                      </p>
                    ) : null}
                  </>
                );
              })()}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {!enCurso && r.ultima_prueba && <UltimaPrueba c={r.ultima_prueba} />}

      <AnimatePresence>{probando && <PruebaExcel cerrar={() => setProbando(false)} lanzada={cargar} />}</AnimatePresence>

      <AnimatePresence>
        {preguntaDetener && (
          <Modal titulo="¿Detener la corrida?" cerrar={() => setPreguntaDetener(false)}>
            <p className="text-sm">Los productos que faltan quedan sin precios en esta corrida. Lo que ya se pagó a DataForSEO no se recupera.</p>
            <div className="mt-5 flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => setPreguntaDetener(false)}>
                Seguir corriendo
              </Boton>
              <Boton onClick={detener}>Detener</Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>

      {r.ultima && (
        <>
          <p className="mb-3 text-sm text-smn-gris-500">
            Última corrida: <b className="text-tinta">{dia(r.ultima.fecha)}, {hora(r.ultima.iniciado_en)}</b>
            {r.ultima.estado !== "completa" && <Insignia className="ml-2 bg-aviso-fondo text-aviso-texto">{textoCorrida(r.ultima)}</Insignia>}
          </p>
          <div className="mb-4 flex gap-2 overflow-x-auto pb-1 sm:flex-wrap sm:overflow-visible" role="group" aria-label="Grupos">
            {tarjetas.map(({ id, texto: t, icono: Icono, color }) => (
              <button
                key={id}
                onClick={() => poner({ grupo: id, p: 1 })}
                aria-pressed={grupo === id}
                className={`flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-semibold whitespace-nowrap transition-colors ${grupo === id ? "border-smn-naranja bg-smn-naranja/10 text-tinta" : "border-smn-gris-100 bg-superficie text-smn-gris-700 hover:border-smn-gris-300"}`}
              >
                {color ? <span className={`h-2.5 w-2.5 rounded-full ${SEMAFORO[color].punto}`} aria-hidden /> : Icono && <Icono className="h-4 w-4" />}
                {t}
                <span className="tabular-nums text-smn-gris-500">{l ? l.conteos[id].toLocaleString("es-MX") : "…"}</span>
              </button>
            ))}
          </div>

          <div className="mb-4 grid grid-cols-2 items-end gap-3 sm:grid-cols-[1fr_auto_auto_auto]">
            <label className="col-span-2 block sm:col-span-1">
              <span className="sr-only">Buscar</span>
              <span className="relative block">
                <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
                <input
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder="Buscar por SKU, descripción o marca"
                  className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 outline-none placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                />
              </span>
            </label>
            <Selector
              etiqueta="Marca"
              valor={marca}
              cambiar={(v) => poner({ marca: v, p: 1 })}
              opciones={[{ valor: "", texto: "Todas" }, ...(l?.marcas ?? []).map((m) => ({ valor: m, texto: m }))]}
              className="min-w-0 sm:w-52"
            />
            <Selector
              etiqueta="Ordenar"
              valor={orden}
              cambiar={(v) => poner({ orden: v, p: 1 })}
              opciones={[
                { valor: "diferencia", texto: "Más caros primero" },
                { valor: "nombre", texto: "Por nombre" },
                { valor: "vendedores", texto: "Más vendedores" },
              ]}
              className="min-w-0 sm:w-48"
            />
            <Boton variante="secundario" onClick={descargar} cargando={descargando} className="col-span-2 py-2.5 sm:col-span-1">
              <Download className="h-4 w-4" /> Excel
            </Boton>
          </div>
        </>
      )}

      {l && l.tiendas.length > 0 && l.conteos.todos > 0 && (
        <p className="mb-3 text-[13px] text-smn-gris-500">
          Tiendas clave en estos {l.conteos.todos.toLocaleString("es-MX")} productos:{" "}
          {l.tiendas.map((t, i) => (
            <span key={t}>
              {i > 0 && " · "}
              <b className="text-tinta">{t}</b> {(l.cobertura[t] ?? 0).toLocaleString("es-MX")}
            </span>
          ))}
        </p>
      )}
      {r.ultima && !l && <Esqueleto className="h-60" />}
      {l && !l.filas.length && r.ultima && (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">Ningún producto con estos filtros.</p>
      )}
      {l && l.filas.length > 0 && (
        <>
          <div className="hidden overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie md:block">
            <table className="w-full text-sm">
              <thead className="bg-smn-gris-100/60 text-left text-[13px] font-medium text-smn-gris-500">
                <tr>
                  <th className="px-4 py-3">Producto</th>
                  <th className="px-4 py-3 text-right">Nuestro precio</th>
                  <th className="px-4 py-3 text-right">Mediana</th>
                  <th className="px-4 py-3 text-right">Diferencia</th>
                  <th className="hidden px-4 py-3 text-right lg:table-cell">Vendedores</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-smn-gris-100">
                {l.filas.map((f) => (
                  <tr key={f.producto_id} onClick={() => abrir(f.producto_id)} className="cursor-pointer transition-colors hover:bg-smn-gris-100/50">
                    <td className="px-4 py-2">
                      <Link href={`/compras/precios/producto/${f.producto_id}`} onClick={(e) => e.stopPropagation()} className="flex items-center gap-3">
                        <Miniatura liga={f.imagen} />
                        <div className="min-w-0">
                          <p className="font-semibold">{f.descripcion ?? f.sku}</p>
                          <p className="text-[13px] text-smn-gris-500">
                            {f.sku} · {f.marca ?? "Sin marca"}
                            <EstadoFila f={f} />
                          </p>
                          <Tiendas t={f.tiendas} />
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {precio(nuestroPrecio(f))}
                      {f.base === "tienda" && <span className="block text-[13px] text-smn-gris-500">tienda en línea</span>}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">{precio(f.mediana)}</td>
                    <td className="px-4 py-3 text-right">
                      <Diferencia valor={f.dif_lista_mediana_pct} alerta={Number(f.limite_pct)} />
                    </td>
                    <td className="hidden px-4 py-3 text-right tabular-nums lg:table-cell">{f.vendedores || "—"}</td>
                    <td className="pr-3 text-smn-gris-500">
                      <ChevronRight className="h-4 w-4" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-2 md:hidden">
            {l.filas.map((f) => (
              <li key={f.producto_id}>
                <Link href={`/compras/precios/producto/${f.producto_id}`} className="flex w-full gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-left">
                  <Miniatura liga={f.imagen} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">{f.descripcion ?? f.sku}</span>
                    <span className="block text-[13px] text-smn-gris-500">
                      {f.sku} · {f.marca ?? "Sin marca"}
                      <EstadoFila f={f} />
                    </span>
                    <Tiendas t={f.tiendas} />
                    <span className="mt-2 flex items-center justify-between gap-2 text-sm tabular-nums">
                      <span>
                        {precio(nuestroPrecio(f))}
                        {f.base === "tienda" && " (tienda)"} <span className="text-smn-gris-500">vs {precio(f.mediana)}</span>
                      </span>
                      <Diferencia valor={f.dif_lista_mediana_pct} alerta={Number(f.limite_pct)} />
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
            <span className="text-smn-gris-500">
              {l.total.toLocaleString("es-MX")} productos{paginas > 1 && ` · página ${num} de ${paginas}`}
            </span>
            {paginas > 1 && (
              <div className="flex gap-2">
                <Boton variante="secundario" onClick={() => poner({ p: num - 1 })} disabled={num <= 1}>
                  Anterior
                </Boton>
                <Boton variante="secundario" onClick={() => poner({ p: num + 1 })} disabled={num >= paginas}>
                  Siguiente
                </Boton>
              </div>
            )}
          </div>
          <p className="mt-3 text-[13px] text-smn-gris-500">{`Diferencia = nuestro precio lista con impuestos contra la mediana del mercado (si no hay precio lista, el de la tienda en línea). Positivo = estamos más caros. Verde: igual o más baratos; amarillo: más caros hasta el límite (${alerta} % general o el propio del producto); rojo: arriba del límite. «Necesitan revisión»: Google no trajo una coincidencia confiable. Debajo de cada producto, el precio de cada tienda clave donde apareció (de su sitio o de Google). «Excel» descarga todos los precios por vendedor.`}</p>
        </>
      )}
    </>
  );
}

function Tiendas({ t }: { t: Record<string, string> }) {
  const lista = Object.entries(t ?? {});
  if (!lista.length) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {lista.map(([n, p]) => (
        <span key={n} className="rounded-full bg-smn-gris-100 px-2 py-0.5 text-[13px] font-semibold whitespace-nowrap text-smn-gris-700 tabular-nums">
          {n} {precio(p)}
        </span>
      ))}
    </span>
  );
}

function EstadoFila({ f }: { f: Fila }) {
  if (f.estado !== "con_precios")
    return <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">{TEXTO_FILA[f.estado]}</Insignia>;
  const Icono = f.coincidencia ? ICONO_COINCIDENCIA[f.coincidencia] : null;
  return Icono && f.coincidencia === "ia" ? (
    <span className="ml-2 inline-flex items-center gap-0.5" title="La coincidencia la decidió la IA">
      <Icono className="h-3 w-3" /> IA
    </span>
  ) : null;
}
