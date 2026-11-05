"use client";
// Piezas del Radar de precios: miniatura, diferencia contra el mercado, gráfica y tarjeta de coincidencia.

import { motion } from "motion/react";
import { Bot, ExternalLink, ImageOff, ShieldCheck, User } from "lucide-react";
import { useState } from "react";
import { pesos } from "@/lib/api";
import { SEMAFORO, TEXTO_COINCIDENCIA, colorDe, dia, pct, type Coincidencia, type Punto } from "@/lib/precios";
import { Insignia } from "@/componentes/ui";

export const precio = (v: string | null) => (v === null ? "—" : pesos(v));

export function Miniatura({ liga, grande }: { liga: string | null; grande?: boolean }) {
  const [fallo, setFallo] = useState(false);
  const tam = grande ? "h-40 w-40" : "h-11 w-11";
  if (!liga || fallo)
    return (
      <span className={`${tam} flex shrink-0 items-center justify-center rounded-xl bg-smn-gris-100/60 text-smn-gris-500`} title="Sin imagen">
        <ImageOff className={grande ? "h-8 w-8" : "h-4 w-4"} />
      </span>
    );
  return (
    // eslint-disable-next-line @next/next/no-img-element -- imágenes externas (tienda en línea, Google Shopping)
    <img src={liga} alt="" loading="lazy" onError={() => setFallo(true)} className={`${tam} shrink-0 rounded-xl bg-white object-contain p-1`} />
  );
}

/** Diferencia de nuestro precio contra el mercado, con el color del semáforo. Positivo = estamos más caros. */
export function Diferencia({ valor, alerta }: { valor: string | null; alerta: number }) {
  const color = colorDe(valor, alerta);
  if (color === null) return <span className="text-smn-gris-500">—</span>;
  const s = SEMAFORO[color];
  return (
    <Insignia className={`gap-1.5 whitespace-nowrap tabular-nums ${s.insignia}`}>
      <span className={`h-2 w-2 rounded-full ${s.punto}`} aria-hidden />
      <span className="sr-only">{s.texto}: </span>
      {pct(valor)}
    </Insignia>
  );
}

export const ICONO_COINCIDENCIA = { automatica: ShieldCheck, ia: Bot, persona: User };

/** Línea de nuestro precio lista contra la mediana y el mínimo del mercado, por corrida. */
export function Grafica({ serie }: { serie: Punto[] }) {
  const puntos = serie.filter((p) => p.mediana !== null);
  if (puntos.length < 2)
    return <p className="rounded-xl bg-smn-gris-100/60 px-4 py-6 text-center text-sm text-smn-gris-500">La gráfica aparece desde la segunda corrida con precios.</p>;
  const lineas = [
    { clave: "precio_lista" as const, texto: "Nuestro precio lista", clase: "stroke-smn-naranja", punto: "fill-smn-naranja" },
    { clave: "mediana" as const, texto: "Mediana del mercado", clase: "stroke-tinta", punto: "fill-tinta" },
    { clave: "minimo" as const, texto: "Mínimo del mercado", clase: "stroke-smn-gris-500", punto: "fill-smn-gris-500" },
  ];
  const valores = puntos.flatMap((p) => lineas.map((l) => p[l.clave])).filter((v): v is string => v !== null).map(Number);
  const [min, max] = [Math.min(...valores), Math.max(...valores)];
  const rango = max - min || 1;
  const A = 600, H = 180, M = 8;
  const x = (i: number) => M + (i * (A - 2 * M)) / (puntos.length - 1);
  const y = (v: number) => H - M - ((v - min) / rango) * (H - 2 * M);
  return (
    <div>
      <div className="flex justify-between text-[13px] text-smn-gris-500 tabular-nums">
        <span>{pesos(max)}</span>
      </div>
      <svg viewBox={`0 0 ${A} ${H}`} className="h-44 w-full" role="img" aria-label="Historial de precios">
        {lineas.map((l, li) => {
          const d = puntos
            .map((p, i) => (p[l.clave] === null ? null : `${x(i)},${y(Number(p[l.clave]))}`))
            .filter(Boolean)
            .join(" L ");
          return (
            <g key={l.clave}>
              <motion.path
                d={`M ${d}`}
                className={`${l.clase} fill-none`}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeDasharray={l.clave === "minimo" ? "6 5" : undefined}
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.6, delay: li * 0.1 }}
              />
              {puntos.map((p, i) => p[l.clave] !== null && <circle key={i} cx={x(i)} cy={y(Number(p[l.clave]))} r={3} className={l.punto} />)}
            </g>
          );
        })}
      </svg>
      <p className="text-[13px] text-smn-gris-500 tabular-nums">{pesos(min)}</p>
      <div className="mt-1 flex flex-wrap justify-between gap-2 text-[13px] text-smn-gris-500">
        <span>{dia(puntos[0].fecha, "medium")}</span>
        <span className="flex flex-wrap gap-3">
          {lineas.map((l) => (
            <span key={l.clave} className="flex items-center gap-1">
              <svg width="14" height="4" aria-hidden>
                <line x1="0" y1="2" x2="14" y2="2" className={l.clase} strokeWidth={3} strokeDasharray={l.clave === "minimo" ? "4 3" : undefined} />
              </svg>
              {l.texto}
            </span>
          ))}
        </span>
        <span>{dia(puntos[puntos.length - 1].fecha, "medium")}</span>
      </div>
    </div>
  );
}

export function TarjetaCoincidencia({ m }: { m: Coincidencia }) {
  const Icono = ICONO_COINCIDENCIA[m.estado as keyof typeof ICONO_COINCIDENCIA] ?? ShieldCheck;
  return (
    <div className="flex gap-3">
      <Miniatura liga={m.imagen} />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold break-words">{m.titulo ?? "Sin título"}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[13px] text-smn-gris-500">
          <Icono className="h-3.5 w-3.5" /> {TEXTO_COINCIDENCIA[m.estado]}
          {m.decidido_por && ` por ${m.decidido_por}`}
          {m.confianza && ` · ${Number(m.confianza).toFixed(0)} de 100`}
          {m.liga && (
            <a href={m.liga} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-tinta hover:underline">
              Ver en Google <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </p>
        {m.motivo && <p className="mt-1 text-[13px] text-smn-gris-700">{m.motivo}</p>}
        {m.iguales.length > 0 && (
          <div className="mt-2">
            <p className="text-[13px] font-semibold text-smn-gris-700">
              También {m.iguales.length === 1 ? "cuenta 1 publicación" : `cuentan ${m.iguales.length} publicaciones`} del mismo producto:
            </p>
            <ul className="mt-1 space-y-0.5 text-[13px] text-smn-gris-500">
              {m.iguales.map((p, i) => (
                <li key={i} className="break-words">
                  {p.liga ? (
                    <a href={p.liga} target="_blank" rel="noopener noreferrer" className="hover:underline">{p.titulo ?? "Sin título"}</a>
                  ) : (p.titulo ?? "Sin título")}
                  {p.vendedor && ` · ${p.vendedor}`}
                  {p.precio && ` · ${pesos(Number(p.precio))}`}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export function Dato({ t, v }: { t: string; v: string }) {
  return (
    <div>
      <dt className="text-[13px] text-smn-gris-500">{t}</dt>
      <dd className="font-semibold tabular-nums">{v}</dd>
    </div>
  );
}
