"""Fichas técnicas del catálogo (/api/datos/fichas). Las llena la máquina; aquí solo se consultan y se marcan
«Está mal» con motivo (Compras es usuario final, Diego 17 nov 2026)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from datos import fichas
from datos.modelos import Producto, ProductoFicha
from nucleo.bitacora import registrar

router = APIRouter(prefix="/api/datos/fichas", tags=["datos · fichas técnicas"])
VER = requiere("datos.productos.ver")


class EstaMal(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


@router.get("/resumen")
def resumen(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    return fichas.resumen(bd)


@router.get("/producto/{producto_id}")
def de_producto(producto_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict | None:
    if not bd.get(Producto, producto_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    return fichas.salida(bd.get(ProductoFicha, producto_id))


@router.post("/producto/{producto_id}/esta-mal")
def esta_mal(producto_id: int, cuerpo: EstaMal, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    fila = bd.get(ProductoFicha, producto_id)
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto todavía no tiene ficha")
    fichas.marcar_mal(bd, fila, cuerpo.motivo, ctx.usuario.usuario_id)
    registrar(bd, "ficha_esta_mal", usuario_id=ctx.usuario.usuario_id, entidad="producto_ficha", entidad_id=producto_id,
              detalle={"motivo": cuerpo.motivo})
    bd.commit()
    return fichas.salida(fila)
