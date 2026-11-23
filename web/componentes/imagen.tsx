"use client";
// Imagen que no se ve rota: si el archivo no carga, deja un recuadro gris con un ícono en vez del nombre del archivo
// y el marco vacío del navegador. Recibe lo mismo que <img>.

import { ImageOff } from "lucide-react";
import { useState } from "react";

export function Imagen({ className = "", alt = "", ...resto }: React.ImgHTMLAttributes<HTMLImageElement>) {
  const [rota, setRota] = useState(false);
  if (rota || !resto.src)
    return (
      <span role="img" aria-label={alt || "Sin imagen"} className={`${className} flex items-center justify-center bg-smn-gris-50 text-smn-gris-300`}>
        <ImageOff className="h-1/3 max-h-8 w-1/3 max-w-8" aria-hidden />
      </span>
    );
  // eslint-disable-next-line @next/next/no-img-element
  return <img {...resto} alt={alt} className={className} onError={() => setRota(true)} />;
}
