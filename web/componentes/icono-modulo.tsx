import { ShoppingCart, Users, Radar, Plus } from "lucide-react";
import type { Icono } from "@/lib/api";

const iconos = { carrito: ShoppingCart, personas: Users, radar: Radar, mas: Plus };

export function IconoModulo({ icono, className = "h-6 w-6" }: { icono: Icono; className?: string }) {
  const Componente = iconos[icono] ?? Plus;
  return <Componente className={className} aria-hidden />;
}
