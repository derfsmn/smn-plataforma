"""Crea el primer administrador de la plataforma (o da el rol a una cuenta existente).

Uso con Docker:  docker compose exec api python -m scripts.crear_admin
Pide nombre, correo y contraseña. La contraseña no se muestra al escribirla.
"""
import argparse
import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import motor
from core.seguridad import cifrar_contrasena, error_contrasena
from nucleo.bitacora import registrar
from nucleo.modelos import Modulo, Rol, Usuario, UsuarioRol, ahora


def crear(bd: Session, nombre: str, correo: str, contrasena: str) -> Usuario:
    rol = bd.scalar(select(Rol).where(Rol.codigo == "admin"))
    if not rol:
        sys.exit("Faltan los catálogos. Corre primero: python -m scripts.semilla")
    correo = correo.strip().lower()
    usuario = bd.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo))
    if usuario:
        print(f"{correo} ya existe; se le asigna el rol de administrador y la contraseña nueva.")
    else:
        usuario = Usuario(tipo="interno", correo=correo, nombre=nombre.strip(), area="Transformación Digital")
        bd.add(usuario)
    usuario.hash_contrasena = cifrar_contrasena(contrasena)
    usuario.estatus = "activo"
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    bd.flush()
    if not bd.get(UsuarioRol, (usuario.usuario_id, rol.rol_id)):
        bd.add(UsuarioRol(usuario_id=usuario.usuario_id, rol_id=rol.rol_id, asignado_en=ahora()))
    # Queda como responsable de los módulos que aún no tienen uno
    for m in bd.scalars(select(Modulo).where(Modulo.responsable_id.is_(None))):
        m.responsable_id = usuario.usuario_id
    registrar(bd, "crear_admin", usuario_id=usuario.usuario_id, entidad="usuario", entidad_id=usuario.usuario_id)
    bd.commit()
    return usuario


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nombre")
    p.add_argument("--correo")
    p.add_argument("--contrasena", help="Solo para pruebas automáticas; mejor escríbela cuando la pida")
    a = p.parse_args()
    nombre = a.nombre or input("Nombre completo: ")
    correo = a.correo or input("Correo: ")
    contrasena = a.contrasena
    while not contrasena:
        c1 = getpass.getpass("Contraseña (10 caracteres o más): ")
        if motivo := error_contrasena(c1):
            print(motivo)
            continue
        if c1 != getpass.getpass("Repite la contraseña: "):
            print("No coinciden, intenta de nuevo.")
            continue
        contrasena = c1
    if motivo := error_contrasena(contrasena):
        sys.exit(motivo)
    with Session(motor()) as bd:
        u = crear(bd, nombre, correo, contrasena)
        print(f"Listo: {u.nombre} <{u.correo}> es administrador. Entra en la web con ese correo.")


if __name__ == "__main__":
    main()
