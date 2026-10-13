import { EstadoApi } from "@/componentes/estado-api";
import { Encabezado } from "@/componentes/ui";

export default function Sistema() {
  return (
    <>
      <Encabezado titulo="Estado del sistema" descripcion="Conexión real con la API y SQL Server (no es dato de ejemplo)." />
      <EstadoApi />
    </>
  );
}
