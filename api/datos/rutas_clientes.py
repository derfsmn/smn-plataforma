"""Datos → Clientes (/api/datos/clientes): subir el CSV de la consulta, ver los tipos de cliente y recalcular."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from datos import clientes as cl
from datos.modelos import ClienteCorrida
from nucleo.bitacora import registrar

router = APIRouter(prefix="/api/datos/clientes", tags=["datos · clientes"])
VER = requiere("datos.clientes.ver")
CALCULAR = requiere("datos.clientes.calcular")
MB_ARCHIVO = 300
CONSULTA = Path(__file__).with_name("consulta_clientes.sql")  # copia de docs/sistemas/consulta_clientes.sql


def _corrida(c: ClienteCorrida | None) -> dict | None:
    if not c:
        return None
    return {"id": c.corrida_id, "estado": c.estado, "paso": c.paso, "archivo": c.archivo, "renglones": c.renglones,
            "clientes": c.clientes, "tipos": c.tipos, "calidad": c.calidad, "nota_ia": c.nota_ia, "error": c.error,
            "iniciada_en": c.iniciada_en, "terminada_en": c.terminada_en}


@router.get("")
def actual(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    c = cl.ultima(bd)
    fallida = bd.scalar(select(ClienteCorrida).where(ClienteCorrida.estado == "fallida")
                        .order_by(ClienteCorrida.corrida_id.desc()))
    if fallida and c and fallida.corrida_id < c.corrida_id:
        fallida = None
    return {"corrida": _corrida(c), "en_curso": _corrida(cl.en_curso(bd)), "fallida": _corrida(fallida),
            "resumen": json.loads(c.resumen) if c and c.resumen else None,
            "tipos": json.loads(c.perfiles) if c and c.perfiles else [], "hay_archivo": cl.hay_archivo(),
            "objetivo": cl.objetivo(bd), "borrador_objetivo": cl.borrador_objetivo(bd), "niveles": list(cl.NIVELES)}


class Objetivo(BaseModel):
    nivel: str
    descripcion: str | None = Field(None, max_length=3000)


@router.put("/objetivo")
def guardar_objetivo(datos: Objetivo, request: Request, ctx: Contexto = Depends(CALCULAR),
                     bd: Session = Depends(obtener_bd)) -> dict:
    """«Nuestro cliente»: nivel socioeconómico y descripción. «Buscar oportunidades» valida contra esto."""
    if datos.nivel not in cl.NIVELES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige un nivel de la lista.")
    o = cl.guardar_objetivo(bd, datos.nivel, datos.descripcion, ctx.usuario.usuario_id)
    registrar(bd, "clientes_objetivo", usuario_id=ctx.usuario.usuario_id, entidad="cliente_objetivo", entidad_id=1,
              detalle={"nivel": datos.nivel, "descripcion": (datos.descripcion or "")[:500]}, ip=ip_de(request))
    bd.commit()
    return o


@router.get("/consulta", response_class=PlainTextResponse)
def consulta(_: Contexto = Depends(VER)) -> str:
    """La consulta para SMNBI (solo lee; no saca nombres ni números de cliente)."""
    if not CONSULTA.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No se encontró la consulta de clientes.")
    return CONSULTA.read_text(encoding="utf-8")


def _arrancar(bd: Session, ctx: Contexto, request: Request, archivo: str | None, tipos: int | None, accion: str):
    if cl.en_curso(bd):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya se están calculando los tipos de cliente. Espera a que termine.")
    c = cl.iniciar(bd, ctx.usuario.usuario_id, archivo)
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, entidad="cliente_corrida", entidad_id=c.corrida_id,
              detalle={"archivo": archivo, "tipos": tipos}, ip=ip_de(request))
    bd.commit()
    cl.en_hilo(c.corrida_id, tipos)
    return _corrida(c)


@router.post("/cargar", status_code=status.HTTP_202_ACCEPTED)
async def cargar(request: Request, archivo: UploadFile = File(...), tipos: int | None = Form(None),
                 ctx: Contexto = Depends(CALCULAR), bd: Session = Depends(obtener_bd)) -> dict:
    contenido = await archivo.read(MB_ARCHIVO * 1024 * 1024 + 1)
    if len(contenido) > MB_ARCHIVO * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El archivo pasa de {MB_ARCHIVO} MB.")
    if not contenido.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo viene vacío.")
    if tipos is not None and not 2 <= tipos <= cl.MAX_PEDIDOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Elige de 2 a {cl.MAX_PEDIDOS} tipos.")
    if cl.en_curso(bd):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya se están calculando los tipos de cliente. Espera a que termine.")
    try:  # se revisa el formato antes de guardar, para no tirar el último archivo bueno
        cl.leer(contenido[:200_000].rsplit(b"\n", 1)[0] if len(contenido) > 200_000 else contenido)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    cl.guardar_archivo(contenido)
    return _arrancar(bd, ctx, request, (archivo.filename or "clientes.csv")[:260], tipos, "clientes_cargar")


class Recalcular(BaseModel):
    tipos: int | None = Field(None, ge=2, le=cl.MAX_PEDIDOS)  # None = el número que mejor separa


@router.post("/calcular", status_code=status.HTTP_202_ACCEPTED)
def recalcular(request: Request, datos: Recalcular | None = None, ctx: Contexto = Depends(CALCULAR),
               bd: Session = Depends(obtener_bd)) -> dict:
    if not cl.hay_archivo():
        raise HTTPException(status.HTTP_409_CONFLICT, "Primero sube el archivo de la consulta de clientes.")
    ultima = cl.ultima(bd)
    return _arrancar(bd, ctx, request, ultima.archivo if ultima else None, datos.tipos if datos else None,
                     "clientes_calcular")
