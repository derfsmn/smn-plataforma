"""Catálogos iniciales del núcleo: módulos, permisos y roles. Se puede correr varias veces.

No crea usuarios. El primer administrador se crea con: python -m scripts.crear_admin
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from nucleo.modelos import Modulo, Permiso, Rol, RolPermiso

MODULOS = [
    dict(codigo="compras", codigo_iniciativa="TD001", nombre="Inteligencia de Compras", area="Compras",
         descripcion="Semáforo con IA para decidir si un producto nuevo entra al catálogo.",
         tiene_portal_externo=True, orden_menu=10, icono="carrito"),
    dict(codigo="rrhh", codigo_iniciativa=None, nombre="Reclutamiento digital", area="Recursos Humanos",
         descripcion="Postulación a vacantes por tienda con QR y seguimiento.",
         tiene_portal_externo=True, orden_menu=20, icono="personas"),
]

# (código, descripción, módulo o None si es de plataforma)
PERMISOS = [
    ("nucleo.usuarios.administrar", "Dar de alta, editar y desactivar usuarios", None),
    ("nucleo.roles.administrar", "Asignar permisos a los roles", None),
    ("nucleo.modulos.administrar", "Registrar módulos y cambiar su estado", None),
    ("compras.solicitud.ver", "Ver solicitudes de producto nuevo", "compras"),
    ("compras.solicitud.evaluar", "Evaluar solicitudes y confirmar datos", "compras"),
    ("compras.semaforo.ajustar", "Ajustar el color sugerido con motivo", "compras"),
    ("compras.comite.decidir", "Registrar la decisión del Comité", "compras"),
    ("compras.solicitud.enviar", "Enviar propuestas de producto (proveedor)", "compras"),
]

# (código, nombre, descripción, para, módulo, permisos)
ROLES = [
    ("admin", "Administrador de plataforma", "Administra usuarios, roles y módulos.", "interno", None,
     ["nucleo.usuarios.administrar", "nucleo.roles.administrar", "nucleo.modulos.administrar"]),
    ("compras_responsable", "Responsable de Compras", "Evalúa solicitudes y ajusta el semáforo.", "interno", "compras",
     ["compras.solicitud.ver", "compras.solicitud.evaluar", "compras.semaforo.ajustar"]),
    ("compras_comite", "Comité de Compras", "Revisa candidatos y registra la decisión.", "interno", "compras",
     ["compras.solicitud.ver", "compras.comite.decidir"]),
    ("compras_consulta", "Consulta de Compras", "Solo puede ver.", "interno", "compras",
     ["compras.solicitud.ver"]),
    ("proveedor", "Proveedor", "Envía propuestas y ve solo las suyas.", "externo", "compras",
     ["compras.solicitud.enviar"]),
]


def sembrar(bd: Session) -> None:
    modulos: dict[str, Modulo] = {}
    for datos in MODULOS:
        m = bd.scalar(select(Modulo).where(Modulo.codigo == datos["codigo"]))
        if not m:  # si ya existe no se toca: su estado lo administra la plataforma
            m = Modulo(**datos)
            bd.add(m)
        modulos[datos["codigo"]] = m
    bd.flush()

    permisos: dict[str, Permiso] = {}
    for codigo, descripcion, modulo in PERMISOS:
        p = bd.scalar(select(Permiso).where(Permiso.codigo == codigo))
        if not p:
            p = Permiso(codigo=codigo, descripcion=descripcion, modulo_id=modulos[modulo].modulo_id if modulo else None)
            bd.add(p)
        permisos[codigo] = p
    bd.flush()

    for codigo, nombre, descripcion, para, modulo, suyos in ROLES:
        if bd.scalar(select(Rol).where(Rol.codigo == codigo)):
            continue  # los permisos de un rol existente se administran desde la plataforma
        r = Rol(codigo=codigo, nombre=nombre, descripcion=descripcion, para_tipo_usuario=para,
                modulo_id=modulos[modulo].modulo_id if modulo else None)
        bd.add(r)
        bd.flush()
        bd.add_all(RolPermiso(rol_id=r.rol_id, permiso_id=permisos[c].permiso_id) for c in suyos)
    bd.commit()


def main() -> None:
    with Session(motor()) as bd:
        sembrar(bd)
    print("Catálogos del núcleo listos.")


if __name__ == "__main__":
    main()
