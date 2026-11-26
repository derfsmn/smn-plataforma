// El tablero de inventarios se movió a su propia iniciativa (TD006): /inventarios.
import { redirect } from "next/navigation";

export default function Movido() {
  redirect("/inventarios");
}
