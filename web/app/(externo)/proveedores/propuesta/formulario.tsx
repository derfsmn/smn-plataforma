"use client";
// Cuestionario de producto nuevo (v4 de Compras). Lo llena el proveedor desde su portal o Compras por él («compras»),
// con un proveedor actual de Intelisis o uno nuevo. Se guarda solo mientras escribe; lo que falta lo calcula el servidor
// (faltantes) para que la regla sea una sola. Al enviar recibe un folio.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, Cloud, CloudOff, Copy, Loader2, MessageSquareWarning, Plus, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { Boton, Entrada, Esqueleto, Insignia } from "@/componentes/ui";
import { api, fechaLocal, mensajeDe } from "@/lib/api";
import {
  estiloEstado, margenDe, presentacionVacia, RUTA, type Catalogos, type Falta, type Propuesta, type Respuestas,
} from "@/lib/propuestas";
import { ResumenPropuesta } from "@/componentes/propuesta-resumen";
import { Archivos } from "./archivos";
import { Area, Casilla, Casillas, Lista, mascaras, Numero, SiNo, Tarjeta, Texto, verTelefono } from "./campos";

type Ruta = (string | number)[];

function poner<T>(objeto: T, ruta: Ruta, valor: unknown): T {
  const copia = structuredClone(objeto) as Record<string | number, unknown>;
  let nodo = copia;
  ruta.slice(0, -1).forEach((k) => (nodo = nodo[k] as Record<string | number, unknown>));
  nodo[ruta.at(-1)!] = valor;
  return copia as T;
}

// Nombre de cada campo para la lista de pendientes del paso de envío
const CAMPOS: Record<string, string> = {
  marca: "Marca", razon_social: "Razón social", rfc: "RFC", es_proveedor_smn: "¿Ya es proveedor de SMN?",
  cuenta_registro_marca: "Registro de funcionamiento y título de marca", publico_objetivo: "Público objetivo",
  contacto_nombre: "Nombre del contacto", contacto_cargo: "Cargo o área", contacto_correo: "Correo", contacto_telefono: "Teléfono",
  contacto_alterno_nombre: "Contacto alterno", contacto_alterno_telefono: "Teléfono alterno", contacto_alterno_correo: "Correo alterno",
  fabricante: "Fabricante", pais_origen: "País de origen", diferenciador: "Diferenciador", necesidad_atendida: "Necesidad que atiende",
  departamento: "Departamento", registro_sanitario: "Registro o aviso sanitario", forma: "Presentación", forma_otro: "Otra presentación",
  ingrediente_principal: "Ingrediente principal", descripcion: "Descripción", codigo_barras: "Código de barras",
  contenido_neto: "Contenido", unidad_medida: "Unidad de contenido", piezas_caja_master: "Piezas por caja master",
  costo_neto_sin_iva: "Costo neto", pvp_sugerido: "Precio al público", margen_propuesto_pct: "Margen propuesto",
  tasa_iva: "IVA", tasa_ieps: "IEPS", canal_actual: "Dónde se vende hoy", comercios_actuales: "Comercios actuales",
  similares_en_smn: "Similares en SMN", cifra: "Cifra", precio: "Precio del competidor", producto: "Competidor",
  manejo_especial: "Manejo especial", vida_util_total_dias: "Vida útil total", vida_util_minima_dias: "Vida útil mínima",
  apoyos: "Apoyos", apoyos_otro: "Otro apoyo", argumento_principal: "Argumento principal", sustento: "Sustento",
};

// «Presentación 2 · Costo neto: Obligatorio.» en lugar de un «Obligatorio.» suelto
function textoPendiente(f: Falta) {
  if (f.campo.startsWith("adjunto.") || f.campo.startsWith("aviso.")) return f.mensaje;
  const partes = f.campo.split(".");
  const fila = partes.find((x) => /^\d+$/.test(x));
  const ultimo = partes[partes.length - 1];
  const nombre = /^\d+$/.test(ultimo) ? null : CAMPOS[ultimo.replace(/_otro$/, "")];
  const prefijo = f.campo.startsWith("presentaciones.") && fila !== undefined ? `Presentación ${Number(fila) + 1} · ` : "";
  const repetido = nombre && f.mensaje.toLowerCase().includes(nombre.toLowerCase());
  return `${prefijo}${nombre && !repetido ? `${nombre}: ` : ""}${f.mensaje}`;
}

const TODOS = ["aviso", "proveedor", "presentaciones", "imagenes", "mercado", "logistica", "lanzamiento", "envio"];

