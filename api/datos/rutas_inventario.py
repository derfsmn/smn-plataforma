"""Datos → Salud de inventario (/api/datos/inventario): dinero detenido, exceso y posibles faltantes."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from datos import inventario as inv

router = APIRouter(prefix="/api/datos/inventario", tags=["datos · inventario"])
VER = requiere("datos.inventario.ver")


@router.get("")
def resumen(tienda: str | None = None, departamento: str | None = None, _: Contexto = Depends(VER),
            bd: Session = Depends(obtener_bd)) -> dict:
    return inv.resumen(bd, tienda or None, departamento or None) or {"corte": None}


@router.get("/productos")
def productos(tipo: Literal["sin_venta", "exceso", "en_cero"], tienda: str | None = None,
              departamento: str | None = None, limite: int = Query(200, ge=1, le=500), _: Contexto = Depends(VER),
              bd: Session = Depends(obtener_bd)) -> list[dict]:
    return inv.productos(bd, tipo, tienda or None, departamento or None, limite)
