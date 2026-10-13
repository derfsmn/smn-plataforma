"use client";
// Sesión SIMULADA del prototipo. No valida contraseñas ni protege nada.
// La etapa 3 la reemplaza por autenticación real en la API.

export type Sesion = { nombre: string; correo: string; tipo: "interno" | "externo"; rol: string };

const CLAVE = "smn_td_sesion_prototipo";

export function leerSesion(): Sesion | null {
  try {
    const valor = localStorage.getItem(CLAVE);
    return valor ? (JSON.parse(valor) as Sesion) : null;
  } catch {
    return null;
  }
}

export function guardarSesion(sesion: Sesion) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(sesion));
  } catch {}
}

export function cerrarSesion() {
  try {
    localStorage.removeItem(CLAVE);
  } catch {}
}