// compras: la captura alguien de Compras. Sin aviso de privacidad (lo acepta el proveedor en su portal), RFC y contactos
// opcionales por ahora, y las ligas regresan a la bandeja de Compras.
export function FormularioPropuesta({ compras = false }: { compras?: boolean }) {
  const PASOS = compras ? TODOS.filter((s) => s !== "aviso") : TODOS;
  const inicio = compras ? "/compras/propuestas" : "/proveedores";
  const editar = (n: number) => (compras ? `/compras/propuestas/captura/${n}` : `/proveedores/propuesta/${n}`);
  const { id } = useParams<{ id: string }>();
  const avisar = useAvisos();
  const router = useRouter();
  const [p, setP] = useState<Propuesta | null>(null);
  const [r, setR] = useState<Respuestas | null>(null);
  const [cat, setCat] = useState<Catalogos | null>(null);
  const [paso, setPaso] = useState(0);
  const [vistas, setVistas] = useState<Set<string>>(new Set());
  const [guardado, setGuardado] = useState<"listo" | "guardando" | "error">("listo");
  const [enviando, setEnviando] = useState(false);
  const [preguntaBorrar, setPreguntaBorrar] = useState(false);
  const pendiente = useRef<Respuestas | null>(null);
  const reloj = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    Promise.all([api<Propuesta>(`${RUTA}/${id}`), api<Catalogos>(`${RUTA}/catalogos`)])
      .then(([prop, c]) => {
        if (compras && !prop.editable) return router.replace(`/compras/propuestas/${prop.id}`); // ya enviada: se revisa allá
        setP(prop);
        setR(prop.respuestas);
        setCat(c);
      })
      .catch((e) => avisar(mensajeDe(e), "info"));
  }, [id, avisar, compras, router]);

  // Lo que llega del servidor actualiza archivos y faltantes, pero no pisa lo que la persona está escribiendo
  const recibir = useCallback((nueva: Propuesta) => setP(nueva), []);

  const guardar = useCallback(async () => {
    const datos = pendiente.current;
    if (!datos) return;
    pendiente.current = null;
    setGuardado("guardando");
    try {
      recibir(await api<Propuesta>(`${RUTA}/${id}`, { metodo: "PUT", cuerpo: { respuestas: datos } }));
      setGuardado(pendiente.current ? "guardando" : "listo");
    } catch {
      pendiente.current = pendiente.current ?? datos;
      setGuardado("error");
    }
  }, [id, recibir]);

  const cambiar = useCallback(
    (ruta: Ruta, valor: unknown) => {
      setR((actual) => {
        if (!actual) return actual;
        const nueva = poner(actual, ruta, valor);
        pendiente.current = nueva;
        if (reloj.current) clearTimeout(reloj.current);
        reloj.current = setTimeout(guardar, 900);
        setGuardado("guardando");
        return nueva;
      });
    },
    [guardar],
  );

  // Guardar antes de salir de la página
  useEffect(() => {
    const salir = (e: BeforeUnloadEvent) => {
      if (pendiente.current) {
        guardar();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", salir);
    return () => window.removeEventListener("beforeunload", salir);
  }, [guardar]);

  const errores = useMemo(() => {
    const m = new Map<string, string>();
    p?.faltantes.forEach((f) => {
      if (vistas.has(f.seccion) && !m.has(f.campo)) m.set(f.campo, f.mensaje);
    });
    return m;
  }, [p, vistas]);
  const err = (campo: string) => errores.get(campo);
  const faltanEn = (seccion: string) => p?.faltantes.filter((f) => f.seccion === seccion) ?? [];

  if (!p || !r || !cat) return <Esqueleto className="h-96" />;

  const o = cat.opciones;
  const ir = (n: number) => {
    setVistas((v) => new Set(v).add(PASOS[paso]));
    setPaso(Math.max(0, Math.min(PASOS.length - 1, n)));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const enviar = async () => {
    setVistas(new Set(PASOS));
    if (reloj.current) clearTimeout(reloj.current);
    await guardar();
    setEnviando(true);
    try {
      const enviada = await api<Propuesta>(`${RUTA}/${id}/enviar`, { metodo: "POST" });
      setP(enviada);
      avisar(`Propuesta enviada con el folio ${enviada.folio}`);
      // Si la captura empezó en el Comité de producto nuevo, se regresa a la reunión (ya se está evaluando)
      const comite = compras ? new URLSearchParams(window.location.search).get("comite") : null;
      if (comite && /^\d+$/.test(comite)) router.replace(`/compras/propuestas/comite/${comite}`);
      else if (compras) router.replace(`/compras/propuestas/${id}`);
      else window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setEnviando(false);
    }
  };

  const duplicar = async () => {
    try {
      const copia = await api<Propuesta>(`${RUTA}/${id}/duplicar`, { metodo: "POST" });
      avisar("Se copió la propuesta. Cambia lo que sea distinto y agrega sus fotos.");
      router.push(editar(copia.id));
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const borrar = async () => {
    try {
      await api(`${RUTA}/${id}`, { metodo: "DELETE" });
      router.replace(inicio);
    } catch (e) {
      avisar(mensajeDe(e), "info");
    }
  };

  const encabezado = (
    <>
      {!compras && ( // en Compras la liga de regreso la pone el layout
        <Link href={inicio} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-smn-gris-500 hover:text-tinta">
          <ArrowLeft className="h-4 w-4" /> Mis propuestas
        </Link>
      )}
      <Entrada className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-naranja-tinta">
            {p.folio ?? "Propuesta nueva"}
            {compras && ` · ${p.empresa} · captura de Compras`}
          </p>
          <h1 className="text-3xl leading-tight font-semibold tracking-tight sm:text-[34px]">{p.producto ?? "Producto nuevo"}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Insignia className={estiloEstado[p.estado]}>{p.estado_texto}</Insignia>
          {p.editable && (
            <span className="flex items-center gap-1 text-[13px] font-medium text-smn-gris-500" aria-live="polite">
              {guardado === "guardando" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : guardado === "error" ? <CloudOff className="h-3.5 w-3.5 text-red-500" /> : <Cloud className="h-3.5 w-3.5" />}
              {guardado === "guardando" ? "Guardando…" : guardado === "error" ? "Sin guardar: revisa tu conexión" : "Guardado"}
            </span>
          )}
          <Boton variante="fantasma" onClick={duplicar} title="Copiar para otro sabor o línea">
            <Copy className="h-4 w-4" /> Duplicar
          </Boton>
        </div>
      </Entrada>
      {p.estado === "devuelta" && p.comentario && (
        <Entrada className="mb-5 flex gap-3 rounded-2xl bg-aviso-fondo p-4 text-aviso-texto">
          <MessageSquareWarning className="h-5 w-5 shrink-0" />
          <div className="text-sm">
            <p className="font-semibold">{compras ? "Se regresó para corregir" : "Compras te regresó la propuesta para que la corrijas"}</p>
            <p className="mt-0.5">{p.comentario}</p>
            <p className="mt-1 text-[13px]">Corrige lo necesario y vuelve a enviarla. Conserva el mismo folio.</p>
          </div>
        </Entrada>
      )}
    </>
  );

  // Ya enviada: se ve lo que mandó y en qué va
  if (!p.editable)
    return (
      <>
        {encabezado}
        <Entrada className="mb-5 flex gap-3 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
          <CheckCircle2 className="h-6 w-6 shrink-0 text-smn-naranja" />
          <div>
            <p className="font-semibold">
              {p.estado === "rechazada" ? "Compras no aceptó esta propuesta" : p.estado === "lista" ? "Tu propuesta pasó a evaluación" : "Recibimos tu propuesta"}
            </p>
            <p className="text-sm text-smn-gris-500">
              {p.estado === "rechazada" && p.comentario ? `Motivo: ${p.comentario}` : "Te avisaremos por correo y en la campana cuando cambie de estado."}
            </p>
          </div>
        </Entrada>
        <Historia p={p} />
        <ResumenPropuesta p={p} cat={cat} />
      </>
    );

  const seccion = PASOS[paso];
  const nombreSeccion = (s: string) => cat.secciones.find((x) => x.valor === s)?.texto ?? "Revisión y envío";
  const pr = r.presentaciones;

  return (
    <>
      {encabezado}

      <nav aria-label="Secciones del cuestionario" className="-mx-4 mb-5 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ol className="flex w-max gap-1 rounded-2xl bg-smn-gris-100 p-1">
          {PASOS.map((s, i) => {
            const completa = s === "envio" ? p.faltantes.length === 0 : faltanEn(s).length === 0;
            return (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => ir(i)}
                  className={`relative flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold whitespace-nowrap transition-colors ${i === paso ? "text-tinta" : "text-smn-gris-500 hover:text-tinta"}`}
                >
                  {i === paso && <motion.span layoutId="paso-propuesta" className="absolute inset-0 rounded-xl bg-superficie shadow-sm" transition={{ duration: 0.25 }} />}
                  <span className={`relative grid h-5 w-5 place-items-center rounded-full text-[13px] ${completa ? "bg-smn-naranja text-smn-negro" : "bg-smn-gris-300 text-superficie"}`}>
                    {completa ? <Check className="h-3 w-3" /> : i + 1}
                  </span>
                  <span className="relative">{nombreSeccion(s)}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="mb-6 h-1.5 overflow-hidden rounded-full bg-smn-gris-100">
        <motion.div
          className="h-full bg-smn-naranja"
          animate={{ width: `${Math.round((PASOS.slice(0, -1).filter((s) => !faltanEn(s).length).length / (PASOS.length - 1)) * 100)}%` }}
        />
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={seccion} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.2 }} className="space-y-4">
          {seccion === "aviso" && (
            <Tarjeta titulo="Aviso de privacidad y declaración">
              <p className="mb-4 text-sm text-smn-gris-500">
                Súper Mayoreo Naturista usa estos datos solo para evaluar tu propuesta.{" "}
                <span className="font-semibold">El texto completo del aviso de privacidad está pendiente de Jurídico.</span>
              </p>
              <div className="space-y-3">
                <Casilla texto="He leído y acepto el aviso de privacidad." valor={r.aviso.acepta_aviso_privacidad} cambiar={(v) => cambiar(["aviso", "acepta_aviso_privacidad"], v)} error={err("aviso.acepta_aviso_privacidad")} />
                <Casilla texto="Declaro que la información es verídica y puede ser verificada por SMN." valor={r.aviso.declara_veracidad} cambiar={(v) => cambiar(["aviso", "declara_veracidad"], v)} error={err("aviso.declara_veracidad")} />
              </div>
            </Tarjeta>
          )}

          {seccion === "proveedor" && (
            <>
              <Tarjeta titulo={compras ? "Proveedor" : "Tu empresa"}>
                <p className="-mt-2 mb-4 text-sm text-smn-gris-500">
                  {compras ? "Se llenan con lo que ya sabemos del proveedor; corrígelos si hace falta." : "Se llenan solos en tus siguientes propuestas; solo corrígelos si cambiaron."}
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Texto etiqueta="Marca" requerido valor={r.proveedor.marca} cambiar={(v) => cambiar(["proveedor", "marca"], v)} error={err("proveedor.marca")} />
                  <Texto etiqueta="Razón social" requerido valor={r.proveedor.razon_social} cambiar={(v) => cambiar(["proveedor", "razon_social"], v)} error={err("proveedor.razon_social")} />
                  <Texto etiqueta="Nombre comercial" ayuda="Si es distinto a la razón social" valor={r.proveedor.nombre_comercial} cambiar={(v) => cambiar(["proveedor", "nombre_comercial"], v)} />
                  <Texto etiqueta="RFC" requerido={!compras} ayuda={compras ? "Opcional por ahora; 12 o 13 caracteres, sin guiones ni espacios" : "12 o 13 caracteres, sin guiones ni espacios"} mascara={mascaras.rfc} autoComplete="off" valor={r.proveedor.rfc} cambiar={(v) => cambiar(["proveedor", "rfc"], v)} error={err("proveedor.rfc")} />
                  <SiNo etiqueta="¿Ya es proveedor de SMN?" requerido valor={r.proveedor.es_proveedor_smn} cambiar={(v) => cambiar(["proveedor", "es_proveedor_smn"], v)} error={err("proveedor.es_proveedor_smn")} />
                </div>
                <Casillas className="mt-4" etiqueta="Público objetivo" requerido opciones={o.publico_objetivo} valores={r.proveedor.publico_objetivo}
                  cambiar={(v) => cambiar(["proveedor", "publico_objetivo"], v)} error={err("proveedor.publico_objetivo")}
                  otro={r.proveedor.publico_objetivo_otro} cambiarOtro={(v) => cambiar(["proveedor", "publico_objetivo_otro"], v)} errorOtro={err("proveedor.publico_objetivo_otro")} />
              </Tarjeta>
              <Tarjeta titulo="Registros">
                <div className="grid gap-4 sm:grid-cols-2">
                  <SiNo etiqueta="¿Está inscrito al GS1?" requerido valor={r.proveedor.inscrito_gs1} cambiar={(v) => cambiar(["proveedor", "inscrito_gs1"], v)} error={err("proveedor.inscrito_gs1")} />
                  <SiNo etiqueta="¿Cuentas con registro de funcionamiento y título de marca?" requerido valor={r.proveedor.cuenta_registro_marca} cambiar={(v) => cambiar(["proveedor", "cuenta_registro_marca"], v)} error={err("proveedor.cuenta_registro_marca")} />
                </div>
                <div className="mt-4 space-y-4">
                  {r.proveedor.inscrito_gs1 === "si" && (
                    <Archivos propuesta={p} tipo="carta_gs1" regla={cat.adjuntos.carta_gs1} etiqueta="Carta de incorporación al GS1" error={err("adjunto.carta_gs1")} cambio={recibir} />
                  )}
                  {r.proveedor.cuenta_registro_marca === "si" && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Archivos propuesta={p} tipo="evidencia_registro_funcionamiento" regla={cat.adjuntos.evidencia_registro_funcionamiento} etiqueta="Registro de funcionamiento" error={err("adjunto.evidencia_registro_funcionamiento")} cambio={recibir} />
                      <Archivos propuesta={p} tipo="evidencia_titulo_marca" regla={cat.adjuntos.evidencia_titulo_marca} etiqueta="Título de marca" error={err("adjunto.evidencia_titulo_marca")} cambio={recibir} />
                    </div>
                  )}
                </div>
              </Tarjeta>
              <Tarjeta titulo={compras ? "Contacto (opcional por ahora)" : "Contacto"}>
                {compras && (
                  <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Si todavía no tienes los datos de contacto, déjalos vacíos. Se pueden completar después.</p>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Texto etiqueta="Nombre del contacto" requerido={!compras} mascara={mascaras.nombre} valor={r.proveedor.contacto_nombre} cambiar={(v) => cambiar(["proveedor", "contacto_nombre"], v)} error={err("proveedor.contacto_nombre")} />
                  <Texto etiqueta="Cargo o área" requerido={!compras} valor={r.proveedor.contacto_cargo} cambiar={(v) => cambiar(["proveedor", "contacto_cargo"], v)} error={err("proveedor.contacto_cargo")} />
                  <Texto etiqueta="Correo" requerido={!compras} type="email" mascara={mascaras.correo} valor={r.proveedor.contacto_correo} cambiar={(v) => cambiar(["proveedor", "contacto_correo"], v)} error={err("proveedor.contacto_correo")} />
                  <Texto etiqueta="Teléfono con lada" requerido={!compras} type="tel" inputMode="numeric" placeholder="55 1234 5678" mascara={mascaras.telefono} ver={verTelefono} valor={r.proveedor.contacto_telefono} cambiar={(v) => cambiar(["proveedor", "contacto_telefono"], v)} error={err("proveedor.contacto_telefono")} />
                  <Texto etiqueta="Nombre de contacto alterno" requerido={!compras} mascara={mascaras.nombre} valor={r.proveedor.contacto_alterno_nombre} cambiar={(v) => cambiar(["proveedor", "contacto_alterno_nombre"], v)} error={err("proveedor.contacto_alterno_nombre")} />
                  <Texto etiqueta="Teléfono de contacto alterno" requerido={!compras} type="tel" inputMode="numeric" placeholder="55 1234 5678" mascara={mascaras.telefono} ver={verTelefono} valor={r.proveedor.contacto_alterno_telefono} cambiar={(v) => cambiar(["proveedor", "contacto_alterno_telefono"], v)} error={err("proveedor.contacto_alterno_telefono")} />
                  <Texto etiqueta="Correo de contacto alterno" requerido={!compras} type="email" mascara={mascaras.correo} valor={r.proveedor.contacto_alterno_correo} cambiar={(v) => cambiar(["proveedor", "contacto_alterno_correo"], v)} error={err("proveedor.contacto_alterno_correo")} />
                </div>
              </Tarjeta>
            </>
          )}

          {seccion === "presentaciones" && (
            <>
              <Tarjeta titulo="Información general del producto">
                <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Se captura una sola vez y aplica a todas las presentaciones.</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Texto etiqueta="Fabricante" requerido valor={r.general.fabricante} cambiar={(v) => cambiar(["general", "fabricante"], v)} error={err("general.fabricante")} />
                  <Lista etiqueta="País de origen" requerido opciones={o.pais_origen} valor={r.general.pais_origen} cambiar={(v) => cambiar(["general", "pais_origen"], v)} error={err("general.pais_origen")}
                    otro={r.general.pais_origen_otro} cambiarOtro={(v) => cambiar(["general", "pais_origen_otro"], v)} errorOtro={err("general.pais_origen_otro")} />
                  <Lista etiqueta="Principal diferenciador" requerido opciones={o.diferenciador} valor={r.general.diferenciador} cambiar={(v) => cambiar(["general", "diferenciador"], v)} error={err("general.diferenciador")}
                    otro={r.general.diferenciador_otro} cambiarOtro={(v) => cambiar(["general", "diferenciador_otro"], v)} errorOtro={err("general.diferenciador_otro")} />
                  <Lista etiqueta="Necesidad que atiende" requerido opciones={o.necesidad_atendida} valor={r.general.necesidad_atendida} cambiar={(v) => cambiar(["general", "necesidad_atendida"], v)} error={err("general.necesidad_atendida")}
                    otro={r.general.necesidad_atendida_otro} cambiarOtro={(v) => cambiar(["general", "necesidad_atendida_otro"], v)} errorOtro={err("general.necesidad_atendida_otro")} />
                  {cat.departamentos.length ? (
                    <Lista etiqueta="Departamento" requerido ayuda="Dónde lo pondrías en Súper Naturista; Compras lo confirma" opciones={cat.departamentos.map((d) => ({ valor: d, texto: d }))}
                      valor={r.general.departamento} cambiar={(v) => cambiar(["general", "departamento"], v)} error={err("general.departamento")} />
                  ) : (
                    <Texto etiqueta="Departamento" requerido ayuda="Dónde lo pondrías en Súper Naturista; Compras lo confirma" valor={r.general.departamento} cambiar={(v) => cambiar(["general", "departamento"], v)} error={err("general.departamento")} />
                  )}
                </div>
              </Tarjeta>
              {pr.map((x, i) => {
                const c = (campo: string) => err(`presentaciones.${i}.${campo}`);
                const m = margenDe(x);
                return (
                  <Tarjeta
                    key={i}
                    titulo={`Presentación ${i + 1}`}
                    accion={
                      pr.length > 1 && (
                        <button type="button" onClick={() => cambiar(["presentaciones"], pr.filter((_, k) => k !== i))} className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-smn-gris-500 hover:bg-smn-gris-100 hover:text-tinta">
                          <Trash2 className="h-4 w-4" /> Quitar
                        </button>
                      )
                    }
                  >
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Texto etiqueta="Código de barras" requerido ayuda="EAN o UPC del empaque (8, 12, 13 o 14 dígitos)" inputMode="numeric" autoComplete="off" mascara={mascaras.codigo} valor={x.codigo_barras}
                        cambiar={(v) => cambiar(["presentaciones", i, "codigo_barras"], v.replace(/\D/g, ""))} error={c("codigo_barras")} />
                      <Texto etiqueta="Número de registro o aviso sanitario" requerido mascara={mascaras.registro} valor={x.registro_sanitario} cambiar={(v) => cambiar(["presentaciones", i, "registro_sanitario"], v)} error={c("registro_sanitario")} />
                      <Lista etiqueta="Presentación" requerido opciones={o.forma} valor={x.forma} cambiar={(v) => cambiar(["presentaciones", i, "forma"], v)} error={c("forma")}
                        otro={x.forma_otro} cambiarOtro={(v) => cambiar(["presentaciones", i, "forma_otro"], v)} errorOtro={c("forma_otro")} />
                      <Texto etiqueta="Ingrediente principal" requerido valor={x.ingrediente_principal} cambiar={(v) => cambiar(["presentaciones", i, "ingrediente_principal"], v)} error={c("ingrediente_principal")} />
                      <Area className="sm:col-span-2" etiqueta="Descripción del producto" requerido maximo={180} valor={x.descripcion} cambiar={(v) => cambiar(["presentaciones", i, "descripcion"], v)} error={c("descripcion")} />
                      <Numero etiqueta="Contenido por presentación" requerido decimales={3} valor={x.contenido_neto} cambiar={(v) => cambiar(["presentaciones", i, "contenido_neto"], v)} error={c("contenido_neto")} />
                      <Lista etiqueta="Unidad de contenido" requerido opciones={o.unidad_medida} valor={x.unidad_medida} cambiar={(v) => cambiar(["presentaciones", i, "unidad_medida"], v)} error={c("unidad_medida")} />
                      <Numero etiqueta="Piezas por caja master" requerido decimales={0} valor={x.piezas_caja_master} cambiar={(v) => cambiar(["presentaciones", i, "piezas_caja_master"], v)} error={c("piezas_caja_master")} />
                      <Numero etiqueta="Costo neto antes de IVA" requerido sufijo="MXN" valor={x.costo_neto_sin_iva} cambiar={(v) => cambiar(["presentaciones", i, "costo_neto_sin_iva"], v)} error={c("costo_neto_sin_iva")} />
                      <Numero etiqueta="Precio al público sugerido" requerido sufijo="MXN" valor={x.pvp_sugerido} cambiar={(v) => cambiar(["presentaciones", i, "pvp_sugerido"], v)} error={c("pvp_sugerido")} />
                      <Numero etiqueta="Margen propuesto" ayuda="Opcional; SMN lo recalcula" max={100} decimales={1} sufijo="%" valor={x.margen_propuesto_pct} cambiar={(v) => cambiar(["presentaciones", i, "margen_propuesto_pct"], v)} error={c("margen_propuesto_pct")} />
                      <Lista etiqueta="IVA" requerido opciones={o.tasa_iva} valor={x.tasa_iva} cambiar={(v) => cambiar(["presentaciones", i, "tasa_iva"], v)} error={c("tasa_iva")} />
                      <Numero etiqueta="IEPS" requerido ayuda="0 si no aplica" max={100} sufijo="%" valor={x.tasa_ieps} cambiar={(v) => cambiar(["presentaciones", i, "tasa_ieps"], v)} error={c("tasa_ieps")} />
                    </div>
                    {m !== null && (
                      <p className="mt-4 rounded-xl bg-smn-gris-50 px-3 py-2 text-sm text-smn-gris-700">
                        Con estos datos, el margen sobre el precio sin impuestos sería de <span className="font-semibold">{m.toFixed(2)} %</span>.
                      </p>
                    )}
                  </Tarjeta>
                );
              })}
              {pr.length < 10 && (
                <Boton variante="secundario" onClick={() => cambiar(["presentaciones"], [...pr, { ...presentacionVacia(), forma: pr.at(-1)?.forma ?? null, ingrediente_principal: pr.at(-1)?.ingrediente_principal ?? null, registro_sanitario: pr.at(-1)?.registro_sanitario ?? null }])}>
                  <Plus className="h-4 w-4" /> Agregar otra presentación
                </Boton>
              )}
            </>
          )}

          {seccion === "imagenes" && (
            <Tarjeta titulo="Imágenes del producto">
              <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Sube fotos legibles del empaque. Con ellas SMN verifica etiquetado y contenido.</p>
              <div className="space-y-6">
                <Archivos propuesta={p} tipo="imagen_producto" regla={cat.adjuntos.imagen_producto} etiqueta="Fotos del producto" ayuda="Marca qué muestra cada foto; frente y reverso son obligatorias"
                  etiquetas={o.etiqueta_producto} error={err("adjunto.imagen_producto")} cambio={recibir} />
                <Archivos propuesta={p} tipo="imagen_etiquetado" regla={cat.adjuntos.imagen_etiquetado} etiqueta="Fotos del etiquetado" ayuda="Tabla nutrimental, sellos u octágonos, certificaciones, ingredientes"
                  etiquetas={o.etiqueta_etiquetado} error={err("adjunto.imagen_etiquetado")} cambio={recibir} />
              </div>
            </Tarjeta>
          )}

          {seccion === "mercado" && (
            <>
              <Tarjeta titulo="¿Dónde se vende hoy?">
                <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Registra puntos de venta actuales, no negociaciones ni planes.</p>
                <Lista etiqueta="¿Dónde se comercializa hoy?" requerido opciones={o.canal_actual} valor={r.mercado.canal_actual} cambiar={(v) => cambiar(["mercado", "canal_actual"], v)} error={err("mercado.canal_actual")} />
                {r.mercado.canal_actual && r.mercado.canal_actual !== "no_se_comercializa" && (
                  <Casillas className="mt-4" etiqueta="¿En qué comercios?" requerido opciones={o.comercios_actuales} valores={r.mercado.comercios_actuales}
                    cambiar={(v) => cambiar(["mercado", "comercios_actuales"], v)} error={err("mercado.comercios_actuales")}
                    otro={r.mercado.comercios_actuales_otro} cambiarOtro={(v) => cambiar(["mercado", "comercios_actuales_otro"], v)} errorOtro={err("mercado.comercios_actuales_otro")} />
                )}
              </Tarjeta>
              <Tarjeta titulo="¿Con qué datos de desempeño cuentas?">
                <Casillas etiqueta="Elige los que tengas" opciones={[...o.desempeno, { valor: "sin_datos", texto: "No cuento con datos" }]}
                  valores={r.mercado.sin_datos_desempeno ? ["sin_datos"] : r.mercado.desempeno.map((d) => d.tipo ?? "")} excluyente="sin_datos"
                  cambiar={(v) => {
                    const sin = v.includes("sin_datos");
                    const antes = new Map(r.mercado.desempeno.map((d) => [d.tipo, d]));
                    cambiar(["mercado"], { ...r.mercado, sin_datos_desempeno: sin,
                      desempeno: sin ? [] : v.map((t) => antes.get(t) ?? { tipo: t, cifra: null, canal: null, periodo: null, fuente: null }) });
                  }} />
                <div className="mt-4 space-y-3">
                  {r.mercado.desempeno.map((d, i) => (
                    <div key={d.tipo} className="rounded-2xl bg-smn-gris-50 p-4">
                      <p className="mb-3 text-sm font-semibold">{o.desempeno.find((x) => x.valor === d.tipo)?.texto}</p>
                      <div className="grid gap-3 sm:grid-cols-4">
                        <Numero etiqueta="Cifra" valor={d.cifra} cambiar={(v) => cambiar(["mercado", "desempeno", i, "cifra"], v)} error={err(`mercado.desempeno.${i}.cifra`)} />
                        <Texto etiqueta="Canal" valor={d.canal} cambiar={(v) => cambiar(["mercado", "desempeno", i, "canal"], v)} />
                        <Texto etiqueta="Periodo" valor={d.periodo} cambiar={(v) => cambiar(["mercado", "desempeno", i, "periodo"], v)} />
                        <Texto etiqueta="Fuente" valor={d.fuente} cambiar={(v) => cambiar(["mercado", "desempeno", i, "fuente"], v)} />
                      </div>
                    </div>
                  ))}
                </div>
              </Tarjeta>
              <Tarjeta titulo="Productos que compiten directamente">
                <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Hasta 3, con precios consultados recientemente.</p>
                <Casilla texto="No identifico comparables" valor={r.mercado.sin_comparables} cambiar={(v) => cambiar(["mercado", "sin_comparables"], v)} />
                {!r.mercado.sin_comparables && (
                  <div className="mt-4 space-y-3">
                    {r.mercado.competidores.map((x, i) => (
                      <div key={i} className="rounded-2xl bg-smn-gris-50 p-4">
                        <div className="mb-3 flex items-center justify-between">
                          <p className="text-sm font-semibold">Competidor {i + 1}</p>
                          <button type="button" onClick={() => cambiar(["mercado", "competidores"], r.mercado.competidores.filter((_, k) => k !== i))} className="text-sm font-semibold text-smn-gris-500 hover:text-tinta">
                            Quitar
                          </button>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <Texto etiqueta="Marca y producto" requerido valor={x.producto} cambiar={(v) => cambiar(["mercado", "competidores", i, "producto"], v)} error={err(`mercado.competidores.${i}.producto`)} />
                          <Texto etiqueta="Presentación" valor={x.presentacion} cambiar={(v) => cambiar(["mercado", "competidores", i, "presentacion"], v)} />
                          <Numero etiqueta="Precio al público" sufijo="MXN" valor={x.precio} cambiar={(v) => cambiar(["mercado", "competidores", i, "precio"], v)} error={err(`mercado.competidores.${i}.precio`)} />
                          <Texto etiqueta="Comercio o canal" valor={x.comercio} cambiar={(v) => cambiar(["mercado", "competidores", i, "comercio"], v)} />
                        </div>
                      </div>
                    ))}
                    {r.mercado.competidores.length < 3 && (
                      <Boton variante="secundario" onClick={() => cambiar(["mercado", "competidores"], [...r.mercado.competidores, { producto: null, presentacion: null, precio: null, comercio: null }])}>
                        <Plus className="h-4 w-4" /> Agregar competidor
                      </Boton>
                    )}
                  </div>
                )}
              </Tarjeta>
              <Tarjeta titulo="Catálogo de Súper Naturista">
                <SiNo etiqueta="¿Identificaste productos similares en el catálogo SMN?" requerido valor={r.mercado.similares_en_smn} cambiar={(v) => cambiar(["mercado", "similares_en_smn"], v)} error={err("mercado.similares_en_smn")} />
                {r.mercado.similares_en_smn === "si" && (
                  <Texto className="mt-4" etiqueta="¿Cuáles?" valor={r.mercado.similares_cuales} cambiar={(v) => cambiar(["mercado", "similares_cuales"], v)} />
                )}
              </Tarjeta>
            </>
          )}

          {seccion === "logistica" && (
            <Tarjeta titulo="Entrega y vida útil">
              <Casillas etiqueta="Manejo especial" requerido opciones={o.manejo_especial} valores={r.logistica.manejo_especial} excluyente="no_requiere"
                cambiar={(v) => cambiar(["logistica", "manejo_especial"], v)} error={err("logistica.manejo_especial")}
                otro={r.logistica.manejo_especial_otro} cambiarOtro={(v) => cambiar(["logistica", "manejo_especial_otro"], v)} errorOtro={err("logistica.manejo_especial_otro")} />
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <Numero etiqueta="Vida útil total desde fabricación" requerido decimales={0} sufijo="días" valor={r.logistica.vida_util_total_dias}
                  cambiar={(v) => cambiar(["logistica", "vida_util_total_dias"], v)} error={err("logistica.vida_util_total_dias")} />
                <div>
                  {!r.logistica.vida_util_minima_no_aplica && (
                    <Numero etiqueta="Vida útil mínima al entregar" requerido ayuda="No puede ser mayor que la total" decimales={0} sufijo="días" valor={r.logistica.vida_util_minima_dias}
                      cambiar={(v) => cambiar(["logistica", "vida_util_minima_dias"], v)} error={err("logistica.vida_util_minima_dias")} />
                  )}
                  <label className="mt-2 flex items-center gap-2 text-sm font-semibold">
                    <input type="checkbox" className="h-4 w-4 accent-smn-naranja" checked={r.logistica.vida_util_minima_no_aplica}
                      onChange={(e) => cambiar(["logistica"], { ...r.logistica, vida_util_minima_no_aplica: e.target.checked, vida_util_minima_dias: null })} />
                    No aplica vida útil mínima al entregar
                  </label>
                </div>
              </div>
            </Tarjeta>
          )}

          {seccion === "lanzamiento" && (
            <>
              <Tarjeta titulo="Apoyo comercial para el lanzamiento">
                <p className="-mt-2 mb-4 text-sm text-smn-gris-500">Selecciona solo apoyos que puedas confirmar, con su alcance y vigencia.</p>
                <Casillas etiqueta="Apoyos" requerido opciones={o.apoyos} valores={r.lanzamiento.apoyos.map((a) => a.tipo ?? "")} error={err("lanzamiento.apoyos")}
                  cambiar={(v) => {
                    const antes = new Map(r.lanzamiento.apoyos.map((a) => [a.tipo, a]));
                    cambiar(["lanzamiento", "apoyos"], v.map((t) => antes.get(t) ?? { tipo: t, detalle: null, inicio: null, fin: null }));
                  }}
                  otro={r.lanzamiento.apoyos_otro} cambiarOtro={(v) => cambiar(["lanzamiento", "apoyos_otro"], v)} errorOtro={err("lanzamiento.apoyos_otro")} />
                <div className="mt-4 space-y-3">
                  {r.lanzamiento.apoyos.map((a, i) => (
                    <div key={a.tipo} className="rounded-2xl bg-smn-gris-50 p-4">
                      <p className="mb-3 text-sm font-semibold">{o.apoyos.find((x) => x.valor === a.tipo)?.texto}</p>
                      <div className="grid gap-3 sm:grid-cols-3">
                        <Texto etiqueta="Cantidad o monto" valor={a.detalle} cambiar={(v) => cambiar(["lanzamiento", "apoyos", i, "detalle"], v)} />
                        <Texto etiqueta="Inicio" type="date" valor={a.inicio} cambiar={(v) => cambiar(["lanzamiento", "apoyos", i, "inicio"], v)} error={err(`lanzamiento.apoyos.${i}`)} />
                        <Texto etiqueta="Fin" type="date" valor={a.fin} cambiar={(v) => cambiar(["lanzamiento", "apoyos", i, "fin"], v)} />
                      </div>
                    </div>
                  ))}
                </div>
              </Tarjeta>
              <Tarjeta titulo="Por qué SMN debería venderlo">
                <div className="grid gap-4">
                  <Lista etiqueta="Argumento principal para SMN" requerido opciones={o.argumento_principal} valor={r.lanzamiento.argumento_principal}
                    cambiar={(v) => cambiar(["lanzamiento", "argumento_principal"], v)} error={err("lanzamiento.argumento_principal")} />
                  <Area etiqueta="Sustento" requerido ayuda="Un argumento concreto, con dato si es posible" maximo={220} valor={r.lanzamiento.sustento}
                    cambiar={(v) => cambiar(["lanzamiento", "sustento"], v)} error={err("lanzamiento.sustento")} />
                </div>
              </Tarjeta>
              <Tarjeta titulo="Documentos">
                <div className="space-y-6">
                  <Archivos propuesta={p} tipo="ficha_tecnica" regla={cat.adjuntos.ficha_tecnica} etiqueta="Ficha técnica" error={err("adjunto.ficha_tecnica")} cambio={recibir} />
                  <Archivos propuesta={p} tipo="documento_adicional" regla={cat.adjuntos.documento_adicional} etiqueta="Documentos adicionales"
                    ayuda="Evidencia de ventas, comparativo de precios, certificaciones, material comercial" cambio={recibir} />
                </div>
              </Tarjeta>
            </>
          )}

          {seccion === "envio" && (
            <Tarjeta titulo="Revisión y envío">
              {p.faltantes.length ? (
                <>
                  <p className="mb-4 text-sm text-smn-gris-500">Antes de enviar falta completar esto:</p>
                  <ul className="space-y-3">
                    {PASOS.slice(0, -1).filter((s) => faltanEn(s).length).map((s) => (
                      <li key={s} className="rounded-2xl border border-smn-gris-100 p-4">
                        <button type="button" onClick={() => ir(PASOS.indexOf(s))} className="flex w-full items-center justify-between text-left font-semibold hover:text-naranja-tinta">
                          {nombreSeccion(s)} <ArrowRight className="h-4 w-4" />
                        </button>
                        <ul className="mt-1 list-disc pl-5 text-sm text-smn-gris-500">
                          {[...new Set(faltanEn(s).map(textoPendiente))].slice(0, 6).map((m) => (
                            <li key={m}>{m}</li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <CheckCircle2 className="h-5 w-5 text-smn-naranja" /> {compras ? "Todo está completo. Al enviar recibe un folio y entra a la bandeja como recibida." : "Todo está completo. Al enviar recibirás un folio y un correo de confirmación."}
                </p>
              )}
              <div className="mt-6 flex flex-wrap gap-2">
                <Boton onClick={enviar} cargando={enviando} disabled={p.faltantes.length > 0}>
                  <Send className="h-4 w-4" /> {p.estado === "devuelta" ? "Volver a enviar" : "Enviar propuesta"}
                </Boton>
                {!p.folio && (
                  <Boton variante="fantasma" onClick={() => setPreguntaBorrar(true)}>
                    <Trash2 className="h-4 w-4" /> Borrar borrador
                  </Boton>
                )}
              </div>
            </Tarjeta>
          )}
        </motion.div>
      </AnimatePresence>

      {seccion !== "envio" && faltanEn(seccion).length > 0 && vistas.has(seccion) && (
        <p className="mt-4 text-sm font-semibold text-aviso-texto">Hay {faltanEn(seccion).length} datos por completar en esta sección. Puedes seguir y volver después.</p>
      )}
      <div className="mt-6 flex justify-between gap-2">
        <Boton variante="secundario" onClick={() => ir(paso - 1)} disabled={paso === 0}>
          <ArrowLeft className="h-4 w-4" /> Atrás
        </Boton>
        {paso < PASOS.length - 1 && (
          <Boton onClick={() => ir(paso + 1)}>
            Siguiente <ArrowRight className="h-4 w-4" />
          </Boton>
        )}
      </div>

      {p.eventos.length > 0 && <div className="mt-8"><Historia p={p} /></div>}

      <AnimatePresence>
        {preguntaBorrar && (
          <Modal titulo="¿Borrar este borrador?" cerrar={() => setPreguntaBorrar(false)}>
            <p className="text-sm text-smn-gris-500">Se pierde lo capturado y los archivos que subiste en esta propuesta.</p>
            <div className="mt-5 flex justify-end gap-2">
              <Boton variante="fantasma" onClick={() => setPreguntaBorrar(false)}>Conservar</Boton>
              <Boton onClick={borrar}>Borrar</Boton>
            </div>
          </Modal>
        )}
      </AnimatePresence>
    </>
  );
}

function Historia({ p }: { p: Propuesta }) {
  if (!p.eventos.length) return null;
  return (
    <section className="mb-5 rounded-2xl border border-smn-gris-100 bg-superficie p-5">
      <h2 className="mb-3 font-semibold">Historia</h2>
      <ol className="space-y-3 border-l-2 border-smn-gris-100 pl-4">
        {[...p.eventos].reverse().map((e, i) => (
          <li key={i} className="relative">
            <span className="absolute top-1.5 -left-[1.4rem] h-2.5 w-2.5 rounded-full bg-smn-naranja" />
            <p className="text-sm font-semibold">
              {{ recibida: "Enviada", en_revision: "En revisión", devuelta: "Regresada para corregir", lista: "Lista para evaluar", rechazada: "Rechazada", borrador: "Borrador" }[e.estado_despues]}
              <span className="font-normal text-smn-gris-500"> · {e.usuario} · {fechaLocal(e.ocurrido_en)}</span>
            </p>
            {e.comentario && <p className="text-sm text-smn-gris-700">{e.comentario}</p>}
          </li>
        ))}
      </ol>
    </section>
  );
}
