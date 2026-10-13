"use client";

import { AnimatePresence, motion } from "motion/react";
import { Check, Copy, Link2, MoreHorizontal, Search, ShieldCheck, UserPlus, UserX, UserCheck, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, haceCuanto, mensajeDe, type Liga, type Rol, type Usuario } from "@/lib/api";
import { iniciales } from "@/componentes/marco-interno";
import { useAvisos } from "@/componentes/avisos";
import { useSesion } from "@/componentes/sesion";
import { Modal } from "@/componentes/modal";
import { Boton, Campo, Encabezado, Esqueleto, Insignia } from "@/componentes/ui";

const estilosEstatus: Record<Usuario["estatus"], string> = {
  activo: "bg-tinta text-superficie",
  invitado: "bg-aviso-fondo text-aviso-texto",
  inactivo: "bg-smn-gris-100 text-smn-gris-500",
};
const filtros = [
  { id: "todos", texto: "Todos" },
  { id: "interno", texto: "Internos" },
  { id: "externo", texto: "Proveedores" },
] as const;

type Ventana =
  | { tipo: "invitar" }
  | { tipo: "liga"; titulo: string; liga: Liga; para: string }
  | { tipo: "rol"; usuario: Usuario };

export default function AdminUsuarios() {
  const avisar = useAvisos();
  const { yo } = useSesion();
  const [lista, setLista] = useState<Usuario[] | null>(null);
  const [roles, setRoles] = useState<Rol[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [texto, setTexto] = useState("");
  const [filtro, setFiltro] = useState<(typeof filtros)[number]["id"]>("todos");
  const [ventana, setVentana] = useState<Ventana | null>(null);

  const cargar = useCallback(() => {
    api<Usuario[]>("/api/nucleo/usuarios").then(setLista).catch((e) => setError(mensajeDe(e)));
  }, []);
  useEffect(() => {
    cargar();
    api<Rol[]>("/api/nucleo/roles").then(setRoles).catch(() => {});
  }, [cargar]);

  const visibles = useMemo(
    () =>
      (lista ?? []).filter(
        (u) => (filtro === "todos" || u.tipo === filtro) && [u.nombre, u.correo, u.area, u.empresa].join(" ").toLowerCase().includes(texto.toLowerCase()),
      ),
    [lista, filtro, texto],
  );

  const reemplazar = (u: Usuario) => setLista((l) => l?.map((x) => (x.id === u.id ? u : x)) ?? null);

  const accion = async (u: Usuario, que: "activar" | "desactivar" | "reenviar" | "liga") => {
    try {
      if (que === "activar" || que === "desactivar") {
        const nuevo = await api<Usuario>(`/api/nucleo/usuarios/${u.id}`, { metodo: "PATCH", cuerpo: { estatus: que === "activar" ? "activo" : "inactivo" } });
        reemplazar(nuevo);
        avisar(`${u.nombre} quedó ${nuevo.estatus === "inactivo" ? "desactivado" : nuevo.estatus}.`);
      } else if (que === "reenviar") {
        const liga = await api<Liga>(`/api/nucleo/usuarios/${u.id}/reenviar-invitacion`, { metodo: "POST" });
        setVentana({ tipo: "liga", titulo: "Invitación renovada", liga, para: u.nombre });
      } else {
        const liga = await api<Liga>(`/api/nucleo/usuarios/${u.id}/liga-contrasena`, { metodo: "POST" });
        setVentana({ tipo: "liga", titulo: "Liga para cambiar contraseña", liga, para: u.nombre });
      }
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  return (
    <>
      <Encabezado
        titulo="Usuarios"
        descripcion="Colaboradores de SMN y proveedores con acceso a la plataforma."
        accion={<Boton onClick={() => setVentana({ tipo: "invitar" })}><UserPlus className="h-4 w-4" /> Invitar usuario</Boton>}
      />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Buscar por nombre, correo, área o empresa"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie py-2.5 pr-3 pl-9 text-sm outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>
        <div className="flex rounded-xl bg-smn-gris-100 p-1">
          {filtros.map((f) => (
            <button key={f.id} onClick={() => setFiltro(f.id)} className={`relative flex-1 rounded-lg px-3 py-1.5 text-sm font-bold ${filtro === f.id ? "" : "text-smn-gris-500"}`}>
              {filtro === f.id && <motion.span layoutId="filtro-usuarios" className="absolute inset-0 rounded-lg bg-superficie shadow-sm" />}
              <span className="relative">{f.texto}</span>
            </button>
          ))}
        </div>
      </div>

      {error ? (
        <p className="rounded-3xl border border-smn-gris-100 bg-superficie p-10 text-center text-sm">{error}</p>
      ) : !lista ? (
        <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} className="h-16" />)}</div>
      ) : (
        <div className="rounded-3xl border border-smn-gris-100 bg-superficie">
          <div className="hidden grid-cols-[2fr_1.2fr_1.4fr_0.8fr_0.9fr_2.5rem] gap-4 border-b border-smn-gris-100 px-5 py-3 text-xs font-bold tracking-wide text-smn-gris-500 uppercase md:grid">
            <span>Nombre</span><span>Área / empresa</span><span>Rol</span><span>Estatus</span><span>Último acceso</span><span />
          </div>
          <ul>
            <AnimatePresence initial={false}>
              {visibles.map((u, i) => (
                <motion.li
                  key={u.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0, transition: { delay: Math.min(i, 10) * 0.03 } }}
                  exit={{ opacity: 0 }}
                  className="relative grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5 border-b border-smn-gris-100 px-5 py-4 last:border-0 md:grid-cols-[2fr_1.2fr_1.4fr_0.8fr_0.9fr_2.5rem] md:gap-4"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-extrabold ${u.tipo === "externo" ? "bg-smn-negro text-smn-naranja" : "bg-smn-naranja/20 text-tinta"}`}>{iniciales(u.nombre)}</span>
                    <div className="min-w-0">
                      <p className="truncate font-bold">{u.nombre}{u.id === yo.usuario.id && <span className="ml-1.5 text-xs font-semibold text-smn-gris-500">(tú)</span>}</p>
                      <p className="truncate text-xs text-smn-gris-500">{u.correo}</p>
                    </div>
                  </div>
                  <div className="row-span-1 md:hidden">
                    <MenuAcciones usuario={u} esYo={u.id === yo.usuario.id} accion={accion} cambiarRol={() => setVentana({ tipo: "rol", usuario: u })} />
                  </div>
                  <span className="col-span-2 text-sm text-smn-gris-700 md:col-span-1">{u.empresa ?? u.area ?? "—"}</span>
                  <span className="col-span-2 text-sm md:col-span-1">{u.roles.map((r) => r.nombre).join(", ")}</span>
                  <span className="flex items-center gap-3 md:block">
                    <Insignia className={estilosEstatus[u.estatus]}>{u.estatus}</Insignia>
                    <span className="text-xs text-smn-gris-500 md:hidden">{haceCuanto(u.ultimo_acceso_en)}</span>
                  </span>
                  <span className="hidden text-sm text-smn-gris-500 md:block">{haceCuanto(u.ultimo_acceso_en)}</span>
                  <div className="hidden md:block">
                    <MenuAcciones usuario={u} esYo={u.id === yo.usuario.id} accion={accion} cambiarRol={() => setVentana({ tipo: "rol", usuario: u })} />
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
          {visibles.length === 0 && <p className="p-10 text-center text-sm text-smn-gris-500">{lista.length ? "Nadie coincide con la búsqueda." : "Aún no hay usuarios."}</p>}
        </div>
      )}

      <AnimatePresence>
        {ventana?.tipo === "invitar" && (
          <Modal titulo="Invitar usuario" cerrar={() => setVentana(null)}>
            <FormularioInvitar
              roles={roles}
              alCrear={(u, liga) => {
                setLista((l) => [u, ...(l ?? [])]);
                setVentana({ tipo: "liga", titulo: "Invitación creada", liga, para: u.nombre });
              }}
            />
          </Modal>
        )}
        {ventana?.tipo === "liga" && (
          <Modal titulo={ventana.titulo} cerrar={() => setVentana(null)}>
            <VerLiga liga={ventana.liga} para={ventana.para} />
          </Modal>
        )}
        {ventana?.tipo === "rol" && (
          <Modal titulo="Cambiar rol" cerrar={() => setVentana(null)}>
            <CambiarRol
              usuario={ventana.usuario}
              roles={roles.filter((r) => r.para === ventana.usuario.tipo)}
              alGuardar={(u) => {
                reemplazar(u);
                setVentana(null);
                avisar(`Rol de ${u.nombre} actualizado.`);
              }}
            />
          </Modal>
        )}
      </AnimatePresence>
    </>
  );
}

function MenuAcciones({
  usuario: u,
  esYo,
  accion,
  cambiarRol,
}: {
  usuario: Usuario;
  esYo: boolean;
  accion: (u: Usuario, que: "activar" | "desactivar" | "reenviar" | "liga") => void;
  cambiarRol: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const cerrar = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setAbierto(false);
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  const opciones = [
    u.estatus === "invitado" && { texto: "Reenviar invitación", icono: Send, hacer: () => accion(u, "reenviar") },
    u.estatus === "activo" && { texto: "Liga para cambiar contraseña", icono: Link2, hacer: () => accion(u, "liga") },
    { texto: "Cambiar rol", icono: ShieldCheck, hacer: cambiarRol },
    !esYo && u.estatus !== "inactivo" && { texto: "Desactivar", icono: UserX, hacer: () => accion(u, "desactivar") },
    u.estatus === "inactivo" && { texto: "Reactivar", icono: UserCheck, hacer: () => accion(u, "activar") },
  ].filter(Boolean) as { texto: string; icono: typeof Send; hacer: () => void }[];

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setAbierto((v) => !v)} aria-label={`Acciones para ${u.nombre}`} className="grid h-9 w-9 place-items-center rounded-full text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta">
        <MoreHorizontal className="h-5 w-5" />
      </button>
      <AnimatePresence>
        {abierto && (
          <motion.ul
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 z-20 mt-1 w-60 origin-top-right overflow-hidden rounded-2xl border border-smn-gris-100 bg-superficie py-1 shadow-xl"
          >
            {opciones.map(({ texto, icono: Icono, hacer }) => (
              <li key={texto}>
                <button onClick={() => { setAbierto(false); hacer(); }} className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm hover:bg-smn-gris-50">
                  <Icono className="h-4 w-4 text-smn-gris-500" /> {texto}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

function Selector({ etiqueta, valor, cambiar, opciones }: { etiqueta: string; valor: string; cambiar: (v: string) => void; opciones: { valor: string; texto: string }[] }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">{etiqueta}</span>
      <select value={valor} onChange={(e) => cambiar(e.target.value)} className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20">
        {opciones.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
      </select>
    </label>
  );
}

function FormularioInvitar({ roles, alCrear }: { roles: Rol[]; alCrear: (u: Usuario, liga: Liga) => void }) {
  const [tipo, setTipo] = useState<Usuario["tipo"]>("interno");
  const [f, setF] = useState({ nombre: "", correo: "", area: "", puesto: "", empresa: "", rfc: "", rol: "" });
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const disponibles = roles.filter((r) => r.para === tipo);
  // Sin rol por omisión: quien invita debe elegirlo (evita dar administrador por descuido)
  const rol = disponibles.some((r) => r.codigo === f.rol) ? f.rol : "";
  const poner = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const valido = f.nombre.trim().length >= 2 && /^\S+@\S+\.\S+$/.test(f.correo) && rol && (tipo === "interno" || f.empresa.trim());

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valido) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api<{ usuario: Usuario } & Liga>("/api/nucleo/usuarios/invitar", {
        cuerpo: {
          tipo, nombre: f.nombre, correo: f.correo, rol,
          ...(tipo === "interno" ? { area: f.area || null, puesto: f.puesto || null } : { empresa: f.empresa, rfc: f.rfc || null }),
        },
      });
      alCrear(r.usuario, { liga: r.liga, expira_en: r.expira_en });
    } catch (err) {
      setError(mensajeDe(err));
      setCargando(false);
    }
  };

  return (
    <form onSubmit={enviar} className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        {(["interno", "externo"] as const).map((t) => (
          <button
            type="button"
            key={t}
            onClick={() => setTipo(t)}
            className={`rounded-xl border-2 p-3 text-sm font-bold transition-colors ${tipo === t ? "border-smn-naranja bg-smn-naranja/10" : "border-smn-gris-100"}`}
          >
            {t === "interno" ? "Colaborador SMN" : "Proveedor"}
          </button>
        ))}
      </div>
      <Campo etiqueta={tipo === "interno" ? "Nombre completo" : "Nombre del contacto"} value={f.nombre} onChange={poner("nombre")} />
      <Campo etiqueta="Correo" type="email" value={f.correo} onChange={poner("correo")} />
      {tipo === "interno" ? (
        <div className="grid grid-cols-2 gap-3">
          <Campo etiqueta="Área" value={f.area} onChange={poner("area")} placeholder="Compras" />
          <Campo etiqueta="Puesto" value={f.puesto} onChange={poner("puesto")} />
        </div>
      ) : (
        <div className="grid grid-cols-[1.4fr_1fr] gap-3">
          <Campo etiqueta="Razón social" value={f.empresa} onChange={poner("empresa")} />
          <Campo etiqueta="RFC (opcional)" value={f.rfc} onChange={poner("rfc")} maxLength={13} />
        </div>
      )}
      <Selector
        etiqueta="Rol"
        valor={rol}
        cambiar={(v) => setF({ ...f, rol: v })}
        opciones={[{ valor: "", texto: "Elige un rol" }, ...disponibles.map((r) => ({ valor: r.codigo, texto: r.nombre }))]}
      />
      {error && <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-600 dark:text-red-400">{error}</p>}
      <p className="text-xs text-smn-gris-500">Se crea una liga de un solo uso para que la persona cree su contraseña. Vence en 7 días.</p>
      <Boton type="submit" disabled={!valido} cargando={cargando} className="w-full py-3">Crear invitación</Boton>
    </form>
  );
}

function VerLiga({ liga, para }: { liga: Liga; para: string }) {
  const [copiada, setCopiada] = useState(false);
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(liga.liga);
      setCopiada(true);
      setTimeout(() => setCopiada(false), 2000);
    } catch {}
  };
  const vence = new Date(liga.expira_en.endsWith("Z") ? liga.expira_en : `${liga.expira_en}Z`).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="space-y-4">
      <p className="text-sm text-smn-gris-700">
        Envíale esta liga a <b>{para}</b> por correo o mensaje. Es de un solo uso y vence el {vence}
      </p>
      <div className="flex items-center gap-2 rounded-xl border border-smn-gris-300 bg-smn-gris-50 p-2 pl-3">
        <code className="min-w-0 flex-1 truncate text-xs">{liga.liga}</code>
        <Boton variante="secundario" className="shrink-0 px-3 py-1.5" onClick={copiar}>
          {copiada ? <Check className="h-4 w-4 text-smn-naranja" /> : <Copy className="h-4 w-4" />}
          {copiada ? "Copiada" : "Copiar"}
        </Boton>
      </div>
      <p className="text-xs text-smn-gris-500">Cuando tengamos correo de salida (etapa 4) la plataforma la enviará sola.</p>
    </div>
  );
}

function CambiarRol({ usuario, roles, alGuardar }: { usuario: Usuario; roles: Rol[]; alGuardar: (u: Usuario) => void }) {
  const [rol, setRol] = useState(usuario.roles[0]?.codigo ?? roles[0]?.codigo ?? "");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const guardar = async () => {
    setCargando(true);
    try {
      alGuardar(await api<Usuario>(`/api/nucleo/usuarios/${usuario.id}`, { metodo: "PATCH", cuerpo: { roles: [rol] } }));
    } catch (e) {
      setError(mensajeDe(e));
      setCargando(false);
    }
  };
  return (
    <div className="space-y-4">
      <p className="text-sm text-smn-gris-700">{usuario.nombre}</p>
      <Selector etiqueta="Rol" valor={rol} cambiar={setRol} opciones={roles.map((r) => ({ valor: r.codigo, texto: r.nombre }))} />
      {error && <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-600 dark:text-red-400">{error}</p>}
      <Boton onClick={guardar} cargando={cargando} className="w-full py-3">Guardar</Boton>
    </div>
  );
}
