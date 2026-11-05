"""Administración > Configuración: ver y cambiar ajustes de la plataforma sin tocar el .env."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core import ajustes
from core.bd import obtener_bd
from core.config import configuracion
from core.correo import enviar
from core.seguridad import Contexto, ip_de, requiere
from nucleo.bitacora import registrar
from nucleo.modelos import ConfiguracionAjuste

router = APIRouter(prefix="/api/nucleo/configuracion", tags=["configuración"])
PERMISO = "nucleo.configuracion.administrar"
OCULTO = "••••"


class AjusteSalida(BaseModel):
    clave: str
    etiqueta: str
    tipo: str
    ayuda: str
    minimo: float | None
    maximo: float | None
    opciones: list[dict[str, str]]
    valor: Any  # en secretos siempre nulo
    configurado: bool
    pista: str | None  # últimos 4 caracteres de un secreto
    origen: str  # pantalla / archivo (.env) / omision


class GrupoSalida(BaseModel):
    grupo: str
    nombre: str
    ajustes: list[AjusteSalida]


class Cambios(BaseModel):
    # valor nulo = volver al valor del .env
    cambios: dict[str, Any]


class ResultadoCorreo(BaseModel):
    enviado: bool
    mensaje: str


def _vista(bd: Session) -> list[GrupoSalida]:
    cfg = configuracion()
    en_base = ajustes.guardados(bd)
    grupos = []
    for g, nombre in ajustes.GRUPOS.items():
        filas = []
        for a in (x for x in ajustes.CATALOGO if x.grupo == g):
            actual = getattr(cfg, a.clave)
            secreto = a.tipo == "secreto"
            filas.append(AjusteSalida(
                clave=a.clave, etiqueta=a.etiqueta, tipo=a.tipo, ayuda=a.ayuda, minimo=a.minimo, maximo=a.maximo,
                opciones=[{"valor": v, "texto": t} for v, t in a.opciones],
                valor=None if secreto else actual, configurado=bool(actual) if secreto else actual not in (None, ""),
                pista=(actual[-4:] if secreto and actual and len(actual) >= 12 else None),
                origen=ajustes.origen(a.clave, en_base),
            ))
        grupos.append(GrupoSalida(grupo=g, nombre=nombre, ajustes=filas))
    return grupos


@router.get("", response_model=list[GrupoSalida])
def ver(_: Contexto = Depends(requiere(PERMISO)), bd: Session = Depends(obtener_bd)) -> list[GrupoSalida]:
    return _vista(bd)


@router.put("", response_model=list[GrupoSalida])
def guardar(datos: Cambios, request: Request, ctx: Contexto = Depends(requiere(PERMISO)),
            bd: Session = Depends(obtener_bd)) -> list[GrupoSalida]:
    cfg = configuracion()
    detalle = {}
    for clave, valor in datos.cambios.items():
        a = ajustes.POR_CLAVE.get(clave)
        if not a:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El ajuste «{clave}» no se puede cambiar desde aquí.")
        antes = getattr(cfg, clave)
        fila = bd.get(ConfiguracionAjuste, clave)
        if valor is None:
            if fila:
                bd.delete(fila)
        else:
            try:
                limpio = ajustes.convertir(a, valor)
            except ValueError as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
            texto = ajustes.a_texto(a, limpio)
            if fila:
                fila.valor = texto
                fila.actualizado_por = ctx.usuario.usuario_id
            else:
                bd.add(ConfiguracionAjuste(clave=clave, valor=texto, actualizado_por=ctx.usuario.usuario_id))
        secreto = a.tipo == "secreto"
        detalle[clave] = {"antes": OCULTO if secreto and antes else antes,
                          "despues": "(valor del .env)" if valor is None else OCULTO if secreto else valor}
    bd.flush()
    ajustes.aplicar(bd)
    registrar(bd, "actualizar", usuario_id=ctx.usuario.usuario_id, entidad="configuracion", detalle=detalle,
              ip=ip_de(request))
    bd.commit()
    return _vista(bd)


@router.post("/probar-correo", response_model=ResultadoCorreo)
def probar_correo(ctx: Contexto = Depends(requiere(PERMISO))) -> ResultadoCorreo:
    cfg = configuracion()
    if not cfg.smtp_servidor:
        return ResultadoCorreo(enviado=False, mensaje="No hay servidor SMTP configurado.")
    enviado = enviar(ctx.usuario.correo, "Prueba de correo", f"Hola, {ctx.usuario.nombre}",
                     ["Este es un correo de prueba de SMN - Transformación digital.",
                      f"Salió por {cfg.smtp_servidor}:{cfg.smtp_puerto}. Si lo lees, el correo de salida funciona."])
    return ResultadoCorreo(
        enviado=enviado,
        mensaje=f"Enviado a {ctx.usuario.correo}." if enviado
        else "No se pudo enviar. Revisa servidor, puerto, usuario, contraseña y TLS; el detalle está en la consola de la API.",
    )
