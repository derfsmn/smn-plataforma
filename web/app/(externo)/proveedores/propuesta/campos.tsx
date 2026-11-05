"use client";
// Campos del cuestionario de productos nuevos. Cada uno muestra su error (lo calcula el servidor en `faltantes`).

import { motion } from "motion/react";
import type { Opcion } from "@/lib/propuestas";

const marco = (error?: string) =>
  `w-full rounded-xl border bg-superficie px-3.5 py-2.5 text-base outline-none transition-shadow placeholder:text-smn-gris-300 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20 disabled:bg-smn-gris-50 ${
    error ? "border-red-400" : "border-smn-gris-300"
  }`;

export function Etiqueta({ texto, requerido, ayuda }: { texto: string; requerido?: boolean; ayuda?: string }) {
  return (
    <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">
      {texto}
      {requerido && <span className="text-naranja-tinta"> *</span>}
      {ayuda && <span className="block text-[13px] font-normal text-smn-gris-500">{ayuda}</span>}
    </span>
  );
}

export function Error({ mensaje }: { mensaje?: string }) {
  if (!mensaje) return null;
  return (
    <motion.span initial={{ opacity: 0, y: -2 }} animate={{ opacity: 1, y: 0 }} className="mt-1 block text-sm text-red-700 dark:text-red-400">
      {mensaje}
    </motion.span>
  );
}

type Base = { etiqueta: string; requerido?: boolean; ayuda?: string; error?: string; className?: string };

// Máscaras: cada campo solo acepta su formato desde que se escribe; lo que se guarda ya va limpio
const soloDigitos = (v: string) => v.replace(/\D/g, "");
export const mascaras = {
  rfc: (v: string) => v.toUpperCase().replace(/[^A-ZÑ&0-9]/g, "").slice(0, 13),
  correo: (v: string) => v.toLowerCase().replace(/\s/g, ""),
  telefono: (v: string) => soloDigitos(v).slice(0, 10),
  codigo: (v: string) => soloDigitos(v).slice(0, 14),
  registro: (v: string) => v.toUpperCase().replace(/[^A-ZÑ0-9 /-]/g, ""),
  nombre: (v: string) => v.replace(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]/g, ""),
};
// 55 1234 5678 en pantalla; se guardan solo los 10 dígitos
export const verTelefono = (v: string) => {
  const d = soloDigitos(v);
  return d.length <= 2 ? d : d.length <= 6 ? `${d.slice(0, 2)} ${d.slice(2)}` : `${d.slice(0, 2)} ${d.slice(2, 6)} ${d.slice(6)}`;
};
// Sin espacios de más al salir del campo
const sinEspaciosDeMas = (v: string) => v.replace(/[ \t]+/g, " ").trim();

export function Texto({
  etiqueta,
  requerido,
  ayuda,
  error,
  className = "",
  valor,
  cambiar,
  mascara,
  ver,
  ...resto
}: Base & { valor: string | null; cambiar: (v: string) => void; mascara?: (v: string) => string; ver?: (v: string) => string } & Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange"
  >) {
  const v = valor ?? "";
  return (
    <label className={`block ${className}`}>
      <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
      <input
        value={ver ? ver(v) : v}
        onChange={(e) => cambiar(mascara ? mascara(e.target.value) : e.target.value)}
        onBlur={() => {
          const limpio = sinEspaciosDeMas(v);
          if (limpio !== v) cambiar(limpio);
        }}
        className={marco(error)}
        aria-invalid={!!error}
        {...resto}
      />
      <Error mensaje={error} />
    </label>
  );
}

// Solo dígitos y un punto decimal; sin «e», signos ni comas de miles (1,250.50 queda 1250.50)
export function numeroConMascara(v: string, decimales: number, max?: number) {
  let t = v.replace(decimales ? /[^\d.]/g : /\D/g, "");
  const punto = t.indexOf(".");
  if (punto >= 0) t = t.slice(0, punto + 1) + t.slice(punto + 1).replace(/\./g, "").slice(0, decimales);
  if (t.length > 1 && t.startsWith("0") && t[1] !== ".") t = t.replace(/^0+(?=\d)/, "");
  if (max !== undefined && Number(t) > max) t = String(max);
  return t.slice(0, 12);
}

