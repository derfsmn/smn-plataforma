"use client";
// Bitácora: quién hizo qué y cuándo. Solo lectura.

import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api, fechaLocal, mensajeDe, type PaginaBitacora } from "@/lib/api";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia, Selector } from "@/componentes/ui";

const ACCIONES: Record<string, string> = {
  login: "Inicio de sesión",
  login_fallido: "Intento fallido",
  invitar: "Invitación",
  reenviar_invitacion: "Invitación reenviada",
  invitacion_aceptada: "Invitación aceptada",
  liga_contrasena: "Liga de contraseña",
  recuperacion_solicitada: "Recuperación pedida",
  contrasena_restablecida: "Contraseña restablecida",
  cambio_contrasena: "Cambio de contraseña",
  actualizar: "Cambio",
  cambiar_estado: "Cambio de estado",
  subir_archivo: "Archivo subido",
};
const ENTIDADES: Record<string, string> = {
  usuario: "Usuario",
  rol: "Rol",
  modulo: "Módulo",
  archivo: "Archivo",
  ia_presupuesto: "Topes de IA",
  ia_tarea: "Tarea de IA",
};
const nombreAccion = (a: string) => ACCIONES[a] ?? a.replaceAll("_", " ");
const colorAccion = (a: string) =>
  a === "login_fallido" ? "bg-red-500/10 text-red-700 dark:text-red-400" : a === "login" ? "bg-smn-gris-100 text-smn-gris-700" : "bg-smn-naranja/15 text-aviso-texto";

