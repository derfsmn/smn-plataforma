"""Formas de entrada y salida de la API del núcleo."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from nucleo.modelos import Modulo, Usuario


class RolBreve(BaseModel):
    codigo: str
    nombre: str


class UsuarioSalida(BaseModel):
    id: int
    nombre: str
    correo: str
    tipo: str
    area: str | None
    puesto: str | None
    empresa: str | None
    estatus: str
    roles: list[RolBreve]
    ultimo_acceso_en: datetime | None
    creado_en: datetime

    @classmethod
    def de(cls, u: Usuario) -> "UsuarioSalida":
        return cls(
            id=u.usuario_id, nombre=u.nombre, correo=u.correo, tipo=u.tipo, area=u.area, puesto=u.puesto,
            empresa=u.organizacion.nombre if u.organizacion else None, estatus=u.estatus,
            roles=[RolBreve(codigo=r.codigo, nombre=r.nombre) for r in u.roles],
            ultimo_acceso_en=u.ultimo_acceso_en, creado_en=u.creado_en,
        )


class ModuloSalida(BaseModel):
    codigo: str
    iniciativa: str | None
    nombre: str
    area: str
    descripcion: str | None
    estado: str
    responsable: str | None
    tiene_portal_externo: bool
    icono: str

    @classmethod
    def de(cls, m: Modulo) -> "ModuloSalida":
        return cls(
            codigo=m.codigo, iniciativa=m.codigo_iniciativa, nombre=m.nombre, area=m.area,
            descripcion=m.descripcion, estado=m.estado,
            responsable=m.responsable.nombre if m.responsable else None,
            tiene_portal_externo=m.tiene_portal_externo, icono=m.icono,
        )


class Yo(BaseModel):
    usuario: UsuarioSalida
    permisos: list[str]
    modulos: list[ModuloSalida]
    debe_cambiar_contrasena: bool
    entorno: str


class Credenciales(BaseModel):
    correo: str = Field(max_length=254)
    contrasena: str = Field(max_length=200)


class CambioContrasena(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


class SolicitudRecuperacion(BaseModel):
    correo: str = Field(max_length=254)


class NuevaContrasena(BaseModel):
    contrasena: str = Field(max_length=200)
    acepta_aviso_privacidad: bool = False


class DatosLiga(BaseModel):
    nombre: str
    correo: str
    tipo: str
    empresa: str | None


class NuevaInvitacion(BaseModel):
    tipo: Literal["interno", "externo"]
    nombre: str = Field(min_length=2, max_length=200)
    correo: EmailStr
    rol: str = Field(max_length=60)
    area: str | None = Field(default=None, max_length=120)
    puesto: str | None = Field(default=None, max_length=120)
    empresa: str | None = Field(default=None, max_length=200)
    rfc: str | None = Field(default=None, max_length=13)


class Liga(BaseModel):
    liga: str
    expira_en: datetime
    # False si no hay correo configurado o el envío falló: entonces la liga se comparte a mano
    correo_enviado: bool = False


class InvitacionCreada(Liga):
    usuario: UsuarioSalida


class CambioUsuario(BaseModel):
    estatus: Literal["activo", "inactivo"] | None = None
    roles: list[str] | None = None


class RolSalida(BaseModel):
    codigo: str
    nombre: str
    descripcion: str | None
    para: str
    modulo: str | None
    permisos: list[str]


class PermisoSalida(BaseModel):
    codigo: str
    descripcion: str
    modulo: str


class PermisosDeRol(BaseModel):
    permisos: list[str]


class CambioModulo(BaseModel):
    estado: Literal["en_diseno", "piloto", "activo", "retirado"]


class Resumen(BaseModel):
    iniciativas: int
    usuarios_activos: int
    proveedores: int
    invitaciones_pendientes: int
