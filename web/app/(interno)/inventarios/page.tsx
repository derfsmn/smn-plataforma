"use client";
// Inventarios (TD006) → Tablero de inventarios (EJEMPLO para la junta del 26 nov 2026).
// Cifras fijas, calculadas una sola vez con docs/inventarios/exportar_tablero.py sobre la base de la plataforma:
// inventario al 1 nov 2026 (datos.inventario) y venta de tiendas sin mayoreo del 6 jul al 28 sep 2026 (datos.venta_semanal).
// No consulta la base: es una página de muestra. La versión con datos vivos (reportes 1–7) espera aprobación.

import { Encabezado } from "@/componentes/ui";
import { useSesion } from "@/componentes/sesion";

const tarjeta = "rounded-2xl border border-smn-gris-100 bg-superficie p-5";
const etiqueta = "text-sm text-smn-gris-500";

function Barra({ valor, max = 100, color }: { valor: number; max?: number; color: string }) {
  return (
    <div className="h-3 w-full rounded bg-smn-gris-100">
      <div className="h-3 rounded" style={{ width: `${Math.min(100, (valor / max) * 100)}%`, background: color }} />
    </div>
  );
}

const NEGRO = "var(--color-smn-negro)";
const NARANJA = "#F5A01A";

const PARETO = [
  { g: "Cabeza", d: "80 % de la venta", skus: "1,258", venta: 80, inv: 74, costo: "$226.7 M" },
  { g: "Panza", d: "siguiente 15 %", skus: "1,451", venta: 15, inv: 15.7, costo: "$48.1 M" },
  { g: "Cola", d: "último 5 %", skus: "2,545", venta: 5, inv: 8.8, costo: "$27.0 M" },
  { g: "Sin venta", d: "13 semanas", skus: "2,513", venta: 0, inv: 1.5, costo: "$4.7 M" },
];

const CLASES = [
  { c: "AA", venta: 22.5, inv: 19.8, costo: "$60.7 M" },
  { c: "A", venta: 13.4, inv: 11.1, costo: "$34.1 M" },
  { c: "B", venta: 12.8, inv: 13.2, costo: "$40.4 M" },
  { c: "C", venta: 22.5, inv: 19.4, costo: "$59.6 M" },
  { c: "D", venta: 14.5, inv: 14.2, costo: "$43.4 M" },
  { c: "E", venta: 11.9, inv: 19.5, costo: "$59.9 M", ojo: true },
  { c: "NUEVO", venta: 0, inv: 1.2, costo: "$3.6 M" },
  { c: "Sin clase", venta: 2.3, inv: 1.6, costo: "$4.8 M" },
];

const TIENDAS = [
  ["PS LAS AGUILAS", 1568],
  ["ZACATECAS SORIANA", 1088],
  ["NUEVO LAREDO", 975],
  ["PS LA FE SENDERO APODACA", 968],
  ["PS TUXTLA", 910],
  ["PS SALINA CRUZ", 886],
  ["ZAMORA", 868],
  ["LAZARO CARDENAS", 865],
] as const;

const ACAPULCO = [
  ["Acapulco 2", "$1.36 M", "$424 k", 321],
  ["Patio Acapulco", "$727 k", "$142 k", 511],
  ["Acapulco Palmas", "$699 k", "$123 k", 569],
] as const;

const DEPTOS = [
  ["Prevención y Salud", "$164.2 M", "$223.7 M"],
  ["Abarrotes comestible", "$54.5 M", "$97.1 M"],
  ["Deportes", "$47.9 M", "$72.4 M"],
  ["Cuidado personal", "$36.0 M", "$50.8 M"],
] as const;

const SIN_VENTA = [
  ["27154", "Granagard Omega 5 60 cap", "E", "$1.10 M"],
  ["93701", "Omega 3 Premium concentrado 120 cap", "NUEVO", "$834 k"],
  ["28075", "Duo Bálsamo herbal corporal 120 g", "NUEVO", "$381 k"],
  ["28074", "Duo Gel pies y piernas cansadas 120 g", "NUEVO", "$231 k"],
  ["54957", "Post 9M Multivitaminas minerales 60 tab", "NUEVO", "$201 k"],
] as const;

