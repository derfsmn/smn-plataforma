"use client";

import { useParams, useRouter } from "next/navigation";
import { CrearContrasena } from "@/componentes/crear-contrasena";
import { PantallaPublica } from "@/componentes/pantalla-publica";
import { destinoDe } from "@/componentes/sesion";
import type { Yo } from "@/lib/api";

export default function AceptarInvitacion() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  return (
    <PantallaPublica>
      <CrearContrasena
        ruta={`/api/auth/invitacion/${token}`}
        titulo={(d) => `Bienvenido, ${d.nombre.split(" ")[0]}`}
        boton="Crear contraseña y entrar"
        pedirAviso
        alTerminar={(yo) => router.replace(destinoDe(yo as Yo))}
      />
    </PantallaPublica>
  );
}
