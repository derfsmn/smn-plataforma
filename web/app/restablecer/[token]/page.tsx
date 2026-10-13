"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "motion/react";
import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { CrearContrasena } from "@/componentes/crear-contrasena";
import { PantallaPublica } from "@/componentes/pantalla-publica";

export default function Restablecer() {
  const { token } = useParams<{ token: string }>();
  const [listo, setListo] = useState(false);
  return (
    <PantallaPublica>
      {listo ? (
        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="rounded-3xl border border-smn-gris-100 bg-superficie p-8 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-smn-naranja" />
          <p className="mt-3 text-lg font-extrabold">Contraseña actualizada</p>
          <p className="mt-1 text-sm text-smn-gris-500">Por seguridad cerramos tus sesiones abiertas.</p>
          <Link href="/login" className="mt-6 inline-block rounded-xl bg-smn-naranja px-5 py-2.5 text-sm font-bold text-smn-negro">Iniciar sesión</Link>
        </motion.div>
      ) : (
        <CrearContrasena ruta={`/api/auth/restablecer/${token}`} titulo={() => "Crea una contraseña nueva"} boton="Guardar contraseña" alTerminar={() => setListo(true)} />
      )}
    </PantallaPublica>
  );
}