export default function Bitacora() {
  const avisar = useAvisos();
  const [filtros, setFiltros] = useState({ buscar: "", accion: "", desde: "", hasta: "" });
  const [buscarEscrito, setBuscarEscrito] = useState("");
  const [pagina, setPagina] = useState(1);
  const [datos, setDatos] = useState<PaginaBitacora | null>(null);
  const [acciones, setAcciones] = useState<string[]>([]);
  const [abierto, setAbierto] = useState<number | null>(null);

  useEffect(() => {
    api<string[]>("/api/nucleo/bitacora/acciones").then(setAcciones).catch(() => {});
  }, []);

  // Espera a que dejes de escribir para buscar
  useEffect(() => {
    const t = setTimeout(() => setFiltros((f) => (f.buscar === buscarEscrito ? f : { ...f, buscar: buscarEscrito })), 350);
    return () => clearTimeout(t);
  }, [buscarEscrito]);

  useEffect(() => setPagina(1), [filtros]);

  useEffect(() => {
    const q = new URLSearchParams({ pagina: String(pagina), por_pagina: "30" });
    if (filtros.buscar) q.set("buscar", filtros.buscar);
    if (filtros.accion) q.set("accion", filtros.accion);
    // Días completos en la hora local de quien consulta
    if (filtros.desde) q.set("desde", new Date(`${filtros.desde}T00:00`).toISOString());
    if (filtros.hasta) {
      const fin = new Date(`${filtros.hasta}T00:00`);
      fin.setDate(fin.getDate() + 1);
      q.set("hasta", fin.toISOString());
    }
    api<PaginaBitacora>(`/api/nucleo/bitacora?${q}`)
      .then(setDatos)
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [filtros, pagina, avisar]);

  const paginas = datos ? Math.max(1, Math.ceil(datos.total / datos.por_pagina)) : 1;
  const poner = (k: keyof typeof filtros) => (v: string) => setFiltros((f) => ({ ...f, [k]: v }));

  return (
    <>
      <Encabezado titulo="Bitácora" descripcion="Registro de accesos y cambios en la plataforma. No se puede editar ni borrar." />

      <Entrada className="mb-5 grid gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Buscar</span>
          <span className="relative block">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
            <input
              value={buscarEscrito}
              onChange={(e) => setBuscarEscrito(e.target.value)}
              placeholder="Nombre, correo o dato"
              className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
            />
          </span>
        </label>
        <Selector
          etiqueta="Acción"
          valor={filtros.accion}
          cambiar={poner("accion")}
          opciones={[{ valor: "", texto: "Todas" }, ...acciones.map((a) => ({ valor: a, texto: nombreAccion(a) }))]}
        />
        <Fecha etiqueta="Desde" valor={filtros.desde} cambiar={poner("desde")} />
        <Fecha etiqueta="Hasta" valor={filtros.hasta} cambiar={poner("hasta")} />
      </Entrada>

      {!datos ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Esqueleto key={i} className="h-14" />
          ))}
        </div>
      ) : (
        <>
          <p className="mb-2 text-sm text-smn-gris-500">
            {datos.total.toLocaleString("es-MX")} {datos.total === 1 ? "registro" : "registros"}
          </p>
          <ul className="overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie">
            {datos.renglones.length === 0 && <li className="px-4 py-12 text-center text-sm text-smn-gris-500">No hay registros con esos filtros.</li>}
            {datos.renglones.map((r, i) => (
              <motion.li
                key={r.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i, 12) * 0.02 }}
                className="border-b border-smn-gris-100 last:border-0"
              >
                <button
                  onClick={() => setAbierto(abierto === r.id ? null : r.id)}
                  className="grid w-full grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-smn-gris-50 md:grid-cols-[10rem_1fr_11rem_8rem_auto]"
                  aria-expanded={abierto === r.id}
                >
                  <span className="order-2 text-[13px] text-smn-gris-500 md:order-none md:text-sm">{fechaLocal(r.ocurrido_en)}</span>
                  <span className="order-1 min-w-0 md:order-none">
                    <span className="block truncate text-sm font-semibold">{r.usuario ?? "Sin sesión"}</span>
                    <span className="block truncate text-[13px] text-smn-gris-500">{r.correo ?? (r.detalle as { correo?: string })?.correo ?? ""}</span>
                  </span>
                  <span className="order-3 md:order-none">
                    <Insignia className={colorAccion(r.accion)}>{nombreAccion(r.accion)}</Insignia>
                  </span>
                  <span className="order-4 hidden text-sm text-smn-gris-500 md:block">
                    {r.entidad ? `${ENTIDADES[r.entidad] ?? r.entidad}${r.entidad_id ? ` ${r.entidad_id}` : ""}` : ""}
                  </span>
                  <ChevronDown className={`order-5 hidden h-4 w-4 text-smn-gris-500 transition-transform md:block ${abierto === r.id ? "rotate-180" : ""}`} />
                </button>
                <AnimatePresence initial={false}>
                  {abierto === r.id && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                      <dl className="grid gap-2 bg-smn-gris-50 px-4 py-3 text-sm sm:grid-cols-[8rem_1fr]">
                        <dt className="font-semibold text-smn-gris-500">Sobre</dt>
                        <dd>{r.entidad ? `${ENTIDADES[r.entidad] ?? r.entidad} ${r.entidad_id ?? ""}` : "—"}</dd>
                        {r.modulo && (
                          <>
                            <dt className="font-semibold text-smn-gris-500">Módulo</dt>
                            <dd>{r.modulo}</dd>
                          </>
                        )}
                        <dt className="font-semibold text-smn-gris-500">IP</dt>
                        <dd>{r.ip ?? "—"}</dd>
                        <dt className="font-semibold text-smn-gris-500">Detalle</dt>
                        <dd>
                          {r.detalle ? (
                            <pre className="overflow-x-auto rounded-xl bg-superficie p-3 text-[13px]">{JSON.stringify(r.detalle, null, 2)}</pre>
                          ) : (
                            "—"
                          )}
                        </dd>
                      </dl>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.li>
            ))}
          </ul>
          {paginas > 1 && (
            <div className="mt-4 flex items-center justify-between">
              <Boton variante="secundario" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                <ChevronLeft className="h-4 w-4" /> Más recientes
              </Boton>
              <span className="text-sm text-smn-gris-500">
                Página {pagina} de {paginas}
              </span>
              <Boton variante="secundario" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)}>
                Anteriores <ChevronRight className="h-4 w-4" />
              </Boton>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Fecha({ etiqueta, valor, cambiar }: { etiqueta: string; valor: string; cambiar: (v: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">{etiqueta}</span>
      <input
        type="date"
        value={valor}
        onChange={(e) => cambiar(e.target.value)}
        className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
      />
    </label>
  );
}
