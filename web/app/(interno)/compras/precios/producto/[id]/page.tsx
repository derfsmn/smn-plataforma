"use client";
// Radar de precios · Página de un producto: los números arriba y el detalle en pestañas (vendedores, historial, coincidencia en Google, ajustes).

import { motion } from "motion/react";
import { ArrowLeft, Check, CircleSlash, Loader2, Pencil, RefreshCw, Search, X } from "lucide-react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, mensajeDe } from "@/lib/api";
import { TEXTO_FILA, dia, disponibilidad, hora, nuestroPrecio, type DetalleProducto, type Observacion, type TiendaDirecta } from "@/lib/precios";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Boton, Esqueleto, Insignia } from "@/componentes/ui";
import { Dato, Diferencia, Grafica, Miniatura, TarjetaCoincidencia, precio } from "../../piezas";

type Pestana = "vendedores" | "historial" | "coincidencia" | "ajustes";

export default function Pagina() {
  return (
    <Suspense fallback={<Esqueleto className="h-72" />}>
      <Producto />
    </Suspense>
  );
}

function Producto() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const ruta = usePathname();
  const parametros = useSearchParams();
  const { puede } = useSesion();
  const avisar = useAvisos();
  const administra = puede("compras.precios.administrar");
  const [d, setD] = useState<DetalleProducto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [consulta, setConsulta] = useState("");
  const [limite, setLimite] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);

  const cargar = useCallback(() => {
    api<DetalleProducto>(`/api/compras/precios/productos/${id}`)
      .then((x) => {
        setD(x);
        setConsulta(x.consulta ?? "");
        setLimite(x.limite_propio_pct === null ? "" : String(Number(x.limite_propio_pct)));
      })
      .catch((e) => setError(mensajeDe(e)));
  }, [id]);
  useEffect(cargar, [cargar]);

  const regresar = () => (window.history.length > 1 ? router.back() : router.push("/compras/precios"));

  const accion = async (clave: string, hacer: () => Promise<unknown>, texto: string) => {
    setOcupado(clave);
    try {
      await hacer();
      avisar(texto, "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };
  const decidir = (a: "confirmar" | "rechazar") =>
    accion(a, async () => setD(await api<DetalleProducto>(`/api/compras/precios/productos/${id}/coincidencia/${a}`, { metodo: "POST" })),
      a === "confirmar" ? "Coincidencia confirmada" : "Listo: la siguiente corrida buscará otra");
  const elegir = async (clave: string) => {
    setOcupado(`elegir-${clave}`);
    try {
      const x = await api<DetalleProducto>(`/api/compras/precios/productos/${id}/elegir`, { metodo: "POST", cuerpo: { clave } });
      setD(x);
      const trayendo = x.ultima?.estado === "pendiente";
      avisar(trayendo ? "Listo: trayendo los precios de esta publicación" : "Listo: la siguiente corrida toma los vendedores de este producto", "exito");
      if (trayendo) router.replace(`${ruta}?pestana=vendedores`, { scroll: false });
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  const rechazarTienda = (t: TiendaDirecta) =>
    accion(`tienda-${t.id}`, async () => setD(await api<DetalleProducto>(`/api/compras/precios/productos/${id}/tiendas/${t.id}/rechazar`, { metodo: "POST" })),
      `Listo: el precio de ${t.tienda} ya no cuenta y la siguiente corrida busca otro`);

  const actualizar = async () => {
    setOcupado("actualizar");
    try {
      setD(await api<DetalleProducto>(`/api/compras/precios/productos/${id}/actualizar`, { metodo: "POST" }));
      avisar("Trayendo los precios de este producto", "exito");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setOcupado(null);
    }
  };

  // Después de «Usar este» los precios se piden a DataForSEO al momento: se revisa hasta que lleguen
  const pendiente = d?.ultima?.estado === "pendiente";
  useEffect(() => {
    if (!pendiente) return;
    const t = setTimeout(cargar, 5000);
    return () => clearTimeout(t);
  }, [pendiente, d, cargar]);
  const guardarConsulta = () =>
    accion("consulta", async () => {
      await api(`/api/compras/precios/vigilados/${id}`, { metodo: "PATCH", cuerpo: { consulta: consulta.trim() || null } });
      setEditando(false);
      cargar();
    }, "Búsqueda guardada; se usa en la siguiente corrida");
  const guardarLimite = (valor: number | null) =>
    accion("limite", async () => {
      await api(`/api/compras/precios/vigilados/${id}`, { metodo: "PATCH", cuerpo: { limite_pct: valor } });
      cargar();
    }, valor === null ? "Usa el límite general" : `Límite de este producto: ${valor} %`);

  if (error)
    return (
      <div>
        <BotonRegresar regresar={regresar} />
        <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">{error}</p>
      </div>
    );
  if (!d) return <Esqueleto className="h-72" />;

  const f = d.ultima;
  const alerta = Number(d.limite_pct);
  const sinCoincidencia = !d.coincidencia || f?.estado === "sin_coincidencia";
  const pestanas: { id: Pestana; texto: string }[] = [
    { id: "vendedores", texto: "Vendedores" },
    { id: "historial", texto: "Historial" },
    { id: "coincidencia", texto: "Coincidencia en Google" },
    ...(d.vigilado ? [{ id: "ajustes" as const, texto: "Ajustes" }] : []),
  ];
  const pedida = parametros.get("pestana") as Pestana | null;
  const pestana: Pestana =
    pedida && pestanas.some((p) => p.id === pedida) ? pedida : sinCoincidencia && !d.observaciones.length ? "coincidencia" : "vendedores";
  const cambiar = (p: Pestana) => router.replace(`${ruta}?pestana=${p}`, { scroll: false });
  // Semáforo por vendedor: nuestro precio contra el suyo (positivo = estamos más caros), como diferencia_pct de la API
  const base = f ? nuestroPrecio(f) : null;
  const contra = (suyo: string) => (base === null || !Number(suyo) ? null : ((Number(base) / Number(suyo) - 1) * 100).toFixed(2));
  const comparables = d.observaciones.filter((o) => !o.es_propia && !o.fuera && o.moneda === "MXN" && base !== null);
  const caros = comparables.filter((o) => Number(contra(o.precio_comparable)) > 0).length;
  const numero = limite.trim() === "" ? null : Number(limite);
  const valido = numero !== null && Number.isFinite(numero) && numero >= 0 && numero <= 100;

  return (
    <>
      <BotonRegresar regresar={regresar} />

      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center">
        <Miniatura liga={d.imagen} grande />
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">{d.descripcion ?? d.sku}</h2>
          <p className="mt-1 text-sm text-smn-gris-500">
            {d.marca ?? "Sin marca"} · <span className="font-mono">{d.sku}</span>
            {d.codigo_barras && <> · código de barras <span className="font-mono">{d.codigo_barras}</span></>}
            {d.liga_tienda && (
              <>
                {" · "}
                <a href={d.liga_tienda} target="_blank" rel="noopener noreferrer" className="font-semibold text-tinta hover:underline">
                  Ver en nuestra tienda
                </a>
              </>
            )}
          </p>
          {!d.vigilado && <Insignia className="mt-2 bg-smn-gris-100 text-smn-gris-700">Ya no se vigila</Insignia>}
        </div>
      </div>

      {pendiente && (
        <div className="mb-4 flex items-center gap-3 rounded-2xl border border-smn-naranja bg-aviso-fondo px-4 py-3 text-sm text-aviso-texto">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          <p>
            <b>{f?.mensaje ?? "Trayendo precios"}.</b> DataForSEO suele tardar uno o dos minutos; los números se actualizan solos y puedes salir de esta pantalla.
          </p>
        </div>
      )}
      {f ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Numero t={f.base === "tienda" ? "Nuestro precio (tienda en línea)" : "Nuestro precio lista"} v={precio(nuestroPrecio(f))} />
            <Numero t="Mediana del mercado" v={precio(f.mediana)} />
            <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <p className="text-[13px] text-smn-gris-500">Diferencia</p>
              <div className="mt-1.5 text-lg">
                <Diferencia valor={f.dif_lista_mediana_pct} alerta={alerta} />
              </div>
              <p className="mt-1 text-[13px] text-smn-gris-500">Límite {alerta} %{d.limite_propio_pct !== null && " (propio)"}</p>
            </div>
            <Numero t="Vendedores que cuentan" v={String(f.vendedores)} />
          </div>
          <p className="mt-2 text-[13px] text-smn-gris-500">
            Corrida del {dia(d.ultima_fecha!)}
            {d.ultima_iniciada && `, ${hora(d.ultima_iniciada)}`} · {TEXTO_FILA[f.estado]}
            {f.mensaje && `: ${f.mensaje}`}. Precios con impuestos.
          </p>
        </>
      ) : (
        <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-6 text-sm text-smn-gris-500">Todavía no ha pasado por una corrida.</p>
      )}

      <nav className="-mx-4 mt-6 mb-4 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Detalle del producto">
        <ul className="flex w-max gap-5 border-b border-smn-gris-100">
          {pestanas.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => cambiar(p.id)}
                aria-current={pestana === p.id ? "page" : undefined}
                className={`relative flex items-center gap-1.5 pb-2.5 text-sm font-semibold whitespace-nowrap ${pestana === p.id ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
              >
                {p.id === "coincidencia" && sinCoincidencia && <CircleSlash className="h-3.5 w-3.5 text-aviso-texto" />}
                {p.texto}
                {pestana === p.id && <motion.span layoutId="pestana-producto" className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-smn-naranja" />}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {pestana === "vendedores" && administra && d.coincidencia && !pendiente && (
        <div className="mb-3 flex justify-end">
          <Boton variante="secundario" onClick={actualizar} cargando={ocupado === "actualizar"} className="px-3 py-1.5">
            <RefreshCw className="h-4 w-4" /> Actualizar precios ahora
          </Boton>
        </div>
      )}
      {pestana === "vendedores" && d.tiendas.length > 0 && f && (
        <section className="mb-5">
          <h3 className="mb-2 text-sm font-semibold">Tiendas clave</h3>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {d.tiendas.map((t) => (
              <TarjetaTienda
                key={t}
                tienda={t}
                obs={d.observaciones.filter((o) => o.tienda_clave === t && !o.es_propia && !o.fuera && o.moneda === "MXN")
                  .sort((a, b) => Number(a.precio_comparable) - Number(b.precio_comparable))[0]}
                directa={d.directas.find((x) => x.tienda === t)}
                contra={contra}
                alerta={alerta}
                rechazar={administra ? rechazarTienda : undefined}
                ocupado={ocupado}
              />
            ))}
          </div>
        </section>
      )}
      {pestana === "vendedores" &&
        (d.observaciones.length ? (
          <section>
            {comparables.length > 0 && (
              <p className="mb-3 text-sm text-smn-gris-700">
                Con nuestro precio de <b className="text-tinta">{precio(base)}</b> estamos{" "}
                {caros === 0 ? (
                  <b className="text-tinta">igual o más baratos que {comparables.length === 1 ? "el único vendedor" : `los ${comparables.length} vendedores`}</b>
                ) : caros === comparables.length ? (
                  <b className="text-tinta">más caros que {comparables.length === 1 ? "el único vendedor" : `los ${comparables.length} vendedores`}</b>
                ) : (
                  <>
                    <b className="text-tinta">más caros que {caros}</b> de {comparables.length} vendedores
                  </>
                )}
                .
              </p>
            )}
            <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie text-sm">
              {d.observaciones.map((o, i) => (
                <li key={i} className={`flex items-center gap-3 px-4 py-3 ${o.fuera ? "opacity-60" : ""}`}>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">
                      {o.liga ? (
                        <a href={o.liga} target="_blank" rel="noopener noreferrer" className="hover:underline">
                          {o.vendedor}
                        </a>
                      ) : (
                        o.vendedor
                      )}
                      {o.es_propia && <Insignia className="ml-2 bg-smn-naranja/15 text-aviso-texto">Nuestra tienda</Insignia>}
                      {o.tienda_clave && <Insignia className="ml-2 bg-smn-gris-100 text-smn-gris-700">{o.directa ? "Tienda clave · su sitio" : "Tienda clave"}</Insignia>}
                    </p>
                    {o.publicacion && <p className="text-[13px] break-words text-smn-gris-700">{o.publicacion}</p>}
                    <p className="text-[13px] text-smn-gris-500">
                      {disponibilidad(o.disponibilidad)}
                      {o.envio !== null && Number(o.envio) > 0 && ` · envío ${precio(o.envio)}`}
                      {o.moneda !== "MXN" && ` · ${o.moneda}: no se compara`}
                    </p>
                    {o.fuera && <p className="text-[13px] font-semibold text-aviso-texto">No cuenta: {o.fuera}</p>}
                  </div>
                  <span className="flex flex-col items-end gap-1">
                    <span className="font-semibold whitespace-nowrap tabular-nums">{o.moneda === "MXN" ? precio(o.precio_comparable) : `${o.precio_comparable} ${o.moneda}`}</span>
                    {!o.es_propia && o.moneda === "MXN" && <Diferencia valor={contra(o.precio_comparable)} alerta={alerta} />}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[13px] text-smn-gris-500">
              Semáforo de cada vendedor: nuestro precio contra el suyo. Verde: estamos igual o más baratos; amarillo: más caros hasta {alerta} %; rojo: más caros arriba de eso.
            </p>
            <p className="mt-1 text-[13px] text-smn-gris-500">«Su sitio»: el precio se leyó en la página de la tienda; si Google trae la misma tienda, se queda este.</p>
            <p className="mt-1 text-[13px] text-smn-gris-500">Nuestra tienda, los agotados, los precios en otra moneda y las ofertas que parecen de otra presentación no cuentan para la mediana.</p>
          </section>
        ) : (
          <Vacio texto={pendiente ? "Esperando los precios de los vendedores…" : sinCoincidencia ? "Sin vendedores: no hay una coincidencia confiable en Google. Revísalo en «Coincidencia en Google»." : "La última corrida no trajo vendedores."} />
        ))}

      {pestana === "historial" && (
        <section className="space-y-5">
          <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
            <Grafica serie={d.serie} />
          </div>
          {f && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-sm sm:grid-cols-3">
              <Dato t="Nuestro precio lista" v={precio(f.precio_lista)} />
              <Dato t="Membresía" v={precio(f.precio_membresia)} />
              <Dato t="Tienda en línea" v={precio(f.precio_tienda)} />
              <Dato t="Mínimo del mercado" v={precio(f.minimo)} />
              <Dato t="Mediana del mercado" v={precio(f.mediana)} />
              <Dato t="Máximo del mercado" v={precio(f.maximo)} />
              <div>
                <dt className="text-[13px] text-smn-gris-500">Membresía contra mediana</dt>
                <dd className="mt-0.5">
                  <Diferencia valor={f.dif_membresia_mediana_pct} alerta={alerta} />
                </dd>
              </div>
            </dl>
          )}
        </section>
      )}

      {pestana === "coincidencia" && (
        <section className="space-y-6">
          {d.coincidencia ? (
            <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
              <TarjetaCoincidencia m={d.coincidencia} />
              {administra && (
                <div className="mt-3 flex flex-wrap gap-2 border-t border-smn-gris-100 pt-3">
                  <p className="w-full text-[13px] text-smn-gris-500">
                    {d.coincidencia.estado === "persona"
                      ? "Lo confirmó una persona y se reutiliza en cada corrida. Si lo quitas, la siguiente corrida lo vuelve a buscar."
                      : "Opcional: nada espera tu revisión. Si es incorrecto, la siguiente corrida busca otro."}
                  </p>
                  {d.coincidencia.estado !== "persona" && (
                    <Boton variante="secundario" onClick={() => decidir("confirmar")} cargando={ocupado === "confirmar"} className="px-3 py-2">
                      <Check className="h-4 w-4" /> Es correcto
                    </Boton>
                  )}
                  <Boton variante="fantasma" onClick={() => decidir("rechazar")} cargando={ocupado === "rechazar"} className="px-3 py-2">
                    <X className="h-4 w-4" /> No es este producto
                  </Boton>
                </div>
              )}
            </div>
          ) : (
            <p className="rounded-2xl border border-dashed border-smn-naranja bg-aviso-fondo px-4 py-4 text-sm text-aviso-texto">
              Sin coincidencia confiable: este producto no entra a la comparación.
              {administra ? " Elige abajo la publicación correcta con «Usar este» o cambia la búsqueda en «Ajustes»." : " La siguiente corrida lo vuelve a buscar."}
            </p>
          )}

          <div className="text-sm">
            <p className="flex items-center gap-1.5 text-[13px] font-medium text-smn-gris-500">
              <Search className="h-3.5 w-3.5" /> Se busca como
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-2">
              {d.consultas.map((c) => (
                <Insignia key={c} className="bg-smn-gris-100 font-mono font-normal text-smn-gris-700">
                  {c}
                </Insignia>
              ))}
            </p>
          </div>

          {d.candidatos.length > 0 && (
            <div>
              <h3 className="font-semibold">Lo que regresó Google</h3>
              <p className="mb-2 text-[13px] text-smn-gris-500">
                Última búsqueda{d.candidatos_fecha ? ` del ${dia(d.candidatos_fecha, "medium")}` : ""}, de mejor a peor calificación.
                {administra && " Si el correcto no es el elegido, presiona «Usar este»."}
              </p>
              <ul className="divide-y divide-smn-gris-100 rounded-2xl border border-smn-gris-100 bg-superficie text-sm">
                {d.candidatos.map((c) => (
                  <li key={c.clave} className={`flex flex-wrap items-start gap-3 px-4 py-3 ${c.elegida ? "bg-smn-naranja/5" : ""}`}>
                    <Miniatura liga={c.imagen} />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold break-words">
                        {c.liga ? (
                          <a href={c.liga} target="_blank" rel="noopener noreferrer" className="hover:underline">
                            {c.titulo}
                          </a>
                        ) : (
                          c.titulo
                        )}
                        {c.elegida && <Insignia className="ml-2 bg-smn-naranja/15 text-aviso-texto">Elegido</Insignia>}
                      </p>
                      <p className="text-[13px] text-smn-gris-500">
                        {c.precio !== null && `${c.moneda && c.moneda !== "MXN" ? `${c.precio} ${c.moneda}` : precio(c.precio)} · `}
                        {c.vendedor && `${c.vendedor} · `}
                        {c.posicion !== null && `lugar ${c.posicion} · `}
                        {c.calificacion !== null ? `calificación ${Math.round(c.calificacion)}` : "sin calificar"}
                        {c.estrategias.includes("codigo_barras") && " · por código de barras"}
                      </p>
                      {c.motivo && <p className="text-[13px] text-smn-gris-500">{c.motivo}</p>}
                    </div>
                    {administra && !c.elegida && (
                      <Boton variante="secundario" onClick={() => elegir(c.clave)} cargando={ocupado === `elegir-${c.clave}`} className="px-3 py-1.5">
                        <Check className="h-4 w-4" /> Usar este
                      </Boton>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {d.anteriores.length > 0 && (
            <div>
              <h3 className="mb-2 font-semibold">Coincidencias anteriores</h3>
              <ul className="space-y-3">
                {d.anteriores.map((m) => (
                  <li key={m.id} className="rounded-2xl border border-smn-gris-100 bg-superficie p-3 opacity-80">
                    <TarjetaCoincidencia m={m} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {pestana === "ajustes" && (
        <section className="space-y-4">
          <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
            <h3 className="mb-1 font-semibold">Semáforo de este producto</h3>
            <p className="mb-3 text-sm text-smn-gris-500">
              Verde si estamos igual o más baratos que la mediana; amarillo si estamos más caros hasta <b className="text-tinta">{alerta} %</b>; rojo arriba de eso
              {d.limite_propio_pct === null ? " (límite general de Configuración)." : " (límite propio de este producto)."}
            </p>
            {administra && (
              <div className="flex flex-wrap items-end gap-2">
                <label className="block">
                  <span className="mb-1 block text-[13px] font-semibold text-smn-gris-700">Límite propio (%)</span>
                  <input
                    value={limite}
                    onChange={(e) => setLimite(e.target.value)}
                    inputMode="decimal"
                    placeholder="General"
                    className="w-28 rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 tabular-nums outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                  />
                </label>
                <Boton onClick={() => guardarLimite(numero)} disabled={!valido} cargando={ocupado === "limite"} className="px-3 py-2">
                  Guardar
                </Boton>
                {d.limite_propio_pct !== null && (
                  <Boton variante="fantasma" onClick={() => guardarLimite(null)} className="px-3 py-2">
                    Usar el general
                  </Boton>
                )}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 text-sm">
            <h3 className="mb-1 font-semibold">Búsqueda en Google Shopping</h3>
            <p className="mb-3 text-smn-gris-500">Si Google no encuentra el producto correcto o trae otra variante, escribe cómo buscarlo (por ejemplo «demograss clásico 30 cápsulas»).</p>
            {editando ? (
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  value={consulta}
                  onChange={(e) => setConsulta(e.target.value)}
                  maxLength={300}
                  placeholder="Vacío = se arma sola con el código de barras, la marca y la descripción"
                  className="min-w-0 flex-1 rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
                />
                <Boton onClick={guardarConsulta} cargando={ocupado === "consulta"} className="px-3 py-2">
                  Guardar
                </Boton>
              </div>
            ) : (
              <p className="flex flex-wrap items-center gap-2">
                {d.consultas.map((c) => (
                  <Insignia key={c} className="bg-smn-gris-100 font-mono font-normal text-smn-gris-700">
                    {c}
                  </Insignia>
                ))}
                {administra && (
                  <button onClick={() => setEditando(true)} className="inline-flex items-center gap-1 text-[13px] font-medium text-smn-gris-500 hover:text-tinta">
                    <Pencil className="h-3 w-3" /> Buscar con otro texto
                  </button>
                )}
              </p>
            )}
          </div>
        </section>
      )}
    </>
  );
}

function BotonRegresar({ regresar }: { regresar: () => void }) {
  return (
    <button onClick={regresar} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
      <ArrowLeft className="h-4 w-4" /> Productos
    </button>
  );
}

function Numero({ t, v }: { t: string; v: string }) {
  return (
    <div className="rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <p className="text-[13px] text-smn-gris-500">{t}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums sm:text-2xl">{v}</p>
    </div>
  );
}

function Vacio({ texto }: { texto: string }) {
  return <p className="rounded-2xl border border-dashed border-smn-gris-300 bg-superficie px-4 py-8 text-center text-sm text-smn-gris-500">{texto}</p>;
}

const SIN_PRECIO: Record<TiendaDirecta["estado"], string> = {
  encontrado: "Sin precio que cuente",
  sin_precio: "Lo tiene, pero no mostró precio",
  no_lo_tiene: "No lo tiene",
  dudoso: "No se supo cuál es",
  error: "No se pudo consultar",
};

function TarjetaTienda({ tienda, obs, directa, contra, alerta, rechazar, ocupado }: {
  tienda: string;
  obs: Observacion | undefined;
  directa: TiendaDirecta | undefined;
  contra: (suyo: string) => string | null;
  alerta: number;
  rechazar?: (t: TiendaDirecta) => void;
  ocupado: string | null;
}) {
  const quitar = rechazar && directa?.id && directa.estado === "encontrado" && obs?.directa;
  return (
    <div className="flex flex-col rounded-2xl border border-smn-gris-100 bg-superficie p-3 text-sm">
      <p className="text-[13px] font-medium text-smn-gris-500">{tienda}</p>
      {obs ? (
        <>
          <p className="mt-1 flex flex-wrap items-center justify-between gap-1">
            <span className="text-base font-semibold tabular-nums">{precio(obs.precio_comparable)}</span>
            <Diferencia valor={contra(obs.precio_comparable)} alerta={alerta} />
          </p>
          <p className="mt-0.5 text-[13px] text-smn-gris-500">
            {obs.liga ? (
              <a href={obs.liga} target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline">
                {obs.directa ? "En su sitio" : "En Google"}
              </a>
            ) : obs.directa ? "En su sitio" : "En Google"}
            {obs.directa && directa?.titulo && ` · ${directa.titulo}`}
          </p>
        </>
      ) : (
        <>
          <p className="mt-1 font-semibold text-smn-gris-700">{directa ? SIN_PRECIO[directa.estado] : "No apareció"}</p>
          {directa?.mensaje && directa.estado !== "no_lo_tiene" && <p className="mt-0.5 text-[13px] break-words text-smn-gris-500">{directa.mensaje}</p>}
        </>
      )}
      {quitar && (
        <button
          onClick={() => rechazar(directa)}
          disabled={ocupado === `tienda-${directa.id}`}
          className="mt-2 inline-flex items-center gap-1 self-start text-[13px] font-semibold text-smn-gris-500 hover:text-tinta disabled:opacity-50"
        >
          <X className="h-3 w-3" /> No es este producto
        </button>
      )}
    </div>
  );
}
