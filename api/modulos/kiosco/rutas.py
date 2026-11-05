"""Rutas del Kiosco Digital (/api/kiosco)."""
import hmac
import threading
import time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from modulos.kiosco import naturi
from modulos.kiosco import productos as catalogo
from nucleo.bitacora import registrar

router = APIRouter(prefix="/api/kiosco", tags=["kiosco · Naturi"])
USAR = requiere("kiosco.naturi.usar")
SIN_GUARDAR = {"Cache-Control": "no-store"}


class Configuracion(BaseModel):
    disponible: bool
    terminos: str
    version_terminos: str
    texto: bool
    fotos: bool


class PideSesion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo: Literal["voz", "texto"] = "voz"
    acepta_terminos: bool = False
    version_terminos: str = Field("", max_length=64)


class Sesion(BaseModel):
    signed_url: str
    modo: str


@router.get("/configuracion", response_model=Configuracion)
def configuracion_naturi(response: Response, _: Contexto = Depends(USAR)) -> Configuracion:
    response.headers.update(SIN_GUARDAR)
    if not naturi.disponible():
        return Configuracion(disponible=False, terminos="", version_terminos="", texto=False, fotos=False)
    return Configuracion(disponible=True, **naturi.configuracion_agente())


@router.post("/sesion", response_model=Sesion)
def sesion(datos: PideSesion, request: Request, response: Response, ctx: Contexto = Depends(USAR),
           bd: Session = Depends(obtener_bd)) -> Sesion:
    """Autorización de un solo uso para conversar. La llave de ElevenLabs nunca sale del servidor."""
    response.headers.update(SIN_GUARDAR)
    if not naturi.disponible():
        raise HTTPException(503, "Naturi todavía no está disponible para conversar.")
    cfg = naturi.configuracion_agente()
    if cfg["terminos"] and (not datos.acepta_terminos or datos.version_terminos != cfg["version_terminos"]):
        raise HTTPException(409, "Lee y acepta los términos vigentes antes de comenzar.")
    if datos.modo == "texto" and not cfg["texto"]:
        raise HTTPException(409, "Por ahora puedes escribir durante una conversación de voz.")
    naturi.admitir(ctx.usuario.usuario_id)
    firmada = naturi.liga_firmada()
    registrar(bd, "kiosco_conversacion", usuario_id=ctx.usuario.usuario_id, ip=ip_de(request),
              detalle={"modo": datos.modo})
    bd.commit()
    return Sesion(signed_url=firmada, modo=datos.modo)


# ---------------------------------------------------------------- herramienta del agente

_ritmo_lock = threading.Lock()
_ritmo = {"minuto": -1, "consultas": 0}
PARAMETROS = {"consulta", "limite", "desplazamiento", "excluir_skus", "presentacion", "marca", "precio_maximo",
              "precio_menor_que", "tipo_precio", "orden"}


def _autorizar(request: Request) -> None:
    """La llama ElevenLabs (servidor a servidor) con el token de Configuración; sin token capturado, nadie entra."""
    esperado = configuracion().kiosco_token_herramienta
    dado = request.headers.get("authorization", "")
    if not esperado or not hmac.compare_digest(dado.encode(), f"Bearer {esperado}".encode()):
        raise HTTPException(401, "Token requerido o inválido.", headers={"WWW-Authenticate": "Bearer"})
    with _ritmo_lock:
        minuto = int(time.monotonic() // 60)
        if _ritmo["minuto"] != minuto:
            _ritmo.update(minuto=minuto, consultas=0)
        _ritmo["consultas"] += 1
        if _ritmo["consultas"] > 120:
            raise HTTPException(429, "Límite de consultas alcanzado.", headers={"Retry-After": "60"})


def _sin_control(texto: str) -> bool:
    return not any(ord(c) < 32 for c in texto)


@router.get("/productos")
def buscar_productos(request: Request, response: Response, bd: Session = Depends(obtener_bd),
                     consulta: str = Query("", max_length=120), limite: int = Query(5, ge=1, le=10),
                     desplazamiento: int = Query(0, ge=0, le=100000), excluir_skus: str = Query("", max_length=4096),
                     presentacion: Literal["capsulas", "tabletas", "polvo", "gomitas", "liquido"] | None = None,
                     marca: str | None = Query(None, max_length=160),
                     precio_maximo: str | None = Query(None, max_length=40),
                     precio_menor_que: str | None = Query(None, max_length=40),
                     tipo_precio: Literal["lista", "membresia"] = "lista",
                     orden: Literal["relevancia", "precio_asc"] = "relevancia") -> dict:
    """Herramienta `buscar_productos_smn` de Naturi. Mismos parámetros que la del proyecto SMN_Direccion."""
    _autorizar(request)
    response.headers.update(SIN_GUARDAR)
    if set(request.query_params) - PARAMETROS or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise HTTPException(422, "Parámetros inválidos.")
    consulta = consulta.strip()
    if len(consulta) < 2 or not any(c.isalnum() for c in consulta) or not _sin_control(consulta):
        raise HTTPException(422, "Consulta inválida.")
    excluir = [s.strip() for s in excluir_skus.split(",")] if excluir_skus else []
    if len(excluir) > 50 or any(not s or len(s) > 80 or not _sin_control(s) for s in excluir):
        raise HTTPException(422, "Lista de SKU inválida.")
    maximo = catalogo.importe(precio_maximo) if precio_maximo is not None else None
    menor = catalogo.importe(precio_menor_que) if precio_menor_que is not None else None
    if (precio_maximo is not None and maximo is None) or (precio_menor_que is not None and menor is None):
        raise HTTPException(422, "Importe inválido.")
    if marca is not None and (not catalogo.clave_marca(marca) or not _sin_control(marca)):
        raise HTTPException(422, "Marca inválida.")
    return catalogo.buscar(bd, consulta, limite, desplazamiento=desplazamiento, excluir=tuple(dict.fromkeys(excluir)),
                           presentacion=presentacion, marca=marca.strip() if marca else None,
                           maximo=Decimal(maximo) if maximo else None, menor_que=Decimal(menor) if menor else None,
                           tipo_precio=tipo_precio, orden=orden)
