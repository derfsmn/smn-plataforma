"use client";
// Cascarón para usuarios internos con el diseño sobrio: menú lateral que se encoge (escritorio), barra inferior
// (celular) y barra superior con la ruta, el buscador Ctrl + K, tema y perfil. El menú se arma con los permisos del usuario.

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion, MotionConfig } from "motion/react";
import { Home, LayoutGrid, Shield, UserRound, LogOut, Users, KeyRound, Boxes, Activity, ChevronDown, ChevronRight, CornerDownRight, ScrollText, Sparkles, Settings, Network, Package, DatabaseZap, Truck, MapPin, Warehouse, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { IconoModulo } from "./icono-modulo";
import { FranjaEntorno, ProveedorAvisos } from "./avisos";
import { SelectorTema } from "./selector-tema";
import { Campana } from "./campana";
import { ProveedorSesion, useSesion } from "./sesion";
import { Paleta, usePaleta, type EntradaPaleta } from "./paleta";
import { NOMBRES_RUTA, RUTAS_CON_PANTALLA } from "@/lib/inicio";

const CLAVE_MENU = "smn_td_menu";

export const iniciales = (nombre: string) =>
  nombre.replace(/\(.*\)/, "").trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

function EnlaceMenu({ href, activo, corto, texto, icono: Icono }: { href: string; activo: boolean; corto: boolean; texto: string; icono: React.ComponentType<{ className?: string }> }) {
  return (
    <Link
      href={href}
      title={corto ? texto : undefined}
      aria-current={activo ? "page" : undefined}
      className={`group relative flex h-11 shrink-0 items-center gap-3 rounded-lg text-[15px] transition-colors ${corto ? "justify-center px-0" : "px-3"} ${
        activo ? "font-medium text-[var(--menu-activo-tinta)]" : "text-[var(--menu-suave)] hover:bg-[var(--menu-hover)] hover:text-[var(--menu-tinta)]"
      }`}
    >
      {activo && <motion.span layoutId="menu-activo" className="absolute inset-0 rounded-lg border border-[var(--menu-linea)] bg-[var(--menu-activo-fondo)]" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
      <Icono className={`relative h-[18px] w-[18px] shrink-0 ${activo ? "text-[var(--menu-activo-icono)]" : "text-[var(--menu-tenue)] group-hover:text-[var(--menu-tinta)]"}`} />
      {!corto && <span className="relative min-w-0 flex-1 truncate">{texto}</span>}
    </Link>
  );
}

// En el tema «Con color» el logo va de un solo color (negro o blanco, el mismo que la letra del menú) para que se lea
// sobre cualquier color: se usa la imagen como máscara y se pinta con --menu-tinta.
function LogoDeUnColor({ src, className = "" }: { src: string; className?: string }) {
  const mascara = { maskImage: `url(${src})`, WebkitMaskImage: `url(${src})`, maskSize: "contain", WebkitMaskSize: "contain", maskRepeat: "no-repeat", WebkitMaskRepeat: "no-repeat", maskPosition: "left center", WebkitMaskPosition: "left center" };
  return <span role="img" aria-label="Súper Naturista" className={`bg-[var(--menu-tinta)] ${className}`} style={mascara} />;
}

// Sección del menú que se contrae: el encabezado abre o cierra sus enlaces. La sección de la pantalla actual siempre
// se ve abierta. Con el menú encogido no hay encabezados, solo una línea entre secciones.
function Seccion({ texto, corto, cerrada, activa, alternar, children }: { texto: string; corto: boolean; cerrada: boolean; activa: boolean; alternar: () => void; children: React.ReactNode }) {
  if (corto) return (<><div className="mx-3 my-4 h-px shrink-0 bg-[var(--menu-linea)]" />{children}</>);
  const abierta = !cerrada || activa;
  return (
    <div className="mt-5 flex shrink-0 flex-col">
      <button
        type="button"
        onClick={alternar}
        aria-expanded={abierta}
        disabled={activa}
        title={activa ? "Aquí estás; esta sección se queda abierta" : abierta ? `Contraer ${texto}` : `Abrir ${texto}`}
        className="group mb-1 flex h-9 shrink-0 items-center justify-between rounded-lg px-3 text-[13px] font-medium text-[var(--menu-tenue)] transition-colors hover:text-[var(--menu-tinta)] disabled:cursor-default disabled:hover:text-[var(--menu-tenue)]"
      >
        {texto}
        <ChevronDown className={`h-4 w-4 transition-transform duration-200 ${abierta ? "" : "-rotate-90"} ${activa ? "opacity-0" : "opacity-60 group-hover:opacity-100"}`} />
      </button>
      <AnimatePresence initial={false}>
        {abierta && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="-mx-1 overflow-hidden px-1"
          >
            <div className="flex flex-col gap-1">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const CLAVE_SECCIONES = "smn_td_menu_cerradas";

// Pantallas dentro de cada iniciativa, para el buscador (se muestran solo con su permiso)
const SUBPANTALLAS: { permiso: string; texto: string; grupo: string; href: string; palabras?: string }[] = [
  { permiso: "compras.precios.ver", texto: "Radar de precios", grupo: "Compras", href: "/compras/precios", palabras: "competencia internet" },
  { permiso: "compras.productos.ver", texto: "Radar de productos", grupo: "Compras", href: "/compras/productos", palabras: "semaforo ideas evaluar" },
  { permiso: "compras.productos.ver", texto: "Buscar oportunidades", grupo: "Compras", href: "/compras/productos/oportunidades" },
  { permiso: "compras.propuestas.ver", texto: "Propuestas de proveedores", grupo: "Compras", href: "/compras/propuestas" },
  { permiso: "compras.radar.ver", texto: "Radar de mercado", grupo: "Compras", href: "/compras/radar", palabras: "tendencias señales noticias" },
  { permiso: "compras.conocimiento.ver", texto: "Base de conocimiento de Compras", grupo: "Compras", href: "/compras/conocimiento", palabras: "politicas pesos" },
  { permiso: "contraloria.diot.ver", texto: "DIOT", grupo: "Contraloría", href: "/contraloria/diot", palabras: "fiscal txt sat" },
  { permiso: "contraloria.diot.ver", texto: "Base de conocimiento fiscal", grupo: "Contraloría", href: "/contraloria/conocimiento", palabras: "criterios" },
  { permiso: "metodos.consultar", texto: "Preguntar a los manuales", grupo: "Métodos", href: "/metodos", palabras: "procedimientos" },
  { permiso: "metodos.consultar", texto: "Manuales vigentes", grupo: "Métodos", href: "/metodos?vista=documentos", palabras: "procedimientos documentos" },
  { permiso: "metodos.cargar", texto: "Borradores de manuales", grupo: "Métodos", href: "/metodos?vista=borradores", palabras: "nuevo manual redactar" },
];

export function MarcoInterno({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <ProveedorAvisos>
        <ProveedorSesion tipo="interno">
          <Marco>{children}</Marco>
        </ProveedorSesion>
      </ProveedorAvisos>
    </MotionConfig>
  );
}

function Marco({ children }: { children: React.ReactNode }) {
  const ruta = usePathname();
  const { yo, salir, puede } = useSesion();
  const [menuPerfil, setMenuPerfil] = useState(false);
  const [corto, setCorto] = useState(false);
  const [cerradas, setCerradas] = useState<string[]>([]);
  const paleta = usePaleta();
  const refPerfil = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      setCorto(localStorage.getItem(CLAVE_MENU) === "corto");
      const g = JSON.parse(localStorage.getItem(CLAVE_SECCIONES) ?? "[]");
      if (Array.isArray(g)) setCerradas(g.filter((x) => typeof x === "string"));
    } catch {}
    const cerrar = (e: MouseEvent) => {
      if (refPerfil.current && !refPerfil.current.contains(e.target as Node)) setMenuPerfil(false);
    };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  const alternarMenu = () =>
    setCorto((v) => {
      try {
        localStorage.setItem(CLAVE_MENU, v ? "largo" : "corto");
      } catch {}
      return !v;
    });

  const alternarSeccion = (clave: string) =>
    setCerradas((v) => {
      const nuevo = v.includes(clave) ? v.filter((x) => x !== clave) : [...v, clave];
      try {
        localStorage.setItem(CLAVE_SECCIONES, JSON.stringify(nuevo));
      } catch {}
      return nuevo;
    });

  const admin = [
    puede("nucleo.usuarios.administrar") && { href: "/admin/usuarios", texto: "Usuarios", icono: Users },
    puede("nucleo.roles.administrar") && { href: "/admin/roles", texto: "Roles y permisos", icono: KeyRound },
    puede("nucleo.modulos.administrar") && { href: "/admin/modulos", texto: "Módulos", icono: Boxes },
    puede("nucleo.ia.administrar") && { href: "/admin/ia", texto: "Inteligencia artificial", icono: Sparkles },
    puede("nucleo.bitacora.ver") && { href: "/admin/bitacora", texto: "Bitácora", icono: ScrollText },
    puede("nucleo.configuracion.administrar") && { href: "/admin/configuracion", texto: "Configuración", icono: Settings },
    puede("nucleo.modulos.administrar") && { href: "/admin/sistema", texto: "Estado del sistema", icono: Activity },
  ].filter(Boolean) as { href: string; texto: string; icono: typeof Users }[];

  // Datos: el Centro de datos y modelos solo lo ven administradores; lo demás, quien tenga su permiso.
  const datos = [
    puede("datos.productos.ver") && { href: "/datos/productos", texto: "Catálogo de productos", icono: Package },
    puede("datos.proveedores.ver") && { href: "/datos/proveedores", texto: "Proveedores", icono: Truck },
    puede("datos.tiendas.ver") && { href: "/datos/tiendas", texto: "Mapa de tiendas", icono: MapPin },
    puede("datos.inventario.ver") && { href: "/datos/inventario", texto: "Salud de inventario", icono: Warehouse },
    puede("datos.etl.ver") && { href: "/datos/etl", texto: "ETL de ventas", icono: DatabaseZap },
    puede("nucleo.modulos.administrar") && { href: "/datos", texto: "Centro de datos y modelos", icono: Network },
  ].filter(Boolean) as { href: string; texto: string; icono: typeof Users }[];

  const entradasPaleta: EntradaPaleta[] = [
    { texto: "Inicio", grupo: "Ir a", href: "/inicio", icono: Home },
    ...yo.modulos.map((m) => ({ texto: m.nombre, grupo: "Iniciativas", href: `/modulos/${m.codigo}`, icono: LayoutGrid, palabras: m.area })),
    ...SUBPANTALLAS.filter((x) => puede(x.permiso)).map((x) => ({ ...x, icono: CornerDownRight })),
    ...datos.map((d) => ({ ...d, grupo: "Datos" })),
    ...admin.map((a) => ({ ...a, grupo: "Administración" })),
  ];

  const inferior = [
    { href: "/inicio", texto: "Inicio", icono: Home },
    ...(yo.modulos[0] ? [{ href: `/modulos/${yo.modulos[0].codigo}`, texto: "Módulos", icono: LayoutGrid, prefijo: "/modulos" }] : []),
    ...(datos[0] ? [{ href: datos[0].href, texto: "Datos", icono: Network, prefijo: "/datos" }] : []),
    ...(admin[0] ? [{ href: admin[0].href, texto: "Admin", icono: Shield, prefijo: "/admin" }] : []),
    { href: "/perfil", texto: "Perfil", icono: UserRound },
  ];
  const { usuario } = yo;

  // Ruta legible para la barra de arriba
  const tramos = ruta.split("/").filter(Boolean);
  const migas = tramos.map((t, i) => {
    const modulo = tramos[i - 1] === "modulos" ? yo.modulos.find((m) => m.codigo === t) : undefined;
    return {
      texto: modulo?.nombre ?? NOMBRES_RUTA[t] ?? (/^\d+$/.test(t) ? "Detalle" : t),
      href: i === 0 && yo.modulos.some((m) => m.codigo === t) ? `/modulos/${t}` : "/" + tramos.slice(0, i + 1).join("/"),
      saltar: t === "modulos",
    };
  }).filter((m) => !m.saltar);

  return (
    <div className={`min-h-screen transition-[padding] duration-200 ${corto ? "lg:pl-[72px]" : "lg:pl-72"}`}>
      {/* Menú lateral */}
      <aside className={`fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-[var(--menu-linea)] bg-[var(--menu-fondo)] font-sobria transition-[width] duration-200 lg:flex ${corto ? "w-[72px] px-3" : "w-72 px-4"}`}>
        <Link href="/inicio" className={`flex shrink-0 items-center pt-7 pb-5 ${corto ? "justify-center" : "px-3"}`} title="Inicio">
          {corto ? (
            <>
              <Image src="/marca/isotipo-naranja.png" alt="Súper Naturista" width={64} height={64} className="h-7 w-7 object-contain marca:hidden" priority />
              <LogoDeUnColor src="/marca/isotipo-naranja.png" className="hidden h-7 w-8 marca:block" />
            </>
          ) : (
            <span className="min-w-0">
              <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-40 dark:hidden marca:hidden" priority />
              <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-40 dark:block marca:hidden" priority />
              <LogoDeUnColor src="/marca/logo-1linea-naranja-blanco.png" className="hidden aspect-[1200/171] w-40 marca:block" />
              <span className="mt-1.5 block text-[13px] text-[var(--menu-tenue)]">Transformación Digital</span>
            </span>
          )}
        </Link>
        <nav className="-mx-1 flex flex-1 flex-col gap-1 overflow-x-hidden overflow-y-auto px-1 pt-3 pb-6">
          <EnlaceMenu href="/inicio" activo={ruta === "/inicio"} corto={corto} texto="Inicio" icono={Home} />
          {yo.modulos.length > 0 && (
            <Seccion
              texto="Iniciativas"
              corto={corto}
              cerrada={cerradas.includes("iniciativas")}
              activa={ruta.startsWith("/modulos") || yo.modulos.some((m) => ruta === `/${m.codigo}` || ruta.startsWith(`/${m.codigo}/`))}
              alternar={() => alternarSeccion("iniciativas")}
            >
              {yo.modulos.map((m) => (
                <EnlaceMenu
                  key={m.codigo}
                  href={`/modulos/${m.codigo}`}
                  activo={ruta === `/modulos/${m.codigo}` || ruta.startsWith(`/${m.codigo}/`) || ruta === `/${m.codigo}`}
                  corto={corto}
                  texto={m.area}
                  icono={({ className }: { className?: string }) => <IconoModulo icono={m.icono} className={className} />}
                />
              ))}
            </Seccion>
          )}
          {datos.length > 0 && (
            <Seccion texto="Datos" corto={corto} cerrada={cerradas.includes("datos")} activa={datos.some((d) => ruta === d.href)} alternar={() => alternarSeccion("datos")}>
              {datos.map(({ href, texto, icono }) => (
                <EnlaceMenu key={href} href={href} activo={ruta === href} corto={corto} texto={texto} icono={icono} />
              ))}
            </Seccion>
          )}
          {admin.length > 0 && (
            <Seccion texto="Administración" corto={corto} cerrada={cerradas.includes("admin")} activa={ruta.startsWith("/admin")} alternar={() => alternarSeccion("admin")}>
              {admin.map(({ href, texto, icono }) => (
                <EnlaceMenu key={href} href={href} activo={ruta === href} corto={corto} texto={texto} icono={icono} />
              ))}
            </Seccion>
          )}
        </nav>
        <button
          onClick={alternarMenu}
          className={`mt-2 mb-6 flex h-11 shrink-0 items-center gap-3 rounded-lg text-[15px] text-[var(--menu-tenue)] hover:bg-[var(--menu-hover)] hover:text-[var(--menu-tinta)] ${corto ? "justify-center" : "px-3"}`}
          aria-label={corto ? "Abrir menú" : "Encoger menú"}
          title={corto ? "Abrir menú" : "Encoger menú"}
        >
          {corto ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
          {!corto && "Encoger menú"}
        </button>
      </aside>

      {/* Barra superior */}
      <header className="sticky top-0 z-20 border-b border-smn-gris-100 bg-superficie/80 font-sobria backdrop-blur-md">
        <FranjaEntorno />
        <div className="flex h-16 items-center gap-3 px-4 sm:px-8">
          <Link href="/inicio" className="lg:hidden">
            <Image src="/marca/logo-1linea-naranja-negro.png" alt="Súper Naturista" width={1200} height={171} className="h-auto w-32 dark:hidden" priority />
            <Image src="/marca/logo-1linea-naranja-blanco.png" alt="Súper Naturista" width={1200} height={171} className="hidden h-auto w-32 dark:block" priority />
          </Link>
          <nav aria-label="Ruta" className="hidden min-w-0 items-center gap-2 text-[15px] lg:flex">
            {migas.map((m, i) => (
              <span key={m.href} className="flex min-w-0 items-center gap-1.5">
                {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-smn-gris-500" />}
                {i === migas.length - 1 ? (
                  <span className="truncate font-medium text-tinta">{m.texto}</span>
                ) : !m.href.startsWith("/modulos/") && !RUTAS_CON_PANTALLA.has(m.href) ? (
                  <span className="truncate text-smn-gris-500">{m.texto}</span>
                ) : (
                  <Link href={m.href} className="truncate text-smn-gris-500 hover:text-tinta">{m.texto}</Link>
                )}
              </span>
            ))}
          </nav>
          <button
            onClick={paleta.abrir}
            className="ml-auto flex h-10 items-center gap-2.5 rounded-lg border border-smn-gris-100 bg-superficie px-3 text-sm text-smn-gris-500 transition-colors hover:border-smn-gris-300 hover:text-tinta sm:w-64"
            aria-label="Buscar o ir a"
          >
            <Search className="h-4 w-4" />
            <span className="hidden sm:inline">Buscar o ir a…</span>
            <kbd className="ml-auto hidden rounded border border-smn-gris-100 px-1.5 font-sobria text-[13px] sm:inline">Ctrl K</kbd>
          </button>
          <div className="flex items-center gap-1.5 sm:gap-2">
            <SelectorTema />
            <Campana />
            <div className="relative" ref={refPerfil}>
              <button
                onClick={() => setMenuPerfil((v) => !v)}
                className="flex items-center gap-2 rounded-md p-1 transition-colors hover:bg-smn-gris-50"
                aria-expanded={menuPerfil}
                aria-label="Menú de perfil"
              >
                <span className="grid h-9 w-9 place-items-center rounded-full border border-smn-gris-100 bg-smn-gris-50 text-[13px] font-semibold text-tinta">{iniciales(usuario.nombre)}</span>
                <ChevronDown className={`hidden h-3.5 w-3.5 text-smn-gris-500 transition-transform sm:block ${menuPerfil ? "rotate-180" : ""}`} />
              </button>
              <AnimatePresence>
                {menuPerfil && (
                  <motion.div
                    initial={{ opacity: 0, y: -4, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -4, scale: 0.98 }}
                    transition={{ duration: 0.12 }}
                    className="absolute right-0 mt-2 w-60 origin-top-right overflow-hidden rounded-lg border border-smn-gris-100 bg-superficie p-1 shadow-xl shadow-black/10"
                  >
                    <div className="px-2.5 py-2">
                      <p className="truncate text-sm font-medium">{usuario.nombre}</p>
                      <p className="truncate text-[13px] text-smn-gris-500">{usuario.correo}</p>
                    </div>
                    <div className="my-1 h-px bg-smn-gris-100" />
                    <Link href="/perfil" onClick={() => setMenuPerfil(false)} className="flex items-center gap-2 rounded-md px-2.5 py-2 text-sm hover:bg-smn-gris-50">
                      <UserRound className="h-4 w-4 text-smn-gris-500" /> Mi perfil
                    </Link>
                    <button onClick={salir} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm hover:bg-smn-gris-50">
                      <LogOut className="h-4 w-4 text-smn-gris-500" /> Cerrar sesión
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </header>

      <Paleta abierta={paleta.abierta} cerrar={paleta.cerrar} entradas={entradasPaleta} preguntar={puede("metodos.consultar")} salir={salir} />

      <main className="mx-auto max-w-6xl px-4 pt-8 pb-28 sm:px-8 lg:pt-10 lg:pb-16">
        <AnimatePresence mode="wait">
          <motion.div key={ruta} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
            {children}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Barra inferior en celular */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-smn-gris-100 bg-superficie/95 pb-[env(safe-area-inset-bottom)] font-sobria backdrop-blur-md lg:hidden">
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${inferior.length}, 1fr)` }}>
          {inferior.map(({ href, texto, icono: Icono, prefijo }) => {
            const activo = prefijo ? ruta.startsWith(prefijo) : ruta === href;
            return (
              <li key={href}>
                <Link href={href} className={`relative flex flex-col items-center gap-0.5 py-2.5 text-[13px] font-medium ${activo ? "text-tinta" : "text-smn-gris-500"}`}>
                  {activo && <motion.span layoutId="inferior-activo" className="absolute top-0 h-0.5 w-8 rounded-b-full bg-smn-naranja" />}
                  <Icono className={`h-5 w-5 ${activo ? "text-smn-naranja" : ""}`} />
                  {texto}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