export function Numero({
  etiqueta,
  requerido,
  ayuda,
  error,
  className = "",
  valor,
  cambiar,
  max,
  decimales = 2,
  sufijo,
}: Base & { valor: string | null; cambiar: (v: string) => void; max?: number; decimales?: number; sufijo?: string }) {
  const v = valor ?? "";
  return (
    <label className={`block ${className}`}>
      <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
      <span className="relative block">
        <input
          value={v}
          onChange={(e) => cambiar(numeroConMascara(e.target.value, decimales, max))}
          onBlur={() => v.endsWith(".") && cambiar(v.slice(0, -1))}
          type="text"
          inputMode={decimales ? "decimal" : "numeric"}
          className={`${marco(error)} ${sufijo ? "pr-14" : ""}`}
          aria-invalid={!!error}
        />
        {sufijo && <span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center text-sm text-smn-gris-500">{sufijo}</span>}
      </span>
      <Error mensaje={error} />
    </label>
  );
}

export function Area({ etiqueta, requerido, ayuda, error, className = "", valor, cambiar, maximo }: Base & { valor: string | null; cambiar: (v: string) => void; maximo: number }) {
  return (
    <label className={`block ${className}`}>
      <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
      <textarea value={valor ?? ""} onChange={(e) => cambiar(e.target.value)} maxLength={maximo} rows={3} className={`${marco(error)} resize-y`} aria-invalid={!!error} />
      <span className="mt-0.5 block text-right text-[13px] text-smn-gris-500">
        {(valor ?? "").length} / {maximo}
      </span>
      <Error mensaje={error} />
    </label>
  );
}

// Desplegable. Si la opción es «Otro» u «Otra», pide el texto.
export function Lista({
  etiqueta,
  requerido,
  ayuda,
  error,
  className = "",
  valor,
  cambiar,
  opciones,
  otro,
  cambiarOtro,
  errorOtro,
}: Base & {
  valor: string | null;
  cambiar: (v: string) => void;
  opciones: Opcion[];
  otro?: string | null;
  cambiarOtro?: (v: string) => void;
  errorOtro?: string;
}) {
  const conOtro = cambiarOtro && ["otro", "otra"].includes((valor ?? "").toLowerCase());
  return (
    <div className={className}>
      <label className="block">
        <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
        <select value={valor ?? ""} onChange={(e) => cambiar(e.target.value)} className={marco(error)} aria-invalid={!!error}>
          <option value="">Selecciona…</option>
          {opciones.map((o) => (
            <option key={o.valor} value={o.valor}>
              {o.texto}
            </option>
          ))}
        </select>
        <Error mensaje={error} />
      </label>
      {conOtro && <Texto className="mt-2" etiqueta="Especifica cuál" requerido maxLength={120} valor={otro ?? null} cambiar={cambiarOtro} error={errorOtro} />}
    </div>
  );
}

const pastilla = (activa: boolean) =>
  `inline-flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm font-semibold transition-colors ${
    activa ? "border-smn-naranja bg-smn-naranja/15 text-tinta" : "border-smn-gris-300 text-smn-gris-700 hover:border-tinta"
  }`;

export function SiNo({ etiqueta, requerido, ayuda, error, className = "", valor, cambiar }: Base & { valor: string | null; cambiar: (v: string) => void }) {
  return (
    <fieldset className={className}>
      <legend>
        <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
      </legend>
      <div className="flex gap-2">
        {[
          ["si", "Sí"],
          ["no", "No"],
        ].map(([v, t]) => (
          <label key={v} className={pastilla(valor === v)}>
            <input type="radio" className="sr-only" checked={valor === v} onChange={() => cambiar(v)} />
            {t}
          </label>
        ))}
      </div>
      <Error mensaje={error} />
    </fieldset>
  );
}

// Casillas. `excluyente`: opción que apaga a las demás (p. ej. «No requiere»).
export function Casillas({
  etiqueta,
  requerido,
  ayuda,
  error,
  className = "",
  valores,
  cambiar,
  opciones,
  excluyente,
  otro,
  cambiarOtro,
  errorOtro,
}: Base & {
  valores: string[];
  cambiar: (v: string[]) => void;
  opciones: Opcion[];
  excluyente?: string;
  otro?: string | null;
  cambiarOtro?: (v: string) => void;
  errorOtro?: string;
}) {
  const alternar = (v: string) => {
    if (valores.includes(v)) return cambiar(valores.filter((x) => x !== v));
    if (v === excluyente) return cambiar([v]);
    cambiar([...valores.filter((x) => x !== excluyente), v]);
  };
  return (
    <fieldset className={className}>
      <legend>
        <Etiqueta texto={etiqueta} requerido={requerido} ayuda={ayuda} />
      </legend>
      <div className="flex flex-wrap gap-2">
        {opciones.map((o) => (
          <label key={o.valor} className={pastilla(valores.includes(o.valor))}>
            <input type="checkbox" className="sr-only" checked={valores.includes(o.valor)} onChange={() => alternar(o.valor)} />
            {o.texto}
          </label>
        ))}
      </div>
      <Error mensaje={error} />
      {cambiarOtro && valores.includes("otro") && (
        <Texto className="mt-2" etiqueta="Especifica cuál" requerido maxLength={120} valor={otro ?? null} cambiar={cambiarOtro} error={errorOtro} />
      )}
    </fieldset>
  );
}

export function Casilla({ texto, valor, cambiar, error }: { texto: React.ReactNode; valor: boolean; cambiar: (v: boolean) => void; error?: string }) {
  return (
    <div>
      <label className="flex cursor-pointer items-start gap-3 rounded-2xl border border-smn-gris-100 p-4 hover:border-smn-gris-300">
        <input type="checkbox" checked={valor} onChange={(e) => cambiar(e.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-smn-naranja" />
        <span className="text-sm">{texto}</span>
      </label>
      <Error mensaje={error} />
    </div>
  );
}

export function Tarjeta({ titulo, children, accion }: { titulo?: string; children: React.ReactNode; accion?: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-5 sm:p-6">
      {(titulo || accion) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {titulo && <h3 className="font-semibold">{titulo}</h3>}
          {accion}
        </div>
      )}
      {children}
    </section>
  );
}
