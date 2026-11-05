"""Centro de datos y modelos (/api/datos/centro): tablas reales con sus registros, relaciones, modelos y «Ver datos»."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, requiere
from datos import centro

router = APIRouter(prefix="/api/datos/centro", tags=["datos · centro"])
VER = requiere("nucleo.modulos.administrar")


@router.get("")
def resumen(bd: Session = Depends(obtener_bd), _: Contexto = Depends(VER)) -> dict:
    return {"dominios": centro.DOMINIOS, "tablas": centro.tablas(bd),
            "relaciones": [list(par) for par in centro.relaciones()], "modelos": centro.modelos(bd)}


@router.get("/tablas/{tabla_id}/filas")
def filas(tabla_id: str, bd: Session = Depends(obtener_bd), _: Contexto = Depends(VER)) -> dict:
    t = centro.POR_ID.get(tabla_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa tabla en el Centro de datos.")
    if not t.ver_datos:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta tabla solo se consulta desde su módulo.")
    columnas, renglones = centro.filas(bd, tabla_id)
    return {"columnas": columnas, "filas": renglones, "maximo": centro.MAX_FILAS}
