"use client";
// Configuración de la plataforma: correo, archivos, IA y generales. Lo que se guarda aquí manda sobre el .env.

import { AnimatePresence, motion } from "motion/react";
import { Gauge, KeyRound, Mail, Package, Radar, RotateCcw, Save, Send, Settings2, FolderUp, Sparkles, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { api, mensajeDe, type AjusteConfig, type GrupoConfig } from "@/lib/api";
import { useAvisos } from "@/componentes/avisos";
import { Boton, Encabezado, Entrada, Esqueleto, Insignia } from "@/componentes/ui";

const ICONOS: Record<string, typeof Mail> = { general: Settings2, correo: Mail, archivos: FolderUp, ia: Sparkles, radar: Radar, catalogo: Package, precios: Tags, productos: Gauge };
const ORIGEN: Record<string, { texto: string; clase: string }> = {
  pantalla: { texto: "Guardado aquí", clase: "bg-smn-naranja/15 text-aviso-texto" },
  archivo: { texto: "Desde .env", clase: "bg-smn-gris-100 text-smn-gris-700" },
  omision: { texto: "Por omisión", clase: "bg-smn-gris-100 text-smn-gris-500" },
};

type Borrador = Record<string, unknown>; // clave → valor nuevo; null = volver al .env

export default function Configuracion() {
  const avisar = useAvisos();
  const [grupos, setGrupos] = useState<GrupoConfig[] | null>(null);

  useEffect(() => {
    api<GrupoConfig[]>("/api/nucleo/configuracion").then(setGrupos).catch((e) => avisar(mensajeDe(e), "info"));
  }, [avisar]);

  return (
    <>
      <Encabezado
        titulo="Configuración"
        descripcion="Ajustes de la plataforma. Lo que guardes aquí aplica de inmediato y manda sobre el archivo .env."
      />
      {!grupos ? (
        <div className="space-y-4">
          <Esqueleto className="h-48" />
          <Esqueleto className="h-72" />
        </div>
      ) : (
        <div className="space-y-6">
          {grupos.map((g, i) => (
            <Entrada key={g.grupo} retraso={i * 0.05}>
              <Grupo grupo={g} alGuardar={setGrupos} />
            </Entrada>
          ))}
          <p className="text-sm text-smn-gris-500">
            La conexión a la base de datos, el entorno y los orígenes permitidos solo se cambian en el .env, por seguridad.
          </p>
        </div>
      )}
    </>
  );
}

function Grupo({ grupo, alGuardar }: { grupo: GrupoConfig; alGuardar: (g: GrupoConfig[]) => void }) {
  const avisar = useAvisos();
  const [borrador, setBorrador] = useState<Borrador>({});
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [probando, setProbando] = useState(false);
  const Icono = ICONOS[grupo.grupo] ?? Settings2;
  const cambios = Object.keys(borrador).length;

  const guardar = async (extra: Borrador = {}) => {
    const cuerpo = { ...borrador, ...extra };
    if (!Object.keys(cuerpo).length) return;
    setGuardando(true);
    setError(null);
    try {
      alGuardar(await api<GrupoConfig[]>("/api/nucleo/configuracion", { metodo: "PUT", cuerpo: { cambios: cuerpo } }));
      setBorrador({});
      avisar(`${grupo.nombre}: guardado`, "exito");
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setGuardando(false);
    }
  };

  const probarCorreo = async () => {
    setProbando(true);
    try {
      const r = await api<{ enviado: boolean; mensaje: string }>("/api/nucleo/configuracion/probar-correo", { metodo: "POST" });
      avisar(r.mensaje, r.enviado ? "exito" : "info");
    } catch (e) {
      avisar(mensajeDe(e), "info");
    } finally {
      setProbando(false);
    }
  };

  return (
    <section className="rounded-2xl border border-smn-gris-100 bg-superficie p-4 sm:p-5">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <span className="grid h-9 w-9 place-items-center rounded-xl border border-smn-gris-100 bg-superficie text-smn-naranja">
          <Icono className="h-5 w-5" />
        </span>
        {grupo.nombre}
      </h2>
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
        {grupo.ajustes.map((a) => (
          <Campo
            key={a.clave}
            ajuste={a}
            valor={borrador[a.clave]}
            cambiar={(v) =>
              setBorrador((b) => {
                const n = { ...b };
                if (v === undefined) delete n[a.clave];
                else n[a.clave] = v;
                return n;
              })
            }
            restablecer={() => guardar({ [a.clave]: null })}
          />
        ))}
      </div>
      <AnimatePresence>
        {error && (
          <motion.p initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="alert" className="mt-4 rounded-xl bg-red-500/10 px-3 py-2.5 text-sm font-semibold text-red-700 dark:text-red-400">
            {error}
          </motion.p>
        )}
      </AnimatePresence>
      <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
        {grupo.grupo === "correo" && (
          <Boton variante="secundario" onClick={probarCorreo} cargando={probando} disabled={cambios > 0} title={cambios ? "Guarda primero los cambios" : undefined}>
            <Send className="h-4 w-4" /> Enviarme un correo de prueba
          </Boton>
        )}
        {cambios > 0 && (
          <Boton variante="fantasma" onClick={() => setBorrador({})}>
            Descartar
          </Boton>
        )}
        <Boton onClick={() => guardar()} cargando={guardando} disabled={!cambios}>
          <Save className="h-4 w-4" /> Guardar{cambios ? ` (${cambios})` : ""}
        </Boton>
      </div>
    </section>
  );
}

const DIAS_SEMANA = [
  ["1", "L", "Lunes"],
  ["2", "M", "Martes"],
  ["3", "Mi", "Miércoles"],
  ["4", "J", "Jueves"],
  ["5", "V", "Viernes"],
  ["6", "S", "Sábado"],
  ["7", "D", "Domingo"],
] as const;

const claseEntrada =
  "w-full rounded-xl border border-smn-gris-300 bg-superficie px-3.5 py-2.5 outline-none transition-shadow placeholder:text-smn-gris-500 focus:border-smn-naranja focus:ring-4 focus:ring-smn-naranja/20";

function Campo({
  ajuste: a,
  valor,
  cambiar,
  restablecer,
}: {
  ajuste: AjusteConfig;
  valor: unknown;
  cambiar: (v: unknown) => void;
  restablecer: () => void;
}) {
  const id = `ajuste-${a.clave}`;
  const editado = valor !== undefined;
  const actual = a.valor === null || a.valor === undefined ? "" : String(a.valor);

  let control: React.ReactNode;
  if (a.tipo === "booleano") {
    const encendido = editado ? Boolean(valor) : Boolean(a.valor);
    control = (
      <button
        id={id}
        role="switch"
        aria-checked={encendido}
        onClick={() => (encendido === Boolean(a.valor) ? cambiar(!encendido) : cambiar(undefined))}
        className={`relative h-6 w-11 rounded-full transition-colors ${encendido ? "bg-smn-naranja" : "bg-smn-gris-300"}`}
      >
        <motion.span layout className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow ${encendido ? "right-0.5" : "left-0.5"}`} />
      </button>
    );
  } else if (a.tipo === "secreto") {
    control = (
      <div className="relative">
        <KeyRound className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-smn-gris-500" />
        <input
          id={id}
          type="password"
          autoComplete="new-password"
          value={(valor as string) ?? ""}
          onChange={(e) => cambiar(e.target.value ? e.target.value : undefined)}
          placeholder={a.configurado ? (a.pista ? `Guardada · termina en ${a.pista}` : "Guardada") : "Sin capturar"}
          className={`${claseEntrada} pl-9`}
        />
      </div>
    );
  } else if (a.tipo === "dias") {
    const elegidos = new Set((editado ? String(valor) : actual).split(",").filter(Boolean));
    const alternar = (d: string) => {
      const nuevo = new Set(elegidos);
      if (nuevo.has(d)) nuevo.delete(d);
      else nuevo.add(d);
      const texto = [...nuevo].sort().join(",");
      cambiar(texto === actual ? undefined : texto);
    };
    control = (
      <div id={id} role="group" aria-label={a.etiqueta} className="flex flex-wrap gap-1.5">
        {DIAS_SEMANA.map(([d, corto, largo]) => {
          const activo = elegidos.has(d);
          return (
            <button
              key={d}
              type="button"
              aria-pressed={activo}
              title={largo}
              onClick={() => alternar(d)}
              className={`h-10 min-w-11 rounded-xl border px-2 text-sm font-semibold transition-colors ${
                activo ? "border-smn-naranja bg-smn-naranja text-smn-negro" : "border-smn-gris-300 text-smn-gris-500 hover:border-smn-naranja"
              }`}
            >
              {corto}
            </button>
          );
        })}
      </div>
    );
  } else if (a.tipo === "opcion") {
    control = (
      <select
        id={id}
        value={editado ? String(valor) : actual}
        onChange={(e) => cambiar(e.target.value === actual ? undefined : e.target.value)}
        className={claseEntrada}
      >
        {a.opciones.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <input
        id={id}
        inputMode={a.tipo === "entero" || a.tipo === "decimal" ? "decimal" : undefined}
        value={editado ? String(valor) : actual}
        onChange={(e) => cambiar(e.target.value === actual ? undefined : e.target.value)}
        className={claseEntrada}
      />
    );
  }

  return (
    <div className={a.tipo === "booleano" ? "flex items-start justify-between gap-4 rounded-xl border border-smn-gris-100 p-3 md:self-end" : ""}>
      <div className={a.tipo === "booleano" ? "min-w-0" : "mb-1.5 flex flex-wrap items-center justify-between gap-2"}>
        <label htmlFor={id} className="text-sm font-semibold text-smn-gris-700">
          {a.etiqueta}
          {editado && <span className="ml-1.5 text-naranja-tinta">•</span>}
        </label>
        {a.tipo !== "booleano" && <Etiquetas ajuste={a} restablecer={restablecer} />}
        {a.ayuda && a.tipo === "booleano" && <p className="mt-0.5 text-[13px] text-smn-gris-500">{a.ayuda}</p>}
        {a.tipo === "booleano" && (
          <div className="mt-1">
            <Etiquetas ajuste={a} restablecer={restablecer} />
          </div>
        )}
      </div>
      {control}
      {a.ayuda && a.tipo !== "booleano" && <p className="mt-1 text-[13px] text-smn-gris-500">{a.ayuda}</p>}
    </div>
  );
}

function Etiquetas({ ajuste: a, restablecer }: { ajuste: AjusteConfig; restablecer: () => void }) {
  return (
    <span className="flex items-center gap-2">
      <Insignia className={ORIGEN[a.origen]?.clase ?? ""}>{ORIGEN[a.origen]?.texto ?? a.origen}</Insignia>
      {a.origen === "pantalla" && (
        <button onClick={restablecer} className="flex items-center gap-1 text-[13px] font-medium text-smn-gris-500 hover:text-tinta" title="Quitar lo guardado aquí y usar el valor del .env">
          <RotateCcw className="h-3.5 w-3.5" /> {a.tipo === "secreto" ? "Quitar" : "Usar .env"}
        </button>
      )}
    </span>
  );
}
