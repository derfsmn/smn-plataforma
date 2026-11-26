import { redirect } from "next/navigation";

// El Monitor pasó a /monitor (v0.6.5): pantalla propia, sin el menú del sitio encima.
export default function MonitorViejo() {
  redirect("/monitor");
}
