"use client";
// Radar de precios · Productos vigilados: qué productos del catálogo se comparan contra el mercado.

import { Eye, EyeOff, Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import type { ProductoCatalogo } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Entrada, Esqueleto, Selector } from "@/componentes/ui";
import { Diferencia, Miniatura, precio } from "../piezas";

type Lista = { total: number; productos: ProductoCatalogo[] };
type Clase = { clase: string; productos: number; vigilados: number };

const nombreClase = (c: string) => (c === "SIN" ? "Sin clase" : c);

export default function Vigilados() {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const administra = puede("compras.precios.administrar");
  const [vigilados, setVigilados] = useState<Lista | null>(null);
  const [filtroLista, setFiltroLista] = useState("");
  const [texto, setTexto] = useState("");
  const [encontrados, setEncontrados] = useState<Lista | null>(null);
  const [marcas, setMarcas] = useState<string[]>([]);
  const [marca, setMarca] = useState("");
  const [ocupado, setOcupado] = useState<number | string | null>(null);
  const [clases, setClases] = useState<Clase[]>([]);
  const [clase, setClase] = useState(""); // para buscar y agregar
  const [claseLista, setClaseLista] = useState(""); // para filtrar los vigilados
  const router = useRouter();

  const cargar = useCallback(() => {
    const extra = claseLista ? `&clase=${encodeURIComponent(claseLista)}` : "";
    api<Lista>(`/api/compras/precios/catalogo?solo_vigilados=true${extra}`)
      .then(setVigilados)
      .catch((e) => avisar(mensajeDe(e), "info"));
    api<Clase[]>("/api/compras/precios/vigilados/clases")
      .then(setClases)
      .catch(() => {});
  }, [avisar, claseLista]);
  useEffect(cargar, [cargar]);
  const opcionesClase = (vacio: string, conVigilados: boolean) => [
    { valor: "", texto: vacio },
    ...clases.map((c) => ({
      valor: c.clase,
      texto: conVigilados
        ? `${nombreClase(c.clase)} · ${c.productos.toLocaleString("es-MX")} (${c.vigilados.toLocaleString("es-MX")} vigilados)`
        : `${nombreClase(c.clase)} · ${c.vigilados.toLocaleString("es-MX")}`,
    })),
  ];
  const deClase = clases.find((c) => c.clase === clase);
  useEffect(() => {
    if (administra && puede("datos.productos.ver"))
      api<{ marcas: string[] }>("/api/datos/productos/filtros")
        .then((f) => setMarcas(f.marcas))
        .catch(() => {});
  }, [administra, puede]);

  useEffect(() => {
    const q = texto.trim();
    if (q.length < 2 && !clase) return setEncontrados(null);
    const t = setTimeout(() => {
      const extra = clase ? `&clase=${encodeURIComponent(clase)}` : "";
      api<Lista>(
        `/api/compras/precios/catalogo?q=${encodeURIComponent(q)}${extra}`,
      )
        .then(setEncontrados)
        .catch((e) => avisar(mensajeDe(e), "info"));
    }, 300);
    return () => clearTimeout(t);
  }, [texto, clase, avisar]);

  const agregar = async (
    cuerpo: { producto_ids?: number[]; marca?: string; clase?: string },
    clave: number | string,
  ) => {
    setOcupado(clave);
    try {
      const r = await api<{ agregados: number }>(
        "/api/compras/precios/vigilados",
        { cuerpo },
      );
      avisar(
        r.agregados === 1
          ? "Se vigila 1 producto más"
          : `Se vigilan ${r.agregados} productos más`,
        "exito",
      );
      cargar();
      setEncontrados(
        (e) =>
          e && {
            ...e,
            productos: e.productos.map((p) =>
              cuerpo.producto_ids?.includes(p.producto_id) ||
              (cuerpo.clase && p.clasificacion === cuerpo.clase)
                ? { ...p, vigilado: true }
                : p,
            ),
          },
      );
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  const quitar = async (id: number) => {
    setOcupado(id);
    try {
      await api(`/api/compras/precios/vigilados/${id}`, { metodo: "DELETE" });
      avisar("Ya no se vigila; su historial se conserva", "exito");
      cargar();
      setEncontrados(
        (e) =>
          e && {
            ...e,
            productos: e.productos.map((p) =>
              p.producto_id === id ? { ...p, vigilado: false } : p,
            ),
          },
      );
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  const q = filtroLista.trim().toLowerCase();
  const lista = (vigilados?.productos ?? []).filter(
    (p) =>
      !q ||
      [p.sku, p.descripcion, p.marca].some((v) => v?.toLowerCase().includes(q)),
  );

  return (
    <>
      <p className="mb-5 max-w-2xl text-sm text-smn-gris-500">
        Cada producto vigilado se busca en Google Shopping en cada corrida y
        cuesta créditos de DataForSEO. La primera vez se paga la búsqueda;
        después solo la consulta de vendedores.
      </p>

      {administra && (
        <Entrada className="mb-8 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <h2 className="mb-3 font-semibold">Agregar productos</h2>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem] sm:items-end">
            <label className="block">
              <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">
                Buscar en el catálogo
              </span>
              <span className="relative block">
                <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
                <input
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder="SKU, descripción, marca o código de barras"
                  className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 outline-none placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                />
              </span>
            </label>
            <Selector
              etiqueta="Categoría"
              valor={clase}
              cambiar={setClase}
              opciones={opcionesClase("Todas", true)}
            />
            {marcas.length > 0 && (
              <div className="flex items-end gap-2 sm:col-span-2">
                <Selector
                  etiqueta="O toda una marca"
                  valor={marca}
                  cambiar={setMarca}
                  opciones={[
                    { valor: "", texto: "Elige una marca" },
                    ...marcas.map((m) => ({ valor: m, texto: m })),
                  ]}
                  className="min-w-0 sm:w-56"
                />
                <Boton
                  onClick={() => agregar({ marca }, "marca")}
                  disabled={!marca}
                  cargando={ocupado === "marca"}
                >
                  <Plus className="h-4 w-4" /> Agregar
                </Boton>
              </div>
            )}
          </div>
          {encontrados && (
            <div className="mt-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-[13px] text-smn-gris-500">
                  {encontrados.total > encontrados.productos.length
                    ? `Primeros ${encontrados.productos.length} de ${encontrados.total.toLocaleString("es-MX")}`
                    : `${encontrados.total.toLocaleString("es-MX")} encontrados`}
                  {clase && ` en ${nombreClase(clase)}`}
                </p>
                {deClase &&
                  !texto.trim() &&
                  deClase.productos > deClase.vigilados && (
                    <Boton
                      variante="secundario"
                      className="px-3 py-1.5"
                      onClick={() => agregar({ clase }, "clase")}
                      cargando={ocupado === "clase"}
                    >
                      <Plus className="h-4 w-4" /> Vigilar los{" "}
                      {(deClase.productos - deClase.vigilados).toLocaleString(
                        "es-MX",
                      )}{" "}
                      de {nombreClase(clase)} que faltan
                    </Boton>
                  )}
              </div>
              <ul className="max-h-96 divide-y divide-smn-gris-100 overflow-y-auto rounded-2xl border border-smn-gris-100">
                {encontrados.productos.map((p) => (
                  <Renglon key={p.producto_id} p={p}>
                    {p.vigilado ? (
                      <span className="flex items-center gap-1 text-[13px] font-medium text-smn-gris-500">
                        <Eye className="h-4 w-4" /> Vigilado
                      </span>
                    ) : (
                      <Boton
                        variante="secundario"
                        className="px-3 py-1.5"
                        onClick={() =>
                          agregar(
                            { producto_ids: [p.producto_id] },
                            p.producto_id,
                          )
                        }
                        cargando={ocupado === p.producto_id}
                      >
                        <Plus className="h-4 w-4" /> Vigilar
                      </Boton>
                    )}
                  </Renglon>
                ))}
              </ul>
            </div>
          )}
        </Entrada>
      )}

      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-lg font-semibold">
          Vigilados{" "}
          {vigilados && (
            <span className="text-smn-gris-500">
              ({vigilados.total.toLocaleString("es-MX")})
            </span>
          )}
        </h2>
        <div className="flex w-full flex-wrap items-end gap-2 sm:w-auto">
          {clases.some((c) => c.vigilados > 0) && (
            <Selector
              etiqueta="Categoría"
              valor={claseLista}
              cambiar={setClaseLista}
              opciones={opcionesClase("Todas", false).filter(
                (o, i) =>
                  i === 0 ||
                  (clases[i - 1]?.vigilados ?? 0) > 0 ||
                  o.valor === claseLista,
              )}
              className="w-full sm:w-44"
            />
          )}
          {vigilados && vigilados.total > 10 && (
            <input
              value={filtroLista}
              onChange={(e) => setFiltroLista(e.target.value)}
              placeholder="Filtrar la lista"
              className="h-11 w-full rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-sm outline-none focus:border-smn-naranja sm:w-64"
            />
          )}
        </div>
      </div>
      {!vigilados ? (
        <Esqueleto className="h-48" />
      ) : !vigilados.total ? (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">
          {claseLista
            ? `No se vigila ningún producto de ${nombreClase(claseLista)}.`
            : "Todavía no se vigila ningún producto. Búscalos arriba o agrega toda una marca o categoría."}
        </p>
      ) : (
        <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie">
          {lista.map((p) => (
            <Renglon
              key={p.producto_id}
              p={p}
              abrir={() =>
                router.push(`/compras/precios/producto/${p.producto_id}`)
              }
            >
              <span className="flex flex-col items-end gap-0.5 text-right">
                {p.color ? (
                  <Diferencia valor={p.dif_pct} alerta={Number(p.limite_pct)} />
                ) : (
                  <span className="text-[13px] text-smn-gris-500">
                    Sin comparación
                  </span>
                )}
                <span className="text-[13px] whitespace-nowrap text-smn-gris-500">
                  Límite {Number(p.limite_pct)} %
                  {p.limite_propio_pct !== null && " propio"}
                </span>
              </span>
              {administra && (
                <Boton
                  variante="fantasma"
                  className="px-3 py-1.5"
                  onClick={() => quitar(p.producto_id)}
                  cargando={ocupado === p.producto_id}
                  aria-label={`Dejar de vigilar ${p.descripcion ?? p.sku}`}
                >
                  <EyeOff className="h-4 w-4" />{" "}
                  <span className="hidden sm:inline">Dejar de vigilar</span>
                </Boton>
              )}
            </Renglon>
          ))}
        </ul>
      )}
    </>
  );
}

function Renglon({
  p,
  abrir,
  children,
}: {
  p: ProductoCatalogo;
  abrir?: () => void;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <button
        onClick={abrir}
        disabled={!abrir}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <Miniatura liga={p.imagen} />
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            {p.clasificacion && (
              <span className="shrink-0 rounded-md bg-smn-gris-100 px-1.5 py-0.5 text-[12px] font-semibold text-smn-gris-700">
                {p.clasificacion}
              </span>
            )}
            <span className="truncate text-sm font-semibold">
              {p.descripcion ?? "Sin descripción"}
            </span>
          </span>
          <span className="block text-[13px] text-smn-gris-500">
            {p.sku} · {p.marca ?? "Sin marca"} ·{" "}
            {precio(p.precio_lista_con_impuestos)}
          </span>
        </span>
      </button>
      {children}
    </li>
  );
}
