"use client";
// Datos → Mapa de tiendas: cada almacén de tblAlmacenes en el mapa (MapaLatitud y MapaLongitud), con color por región,
// categoría, cambio de venta o grupo de tiendas que venden parecido, y tamaño según su venta de las últimas 13 semanas. El fondo es de OpenStreetMap: al
// servicio solo le llega la zona del mapa que se está viendo, no nuestros datos.

import "leaflet/dist/leaflet.css";
import type { CircleMarker, Map as MapaLeaflet } from "leaflet";
import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, Loader2, MapPin, MapPinOff, Search, Sparkles, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fechaLocal, mensajeDe, pesos } from "@/lib/api";
import { fechaDia, nombreMes } from "@/lib/etl";
import {
  PALETA,
  RUTA,
  RUTA_GRUPOS,
  AYUDA_CRITERIO,
  PESOS_CRITERIO,
  valorRasgo,
  type Criterio,
  UBICACION,
  calidadGrupos,
  type FichaTienda,
  type Grupos,
  type ListaTiendas,
  type PerfilGrupo,
  type TiendaEnGrupo,
  type TiendaMapa,
} from "@/lib/tiendas";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";

type ColorPor = "grupo" | "region" | "categoria" | "cambio";
const COLOR_POR: Record<ColorPor, string> = { grupo: "Grupo", region: "Región", categoria: "Categoría", cambio: "Cambio de venta" };
const MEXICO: [number, number] = [23.6, -102.5];
const entero = (n: number) => n.toLocaleString("es-MX", { maximumFractionDigits: 0 });
const compacto = (n: number) => `$${n.toLocaleString("es-MX", { notation: "compact", maximumFractionDigits: 1 })}`;

function colorCambio(p: number | null) {
  if (p === null) return "#9CA3AF";
  if (p >= 5) return "#059669";
  if (p <= -5) return "#DC2626";
  return "#CA8A04";
}
const TRAMOS_CAMBIO: [string, string][] = [
  ["Crece 5 % o más", "#059669"],
  ["Entre −5 % y +5 %", "#CA8A04"],
  ["Cae 5 % o más", "#DC2626"],
  ["Sin comparación", "#9CA3AF"],
];

