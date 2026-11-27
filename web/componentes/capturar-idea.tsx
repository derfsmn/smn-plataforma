"use client";
// Captura rápida de un producto (idea de Compras): nombre, datos que se sepan, fotos y, si ya se sabe, quién lo surtiría.
// Se evalúa sola al guardarla. Con «Guardar y capturar otro» se cargan varios seguidos con el mismo proveedor.
// La usan el Radar de productos y el Comité de producto nuevo.

import { useRouter } from "next/navigation";
import { Camera, Check, ImagePlus, Lightbulb, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { ElegirIntelisis, type Intelisis } from "@/componentes/proveedor-intelisis";
import { CampoNumero } from "@/componentes/campo-numero";
import { Boton, Campo, Selector } from "@/componentes/ui";
import { leerCodigoBarras } from "@/lib/numeros";
import { llenarVacios, pendientes } from "@/lib/alta-fotos";
import { api, mensajeDe, subirArchivo } from "@/lib/api";
import { RUTA as RUTA_PROPUESTAS, type Catalogos } from "@/lib/propuestas";
import { FORMAS, LISTAS_MARGEN, RUTA, type Evaluacion } from "@/lib/productos";

type TipoProveedor = "ninguno" | "actual" | "nuevo";
const VACIO = {
  nombre: "", marca: "", descripcion: "", departamento: "", ingrediente: "", forma: "", contenido: "",
  precio_visto: "", donde_se_vio: "", costo_estimado: "",
  precio_nuestro: "", codigo_barras: "", activo_g_porcion: "", porciones: "",
  lista_margen: "", precio_membresia: "",
};

/** Marca de un dato que se llenó con la foto de la etiqueta. */
function Leido() {
  return <p className="mt-1 text-[13px] font-medium text-naranja-tinta">Leído de la foto, revisa.</p>;
}

type Foto = { clave: string; nombre: string; vista: string; id?: number; avance: number; error?: string };

/** Lo capturado de una idea, para «Corregir datos» (GET /ideas/{id}). */
export type IdeaDatos = Partial<Record<keyof typeof VACIO, string | number | null>> & {
  proveedor_codigo?: string | null;
  proveedor_nuevo?: string | null;
};

/** alGuardar: el Comité de producto nuevo la sube a su reunión y se queda ahí; sin él, se abre su semáforo.
 *  corregir: la idea ya capturada que se corrige (mismo formulario, sin fotos; guarda y la vuelve a evaluar).
 *  fotosPrimero: «Alta con fotos» (Diego, 27 nov 2026): lo primero es subir las fotos de la etiqueta y leerlas;
 *  el formulario queda abajo, ya lleno, para revisar y completar lo que la etiqueta no trae. */
export function CapturarIdea({ cerrar, alGuardar, corregir, fotosPrimero }: {
  cerrar: () => void;
  fotosPrimero?: boolean;
  alGuardar?: (e: Evaluacion) => Promise<void>;
  corregir?: { id: number; datos: IdeaDatos };
}) {
  const avisar = useAvisos();
  const router = useRouter();
  const entrada = useRef<HTMLInputElement>(null);
  const [departamentos, setDepartamentos] = useState<string[]>([]);
  const [d, setD] = useState(() =>
    corregir
      ? (Object.fromEntries(Object.keys(VACIO).map((k) => [k, corregir.datos[k as keyof typeof VACIO] == null ? "" : String(corregir.datos[k as keyof typeof VACIO])])) as typeof VACIO)
      : VACIO,
  );
  const [fotos, setFotos] = useState<Foto[]>([]);
  const [guardando, setGuardando] = useState<"" | "evaluar" | "otro">("");
  const [tipo, setTipo] = useState<TipoProveedor>(corregir?.datos.proveedor_codigo ? "actual" : corregir?.datos.proveedor_nuevo ? "nuevo" : "ninguno");
  const [elegido, setElegido] = useState<Intelisis | null>(
    corregir?.datos.proveedor_codigo
      ? { codigo: corregir.datos.proveedor_codigo, nombre: `Proveedor ${corregir.datos.proveedor_codigo}`, estatus: null, agente: null, rfc: null }
      : null,
  );
  const [cambiando, setCambiando] = useState(!corregir?.datos.proveedor_codigo);
  const [nuevo, setNuevo] = useState(corregir?.datos.proveedor_nuevo ?? "");
  const [capturados, setCapturados] = useState<string[]>([]);
  // Alta con fotos (26 nov 2026, apagada de fábrica en Configuración): la IA local lee la etiqueta y prellena
  const [conFotos, setConFotos] = useState(false);
  const [leyendo, setLeyendo] = useState(false);
  const [leidos, setLeidos] = useState<Set<string>>(new Set());
  const [lectura, setLectura] = useState<{ nota: string | null; segundos: number } | null>(null);
  const poner = (k: keyof typeof d) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setD({ ...d, [k]: e.target.value });

  useEffect(() => {
    api<Catalogos>(`${RUTA_PROPUESTAS}/catalogos`).then((c) => setDepartamentos(c.departamentos)).catch(() => setDepartamentos([]));
    if (!corregir) api<{ activo: boolean }>(`${RUTA}/alta-fotos`).then((x) => setConFotos(x.activo)).catch(() => setConFotos(false));
  }, [corregir]);

  const leerFotos = async () => {
    setLeyendo(true);
    setLectura(null);
    try {
      const r = await api<{ campos: Record<string, string>; segundos: number; nota: string | null }>(`${RUTA}/alta-fotos/leer`, {
        cuerpo: { fotos: fotos.filter((f) => f.id).map((f) => f.id).slice(0, 4) },
      });
      // Solo llena lo que está vacío: lo que la persona ya escribió manda
      const { d: lleno, llenos } = llenarVacios(d, r.campos);
      setD(lleno);
      setLeidos(new Set(llenos));
      setLectura({ nota: r.nota, segundos: r.segundos });
    } catch (x) {
      setLectura({ nota: mensajeDe(x), segundos: 0 });
    } finally {
      setLeyendo(false);
    }
  };
  // Lo que una etiqueta no trae (o no se alcanzó a leer), para capturarlo a mano
  const faltan = pendientes(d, tipo === "ninguno");

  const agregarFotos = (lista: FileList | null) => {
    if (!lista) return;
    Array.from(lista).slice(0, 6 - fotos.length).forEach((archivo) => {
      const clave = `${archivo.name}-${archivo.size}-${Math.random()}`;
      const cambiar = (c: Partial<Foto>) => setFotos((fs) => fs.map((f) => (f.clave === clave ? { ...f, ...c } : f)));
      setFotos((fs) => [...fs, { clave, nombre: archivo.name, vista: URL.createObjectURL(archivo), avance: 0 }]);
      subirArchivo(archivo, { modulo: "compras", entidad: "producto_idea" }, (avance) => cambiar({ avance }))
        .then((a) => cambiar({ id: a.id, avance: 100 }))
        .catch((e) => cambiar({ error: mensajeDe(e) }));
    });
    if (entrada.current) entrada.current.value = "";
  };

  const subiendo = fotos.some((f) => !f.id && !f.error);
  // Los campos de número ya traen el número limpio (CampoNumero); aquí solo se manda vacío como null
  const numero = (v: string) => (v.trim() ? v.trim() : null);
  const [malos, setMalos] = useState<Record<string, boolean>>({});
  const marcarMalo = (k: string) => (hay: boolean) => setMalos((m) => (m[k] === hay ? m : { ...m, [k]: hay }));
  const hayMalos = Object.values(malos).some(Boolean);
  const barras = leerCodigoBarras(d.codigo_barras);
  const barrasMal = !!d.codigo_barras.trim() && !!barras.error;
  const ponerNumero = (k: keyof typeof d) => (v: string) => setD((x) => ({ ...x, [k]: v }));

  const faltaProveedor = (tipo === "actual" && !elegido) || (tipo === "nuevo" && nuevo.trim().length < 2);
  // El contenido lleva su unidad (Diego, 18 nov 2026: «40» sin unidad hizo que el radar tomara los 30 g del nombre)
  const sinUnidad = !!d.contenido.trim() && !/\d\s*[a-záéíóúñ]/i.test(d.contenido);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    const otro = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-otro") === "si";
    setGuardando(otro ? "otro" : "evaluar");
    try {
      const r = await api<Evaluacion>(corregir ? `${RUTA}/ideas/${corregir.id}` : `${RUTA}/ideas`, {
        metodo: corregir ? "PUT" : "POST",
        cuerpo: {
          ...Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.replace(/\s+/g, " ").trim() || null])),
          codigo_barras: barras.valor,
          precio_visto: numero(d.precio_visto),
          costo_estimado: numero(d.costo_estimado),
          precio_nuestro: numero(d.precio_nuestro),
          precio_membresia: numero(d.precio_membresia),
          activo_g_porcion: numero(d.activo_g_porcion),
          porciones: d.porciones.trim() ? Number(d.porciones) : null,
          fotos: fotos.filter((f) => f.id).map((f) => f.id),
          proveedor_codigo: tipo === "actual" ? elegido?.codigo : null,
          proveedor_nuevo: tipo === "nuevo" ? nuevo.replace(/\s+/g, " ").trim() : null,
        },
      });
      if (alGuardar) await alGuardar(r);
      if (otro) {
        // Se queda el proveedor y el departamento; lo demás se limpia para el siguiente.
        setCapturados((c) => [...c, d.nombre.trim()]);
        setD({ ...VACIO, departamento: d.departamento, lista_margen: d.lista_margen });
        setFotos([]);
        setGuardando("");
        avisar(`«${d.nombre.trim()}» capturado; el radar ya lo está evaluando`);
        document.getElementById("idea-nombre")?.focus();
        return;
      }
      avisar(corregir ? "Datos corregidos; el radar lo está evaluando de nuevo" : "Producto capturado; el radar ya lo está evaluando");
      if (alGuardar) cerrar();
      else router.push(`/compras/productos/${r.id}`);
    } catch (err) {
      avisar(mensajeDe(err), "info");
      setGuardando("");
    }
  };

  const opcion = (valor: TipoProveedor, titulo: string, texto: string) => (
    <button
      type="button"
      onClick={() => setTipo(valor)}
      aria-pressed={tipo === valor}
      className={`rounded-xl border p-2.5 text-left transition-colors ${tipo === valor ? "border-tinta bg-tinta text-superficie" : "border-smn-gris-100 hover:border-smn-gris-300"}`}
    >
      <span className="block text-[15px] font-semibold">{titulo}</span>
      <span className={`block text-[13px] ${tipo === valor ? "opacity-80" : "text-smn-gris-700"}`}>{texto}</span>
    </button>
  );

  // Las fotos: arriba y como primer paso en «Alta con fotos»; al final del formulario en la captura de siempre
  const bloqueFotos = corregir ? null : (
<div className={fotosPrimero ? "rounded-2xl border border-smn-naranja/40 bg-smn-naranja/5 p-4" : undefined}>
          {fotosPrimero ? (
            <div className="mb-3">
              <p className="flex items-center gap-2 text-[17px] font-semibold text-tinta"><Camera className="h-5 w-5 text-smn-naranja" /> 1. Sube las fotos de la etiqueta</p>
              <p className="mt-1 text-sm text-smn-gris-700">Frente, tabla nutrimental y código de barras (hasta 6). Luego pica <b>«Leer las fotos»</b> y la plataforma llena los datos por ti.</p>
            </div>
          ) : (
            <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Fotos (hasta 6)</span>
          )}
          <div className="flex flex-wrap gap-2">
            {fotos.map((f) => (
              <div key={f.clave} className="relative h-24 w-24 overflow-hidden rounded-2xl border border-smn-gris-100 bg-smn-gris-50">
                {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local antes de subir */}
                <img src={f.vista} alt={f.nombre} className={`h-full w-full object-cover ${f.error ? "opacity-30" : ""}`} />
                {!f.id && !f.error && (
                  <span className="absolute inset-x-0 bottom-0 h-1 bg-smn-gris-300">
                    <span className="block h-full bg-smn-naranja transition-all" style={{ width: `${f.avance}%` }} />
                  </span>
                )}
                {f.error && <span className="absolute inset-0 grid place-items-center p-1 text-center text-[13px] font-semibold text-red-700">{f.error}</span>}
                <button
                  type="button"
                  onClick={() => setFotos((fs) => fs.filter((x) => x.clave !== f.clave))}
                  aria-label={`Quitar ${f.nombre}`}
                  className="absolute top-1 right-1 rounded-full bg-smn-negro/70 p-0.5 text-white"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {fotos.length < 6 && (
              <button
                type="button"
                onClick={() => entrada.current?.click()}
                className="flex h-24 w-24 flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-smn-gris-300 text-[13px] font-medium text-smn-gris-500 hover:border-smn-naranja hover:text-tinta"
              >
                <ImagePlus className="h-6 w-6 text-smn-naranja" /> Agregar
              </button>
            )}
          </div>
          <input ref={entrada} type="file" accept=".png,.jpg,.jpeg,.webp,image/*" multiple className="hidden" onChange={(e) => agregarFotos(e.target.files)} />
          {(conFotos || fotosPrimero) && (
            <div className="mt-2">
              <Boton type="button" variante={fotosPrimero ? "primario" : "secundario"} onClick={leerFotos} cargando={leyendo} disabled={leyendo || subiendo || !fotos.some((f) => f.id)}>
                {leyendo ? "Leyendo la etiqueta…" : "Leer las fotos"}
              </Boton>
              {leyendo && <p className="mt-1 text-[13px] text-smn-gris-500">La IA local está leyendo la etiqueta; tarda unos segundos por foto. Puedes seguir capturando.</p>}
              {/* El resultado va junto al botón: ahí está la persona cuando termina de leer */}
              {lectura && (
                <div className="mt-2 rounded-2xl bg-smn-gris-50 p-3 text-sm">
                  {lectura.nota ? (
                    <p className="text-smn-gris-700">{lectura.nota}</p>
                  ) : (
                    <p className="text-smn-gris-700">Se llenaron {leidos.size} {leidos.size === 1 ? "dato" : "datos"} con la etiqueta en {Math.round(lectura.segundos)} s; están marcados «Leído de la foto, revisa».</p>
                  )}
                  {faltan.length > 0 && <p className="mt-1 font-semibold text-tinta">Te falta capturar: {faltan.join(", ")}.</p>}
                </div>
              )}
            </div>
          )}
        </div>
  );

  return (
    <Modal titulo={corregir ? "Corregir datos" : fotosPrimero ? "Alta con fotos" : "Captura rápida"} cerrar={cerrar} ancho="max-w-2xl">
      <form onSubmit={guardar} className="space-y-4">
        {fotosPrimero && bloqueFotos}
        {fotosPrimero && <p className="text-[17px] font-semibold text-tinta">2. Revisa y completa</p>}
        {!fotosPrimero && <p className="flex gap-2 rounded-2xl bg-smn-gris-50 p-3 text-sm text-smn-gris-700">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-smn-naranja" />
          <span>
            Con nombre y tipo de producto ya se puede evaluar. Lo que más ayuda: <b>la marca del empaque, el contenido con su unidad y el código de barras</b>, porque con eso se encuentra su precio afuera; con <b>precio y costo</b> se calcula el margen.
          </span>
        </p>}

        {conFotos && !fotosPrimero && (
          <p className="rounded-2xl border border-smn-naranja/40 bg-smn-naranja/5 p-3 text-sm text-smn-gris-700">
            ¿Tienes fotos de la etiqueta? Súbelas en «Fotos» (frente, tabla nutrimental y código de barras) y pica <b>«Leer las fotos»</b>: llenamos lo que diga la etiqueta y tú revisas.
          </p>
        )}
        <fieldset>
          <legend className="mb-1.5 text-sm font-semibold text-smn-gris-700">¿Quién lo surtiría?</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {opcion("ninguno", "Sin proveedor", "Todavía no sabemos")}
            {opcion("actual", "Proveedor actual", "Está en Intelisis")}
            {opcion("nuevo", "Proveedor nuevo", "Todavía no le compramos")}
          </div>
          {tipo === "actual" &&
            (elegido && !cambiando ? (
              <div className="mt-2 flex items-center gap-3 rounded-xl border border-smn-gris-100 px-3 py-2.5">
                <Check className="h-4 w-4 shrink-0 text-smn-naranja" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium">{elegido.nombre}</span>
                  <span className="block text-[13px] text-smn-gris-700">Clave {elegido.codigo}{elegido.agente && ` · Agente ${elegido.agente}`}</span>
                </span>
                <Boton type="button" variante="fantasma" onClick={() => setCambiando(true)}>Cambiar</Boton>
              </div>
            ) : (
              <div className="mt-2">
                <ElegirIntelisis
                  elegido={elegido}
                  elegir={(p) => {
                    setElegido(p);
                    setCambiando(false);
                  }}
                  altura="max-h-48"
                />
              </div>
            ))}
          {tipo === "nuevo" && (
            <div className="mt-2">
              <Campo etiqueta="Razón social o nombre del proveedor" value={nuevo} onChange={(e) => setNuevo(e.target.value)} maxLength={200} />
            </div>
          )}
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Campo id="idea-nombre" etiqueta="Nombre del producto *" value={d.nombre} onChange={poner("nombre")} required minLength={2} maxLength={300} placeholder="Ej. Citrato de magnesio en polvo" autoFocus />
            {leidos.has("nombre") && <Leido />}
            <p className="mt-1 text-[13px] text-smn-gris-500">Como viene en la etiqueta: qué es y su forma. La marca y el contenido van en su campo.</p>
          </div>
          <div>
            <Campo etiqueta="Marca" value={d.marca} onChange={poner("marca")} maxLength={120} placeholder="Ej. BDM Life" />
            {leidos.has("marca") && <Leido />}
            <p className="mt-1 text-[13px] text-smn-gris-500">La que trae el empaque, no la del proveedor que lo surte.</p>
          </div>
          <Selector
            etiqueta="Departamento"
            valor={d.departamento}
            cambiar={(v) => setD({ ...d, departamento: v })}
            opciones={[{ valor: "", texto: "Sin elegir" }, ...departamentos.map((x) => ({ valor: x, texto: x }))]}
          />
          <div>
            <Campo etiqueta="Ingrediente principal" value={d.ingrediente} onChange={poner("ingrediente")} maxLength={200} placeholder="Ej. Magnesio" />
            {leidos.has("ingrediente") && <Leido />}
            <p className="mt-1 text-[13px] text-smn-gris-500">El activo principal; con él se buscan los parecidos que ya vendemos.</p>
          </div>
          <Selector
            etiqueta="Forma"
            valor={d.forma}
            cambiar={(v) => setD({ ...d, forma: v })}
            opciones={[{ valor: "", texto: "Sin elegir" }, ...FORMAS.map((x) => ({ valor: x, texto: x }))]}
          />
          {leidos.has("forma") && <p className="-mt-2 text-[13px] font-medium text-naranja-tinta sm:col-span-2">Forma: leída de la foto, revisa.</p>}
          <div>
            <Campo etiqueta="Contenido (con su unidad)" value={d.contenido} onChange={poner("contenido")} maxLength={60} placeholder="Ej. 60 cápsulas, 500 g, 40 g" error={sinUnidad ? "x" : undefined} />
            {leidos.has("contenido") && <Leido />}
            {sinUnidad ? <p className="mt-1 text-[13px] text-red-700 dark:text-red-400">Escribe la unidad: «40 g», «500 ml» o «30 cápsulas».</p> : <p className="mt-1 text-[13px] text-smn-gris-500">Cantidad y unidad del empaque; decimales con punto («1.2 g»).</p>}
          </div>
          <CampoNumero etiqueta="Nuestro precio de venta (con IVA)" valor={d.precio_nuestro} cambiar={ponerNumero("precio_nuestro")} alError={marcarMalo("precio_nuestro")} placeholder="Ej. 349.90" ayuda="Precio de anaquel con IVA al que lo venderíamos." />
          <CampoNumero etiqueta="Precio de membresía (con IVA, si lo sabes)" valor={d.precio_membresia} cambiar={ponerNumero("precio_membresia")} alError={marcarMalo("precio_membresia")} placeholder="Ej. 319.90" ayuda="Si lo dejas vacío se calcula con su tipo de producto." />
          <Selector
            etiqueta="Tipo de producto (lista de márgenes) *"
            valor={d.lista_margen}
            cambiar={(v) => setD({ ...d, lista_margen: v })}
            opciones={[{ valor: "", texto: "Elige uno" }, ...LISTAS_MARGEN]}
          />
          <p className="-mt-2 text-[13px] text-smn-gris-500 sm:col-span-2">El tipo de producto define el margen mínimo que debe dejar.</p>
          <CampoNumero etiqueta="Costo estimado sin IVA (si lo sabes)" valor={d.costo_estimado} cambiar={ponerNumero("costo_estimado")} alError={marcarMalo("costo_estimado")} placeholder="Ej. 210.00" ayuda="Lo que nos cobraría el proveedor por pieza, sin IVA." />
          <CampoNumero etiqueta="Precio que viste afuera (con IVA)" valor={d.precio_visto} cambiar={ponerNumero("precio_visto")} alError={marcarMalo("precio_visto")} placeholder="Ej. 399.00" ayuda="De referencia; el radar busca solo los precios de afuera." />
          <Campo etiqueta="¿Dónde lo viste?" value={d.donde_se_vio} onChange={poner("donde_se_vio")} maxLength={300} placeholder="Ej. Chedraui, su página" />
          <div>
            <Campo
              etiqueta="Código de barras"
              value={d.codigo_barras}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setD({ ...d, codigo_barras: e.target.value.slice(0, 24) })}
              onBlur={() => barras.valor && !barras.error && setD((x) => ({ ...x, codigo_barras: barras.valor! }))}
              inputMode="numeric"
              placeholder="Ej. 7501234567890"
              error={barrasMal ? barras.error : undefined}
            />
            {leidos.has("codigo_barras") && <Leido />}
            {!barrasMal && <p className="mt-1 text-[13px] text-smn-gris-500">Los números bajo las barras (13 por lo general), con sus ceros.</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <CampoNumero etiqueta="Activo por porción (g)" valor={d.activo_g_porcion} cambiar={ponerNumero("activo_g_porcion")} alError={marcarMalo("activo_g_porcion")} decimales={3} placeholder="Ej. 5" ayuda="Gramos del activo en una porción." />
            <div>
              <Campo
                etiqueta="Porciones"
                value={d.porciones}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setD({ ...d, porciones: e.target.value.replace(/\D/g, "").slice(0, 5) })}
                inputMode="numeric"
                placeholder="Ej. 30"
              />
              <p className="mt-1 text-[13px] text-smn-gris-500">Porciones por envase.</p>
            {leidos.has("porciones") && <Leido />}
            </div>
          </div>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Descripción</span>
          <textarea
            value={d.descripcion}
            onChange={poner("descripcion")}
            rows={3}
            maxLength={2000}
            placeholder="Qué es, para qué sirve, qué lo hace distinto"
            className="w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20"
          />
        </label>

        {!fotosPrimero && bloqueFotos}

        {capturados.length > 0 && (
          <p className="rounded-xl bg-smn-gris-50 px-3 py-2 text-[13px] text-smn-gris-700">
            Llevas {capturados.length} {capturados.length === 1 ? "producto capturado" : "productos capturados"}: {capturados.join(", ")}.
          </p>
        )}
        {faltaProveedor && <p className="text-[13px] text-smn-gris-700">{tipo === "actual" ? "Elige el proveedor de la lista." : "Escribe el nombre del proveedor."}</p>}
        {/* Sin esto el botón se veía apagado sin decir por qué (revisión de usabilidad, 26 nov 2026) */}
        {!faltaProveedor && (d.nombre.trim().length < 2 || !d.lista_margen) && (
          <p className="text-[13px] text-smn-gris-700">
            Para guardar falta {[d.nombre.trim().length < 2 && "el nombre del producto", !d.lista_margen && "el tipo de producto (lista de márgenes)"].filter(Boolean).join(" y ")}.
          </p>
        )}
        {(hayMalos || barrasMal) && <p className="text-[13px] text-red-700 dark:text-red-400">Corrige el campo marcado en rojo para poder guardar.</p>}
        <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
          <Boton type="button" variante="fantasma" onClick={cerrar}>{capturados.length ? "Terminar" : "Cancelar"}</Boton>
          {!corregir && <Boton
            type="submit"
            data-otro="si"
            variante="secundario"
            cargando={guardando === "otro"}
            disabled={!!guardando || subiendo || faltaProveedor || sinUnidad || hayMalos || barrasMal || !d.lista_margen || d.nombre.trim().length < 2}
          >
            Guardar y capturar otro
          </Boton>}
          <Boton type="submit" cargando={guardando === "evaluar"} disabled={!!guardando || subiendo || faltaProveedor || sinUnidad || hayMalos || barrasMal || !d.lista_margen || d.nombre.trim().length < 2}>
            {subiendo ? "Subiendo fotos…" : corregir ? "Guardar y volver a evaluar" : alGuardar ? "Guardar" : "Guardar y ver semáforo"}
          </Boton>
        </div>
      </form>
    </Modal>
  );
}
