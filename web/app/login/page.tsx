"use client";
// Inicio de sesión con usuario (correo) y contraseña, sin Microsoft 365.

import Image from "next/image";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { Building2, Eye, EyeOff, MailCheck, Store } from "lucide-react";
import { useEffect, useState } from "react";
import { Boton, Campo } from "@/componentes/ui";
import { FranjaEntorno } from "@/componentes/avisos";
import { SelectorTema } from "@/componentes/selector-tema";
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

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-screen flex-col">
        <FranjaEntorno />
        <div className="grid flex-1 lg:grid-cols-[1.1fr_1fr]">
          {/* Panel de marca */}
          <section className="relative hidden overflow-hidden bg-smn-negro p-12 text-white lg:flex lg:flex-col lg:justify-between">
            <motion.div
              aria-hidden
              className="absolute -top-32 -left-24 h-[28rem] w-[28rem] rounded-full bg-smn-naranja/30 blur-3xl"
              animate={{ x: [0, 40, 0], y: [0, 30, 0] }}
              transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
            />
            <motion.div
              aria-hidden
              className="absolute -right-24 -bottom-40 h-[30rem] w-[30rem] rounded-full bg-smn-naranja/20 blur-3xl"
              animate={{ x: [0, -30, 0], y: [0, -40, 0] }}
              transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
            />
            <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="relative h-auto w-64" priority />
            <motion.div className="relative max-w-md" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
              <p className="text-sm font-bold tracking-widest text-smn-naranja uppercase">Transformación digital</p>
              <h1 className="mt-3 text-4xl leading-tight font-extrabold">Todas las iniciativas de SMN en un solo lugar.</h1>
              <p className="mt-4 text-white/60">Compras, Recursos Humanos y las áreas que vienen, con la misma cuenta.</p>
            </motion.div>
            <p className="relative text-xs text-white/40">© Súper Mayoreo Naturista</p>
          </section>

          {/* Formulario */}
          <section className="relative flex items-center justify-center px-5 py-10 sm:px-10">
            <div className="absolute top-4 right-4">
              <SelectorTema />
            </div>
            <motion.div className="w-full max-w-sm" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
              <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="mb-10 h-auto w-52 lg:hidden dark:hidden" priority />
              <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="mb-10 hidden h-auto w-52 dark:block lg:dark:hidden" priority />

              <h2 className="text-2xl font-extrabold tracking-tight">{recuperar ? "Recupera tu contraseña" : "Inicia sesión"}</h2>
              <p className="mt-1 text-sm text-smn-gris-500">
                {recuperar ? "Te enviaremos una liga de un solo uso a tu correo." : "Usa el correo y la contraseña que te dio el administrador."}
              </p>

              {!recuperar && (
                <div className="mt-6 grid grid-cols-2 rounded-xl bg-smn-gris-100 p-1" role="tablist">
                  {pestanas.map(({ tipo: t, texto, icono: Icono }) => (
                    <button
                      key={t}
                      role="tab"
                      aria-selected={tipo === t}
                      onClick={() => setTipo(t)}
                      className={`relative flex items-center justify-center gap-2 rounded-lg py-2 text-sm font-bold transition-colors ${tipo === t ? "text-tinta" : "text-smn-gris-500"}`}
                    >
                      {tipo === t && <motion.span layoutId="pestana-login" className="absolute inset-0 rounded-lg bg-superficie shadow-sm" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
                      <Icono className="relative h-4 w-4" />
                      <span className="relative">{texto}</span>
                    </button>
                  ))}
                </div>
              )}

              <AnimatePresence mode="wait">
                {ligaEnviada ? (
                  <motion.div key="enviada" initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="mt-6 rounded-2xl border border-smn-gris-100 bg-superficie p-6 text-center">
                    <MailCheck className="mx-auto h-10 w-10 text-smn-naranja" />
                    <p className="mt-3 font-bold">Revisa tu correo</p>
                    <p className="mt-1 text-sm text-smn-gris-500">Si {correo} tiene cuenta, recibirá una liga válida por 30 minutos.</p>
                    <p className="mt-2 text-xs text-smn-gris-500">Mientras no hay correo de salida, pide la liga al administrador de la plataforma.</p>
                    <Boton variante="secundario" className="mt-5 w-full" onClick={() => { setRecuperar(false); setLigaEnviada(false); }}>
                      Volver a iniciar sesión
                    </Boton>
                  </motion.div>
                ) : (
                  <motion.form key={recuperar ? "rec" : tipo} onSubmit={entrar} noValidate className="mt-6 space-y-4" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.2 }}>
                    <Campo
                      etiqueta={tipo === "interno" ? "Correo de SMN" : "Correo de tu empresa"}
                      type="email"
                      autoComplete="email"
                      placeholder={tipo === "interno" ? "nombre@ejemplo.mx" : "contacto@tuempresa.mx"}
                      value={correo}
                      onChange={(e) => setCorreo(e.target.value)}
                      error={errores.correo}
                    />
                    {!recuperar && (
                      <div className="relative">
                        <Campo
                          etiqueta="Contraseña"
                          type={ver ? "text" : "password"}
                          autoComplete="current-password"
                          placeholder="Mínimo 10 caracteres"
                          value={contrasena}
                          onChange={(e) => setContrasena(e.target.value)}
                          error={errores.contrasena}
                        />
                        <button type="button" onClick={() => setVer((v) => !v)} className="absolute top-9 right-3 text-smn-gris-500 hover:text-tinta" aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"}>
                          {ver ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                        </button>
                      </div>
                    )}
                    <AnimatePresence>
                      {errores.general && (
                        <motion.p
                          role="alert"
                          initial={{ opacity: 0, x: 0 }}
                          animate={{ opacity: 1, x: [0, -6, 6, -3, 0] }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.35 }}
                          className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-600 dark:text-red-400"
                        >
                          {errores.general}
                        </motion.p>
                      )}
                    </AnimatePresence>
                    <Boton type="submit" cargando={cargando} className="w-full py-3">
                      {recuperar ? "Enviar liga" : "Entrar"}
                    </Boton>
                    <button type="button" onClick={() => { setRecuperar((v) => !v); setErrores({}); }} className="block w-full text-center text-sm font-semibold text-smn-gris-700 underline-offset-4 hover:underline">
                      {recuperar ? "Volver a iniciar sesión" : "¿Olvidaste tu contraseña?"}
                    </button>
                  </motion.form>
                )}
              </AnimatePresence>

              {tipo === "externo" && !recuperar && (
                <p className="mt-6 rounded-xl bg-smn-gris-100 p-3 text-xs text-smn-gris-700">
                  ¿Aún no tienes cuenta? El equipo de Compras de SMN te envía una invitación a tu correo.
                </p>
              )}
            </motion.div>
          </section>
        </div>
      </div>
    </MotionConfig>
  );
}