export default function MapaTiendas() {
  const [datos, setDatos] = useState<ListaTiendas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [colorPor, setColorPor] = useState<ColorPor>("region");
  const [buscar, setBuscar] = useState("");
  const [mayoreo, setMayoreo] = useState(false);
  const [elegida, setElegida] = useState<string | null>(null);
  const [ficha, setFicha] = useState<string | null>(null);
  const [grupos, setGrupos] = useState<Grupos | null>(null);

  useEffect(() => {
    api<ListaTiendas>(RUTA).then(setDatos).catch((e) => setError(mensajeDe(e)));
  }, []);
  const cargarGrupos = useCallback(() => {
    api<Grupos>(RUTA_GRUPOS)
      .then((g) => {
        setGrupos(g);
        if (g.corrida && !g.en_curso) setColorPor((c) => (c === "region" ? "grupo" : c));
      })
      .catch(() => setGrupos(null));
  }, []);
  useEffect(cargarGrupos, [cargarGrupos]);
  // Mientras se calcula, se pregunta cada 3 segundos
  useEffect(() => {
    if (!grupos?.en_curso) return;
    const t = setTimeout(cargarGrupos, 3000);
    return () => clearTimeout(t);
  }, [grupos, cargarGrupos]);
  const grupoDe = useMemo(() => new Map((grupos?.tiendas ?? []).map((t) => [t.almacen, t])), [grupos]);
  const perfilDe = useMemo(() => new Map((grupos?.grupos ?? []).map((g) => [g.grupo, g])), [grupos]);

  const q = buscar.trim().toLowerCase();
  const visibles = useMemo(
    () =>
      (datos?.tiendas ?? []).filter(
        (t) =>
          (mayoreo || t.categoria !== "MAY") &&
          (!q || [t.nombre, t.almacen, t.poblacion, t.estado, t.region].some((v) => v?.toLowerCase().includes(q))),
      ),
    [datos, mayoreo, q],
  );
  const enMapa = visibles.filter((t) => t.ubicacion === "ok");
  const sinMapa = visibles.filter((t) => t.ubicacion !== "ok");

  // Color de cada grupo, estable aunque cambien los filtros: los grupos con más tiendas toman los primeros colores
  const colores = useMemo(() => {
    if (colorPor === "grupo")
      return new Map<string, string>([...(grupos?.grupos ?? []).map((g): [string, string] => [g.nombre, PALETA[(g.grupo - 1) % PALETA.length]]), ["Sin grupo", "#9CA3AF"]]);
    const campo = colorPor === "categoria" ? "categoria" : "region";
    const cuenta = new Map<string, number>();
    for (const t of datos?.tiendas ?? []) cuenta.set(t[campo] ?? "Sin dato", (cuenta.get(t[campo] ?? "Sin dato") ?? 0) + 1);
    const orden = [...cuenta.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return new Map(orden.map(([g], i) => [g, g === "Sin dato" ? "#9CA3AF" : PALETA[i % PALETA.length]]));
  }, [datos, colorPor, grupos]);
  const claveDe = useCallback(
    (t: TiendaMapa) => {
      if (colorPor === "grupo") {
        const g = grupoDe.get(t.almacen);
        return (g && perfilDe.get(g.grupo)?.nombre) ?? "Sin grupo";
      }
      return (colorPor === "categoria" ? t.categoria : t.region) ?? "Sin dato";
    },
    [colorPor, grupoDe, perfilDe],
  );
  const colorDe = useCallback((t: TiendaMapa) => (colorPor === "cambio" ? colorCambio(t.cambio_pct) : (colores.get(claveDe(t)) ?? "#9CA3AF")), [colorPor, colores, claveDe]);

  if (error) return <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>;
  if (!datos) return <Esqueleto className="h-[600px]" />;

  const total = datos.tiendas.filter((t) => mayoreo || t.categoria !== "MAY");
  const conUbicacion = total.filter((t) => t.ubicacion === "ok").length;
  const ventaVisible = enMapa.reduce((s, t) => s + (t.venta ?? 0), 0);
  const leyenda: [string, string][] =
    colorPor === "cambio" ? TRAMOS_CAMBIO : [...colores.entries()].filter(([g]) => visibles.some((t) => claveDe(t) === g));

  return (
    <>
      <Encabezado
        titulo="Mapa de tiendas"
        descripcion={
          datos.periodo
            ? `Cada tienda con su ubicación de SMNBI. El tamaño del punto es su venta sin IVA de las últimas ${datos.periodo.semanas} semanas (${fechaDia(datos.periodo.desde)} al ${fechaDia(datos.periodo.hasta)}).`
            : "Cada tienda con su ubicación de SMNBI. Todavía no hay venta cargada: los puntos van todos del mismo tamaño."
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        {[
          ["Tiendas en el mapa", `${entero(conUbicacion)} de ${entero(total.length)}`],
          ["Sin ubicación", entero(total.length - conUbicacion)],
          ["Venta de lo que ves", datos.periodo ? pesos(ventaVisible) : "Sin venta cargada"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-2xl border border-smn-gris-100 bg-superficie px-4 py-3">
            <p className="text-[13px] font-medium text-smn-gris-500">{k}</p>
            <p className="mt-0.5 text-xl font-semibold tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-[1_1_240px]">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            type="search"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            placeholder="Buscar tienda, ciudad, estado o región"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <div className="flex rounded-xl border border-smn-gris-300 bg-superficie p-0.5 text-[13px] font-semibold" role="radiogroup" aria-label="Color por">
          {(Object.keys(COLOR_POR) as ColorPor[]).filter((c) => c !== "grupo" || grupos?.corrida).map((c) => (
            <button
              key={c}
              role="radio"
              aria-checked={colorPor === c}
              onClick={() => setColorPor(c)}
              className={`rounded-lg px-3 py-2 transition-colors ${colorPor === c ? "bg-tinta text-superficie" : "text-smn-gris-500 hover:text-tinta"}`}
            >
              {COLOR_POR[c]}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 rounded-xl border border-smn-gris-300 bg-superficie px-3 py-2 text-[13px] font-semibold">
          <input type="checkbox" checked={mayoreo} onChange={(e) => setMayoreo(e.target.checked)} className="accent-[var(--color-smn-naranja)]" />
          Incluir mayoreo (MAY)
        </label>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="relative isolate overflow-hidden rounded-2xl border border-smn-gris-100">
          <Lienzo tiendas={enMapa} colorDe={colorDe} elegida={elegida} elegir={setElegida} abrir={setFicha} hayVenta={!!datos.periodo} />
          <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] max-w-[70%] rounded-xl bg-superficie/95 px-3 py-2 text-[13px] shadow-sm">
            <p className="mb-1 font-semibold">{COLOR_POR[colorPor]}</p>
            <ul className="flex flex-wrap gap-x-3 gap-y-1">
              {leyenda.map(([g, c]) => (
                <li key={g} className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} /> {g}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <aside className="rounded-2xl border border-smn-gris-100 bg-superficie">
          <p className="border-b border-smn-gris-100 px-4 py-3 text-sm font-semibold">
            {entero(enMapa.length)} tiendas {datos.periodo ? "· de mayor a menor venta" : ""}
          </p>
          <ul className="max-h-[520px] divide-y divide-smn-gris-100 overflow-y-auto">
            {[...enMapa]
              .sort((a, b) => (b.venta ?? -1) - (a.venta ?? -1) || a.nombre.localeCompare(b.nombre))
              .map((t) => (
                <li key={t.almacen}>
                  <button
                    onClick={() => setElegida(t.almacen)}
                    onDoubleClick={() => setFicha(t.almacen)}
                    className={`grid w-full grid-cols-[auto_1fr_auto] items-center gap-2.5 px-4 py-2 text-left text-sm hover:bg-smn-gris-50 ${elegida === t.almacen ? "bg-aviso-fondo" : ""}`}
                  >
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: colorDe(t) }} />
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{t.nombre}</span>
                      <span className="block truncate text-[13px] text-smn-gris-500">{[t.poblacion, t.estado].filter(Boolean).join(", ") || t.almacen}</span>
                    </span>
                    <span className="text-right text-[13px] tabular-nums">
                      {t.venta !== null ? compacto(t.venta) : "Sin venta"}
                      {t.cambio_pct !== null && (
                        <span className={`block font-semibold ${t.cambio_pct >= 0 ? "text-emerald-600" : "text-red-700"}`}>
                          {t.cambio_pct > 0 ? "+" : ""}
                          {t.cambio_pct} %
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
          {elegida && (
            <div className="border-t border-smn-gris-100 p-3">
              <button onClick={() => setFicha(elegida)} className="w-full rounded-xl bg-smn-naranja px-3 py-2 text-sm font-semibold text-smn-negro hover:brightness-95">
                Ver ficha de la tienda
              </button>
            </div>
          )}
        </aside>
      </div>

      {sinMapa.length > 0 && (
        <section className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
          <h2 className="flex items-center gap-2 font-semibold">
            <MapPinOff className="h-4 w-4 text-smn-naranja" /> {entero(sinMapa.length)} sin ubicación en el mapa
          </h2>
          <p className="mt-1 text-sm text-smn-gris-500">Para que aparezcan, Sistemas tiene que llenar MapaLatitud y MapaLongitud en tblAlmacenes y volver a cargar la tabla.</p>
          <ul className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {sinMapa.map((t) => (
              <li key={t.almacen} className="min-w-0">
                <button onClick={() => setFicha(t.almacen)} className="truncate font-semibold hover:text-naranja-tinta">
                  {t.nombre}
                </button>{" "}
                <span className="font-mono text-[13px] text-smn-gris-500">{t.almacen}</span>
                <span className="block text-[13px] text-smn-gris-500">{UBICACION[t.ubicacion as "falta" | "fuera"]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <SeccionGrupos g={grupos} recargar={cargarGrupos} tiendas={datos.tiendas} />

      <AnimatePresence>
        {ficha && (
          <VentanaFicha
            almacen={ficha}
            cerrar={() => setFicha(null)}
            enGrupo={grupoDe.get(ficha)}
            perfil={grupoDe.get(ficha) ? perfilDe.get(grupoDe.get(ficha)!.grupo) : undefined}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function Lienzo({
  tiendas,
  colorDe,
  elegida,
  elegir,
  abrir,
  hayVenta,
}: {
  tiendas: TiendaMapa[];
  colorDe: (t: TiendaMapa) => string;
  elegida: string | null;
  elegir: (a: string) => void;
  abrir: (a: string) => void;
  hayVenta: boolean;
}) {
  const caja = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapaLeaflet | null>(null);
  const puntos = useRef<Map<string, CircleMarker>>(new Map());
  const [listo, setListo] = useState(false);
  const encuadrado = useRef(false);

  // Leaflet usa window: se carga solo en el navegador
  useEffect(() => {
    let vivo = true;
    import("leaflet").then((L) => {
      if (!vivo || !caja.current || mapa.current) return;
      const m = L.map(caja.current, { zoomControl: true, attributionControl: true }).setView(MEXICO, 5);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(m);
      mapa.current = m;
      setListo(true);
    });
    return () => {
      vivo = false;
      mapa.current?.remove();
      mapa.current = null;
    };
  }, []);

  useEffect(() => {
    if (!listo || !mapa.current) return;
    let vivo = true;
    import("leaflet").then((L) => {
      const m = mapa.current;
      if (!vivo || !m) return;
      puntos.current.forEach((p) => p.remove());
      puntos.current.clear();
      const maxVenta = Math.max(1, ...tiendas.map((t) => t.venta ?? 0));
      for (const t of tiendas) {
        const radio = hayVenta && t.venta ? 5 + 11 * Math.sqrt(t.venta / maxVenta) : 7;
        const p = L.circleMarker([t.latitud!, t.longitud!], {
          radius: radio,
          color: "#ffffff",
          weight: 1.5,
          fillColor: colorDe(t),
          fillOpacity: 0.85,
        })
          .bindTooltip(
            `<strong>${escapar(t.nombre)}</strong><br>${escapar([t.poblacion, t.estado].filter(Boolean).join(", "))}${
              t.venta !== null ? `<br>${compacto(t.venta)}${t.cambio_pct !== null ? ` · ${t.cambio_pct > 0 ? "+" : ""}${t.cambio_pct} %` : ""}` : ""
            }`,
            { direction: "top" },
          )
          .on("click", () => {
            elegir(t.almacen);
            abrir(t.almacen);
          })
          .addTo(m);
        puntos.current.set(t.almacen, p);
      }
      if (!encuadrado.current && tiendas.length) {
        m.fitBounds(L.latLngBounds(tiendas.map((t) => [t.latitud!, t.longitud!] as [number, number])), { padding: [30, 30], maxZoom: 11 });
        encuadrado.current = true;
      }
    });
    return () => {
      vivo = false;
    };
  }, [listo, tiendas, colorDe, elegir, abrir, hayVenta]);

  useEffect(() => {
    const p = elegida ? puntos.current.get(elegida) : undefined;
    puntos.current.forEach((x, k) => x.setStyle({ color: k === elegida ? "#222221" : "#ffffff", weight: k === elegida ? 3 : 1.5 }));
    if (p && mapa.current) {
      p.bringToFront();
      mapa.current.flyTo(p.getLatLng(), Math.max(mapa.current.getZoom(), 11), { duration: 0.6 });
      p.openTooltip();
    }
  }, [elegida]);

  return (
    <div
      ref={caja}
      className="z-0 h-[560px] w-full bg-smn-gris-50 dark:[&_.leaflet-tile-pane]:[filter:invert(1)_hue-rotate(180deg)_brightness(0.85)_contrast(0.9)]"
      aria-label="Mapa de tiendas"
    />
  );
}

function escapar(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function SeccionGrupos({ g, recargar, tiendas }: { g: Grupos | null; recargar: () => void; tiendas: TiendaMapa[] }) {
  const { puede } = useSesion();
  const avisar = useAvisos();
  const [lanzando, setLanzando] = useState(false);
  const [cuantos, setCuantos] = useState("");
  const [pesos, setPesos] = useState<Record<Criterio, number>>({ ventas: 2, tendencia: 2, mezcla: 2, demografia: 2 });
  if (!g) return null;
  const disponible = new Map(g.criterios.map((x) => [x.clave, x.disponible]));
  const elegidos = Object.fromEntries(Object.entries(pesos).filter(([k, w]) => w > 0 && disponible.get(k as Criterio) !== false));
  const nombreDe = new Map(tiendas.map((t) => [t.almacen, t.nombre]));
  const calcular = async () => {
    setLanzando(true);
    try {
      await api(`${RUTA_GRUPOS}/calcular`, { cuerpo: { grupos: cuantos ? Number(cuantos) : null, criterios: elegidos } });
      recargar();
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setLanzando(false);
    }
  };
  const c = g.corrida;
  const fuera = Object.entries(c?.contexto.fuera ?? {});
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold">
            <Users className="h-5 w-5 text-smn-naranja" /> Grupos de tiendas que venden parecido
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-smn-gris-500">
            Un modelo junta las tiendas que se parecen según los criterios que elijas (26 semanas de venta, sin mayoreo) y marca las que van abajo de sus pares. El
            nombre y la explicación de cada grupo los escribe la IA local de la plataforma; nada sale a internet.
          </p>
        </div>
        {puede("datos.tiendas.calcular") && (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-[13px] font-medium text-smn-gris-500">
              Cuántos grupos
              <select value={cuantos} onChange={(e) => setCuantos(e.target.value)} disabled={!!g.en_curso}
                className="rounded-xl border border-smn-gris-100 bg-superficie px-3 py-2 text-sm font-semibold text-smn-gris-700 outline-none">
                <option value="">Automático (los que mejor separan)</option>
                {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                  <option key={n} value={n}>
                    {n} grupos
                  </option>
                ))}
              </select>
            </label>
            <Boton onClick={calcular} cargando={lanzando} disabled={!!g.en_curso || Object.keys(elegidos).length === 0}>
              <Sparkles className="h-4 w-4" /> {c ? "Volver a calcular" : "Calcular grupos"}
            </Boton>
          </div>
        )}
      </div>

      {puede("datos.tiendas.calcular") && (
        <div className="mb-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {g.criterios.map((x) => (
            <div key={x.clave} className={`rounded-xl border px-3 py-2.5 ${pesos[x.clave] > 0 && x.disponible ? "border-smn-naranja/60 bg-smn-naranja/5" : "border-smn-gris-100"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold">{x.nombre}</span>
                <select
                  aria-label={`Peso de ${x.nombre}`}
                  value={x.disponible ? pesos[x.clave] : 0}
                  disabled={!x.disponible || !!g.en_curso}
                  onChange={(e) => setPesos({ ...pesos, [x.clave]: Number(e.target.value) })}
                  className="rounded-lg border border-smn-gris-100 bg-superficie px-2 py-1 text-[13px] font-semibold outline-none"
                >
                  {PESOS_CRITERIO.map((o) => (
                    <option key={o.valor} value={o.valor}>
                      {o.nombre}
                    </option>
                  ))}
                </select>
              </div>
              <p className="mt-1 text-[13px] text-smn-gris-500">{x.disponible ? AYUDA_CRITERIO[x.clave] : "Falta preparar el archivo del Censo 2020 del INEGI."}</p>
            </div>
          ))}
        </div>
      )}

      {g.en_curso && (
        <p className="mb-3 flex items-center gap-2 rounded-xl bg-aviso-fondo px-4 py-2.5 text-sm text-aviso-texto">
          <Loader2 className="h-4 w-4 animate-spin" /> Calculando grupos y pidiendo a la IA local que los explique. Puede tardar un par de minutos.
        </p>
      )}
      {g.fallida && (
        <p className="mb-3 rounded-xl bg-red-50 px-4 py-2.5 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
          El último cálculo no terminó: {g.fallida.error}
        </p>
      )}
      {!c ? (
        !g.en_curso && <p className="rounded-2xl bg-smn-gris-50 px-4 py-8 text-center text-sm text-smn-gris-500">Todavía no se han calculado los grupos.</p>
      ) : (
        <>
          <p className="mb-3 text-[13px] text-smn-gris-500">
            Calculado el {fechaLocal(c.terminada_en ?? c.iniciada_en)} con {c.tiendas} tiendas · {calidadGrupos(c.calidad)}
            {c.calidad !== null ? ` (${c.calidad.toLocaleString("es-MX", { maximumFractionDigits: 2 })} de 1)` : ""} · {c.contexto.venta}
            {c.contexto.pedidos ? ` · ${c.contexto.pedidos} grupos pedidos` : " · número de grupos automático"}
          </p>
          {(c.contexto.opciones?.length ?? 0) > 1 && (
            <p className="mb-3 text-[13px] text-smn-gris-500">
              Qué tan separados quedan según cuántos grupos (de 0 a 1, más alto es mejor):{" "}
              {c.contexto.opciones!.map((o, i) => (
                <span key={o.grupos} className={o.grupos === c.grupos ? "font-semibold text-smn-gris-700" : ""}>
                  {i > 0 && " · "}
                  {o.grupos}: {o.calidad.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                </span>
              ))}
            </p>
          )}
          {!c.contexto.criterios && (
            <p className="mb-3 rounded-xl bg-aviso-fondo px-4 py-2.5 text-sm text-aviso-texto">
              Este cálculo es de antes de poder elegir criterios: solo usó la mezcla por departamento. Elige los criterios arriba y presiona «Volver a calcular».
            </p>
          )}
          {c.contexto.criterios && (
            <p className="mb-3 text-[13px] text-smn-gris-500">
              Criterios:{" "}
              {Object.entries(c.contexto.criterios)
                .map(([k, w]) => `${g.criterios.find((x) => x.clave === k)?.nombre ?? k} (${PESOS_CRITERIO.find((o) => o.valor === w)?.nombre.toLowerCase() ?? w})`)
                .join(" · ")}
              {c.contexto.demografia ? ` · Demografía: ${c.contexto.demografia.fuente}` : ""}
            </p>
          )}
          {(c.contexto.avisos ?? []).map((a) => (
            <p key={a} className="mb-3 rounded-xl bg-aviso-fondo px-4 py-2.5 text-sm text-aviso-texto">
              {a}
            </p>
          ))}
          {c.nota_ia && <p className="mb-3 rounded-xl bg-aviso-fondo px-4 py-2.5 text-sm text-aviso-texto">{c.nota_ia}</p>}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {g.grupos.map((p) => (
              <TarjetaGrupo
                key={p.grupo}
                p={p}
                criterios={c.contexto.criterios ?? { mezcla: 1 }}
                tiendas={g.tiendas.filter((t) => t.grupo === p.grupo).map((t) => nombreDe.get(t.almacen) ?? t.almacen)}
              />
            ))}
          </div>
          <AbajoDePares g={g} nombreDe={nombreDe} />
          {fuera.length > 0 && (
            <p className="mt-3 text-[13px] text-smn-gris-500">
              Sin grupo por tener poca venta en estas semanas: {fuera.map(([a, m]) => `${nombreDe.get(a) ?? a} (${m})`).join(", ")}.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function AbajoDePares({ g, nombreDe }: { g: Grupos; nombreDe: Map<string, string> }) {
  const abajo = g.tiendas.filter((t) => t.alertas?.length);
  if (!g.tiendas.some((t) => t.alertas)) return null; // cálculo anterior a esta función
  const nombreGrupo = new Map(g.grupos.map((p) => [p.grupo, p.nombre]));
  return (
    <div className="mt-4 rounded-2xl border border-smn-gris-100 bg-superficie p-4">
      <h3 className="flex items-center gap-2 font-semibold">
        <AlertTriangle className="h-4 w-4 text-red-700" /> {abajo.length} {abajo.length === 1 ? "tienda abajo" : "tiendas abajo"} de sus pares
      </h3>
      <p className="mt-1 text-[13px] text-smn-gris-500">
        Contra la mediana de las otras tiendas de su grupo: vende 30 % menos por semana, su venta cae 10 puntos más o tiene 5 puntos menos de margen.
      </p>
      {abajo.length === 0 ? (
        <p className="mt-2 text-sm text-smn-gris-500">Ninguna tienda se queda atrás de las de su grupo.</p>
      ) : (
        <ul className="mt-3 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
          {abajo
            .sort((a, b) => b.alertas.length - a.alertas.length)
            .map((t) => (
              <li key={t.almacen}>
                <span className="font-semibold">{nombreDe.get(t.almacen) ?? t.almacen}</span>{" "}
                <span className="text-[13px] text-smn-gris-500">· {nombreGrupo.get(t.grupo)}</span>
                {t.alertas.map((a) => (
                  <span key={a.tipo} className="block text-[13px] text-red-700 dark:text-red-300">
                    {a.texto}
                  </span>
                ))}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

function TarjetaGrupo({ p, tiendas, criterios }: { p: PerfilGrupo; tiendas: string[]; criterios: Partial<Record<Criterio, number>> }) {
  const color = PALETA[(p.grupo - 1) % PALETA.length];
  return (
    <article className="flex flex-col gap-2 rounded-2xl border border-smn-gris-100 bg-superficie p-4" style={{ borderTop: `4px solid ${color}` }}>
      <h3 className="flex items-start justify-between gap-2 font-semibold">
        {p.nombre}
        <span className="shrink-0 rounded-full bg-smn-gris-100 px-2 py-0.5 text-[13px] text-smn-gris-700">{p.tiendas} {p.tiendas === 1 ? "tienda" : "tiendas"}</span>
      </h3>
      {p.descripcion && <p className="text-sm text-smn-gris-700">{p.descripcion}</p>}
      {(p.distintivos ?? []).filter((d) => d.criterio !== "mezcla").length > 0 && (
        <ul className="space-y-0.5 rounded-lg bg-smn-gris-50 px-2.5 py-2 text-[13px]">
          {p.distintivos!
            .filter((d) => d.criterio !== "mezcla")
            .map((d) => (
              <li key={d.nombre}>
                {d.nombre}: <span className="font-semibold tabular-nums">{valorRasgo(d.grupo, d.unidad)}</span>{" "}
                <span className="text-smn-gris-500">(empresa {valorRasgo(d.empresa, d.unidad)})</span>
              </li>
            ))}
        </ul>
      )}
      {criterios.mezcla ? (
      <dl className="grid grid-cols-2 gap-2 text-[13px]">
        <div className="rounded-lg bg-emerald-50 px-2.5 py-2 dark:bg-emerald-500/10">
          <dt className="font-semibold text-emerald-700 dark:text-emerald-300">Vende de más</dt>
          {p.de_mas.length ? (
            p.de_mas.map((d) => (
              <dd key={d.departamento}>
                {d.departamento} <span className="font-semibold tabular-nums">+{d.puntos} pts</span>
              </dd>
            ))
          ) : (
            <dd className="text-smn-gris-500">Nada destacado</dd>
          )}
        </div>
        <div className="rounded-lg bg-red-50 px-2.5 py-2 dark:bg-red-500/10">
          <dt className="font-semibold text-red-700 dark:text-red-300">Vende de menos</dt>
          {p.de_menos.length ? (
            p.de_menos.map((d) => (
              <dd key={d.departamento}>
                {d.departamento} <span className="font-semibold tabular-nums">{d.puntos} pts</span>
              </dd>
            ))
          ) : (
            <dd className="text-smn-gris-500">Nada destacado</dd>
          )}
        </div>
      </dl>
      ) : null}
      {criterios.tendencia && (p.caen_en ?? []).length > 0 && (
        <p className="text-[13px] text-red-700 dark:text-red-300">
          Va peor que la empresa en:{" "}
          {p.caen_en!.map((x) => `${x.departamento} (${x.grupo_pct > 0 ? "+" : ""}${x.grupo_pct} % contra ${x.empresa_pct > 0 ? "+" : ""}${x.empresa_pct} %)`).join(", ")}
        </p>
      )}
      {criterios.demografia && (p.localidades ?? []).length > 0 && <p className="text-[13px] text-smn-gris-500">Localidades: {p.localidades!.join(" · ")}</p>}
      {(p.abajo_de_pares ?? 0) > 0 && (
        <p className="flex items-center gap-1 text-[13px] font-semibold text-red-700 dark:text-red-300">
          <AlertTriangle className="h-3.5 w-3.5" /> {p.abajo_de_pares} {p.abajo_de_pares === 1 ? "tienda abajo" : "tiendas abajo"} de sus pares
        </p>
      )}
      {p.acciones.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-sm">
          {p.acciones.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      <p className="mt-auto pt-1 text-[13px] text-smn-gris-500">
        Venta promedio por tienda: {compacto(p.venta_semanal)} a la semana · {p.regiones.join(", ")}
      </p>
      <details className="text-[13px]">
        <summary className="cursor-pointer font-semibold text-smn-gris-700">Ver tiendas</summary>
        <p className="mt-1 text-smn-gris-500">{tiendas.join(", ")}</p>
      </details>
    </article>
  );
}

function VentanaFicha({ almacen, cerrar, enGrupo, perfil }: { almacen: string; cerrar: () => void; enGrupo?: TiendaEnGrupo; perfil?: PerfilGrupo }) {
  const [f, setF] = useState<FichaTienda | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<FichaTienda>(`${RUTA}/${encodeURIComponent(almacen)}`).then(setF).catch((e) => setError(mensajeDe(e)));
  }, [almacen]);
  const max = Math.max(1, ...(f?.por_mes ?? []).map((m) => m.venta));
  return (
    <Modal titulo={f?.nombre ?? "Tienda"} cerrar={cerrar} ancho="sm:max-w-3xl">
      {error ? (
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">{error}</p>
      ) : !f ? (
        <Esqueleto className="h-64" />
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="-mt-3 mb-4 flex flex-wrap items-center gap-2 text-sm text-smn-gris-500">
            <span className="font-mono text-[13px]">{f.almacen}</span>
            {f.categoria && <Insignia className="bg-smn-gris-100 text-smn-gris-700">Categoría {f.categoria}</Insignia>}
            {f.estatus && <Insignia className="bg-smn-gris-100 text-smn-gris-700">{f.estatus}</Insignia>}
            {f.ubicacion === "ok" ? (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" /> {f.latitud?.toFixed(5)}, {f.longitud?.toFixed(5)}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-aviso-texto">
                <MapPinOff className="h-3.5 w-3.5" /> {UBICACION[f.ubicacion]}
              </span>
            )}
          </div>
          {enGrupo && perfil && (
            <div className="mb-4 rounded-xl border border-smn-gris-100 px-4 py-3 text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: PALETA[(perfil.grupo - 1) % PALETA.length] }} />
                <span className="font-semibold">{perfil.nombre}</span>
                {enGrupo.tipicidad !== null && <span className="text-[13px] text-smn-gris-500">· {enGrupo.tipicidad} de 100 de parecido con su grupo</span>}
              </p>
              {(enGrupo.alertas ?? []).map((a) => (
                <p key={a.tipo} className="mt-1.5 flex items-start gap-1.5 font-semibold text-red-700 dark:text-red-300">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {a.texto}
                </p>
              ))}
              {enGrupo.rasgos.length > 0 && "nombre" in enGrupo.rasgos[0] ? (
                <ul className="mt-1.5 space-y-0.5 text-smn-gris-700">
                  <li className="text-[13px] font-medium text-smn-gris-500">En qué se sale de su grupo</li>
                  {enGrupo.rasgos.map((r) => (
                    <li key={r.nombre}>
                      {r.nombre}: <span className="font-semibold">{valorRasgo(r.tienda, r.unidad)}</span> contra {valorRasgo(r.grupo, r.unidad)} de su grupo
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-smn-gris-500">Se parece mucho al resto de su grupo.</p>
              )}
              {enGrupo.metricas?.localidad && (
                <p className="mt-1.5 text-[13px] text-smn-gris-500">
                  Localidad del Censo: {enGrupo.metricas.localidad.nombre}, {enGrupo.metricas.localidad.municipio}, {enGrupo.metricas.localidad.estado} ·{" "}
                  {valorRasgo(enGrupo.metricas.poblacion ?? null, "")} habitantes · nivel socioeconómico aproximado {valorRasgo(enGrupo.metricas.nse ?? null, "")} de 100
                </p>
              )}
            </div>
          )}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-xl bg-smn-gris-50 px-4 py-3 text-sm sm:grid-cols-4">
            {[
              ["Población", f.poblacion],
              ["Estado", f.estado],
              ["Región", f.region],
              ["Ruta", f.ruta],
              ["Grupo", f.grupo],
              ["Código postal", f.codigo_postal],
              ["Apertura", f.fecha_apertura ? fechaDia(f.fecha_apertura) : null],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-[13px] text-smn-gris-500">{k}</dt>
                <dd className="font-semibold">{v || "Sin dato"}</dd>
              </div>
            ))}
          </dl>

          <h3 className="mt-5 mb-2 text-[13px] font-medium text-smn-gris-500">Venta por mes (sin IVA)</h3>
          {f.por_mes.length ? (
            <div className="flex h-40 items-end gap-1.5">
              {f.por_mes.map((m) => (
                <div key={m.mes} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${nombreMes(m.mes)}: ${pesos(m.venta)}`}>
                  <span className="text-[13px] tabular-nums text-smn-gris-500">{compacto(m.venta)}</span>
                  <motion.div
                    className="w-full rounded-t-md bg-smn-naranja"
                    initial={{ height: 0 }}
                    animate={{ height: `${(m.venta / max) * 100}%` }}
                    transition={{ duration: 0.5 }}
                  />
                  <span className="text-[13px] text-smn-gris-500">{nombreMes(m.mes, true)}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-xl bg-smn-gris-50 px-4 py-3 text-center text-sm text-smn-gris-500">Sin venta cargada para este almacén.</p>
          )}

          {f.productos.length > 0 && (
            <>
              <h3 className="mt-5 mb-2 text-[13px] font-medium text-smn-gris-500">Los 10 productos que más vende (últimas 13 semanas)</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-smn-gris-100">
                    {f.productos.map((p) => (
                      <tr key={p.sku}>
                        <td className="py-1.5 pr-3">
                          <span className="font-semibold">{p.descripcion ?? p.sku}</span>
                          <span className="block text-[13px] text-smn-gris-500">
                            {p.sku}
                            {p.departamento ? ` · ${p.departamento}` : ""}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-right whitespace-nowrap tabular-nums">{entero(p.piezas)} pzas</td>
                        <td className="py-1.5 text-right whitespace-nowrap tabular-nums">{pesos(p.venta)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </motion.div>
      )}
    </Modal>
  );
}
