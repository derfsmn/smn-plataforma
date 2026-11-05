"use client";
// Inicio de sesión con usuario (correo) y contraseña, sin Microsoft 365.
// Primera pantalla con el diseño «sobrio»: letra Geist, esquinas de 8 px, líneas finas y el naranja solo para lo importante.

import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import {
  AlertCircle, ArrowLeft, ArrowRight, Building2, Eye, EyeOff, Loader2, Lock, Mail, MailCheck, Store,
} from "lucide-react";
import { forwardRef, useEffect, useState } from "react";
import { FranjaEntorno } from "@/componentes/avisos";
import { SelectorTema } from "@/componentes/selector-tema";
import { PanelMarca, Reticula } from "@/componentes/panel-marca";
import { api, mensajeDe, type Yo } from "@/lib/api";
import { destinoDe } from "@/componentes/sesion";

type Tipo = "interno" | "externo";

const pestanas: { tipo: Tipo; texto: string; icono: typeof Store }[] = [
  { tipo: "interno", texto: "Colaborador SMN", icono: Building2 },
  { tipo: "externo", texto: "Proveedor", icono: Store },
];


export default function Login() {
  const router = useRouter();
  const [tipo, setTipo] = useState<Tipo>("interno");
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [ver, setVer] = useState(false);
  const [mayusculas, setMayusculas] = useState(false);
  const [errores, setErrores] = useState<{ correo?: string; contrasena?: string; general?: string }>({});
  const [cargando, setCargando] = useState(false);
  const [recuperar, setRecuperar] = useState(false);
  const [ligaEnviada, setLigaEnviada] = useState(false);

  const validar = () => {
    const e: typeof errores = {};
    if (!/^\S+@\S+\.\S+$/.test(correo)) e.correo = "Escribe un correo válido.";
    if (!recuperar && contrasena.length < 10) e.contrasena = "La contraseña tiene al menos 10 caracteres.";
    setErrores(e);
    return Object.keys(e).length === 0;
  };

  // Si ya hay sesión abierta, entra directo
  useEffect(() => {
    api<Yo>("/api/auth/yo").then((yo) => router.replace(destinoDe(yo))).catch(() => {});
  }, [router]);

  const entrar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!validar()) return;
    setCargando(true);
    try {
      if (recuperar) {
        await api("/api/auth/recuperar", { cuerpo: { correo } });
        setLigaEnviada(true);
      } else {
        const yo = await api<Yo>("/api/auth/iniciar", { cuerpo: { correo, contrasena } });
        const volver = new URLSearchParams(location.search).get("volver");
        router.replace(volver?.startsWith("/") && yo.usuario.tipo === "interno" && !volver.startsWith("/proveedores") ? volver : destinoDe(yo));
        return;
      }
    } catch (e) {
      setErrores({ general: mensajeDe(e) });
    }
    setCargando(false);
  };

  const cambiarModo = (r: boolean) => {
    setRecuperar(r);
    setLigaEnviada(false);
    setErrores({});
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col font-sobria">
        <FranjaEntorno />
        <div className="grid flex-1 lg:grid-cols-[1.05fr_1fr]">
          <PanelMarca />

          {/* Formulario */}
          <section className="relative flex flex-col overflow-hidden bg-superficie">
            <Reticula className="text-smn-gris-100 [mask-image:radial-gradient(ellipse_at_top,black,transparent_65%)]" />
            <div aria-hidden className="pointer-events-none absolute -top-40 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full bg-smn-naranja/10 blur-3xl lg:hidden" />

            <header className="relative flex items-center justify-between px-5 pt-5 sm:px-8">
              <span className="lg:invisible">
                <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-40 dark:hidden" priority />
                <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-40 dark:block" priority />
              </span>
              <SelectorTema />
            </header>

            <div className="relative flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
              <motion.div className="w-full max-w-[380px]" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}>
                <AnimatePresence mode="wait" initial={false}>
                  {ligaEnviada ? (
                    <motion.div key="enviada" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
                      <span className="grid h-11 w-11 place-items-center rounded-lg border border-smn-gris-100 bg-smn-gris-50">
                        <MailCheck className="h-5 w-5 text-smn-naranja" />
                      </span>
                      <h1 className="mt-5 text-[26px] leading-tight font-semibold tracking-tight">Revisa tu correo</h1>
                      <p className="mt-2 text-sm text-smn-gris-500">
                        Si <span className="font-medium text-tinta">{correo}</span> tiene cuenta, recibirá una liga válida por 30 minutos.
                      </p>
                      <p className="mt-3 text-sm text-smn-gris-500">Si no te llega en unos minutos, revisa la carpeta de spam o pide ayuda al administrador de la plataforma.</p>
                      <BotonSobrio type="button" variante="secundario" className="mt-8 w-full" onClick={() => cambiarModo(false)}>
                        <ArrowLeft className="h-4 w-4" /> Volver a iniciar sesión
                      </BotonSobrio>
                    </motion.div>
                  ) : (
                    <motion.div key={recuperar ? "rec" : "entrar"} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
                      <h1 className="text-[26px] leading-tight font-semibold tracking-tight">{recuperar ? "Recupera tu contraseña" : "Inicia sesión"}</h1>
                      <p className="mt-1.5 text-sm text-smn-gris-500">
                        {recuperar ? "Te enviamos una liga de un solo uso a tu correo." : "Usa el correo y la contraseña que te dio el administrador."}
                      </p>

                      {!recuperar && (
                        <div className="mt-7 grid grid-cols-2 rounded-lg border border-smn-gris-100 bg-smn-gris-50 p-0.5" role="tablist" aria-label="Tipo de cuenta">
                          {pestanas.map(({ tipo: t, texto, icono: Icono }) => (
                            <button
                              key={t}
                              type="button"
                              role="tab"
                              aria-selected={tipo === t}
                              onClick={() => setTipo(t)}
                              className={`relative flex items-center justify-center gap-2 rounded-md py-2 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-smn-naranja ${tipo === t ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
                            >
                              {tipo === t && (
                                <motion.span layoutId="pestana-login" className="absolute inset-0 rounded-md border border-smn-gris-100 bg-superficie shadow-[0_1px_2px_rgba(0,0,0,0.06)]" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
                              )}
                              <Icono className="relative h-3.5 w-3.5" />
                              <span className="relative">{texto}</span>
                            </button>
                          ))}
                        </div>
                      )}

                      <form onSubmit={entrar} noValidate className="mt-6 space-y-4">
                        <CampoSobrio
                          id="correo"
                          etiqueta={tipo === "interno" || recuperar ? "Correo" : "Correo de tu empresa"}
                          icono={Mail}
                          type="email"
                          autoComplete="email"
                          autoFocus
                          placeholder={tipo === "interno" ? "nombre@ejemplo.mx" : "contacto@tuempresa.mx"}
                          value={correo}
                          onChange={(e) => setCorreo(e.target.value)}
                          error={errores.correo}
                        />
                        {!recuperar && (
                          <CampoSobrio
                            id="contrasena"
                            etiqueta="Contraseña"
                            icono={Lock}
                            accion={
                              <button type="button" onClick={() => cambiarModo(true)} className="text-[13px] font-medium text-smn-gris-500 underline-offset-4 hover:text-tinta hover:underline">
                                ¿La olvidaste?
                              </button>
                            }
                            type={ver ? "text" : "password"}
                            autoComplete="current-password"
                            placeholder="Mínimo 10 caracteres"
                            value={contrasena}
                            onChange={(e) => setContrasena(e.target.value)}
                            onKeyUp={(e) => setMayusculas(e.getModifierState?.("CapsLock") ?? false)}
                            onBlur={() => setMayusculas(false)}
                            error={errores.contrasena}
                            nota={mayusculas ? "Tienes activadas las mayúsculas." : undefined}
                            final={
                              <button type="button" onClick={() => setVer((v) => !v)} className="grid h-8 w-8 place-items-center rounded-md text-smn-gris-500 hover:bg-smn-gris-50 hover:text-tinta" aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"}>
                                {ver ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                              </button>
                            }
                          />
                        )}

                        <AnimatePresence>
                          {errores.general && (
                            <motion.p
                              role="alert"
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: "auto", x: [0, -5, 5, -2, 0] }}
                              exit={{ opacity: 0, height: 0 }}
                              transition={{ duration: 0.3 }}
                              className="flex items-start gap-2 overflow-hidden rounded-lg border border-red-500/25 bg-red-500/[0.06] px-3 py-2.5 text-sm text-red-700 dark:text-red-300"
                            >
                              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                              {errores.general}
                            </motion.p>
                          )}
                        </AnimatePresence>

                        <BotonSobrio type="submit" cargando={cargando} className="group w-full">
                          {recuperar ? "Enviar liga" : "Entrar"}
                          {!cargando && <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
                        </BotonSobrio>

                        {recuperar && (
                          <button type="button" onClick={() => cambiarModo(false)} className="flex w-full items-center justify-center gap-1.5 text-sm font-medium text-smn-gris-500 hover:text-tinta">
                            <ArrowLeft className="h-3.5 w-3.5" /> Volver a iniciar sesión
                          </button>
                        )}
                      </form>

                      {tipo === "externo" && !recuperar && (
                        <p className="mt-6 border-t border-smn-gris-100 pt-5 text-[13px] text-smn-gris-500">
                          ¿Aún no tienes cuenta? El equipo de Compras de SMN te envía una invitación a tu correo.
                        </p>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            </div>

            <footer className="relative flex items-center justify-between gap-4 px-5 pb-5 text-[13px] text-smn-gris-500 sm:px-8">
              <span>© {new Date().getFullYear()} Súper Mayoreo Naturista</span>
              <span className="hidden sm:inline">¿Problemas para entrar? Escribe al administrador de la plataforma.</span>
            </footer>
          </section>
        </div>
      </div>
    </MotionConfig>
  );
}

// ---------------------------------------------------------------- piezas del diseño sobrio

type CampoProps = React.InputHTMLAttributes<HTMLInputElement> & {
  etiqueta: string;
  icono: typeof Mail;
  error?: string;
  nota?: string;
  accion?: React.ReactNode;
  final?: React.ReactNode;
};

const CampoSobrio = forwardRef<HTMLInputElement, CampoProps>(function CampoSobrio(
  { id, etiqueta, icono: Icono, error, nota, accion, final, className = "", ...resto },
  ref,
) {
  const ayuda = error ?? nota;
  return (
    <div className={className}>
      <div className="mb-1.5 flex items-center justify-between">
        <label htmlFor={id} className="text-[13px] font-medium text-smn-gris-700">
          {etiqueta}
        </label>
        {accion}
      </div>
      <div
        className={`group flex h-11 items-center gap-2.5 rounded-lg border bg-superficie pr-1.5 pl-3 transition-[border-color,box-shadow] focus-within:ring-4 ${
          error
            ? "border-red-500/60 focus-within:ring-red-500/15"
            : "border-smn-gris-100 hover:border-smn-gris-300 focus-within:border-smn-naranja focus-within:ring-smn-naranja/15"
        }`}
      >
        <Icono className={`h-4 w-4 shrink-0 transition-colors ${error ? "text-red-500" : "text-smn-gris-500 group-focus-within:text-smn-naranja"}`} aria-hidden />
        <input
          ref={ref}
          id={id}
          aria-invalid={!!error}
          aria-describedby={ayuda ? `${id}-ayuda` : undefined}
          className="h-full min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-smn-gris-300"
          {...resto}
        />
        {final}
      </div>
      <AnimatePresence initial={false}>
        {ayuda && (
          <motion.p
            id={`${id}-ayuda`}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className={`mt-1.5 text-[13px] ${error ? "text-red-700 dark:text-red-400" : "text-aviso-texto"}`}
          >
            {ayuda}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
});

function BotonSobrio({
  variante = "primario",
  cargando,
  className = "",
  children,
  disabled,
  ...resto
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario"; cargando?: boolean }) {
  const estilos =
    variante === "primario"
      ? "bg-smn-naranja text-smn-negro shadow-[inset_0_1px_0_rgba(255,255,255,0.25),0_1px_2px_rgba(0,0,0,0.12)] hover:brightness-[1.04]"
      : "border border-smn-gris-100 bg-superficie text-tinta hover:border-smn-gris-300";
  return (
    <button
      disabled={disabled || cargando}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-[filter,border-color,transform] active:scale-[0.99] disabled:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-smn-naranja ${estilos} ${className}`}
      {...resto}
    >
      {cargando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