const FALTA = [
  ["Máximos y mínimos por tienda y artículo", "Para saber qué está arriba del máximo y revisar la regla 80/50/20 de los centrales."],
  ["Movimientos y traspasos", "Entradas, ajustes, merma y lo que va en camino del almacén a la tienda."],
  ["Cierres de cada mes", "Hoy hay 3 cortes (22 oct, 29 oct, 1 nov). Sin cierres no hay tendencia ni rotación anual."],
  ["Venta de oct–nov 2026", "La venta cargada llega al 30 sep 2026."],
  ["Venta oct–dic 2025", "Para la temporada y el «pico de 3 meses» de la regla de máximos."],
  ["Grupo de días por tienda y promociones", "18, 20, 25 o 30 días por tienda, y qué se compró por promoción o membresía."],
] as const;

function Seccion({ titulo, nota, children }: { titulo: string; nota?: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-xl font-semibold tracking-tight">{titulo}</h2>
      {nota && <p className="mt-1 max-w-3xl text-[15px] text-smn-gris-700">{nota}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Leyenda() {
  return (
    <div className="mb-3 flex gap-5 text-sm text-smn-gris-700">
      <span className="flex items-center gap-2"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: NEGRO }} />Parte de la venta</span>
      <span className="flex items-center gap-2"><i className="inline-block h-3 w-3 rounded-sm" style={{ background: NARANJA }} />Parte del inventario</span>
    </div>
  );
}

export default function TableroInventariosEjemplo() {
  const { puede } = useSesion();
  if (!puede("inventarios.tablero.ver"))
    return <p className="rounded-2xl bg-smn-gris-50 px-4 py-10 text-center text-sm text-smn-gris-500">No tienes permiso para ver el tablero de inventarios.</p>;
  return (
    <>
      <Encabezado
        titulo="Tablero de inventarios"
        descripcion="Ejemplo con datos reales de la base: inventario al 1 nov 2026 y venta de tiendas (sin mayoreo) del 6 jul al 28 sep 2026. Valores al costo, sin IVA."
        accion={<span className="rounded-full bg-smn-negro px-3 py-1.5 text-sm font-semibold text-white">Ejemplo · cifras fijas</span>}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl bg-smn-negro p-5 text-white">
          <div className="text-sm text-white/70">Inventario a costo</div>
          <div className="mt-1 text-4xl font-semibold">$306.5 M</div>
          <div className="mt-1 text-sm text-white/70">Existencia × costo promedio</div>
        </div>
        <div className={tarjeta}><div className={etiqueta}>A precio de lista</div><div className="mt-1 text-4xl font-semibold">$824.9 M</div></div>
        <div className={tarjeta}><div className={etiqueta}>Piezas</div><div className="mt-1 text-4xl font-semibold">6.47 M</div><div className={etiqueta}>En 204 almacenes y tiendas</div></div>
        <div className={tarjeta}><div className={etiqueta}>Contra el corte del 29 oct</div><div className="mt-1 text-4xl font-semibold">−0.5 %</div><div className={etiqueta}>29 oct $308.1 M · 22 oct $305.2 M</div></div>
      </div>

      <Seccion titulo="Dónde está" nota="La mitad está en tiendas y 4 de cada 10 pesos en los almacenes centrales.">
        <div className="flex h-14 overflow-hidden rounded-xl text-sm font-semibold">
          <div className="flex items-center px-4 text-white" style={{ width: "51.6%", background: NEGRO }}>Tiendas $158.2 M · 51.6 %</div>
          <div className="flex items-center px-4 text-black" style={{ width: "40.8%", background: NARANJA }}>Almacenes centrales $125.2 M · 40.8 %</div>
          <div className="flex items-center justify-center bg-smn-gris-300" style={{ width: "7.6%" }}>7.6 %</div>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className={tarjeta}><div className="text-lg font-semibold">194 tiendas · $158.2 M</div><p className={etiqueta}>Las que vendieron en las 13 semanas.</p></div>
          <div className={tarjeta}>
            <div className="text-lg font-semibold">Centrales · $125.2 M</div>
            <p className="text-sm text-smn-gris-700"><b>ALM-MEXICO (VCE) $65.8 M</b>: vende y surte.<br /><b>PSALM-MEX (PS) $58.1 M</b>: solo distribuye.<br />PT LAB $1.3 M.</p>
          </div>
          <div className={tarjeta}><div className="text-lg font-semibold">Mayoreo y canales · $23.1 M</div><p className="text-sm text-smn-gris-700">CORP $18.7 M, Mercado Libre $2.3 M, Sanborns $1.4 M, Amazon $0.6 M.</p></div>
        </div>
        <p className="mt-3 text-sm text-smn-gris-500">Por empresa: PS $162.4 M (129 almacenes), VCE $142.8 M (74), LAB $1.3 M (1).</p>
      </Seccion>

      <Seccion titulo="Venta contra inventario" nota="1,258 artículos hacen el 80 % de la venta. La cola vende el 5 % y tiene casi el 9 % del inventario.">
        <div className={tarjeta}>
          <Leyenda />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="text-left text-smn-gris-500"><th className="py-2 pr-3">Grupo</th><th className="py-2 pr-3 text-right">Artículos</th><th className="w-1/4 py-2 pr-3">Venta</th><th className="w-1/4 py-2 pr-3">Inventario</th><th className="py-2 text-right">A costo</th></tr></thead>
              <tbody>
                {PARETO.map((p) => (
                  <tr key={p.g} className="border-t border-smn-gris-100">
                    <td className="py-3 pr-3"><b>{p.g}</b> <span className="text-smn-gris-500">({p.d})</span></td>
                    <td className="py-3 pr-3 text-right tabular-nums">{p.skus}</td>
                    <td className="py-3 pr-3"><div className="flex items-center gap-2"><Barra valor={p.venta} color={NEGRO} /><span className="w-14 tabular-nums">{p.venta} %</span></div></td>
                    <td className="py-3 pr-3"><div className="flex items-center gap-2"><Barra valor={p.inv} color={NARANJA} /><span className="w-14 tabular-nums">{p.inv} %</span></div></td>
                    <td className="py-3 text-right tabular-nums">{p.costo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Seccion>

      <Seccion titulo="Por clase" nota="La clase E vende el 12 % y tiene el 20 % del inventario: $59.9 M en 1,699 artículos.">
        <div className={tarjeta}>
          <Leyenda />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <tbody>
                {CLASES.map((c) => (
                  <tr key={c.c} className={c.ojo ? "bg-[#FDF0DA] dark:bg-[#3a2a0a]" : ""}>
                    <td className="w-24 py-2 pl-2 font-semibold">{c.c}</td>
                    <td className="py-2 pr-3"><div className="flex items-center gap-2"><Barra valor={c.venta} max={25} color={NEGRO} /><span className="w-14 tabular-nums">{c.venta} %</span></div></td>
                    <td className="py-2 pr-3"><div className="flex items-center gap-2"><Barra valor={c.inv} max={25} color={NARANJA} /><span className="w-14 tabular-nums">{c.inv} %</span></div></td>
                    <td className={`w-24 py-2 pr-2 text-right tabular-nums ${c.ojo ? "font-semibold" : ""}`}>{c.costo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Seccion>

      <Seccion titulo="Salud de inventario en tiendas" nota="196 tiendas con venta, sin mayoreo. Mismas reglas que Datos → Salud de inventario.">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl bg-smn-negro p-5 text-white"><div className="text-sm text-white/70">Sin venta en 13 semanas</div><div className="mt-1 text-4xl font-semibold">$26.4 M</div><p className="mt-1 text-sm text-white/70">142,857 combinaciones de tienda y artículo con existencia y ninguna pieza vendida.</p></div>
          <div className="rounded-2xl border p-5" style={{ borderColor: NARANJA }}><div className={etiqueta}>Exceso: más de 180 días</div><div className="mt-1 text-4xl font-semibold">$23.0 M</div><p className={etiqueta}>102,146 combinaciones que sí venden, pero tienen para más de medio año.</p></div>
          <div className={tarjeta}><div className={etiqueta}>En cero, pero sí se venden</div><div className="mt-1 text-4xl font-semibold">2,963</div><p className={etiqueta}>Existencia 0 y venta de 1 pieza o más por semana. Vendieron $5.4 M en 13 semanas.</p></div>
        </div>
      </Seccion>

      <Seccion titulo="Tiendas parecidas, inventario distinto" nota="Por cada $100 que vende a la semana, la tienda típica tiene $472 en inventario. Algunas tienen más del triple.">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className={tarjeta}>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-smn-gris-500"><th className="py-2">Tienda</th><th className="py-2 text-right">Inventario por cada $100 de venta semanal</th></tr></thead>
              <tbody>
                {TIENDAS.map(([t, v]) => (
                  <tr key={t} className="border-t border-smn-gris-100"><td className="py-2">{t}</td><td className="py-2 text-right tabular-nums font-semibold">${v.toLocaleString("es-MX")}</td></tr>
                ))}
                <tr className="border-t border-smn-gris-100 text-smn-gris-500"><td className="py-2">Tienda típica (mediana)</td><td className="py-2 text-right tabular-nums">$472</td></tr>
              </tbody>
            </table>
          </div>
          <div className="rounded-2xl border p-5" style={{ borderColor: NARANJA }}>
            <div className="text-lg font-semibold">El caso Acapulco</div>
            <table className="mt-3 w-full text-sm">
              <thead><tr className="text-left text-smn-gris-500"><th className="py-2">Tienda</th><th className="py-2 text-right">Inventario</th><th className="py-2 text-right">Venta/sem</th><th className="py-2 text-right">Por $100</th></tr></thead>
              <tbody>
                {ACAPULCO.map(([t, i, v, x]) => (
                  <tr key={t} className="border-t border-smn-gris-100"><td className="py-2">{t}</td><td className="py-2 text-right tabular-nums">{i}</td><td className="py-2 text-right tabular-nums">{v}</td><td className="py-2 text-right tabular-nums font-semibold">${x}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-sm text-smn-gris-700">Palmas vende menos de un tercio que Acapulco 2 y tiene la mitad de su inventario. ¿Su grupo de días es el correcto?</p>
          </div>
        </div>
      </Seccion>

      <Seccion titulo="Departamentos y artículos sin venta">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className={tarjeta}>
            <div className="mb-2 font-semibold">Departamentos más grandes</div>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-smn-gris-500"><th className="py-2">Departamento</th><th className="py-2 text-right">Inventario</th><th className="py-2 text-right">Venta 13 sem</th></tr></thead>
              <tbody>{DEPTOS.map(([d, i, v]) => (<tr key={d} className="border-t border-smn-gris-100"><td className="py-2">{d}</td><td className="py-2 text-right tabular-nums">{i}</td><td className="py-2 text-right tabular-nums">{v}</td></tr>))}</tbody>
            </table>
          </div>
          <div className={tarjeta}>
            <div className="mb-2 font-semibold">Más inventario sin venta en 13 semanas</div>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-smn-gris-500"><th className="py-2">Artículo</th><th className="py-2">Clase</th><th className="py-2 text-right">A costo</th></tr></thead>
              <tbody>{SIN_VENTA.map(([s, d, c, v]) => (<tr key={s} className="border-t border-smn-gris-100"><td className="py-2">{s} {d}</td><td className="py-2">{c}</td><td className="py-2 text-right tabular-nums">{v}</td></tr>))}</tbody>
            </table>
          </div>
        </div>
      </Seccion>

      <Seccion titulo="Lo que todavía no podemos ver" nota="Para pasar de foto a control faltan estos datos de Sistemas.">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {FALTA.map(([t, d]) => (
            <div key={t} className="rounded-2xl bg-smn-gris-50 p-5"><div className="font-semibold">{t}</div><p className="mt-1 text-sm text-smn-gris-700">{d}</p></div>
          ))}
        </div>
      </Seccion>
    </>
  );
}
