import { MarcoProveedor } from "@/componentes/marco-proveedor";

export default function LayoutExterno({ children }: { children: React.ReactNode }) {
  return <MarcoProveedor>{children}</MarcoProveedor>;
}
