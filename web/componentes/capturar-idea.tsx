"use client";
// Captura rápida de un producto (idea de Compras): nombre, datos que se sepan, fotos y, si ya se sabe, quién lo surtiría.
// Se evalúa sola al guardarla. Con «Guardar y capturar otro» se cargan varios seguidos con el mismo proveedor.
// La usan el Radar de productos y el Comité de producto nuevo.

import { useRouter } from "next/navigation";
import { Check, ImagePlus, Lightbulb, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAvisos } from "@/componentes/avisos";
import { Modal } from "@/componentes/modal";
import { ElegirIntelisis, type Intelisis } from "@/componentes/proveedor-intelisis";
import { Boton, Campo, Selector } from "@/componentes/ui";
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

type Foto = { clave: string; nombre: string; vista: string; id?: number; avance: number; error?: string };

/** alGuardar: el Comité de producto nuevo la sube a su reunión y se queda ahí; sin él, se abre su semáforo. */
export function CapturarIdea({ cerrar, alGuardar }: { cerrar: () => void; alGuardar?: (e: Evaluacion) => Promise<void> }) {
  const avisar = useAvisos();
  const router = useRouter();
  const entrada = useRef<HTMLInputElement>(null);
  const [departamentos, setDepartamentos] = useState<string[]>([]);
  const [d, setD] = useState(VACIO);
  const [fotos, setFotos] = useState<Foto[]>([]);
  const [guardando, setGuardando] = useState<"" | "evaluar" | "otro">("");
  const [tipo, setTipo] = useState<TipoProveedor>("ninguno");
  const [elegido, setElegido] = useState<Intelisis | null>(null);
  const [cambiando, setCambiando] = useState(true);
  const [nuevo, setNuevo] = useState("");
  const [capturados, setCapturados] = useState<string[]>([]);
  const poner = (k: keyof typeof d) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setD({ ...d, [k]: e.target.value });

  useEffect(() => {
    api<Catalogos>(`${RUTA_PROPUESTAS}/catalogos`).then((c) => setDepartamentos(c.departamentos)).catch(() => setDepartamentos([]));
  }, []);

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
  const numero = (v: string) => (v.trim() ? v.replace(/[$,\s]/g, "") : null);

  const faltaProveedor = (tipo === "actual" && !elegido) || (tipo === "nuevo" && nuevo.trim().length < 2);
  // El contenido lleva su unidad (Diego, 18 nov 2026: «40» sin unidad hizo que el radar tomara los 30 g del nombre)
  const sinUnidad = !!d.contenido.trim() && !/\d\s*[a-záéíóúñ]/i.test(d.contenido);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    const otro = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-otro") === "si";
    setGuardando(otro ? "otro" : "evaluar");
    try {
      const r = await api<Evaluacion>(`${RUTA}/ideas`, {
        cuerpo: {
          ...Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v.trim() || null])),
          precio_visto: numero(d.precio_visto),
          costo_estimado: numero(d.costo_estimado),
          precio_nuestro: numero(d.precio_nuestro),
          precio_membresia: numero(d.precio_membresia),
          activo_g_porcion: numero(d.activo_g_porcion),
          porciones: d.porciones.trim() ? Number(d.porciones) : null,
          fotos: fotos.filter((f) => f.id).map((f) => f.id),
          proveedor_codigo: tipo === "actual" ? elegido?.codigo : null,
          proveedor_nuevo: tipo === "nuevo" ? nuevo.trim() : null,
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
      avisar("Producto capturado; el radar ya lo está evaluando");
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

  return (
    <Modal titulo="Captura rápida" cerrar={cerrar} ancho="max-w-2xl">
      <form onSubmit={guardar} className="space-y-4">
        <p className="flex gap-2 rounded-2xl bg-smn-gris-50 p-3 text-sm text-smn-gris-700">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-smn-naranja" />
          Con nombre e ingrediente ya se puede evaluar; el precio y el costo mejoran el resultado. Si ya sabes quién lo surtiría, elígelo: con un proveedor de Intelisis se evalúa con su calificación.
        </p>

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
          <Campo id="idea-nombre" etiqueta="Nombre del producto *" value={d.nombre} onChange={poner("nombre")} required minLength={2} maxLength={300} placeholder="Ej. Citrato de magnesio en polvo" />
          <Campo etiqueta="Marca" value={d.marca} onChange={poner("marca")} maxLength={120} />
          <Selector
            etiqueta="Departamento"
            valor={d.departamento}
            cambiar={(v) => setD({ ...d, departamento: v })}
            opciones={[{ valor: "", texto: "Sin elegir" }, ...departamentos.map((x) => ({ valor: x, texto: x }))]}
          />
          <Campo etiqueta="Ingrediente principal" value={d.ingrediente} onChange={poner("ingrediente")} maxLength={200} placeholder="Ej. Magnesio" />
          <Selector
            etiqueta="Forma"
            valor={d.forma}
            cambiar={(v) => setD({ ...d, forma: v })}
            opciones={[{ valor: "", texto: "Sin elegir" }, ...FORMAS.map((x) => ({ valor: x, texto: x }))]}
          />
          <div>
            <Campo etiqueta="Contenido (con su unidad)" value={d.contenido} onChange={poner("contenido")} maxLength={60} placeholder="Ej. 60 cápsulas, 500 g, 40 g" error={sinUnidad ? "x" : undefined} />
            {sinUnidad && <p className="mt-1 text-[13px] text-red-700 dark:text-red-400">Escribe la unidad: «40 g», «500 ml» o «30 cápsulas».</p>}
          </div>
          <Campo etiqueta="Nuestro precio de venta (con IVA)" value={d.precio_nuestro} onChange={poner("precio_nuestro")} inputMode="decimal" placeholder="$ al que lo venderíamos" />
          <Campo etiqueta="Precio de membresía (con IVA, si lo sabes)" value={d.precio_membresia} onChange={poner("precio_membresia")} inputMode="decimal" placeholder="Si no, se calcula con su lista" />
          <Selector
            etiqueta="Tipo de producto (lista de márgenes) *"
            valor={d.lista_margen}
            cambiar={(v) => setD({ ...d, lista_margen: v })}
            opciones={[{ valor: "", texto: "Elige uno" }, ...LISTAS_MARGEN]}
          />
          <Campo etiqueta="Costo estimado sin IVA (si lo sabes)" value={d.costo_estimado} onChange={poner("costo_estimado")} inputMode="decimal" placeholder="$" />
          <Campo etiqueta="Precio que viste afuera (con IVA)" value={d.precio_visto} onChange={poner("precio_visto")} inputMode="decimal" placeholder="$ en otra tienda" />
          <Campo etiqueta="¿Dónde lo viste?" value={d.donde_se_vio} onChange={poner("donde_se_vio")} maxLength={300} placeholder="Ej. Chedraui, su página" />
          <Campo
            etiqueta="Código de barras"
            value={d.codigo_barras}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setD({ ...d, codigo_barras: e.target.value.replace(/\D/g, "").slice(0, 14) })}
            inputMode="numeric"
            placeholder="Para buscarlo afuera"
          />
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Activo por porción (g)" value={d.activo_g_porcion} onChange={poner("activo_g_porcion")} inputMode="decimal" placeholder="Ej. 5" />
            <Campo
              etiqueta="Porciones"
              value={d.porciones}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setD({ ...d, porciones: e.target.value.replace(/\D/g, "").slice(0, 5) })}
              inputMode="numeric"
              placeholder="Ej. 30"
            />
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

        <div>
          <span className="mb-1.5 block text-sm font-semibold text-smn-gris-700">Fotos (hasta 6)</span>
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
          <input ref={entrada} type="file" accept=".png,.jpg,.jpeg,.webp" multiple className="hidden" onChange={(e) => agregarFotos(e.target.files)} />
        </div>

        {capturados.length > 0 && (
          <p className="rounded-xl bg-smn-gris-50 px-3 py-2 text-[13px] text-smn-gris-700">
            Llevas {capturados.length} {capturados.length === 1 ? "producto capturado" : "productos capturados"}: {capturados.join(", ")}.
          </p>
        )}
        {faltaProveedor && <p className="text-[13px] text-smn-gris-700">{tipo === "actual" ? "Elige el proveedor de la lista." : "Escribe el nombre del proveedor."}</p>}
        <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
          <Boton type="button" variante="fantasma" onClick={cerrar}>{capturados.length ? "Terminar" : "Cancelar"}</Boton>
          <Boton
            type="submit"
            data-otro="si"
            variante="secundario"
            cargando={guardando === "otro"}
            disabled={!!guardando || subiendo || faltaProveedor || sinUnidad || !d.lista_margen || d.nombre.trim().length < 2}
          >
            Guardar y capturar otro
          </Boton>
          <Boton type="submit" cargando={guardando === "evaluar"} disabled={!!guardando || subiendo || faltaProveedor || sinUnidad || !d.lista_margen || d.nombre.trim().length < 2}>
            {subiendo ? "Subiendo fotos…" : alGuardar ? "Guardar" : "Guardar y ver semáforo"}
          </Boton>
        </div>
      </form>
    </Modal>
  );
}
