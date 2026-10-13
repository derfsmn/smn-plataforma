import Image from "next/image";
import { EstadoApi } from "./estado-api";

// Página provisional de la etapa 1: confirma que web, API y base de datos están conectadas.
// El prototipo visual del cascarón la reemplaza en la etapa 2.
export default function Inicio() {
  return (
    <main>
      <header className="bg-smn-negro px-4 py-4 sm:px-8">
        <Image
          src="/marca/logo-1linea-naranja-blanco.png"
          alt="Súper Naturista"
          width={1200}
          height={171}
          priority
          className="h-8 w-auto sm:h-10"
        />
      </header>
      <section className="mx-auto max-w-4xl px-4 py-12 sm:px-8">
        <p className="text-sm font-bold uppercase tracking-widest text-smn-naranja">Etapa 1 · Cimientos</p>
        <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl">SMN - Transformación digital</h1>
        <p className="mt-3 max-w-2xl text-smn-gris-700">
          Plataforma de las iniciativas de Innovación y Transformación Digital. Esta página solo confirma que
          la web, la API y la base de datos están conectadas.
        </p>
        <div className="mt-8">
          <EstadoApi />
        </div>
      </section>
    </main>
  );
}
