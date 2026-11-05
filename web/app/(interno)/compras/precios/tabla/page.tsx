// La tabla por vendedor se quitó (con 4,000 productos serían unos 20,000 renglones): ahora es el botón «Excel» de Productos.
import { redirect } from "next/navigation";

export default function Tabla() {
  redirect("/compras/precios");
}
