"use client";
// Centro de datos · Catálogo de productos: un solo catálogo por SKU, cargado del API de artículos de SMN
// (después también de la tienda en línea y de la base de Sistemas en Azure). Datos reales, sin ejemplos.

import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Archive, ChevronLeft, ChevronRight, CircleAlert, Clock, Download, ExternalLink, ImageOff, Package, Search, Settings, Store } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, fechaLocal, haceCuanto, mensajeDe, pesos } from "@/lib/api";
import { FUENTES, type Carga, type EstadoCatalogo, type EstadoProductos, type PaginaProductos, type ProductoDetalle } from "@/lib/datos";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { useSesion } from "@/componentes/sesion";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";

const DIAS = ["", "lun", "mar", "mié", "jue", "vie", "sáb", "dom"];
const POR_PAGINA = 50;

const precio = (v: string | null) => (v === null ? "—" : pesos(v));
const pct = (v: string | null) => (v === null ? "—" : `${Number(v).toLocaleString("es-MX", { maximumFractionDigits: 2 })} %`);

export default function Productos() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const administra = puede("datos.catalogo.administrar");
  const [estado, setEstado] = useState<EstadoCatalogo | null>(null);
  const [pagina, setPagina] = useState<PaginaProductos | null>(null);
  const [filtros, setFiltros] = useState<{ departamentos: string[]; marcas: string[] }>({ departamentos: [], marcas: [] });
  const [texto, setTexto] = useState("");
  const [q, setQ] = useState("");
  const [departamento, setDepartamento] = useState("");
  const [marca, setMarca] = useState("");
  const [ver, setVer] = useState<EstadoProductos>("activos");
  const [num, setNum] = useState(1);
  const [detalle, setDetalle] = useState<number | null>(null);
  const [lanzando, setLanzando] = useState<"API" | "TIENDA" | null>(null);
  const enCursoAntes = useRef(false);

  const cargarEstado = useCallback(() => {
    api<EstadoCatalogo>("/api/datos/catalogo").then(setEstado).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);
  const cargarFiltros = useCallback(() => {
    api<{ departamentos: string[]; marcas: string[] }>("/api/datos/productos/filtros").then(setFiltros).catch(() => {});
  }, []);
  const cargarProductos = useCallback(() => {
    const p = new URLSearchParams({ q, departamento, marca, estado: ver, pagina: String(num), por_pagina: String(POR_PAGINA) });
    api<PaginaProductos>(`/api/datos/productos?${p}`).then(setPagina).catch((e) => avisar(mensajeDe(e), "info"));
  }, [q, departamento, marca, ver, num, avisar]);

  useEffect(cargarEstado, [cargarEstado]);
  useEffect(cargarFiltros, [cargarFiltros]);
  useEffect(cargarProductos, [cargarProductos]);

  // Búsqueda con una pausa corta mientras se escribe
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(texto.trim());
      setNum(1);
    }, 300);
    return () => clearTimeout(t);
  }, [texto]);

  // Mientras hay una carga en curso se revisa cada 3 segundos; al terminar se refresca todo
  const enCurso = estado?.en_curso;
  useEffect(() => {
    if (enCurso) {
      enCursoAntes.current = true;
      const t = setTimeout(cargarEstado, 3000);
      return () => clearTimeout(t);
    }
    if (enCursoAntes.current && estado) {
      enCursoAntes.current = false;
      const ultima = estado.cargas[0];
      avisar(ultima?.estado === "completa" ? "Catálogo cargado" : "La carga no terminó; revisa el detalle abajo", ultima?.estado === "completa" ? "exito" : "info");
      cargarProductos();
      cargarFiltros();
    }
  }, [enCurso, estado, cargarEstado, cargarProductos, cargarFiltros, avisar]);

  const lanzar = async (fuente: "API" | "TIENDA") => {
    setLanzando(fuente);
    try {
      await api(`/api/datos/catalogo/cargar?fuente=${fuente}`, { metodo: "POST" });
      avisar(fuente === "API" ? "Carga del API iniciada" : "Carga de la tienda en línea iniciada", "exito");
      cargarEstado();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(null);
    }
  };

  const filtrar = (v: EstadoProductos) => {
    setVer(v);
    setNum(1);
  };

  const totales = estado?.totales;
  const tarjetas: { id: EstadoProductos; texto: string; valor?: number; icono: typeof Package }[] = [
    { id: "activos", texto: "Productos activos", valor: totales?.activos, icono: Package },
    { id: "diferencias", texto: "Con diferencias entre fuentes", valor: totales?.con_diferencias, icono: AlertTriangle },
    { id: "incompletos", texto: "Con datos incompletos", valor: totales?.incompletos, icono: CircleAlert },
    { id: "archivados", texto: "Archivados", valor: totales?.archivados, icono: Archive },
  ];
  const paginas = pagina ? Math.max(1, Math.ceil(pagina.total / pagina.por_pagina)) : 1;

  return (
    <>
      <Encabezado
        titulo="Catálogo de productos"
        descripcion="Un solo catálogo por SKU para toda la plataforma, armado con el API de artículos de SMN y la tienda en línea."
        accion={
          administra && (
            <div className="flex flex-wrap gap-2">
              <Boton onClick={() => lanzar("API")} cargando={lanzando === "API" || enCurso?.fuente === "API"} disabled={!estado || !!enCurso || estado.falta_configurar.length > 0}>
                <Download className="h-4 w-4" /> Cargar API
              </Boton>
              <Boton variante="secundario" onClick={() => lanzar("TIENDA")} cargando={lanzando === "TIENDA" || enCurso?.fuente === "TIENDA"} disabled={!estado || !!enCurso || !estado.tienda_url}>
                <Store className="h-4 w-4" /> Cargar tienda en línea
              </Boton>
            </div>
          )
        }
      />

      {estado && estado.falta_configurar.length > 0 && (
        <Entrada className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-dashed border-smn-naranja bg-aviso-fondo px-4 py-3 text-sm text-aviso-texto">
          <Settings className="h-5 w-5 shrink-0" />
          <p className="min-w-0 flex-1">
            Para cargar el catálogo falta capturar en Configuración, sección «Catálogo de productos»: <b>{estado.falta_configurar.join(", ")}</b>.
          </p>
          {puede("nucleo.configuracion.administrar") && (
            <Link href="/admin/configuracion" className="font-semibold underline underline-offset-2">
              Ir a Configuración
            </Link>
          )}
        </Entrada>
      )}

      <AnimatePresence>{enCurso && <Progreso carga={enCurso} />}</AnimatePresence>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tarjetas.map(({ id, texto: t, valor, icono: Icono }, i) => (
          <Entrada key={id} retraso={i * 0.04}>
            <button
              onClick={() => filtrar(id)}
              aria-pressed={ver === id}
              className={`w-full rounded-2xl border bg-superficie p-4 text-left transition-colors ${ver === id ? "border-smn-naranja ring-2 ring-smn-naranja/25" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
            >
              <Icono className={`mb-2 h-5 w-5 ${ver === id ? "text-smn-naranja" : "text-smn-gris-500"}`} />
              <p className="text-2xl font-semibold tabular-nums">{valor === undefined ? "…" : valor.toLocaleString("es-MX")}</p>
              <p className="text-sm text-smn-gris-500">{t}</p>
            </button>
          </Entrada>
        ))}
      </div>

      {totales && totales.activos > 0 && (
        <p className="-mt-2 mb-5 text-sm text-smn-gris-500">
          De los activos, <b className="text-tinta">{totales.en_api.toLocaleString("es-MX")}</b> vienen del API de artículos,{" "}
          <b className="text-tinta">{totales.en_tienda.toLocaleString("es-MX")}</b> están en la tienda en línea y{" "}
          <b className="text-tinta">{totales.con_imagen.toLocaleString("es-MX")}</b> tienen imagen.
        </p>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Buscar</span>
          <span className="relative block">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="SKU, descripción, marca, proveedor o código de barras"
              className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 outline-none placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
            />
          </span>
        </label>
        <Selector
          etiqueta="Departamento"
          valor={departamento}
          cambiar={(v) => {
            setDepartamento(v);
            setNum(1);
          }}
          opciones={[{ valor: "", texto: "Todos" }, ...filtros.departamentos.map((d) => ({ valor: d, texto: d }))]}
          className="sm:w-56"
        />
        <Selector
          etiqueta="Marca"
          valor={marca}
          cambiar={(v) => {
            setMarca(v);
            setNum(1);
          }}
          opciones={[{ valor: "", texto: "Todas" }, ...filtros.marcas.map((m) => ({ valor: m, texto: m }))]}
          className="sm:w-56"
        />
      </div>

      {!pagina ? (
        <Esqueleto className="h-72" />
      ) : !pagina.productos.length ? (
        <div className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-6 py-12 text-center">
          <Package className="mx-auto mb-3 h-10 w-10 text-smn-gris-500" />
          <p className="font-semibold">{totales?.productos ? "Ningún producto coincide" : "El catálogo está vacío"}</p>
          <p className="mt-1 text-sm text-smn-gris-500">
            {totales?.productos ? "Prueba con otra búsqueda o quita los filtros." : "Se llena con la primera carga del API de artículos."}
          </p>
        </div>
      ) : (
        <>
          {/* Escritorio: tabla */}
          <div className="hidden overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie md:block">
            <table className="w-full text-sm">
              <thead className="bg-smn-gris-100/60 text-left text-[13px] font-medium text-smn-gris-500">
                <tr>
                  <th className="w-16 px-4 py-3">
                    <span className="sr-only">Imagen</span>
                  </th>
                  <th className="px-4 py-3">SKU</th>
                  <th className="px-4 py-3">Descripción</th>
                  <th className="hidden px-4 py-3 lg:table-cell">Departamento</th>
                  <th className="px-4 py-3 text-right">Precio lista</th>
                  <th className="px-4 py-3 text-right">Membresía</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-smn-gris-100">
                {pagina.productos.map((p) => (
                  <tr key={p.id} onClick={() => setDetalle(p.id)} className="cursor-pointer transition-colors hover:bg-smn-gris-100/50">
                    <td className="px-4 py-2">
                      <Miniatura liga={p.liga_imagen} />
                    </td>
                    <td className="px-4 py-3 font-mono text-[13px] whitespace-nowrap">{p.sku}</td>
                    <td className="px-4 py-3">
                      <p className="font-semibold">{p.descripcion ?? "Sin descripción"}</p>
                      <p className="text-[13px] text-smn-gris-500">
                        {p.marca ?? "Sin marca"}
                        <Marcas p={p} />
                      </p>
                    </td>
                    <td className="hidden px-4 py-3 text-smn-gris-700 lg:table-cell">{p.departamento ?? "—"}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">{precio(p.precio_lista_con_impuestos)}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">{precio(p.precio_membresia_con_impuestos)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Celular: tarjetas */}
          <ul className="space-y-2 md:hidden">
            {pagina.productos.map((p) => (
              <li key={p.id}>
                <button onClick={() => setDetalle(p.id)} className="flex w-full gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-left">
                  <Miniatura liga={p.liga_imagen} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-[13px] text-smn-gris-500">{p.sku}</span>
                    <span className="block font-semibold">{p.descripcion ?? "Sin descripción"}</span>
                    <span className="block text-sm text-smn-gris-500">
                      {p.marca ?? "Sin marca"}
                      <Marcas p={p} />
                    </span>
                    <span className="mt-2 block text-sm tabular-nums">
                      Lista {precio(p.precio_lista_con_impuestos)} · Membresía {precio(p.precio_membresia_con_impuestos)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[13px] text-smn-gris-500">Precios con IVA e IEPS. Toca un producto para ver su detalle.</p>

          <div className="mt-4 flex items-center justify-between gap-3 text-sm">
            <span className="text-smn-gris-500">
              {pagina.total.toLocaleString("es-MX")} productos · página {pagina.pagina} de {paginas}
            </span>
            <div className="flex gap-2">
              <Boton variante="secundario" onClick={() => setNum(num - 1)} disabled={num <= 1} aria-label="Página anterior">
                <ChevronLeft className="h-4 w-4" />
              </Boton>
              <Boton variante="secundario" onClick={() => setNum(num + 1)} disabled={num >= paginas} aria-label="Página siguiente">
                <ChevronRight className="h-4 w-4" />
              </Boton>
            </div>
          </div>
        </>
      )}

      {estado && <Cargas estado={estado} />}

      <AnimatePresence>{detalle !== null && <Detalle id={detalle} cerrar={() => setDetalle(null)} />}</AnimatePresence>
    </>
  );
}

function Miniatura({ liga, grande }: { liga: string | null; grande?: boolean }) {
  const [fallo, setFallo] = useState(false);
  const tam = grande ? "h-48 w-full" : "h-12 w-12 shrink-0";
  if (!liga || fallo)
    return (
      <span className={`${tam} flex items-center justify-center rounded-xl bg-smn-gris-100/60 text-smn-gris-500`} title="Sin imagen">
        <ImageOff className={grande ? "h-8 w-8" : "h-4 w-4"} />
      </span>
    );
  return (
    // eslint-disable-next-line @next/next/no-img-element -- imágenes externas de la tienda en línea
    <img src={liga} alt="" loading="lazy" onError={() => setFallo(true)} className={`${tam} rounded-xl bg-white object-contain p-1`} />
  );
}

function Marcas({ p }: { p: { activo: boolean; con_diferencias: boolean; datos_incompletos: boolean } }) {
  return (
    <>
      {!p.activo && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">Archivado</Insignia>}
      {p.con_diferencias && <Insignia className="ml-2 bg-aviso-fondo text-aviso-texto">Diferencias</Insignia>}
      {p.datos_incompletos && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">Incompleto</Insignia>}
    </>
  );
}

function Progreso({ carga }: { carga: Carga }) {
  // En el API el avance es por artículo; en la tienda, por producto leído (cada producto puede traer varias variantes)
  const hechos = carga.fuente === "TIENDA" ? carga.paginas : carga.leidos + carga.invalidos;
  const avance = carga.total_fuente ? Math.min(100, Math.round((hechos / carga.total_fuente) * 100)) : null;
  return (
    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-5 overflow-hidden">
      <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
        <p className="mb-2 text-sm font-semibold">
          {carga.fuente === "TIENDA"
            ? carga.total_fuente
              ? `Leyendo la tienda en línea… ${hechos.toLocaleString("es-MX")} de ${carga.total_fuente.toLocaleString("es-MX")} productos`
              : "Buscando los productos de la tienda en línea…"
            : `Cargando del API de artículos… ${hechos.toLocaleString("es-MX")}${carga.total_fuente ? ` de ${carga.total_fuente.toLocaleString("es-MX")}` : ""} artículos`}
        </p>
        <div className="h-2 overflow-hidden rounded-full bg-smn-gris-100">
          {avance === null ? (
            <div className="h-full w-1/3 animate-pulse rounded-full bg-smn-naranja" />
          ) : (
            <motion.div className="h-full rounded-full bg-smn-naranja" animate={{ width: `${avance}%` }} transition={{ duration: 0.4 }} />
          )}
        </div>
      </div>
    </motion.div>
  );
}

function Cargas({ estado }: { estado: EstadoCatalogo }) {
  const dias = estado.dias_semana.length === 7 ? "todos los días" : estado.dias_semana.map((d) => DIAS[d]).join(", ");
  return (
    <section className="mt-10">
      <h2 className="text-lg font-semibold">Cargas</h2>
      <p className="mb-3 text-sm text-smn-gris-500">
        {estado.automatico
          ? `Se carga sola ${dias} desde las ${estado.hora}:00 (${estado.zona_horaria}): primero el API y después la tienda en línea. Si una falla, reintenta cada 30 minutos hasta 3 veces.`
          : "La carga automática está apagada; solo se carga con el botón."}{" "}
        Un producto que deja de venir en una carga completa queda archivado; nunca se borra.
      </p>
      {!estado.cargas.length ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-6 text-center text-sm text-smn-gris-500">Todavía no hay cargas.</p>
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {estado.cargas.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start gap-x-4 gap-y-1 p-4 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {FUENTES[c.fuente] ?? c.fuente}{" "}
                  <Insignia
                    className={`ml-1 ${c.estado === "completa" ? "bg-tinta text-superficie" : c.estado === "fallida" ? "bg-red-500/10 text-red-700 dark:text-red-400" : "bg-aviso-fondo text-aviso-texto"}`}
                  >
                    {c.estado === "completa" ? "Completa" : c.estado === "fallida" ? "Falló" : "En curso"}
                  </Insignia>
                </p>
                <p className="text-smn-gris-500">
                  <Clock className="mr-1 inline h-3.5 w-3.5" />
                  {fechaLocal(c.inicio_en)} · {c.disparada_por === "manual" ? `a mano${c.usuario ? ` por ${c.usuario}` : ""}` : "programada"}
                  {c.fin_en && ` · ${Math.max(1, Math.round((new Date(c.fin_en).getTime() - new Date(c.inicio_en).getTime()) / 1000))} s`}
                </p>
                {c.error && <p className="mt-1 text-red-700 dark:text-red-400">{c.error}</p>}
              </div>
              <p className="text-smn-gris-700 tabular-nums">
                {c.fuente === "TIENDA" && `${c.paginas.toLocaleString("es-MX")} productos · `}
                {c.leidos.toLocaleString("es-MX")} {c.fuente === "TIENDA" ? "SKU" : "leídos"} · {c.creados} nuevos · {c.actualizados} actualizados · {c.precios_cambiados} con precio nuevo
                {c.ausentes > 0 && ` · ${c.ausentes} archivados`}
                {c.invalidos > 0 && ` · ${c.invalidos} inválidos`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const CAMPOS: [keyof ProductoDetalle, string][] = [
  ["marca", "Marca"],
  ["departamento", "Departamento"],
  ["rama", "Rama"],
  ["subcategoria", "Subcategoría"],
  ["segmento", "Segmento"],
  ["clasificacion", "Clasificación"],
  ["codigo_proveedor", "Código de proveedor"],
  ["nombre_proveedor", "Proveedor"],
  ["codigo_barras", "Código de barras"],
];

function Detalle({ id, cerrar }: { id: number; cerrar: () => void }) {
  const avisar = useAvisos();
  const [p, setP] = useState<ProductoDetalle | null>(null);
  const [crudo, setCrudo] = useState<string | null>(null);
  useEffect(() => {
    api<ProductoDetalle>(`/api/datos/productos/${id}`).then(setP).catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar]);

  return (
    <Modal titulo={p ? p.descripcion ?? p.sku : "Producto"} cerrar={cerrar} ancho="max-w-2xl">
      {!p ? (
        <Esqueleto className="h-64" />
      ) : (
        <div className="space-y-5 text-sm">
          <Miniatura liga={p.liga_imagen} grande />
          <p className="text-smn-gris-500">
            SKU <span className="font-mono text-tinta">{p.sku}</span> · {FUENTES[p.origen] ?? p.origen} · actualizado {haceCuanto(p.actualizado_en).toLowerCase()}
            <Marcas p={p} />
          </p>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Precio lista", p.precio_lista_con_impuestos, p.precio_lista],
              ["Membresía", p.precio_membresia_con_impuestos, p.precio_membresia],
            ].map(([t, con, sin]) => (
              <div key={t} className="col-span-1 rounded-xl bg-smn-gris-100/60 p-3 sm:col-span-2">
                <p className="text-[13px] font-medium text-smn-gris-500">{t}</p>
                <p className="text-lg font-semibold tabular-nums">{precio(con)}</p>
                <p className="text-[13px] text-smn-gris-500">sin impuestos {precio(sin)}</p>
              </div>
            ))}
            <div className="rounded-xl bg-smn-gris-100/60 p-3 sm:col-span-2">
              <p className="text-[13px] font-medium text-smn-gris-500">IVA</p>
              <p className="font-semibold tabular-nums">{pct(p.iva_pct)}</p>
            </div>
            <div className="rounded-xl bg-smn-gris-100/60 p-3 sm:col-span-2">
              <p className="text-[13px] font-medium text-smn-gris-500">IEPS</p>
              <p className="font-semibold tabular-nums">{pct(p.ieps_pct)}</p>
            </div>
          </div>
          {(p.precio_tienda_en_linea !== null || p.liga_producto) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-smn-gris-100 p-3">
              <Store className="h-4 w-4 text-smn-gris-500" />
              <span>
                Tienda en línea: <b className="tabular-nums">{precio(p.precio_tienda_en_linea)}</b>
                {p.disponible_en_linea !== null && <span className="text-smn-gris-500"> · {p.disponible_en_linea ? "disponible" : "agotado"}</span>}
              </span>
              {p.liga_producto && (
                <a href={p.liga_producto} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 font-semibold underline underline-offset-2">
                  Ver en la tienda <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          )}
          {(p.iva_pct === null || p.ieps_pct === null) && (
            <p className="text-[13px] text-aviso-texto">Falta una tasa de impuestos en la fuente, así que no se calcula el precio con impuestos.</p>
          )}

          <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {CAMPOS.map(([campo, t]) => (
              <div key={campo} className="flex justify-between gap-3 border-b border-smn-gris-100 pb-1.5">
                <dt className="text-smn-gris-500">{t}</dt>
                <dd className="text-right font-semibold">{(p[campo] as string | null) ?? "—"}</dd>
              </div>
            ))}
          </dl>

          {p.diferencias.length > 0 && (
            <div className="rounded-xl border border-smn-naranja/40 bg-aviso-fondo p-3 text-aviso-texto">
              <p className="mb-1 font-semibold">Las fuentes no coinciden</p>
              {p.diferencias.map((d) => (
                <p key={d.campo}>
                  {d.campo}:{" "}
                  {Object.entries(d.valores)
                    .map(([f, v]) => `${FUENTES[f] ?? f} dice «${v}»`)
                    .join("; ")}
                </p>
              ))}
            </div>
          )}

          <div>
            <h3 className="mb-2 font-semibold">Historial de precios</h3>
            <p className="mb-2 text-[13px] text-smn-gris-500">Una fila cada vez que cambia un precio o una tasa. Lista y membresía sin impuestos; el de la tienda en línea, como se publica.</p>
            <div className="overflow-x-auto rounded-xl border border-smn-gris-100">
              <table className="w-full text-[13px]">
                <thead className="bg-smn-gris-100/60 text-left font-semibold text-smn-gris-500">
                  <tr>
                    <th className="px-3 py-2">Desde</th>
                    <th className="px-3 py-2 text-right">Lista</th>
                    <th className="px-3 py-2 text-right">Membresía</th>
                    <th className="px-3 py-2 text-right">IVA</th>
                    <th className="px-3 py-2 text-right">IEPS</th>
                    <th className="px-3 py-2 text-right">Tienda en línea</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-smn-gris-100">
                  {p.historial.map((h) => (
                    <tr key={h.vigente_desde}>
                      <td className="px-3 py-2 whitespace-nowrap">{fechaLocal(h.vigente_desde)}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{precio(h.precio_lista)}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{precio(h.precio_membresia)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{pct(h.iva_pct)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{pct(h.ieps_pct)}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap tabular-nums">{precio(h.precio_tienda_en_linea)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h3 className="mb-2 font-semibold">Fuentes</h3>
            <ul className="space-y-2">
              {p.fuentes.map((f) => (
                <li key={f.fuente} className="rounded-xl border border-smn-gris-100 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-semibold">
                      {FUENTES[f.fuente] ?? f.fuente}
                      {!f.presente && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">Ya no viene</Insignia>}
                    </p>
                    <button onClick={() => setCrudo(crudo === f.fuente ? null : f.fuente)} className="text-[13px] font-medium text-smn-gris-500 underline underline-offset-2 hover:text-tinta">
                      {crudo === f.fuente ? "Ocultar lo que llegó" : "Ver lo que llegó"}
                    </button>
                  </div>
                  <p className="text-[13px] text-smn-gris-500">Visto por última vez {fechaLocal(f.visto_por_ultima_vez_en)}</p>
                  {crudo === f.fuente && (
                    <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-smn-gris-100/60 p-2 text-[13px] leading-relaxed">{JSON.stringify(f.datos, null, 2)}</pre>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Modal>
  );
}
