"""Datos → Grupos de tiendas (/api/datos/grupos-tiendas): el último cálculo y el botón para recalcular."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from datos import demografia
from datos import grupos_tiendas as gt
from datos.modelos import TiendaGrupo, TiendaGrupoCorrida
from nucleo.bitacora import registrar

router = APIRouter(prefix="/api/datos/grupos-tiendas", tags=["datos · grupos de tiendas"])
VER = requiere("datos.tiendas.ver")
CALCULAR = requiere("datos.tiendas.calcular")


def _corrida(c: TiendaGrupoCorrida | None) -> dict | None:
    if not c:
        return None
    return {"id": c.corrida_id, "estado": c.estado, "iniciada_en": c.iniciada_en, "terminada_en": c.terminada_en,
            "tiendas": c.tiendas, "grupos": c.grupos, "calidad": c.calidad, "nota_ia": c.nota_ia, "error": c.error,
            "contexto": json.loads(c.contexto) if c.contexto else {}}


@router.get("")
def actual(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    c = gt.ultima(bd)
    # La última que falló se enseña solo si es más reciente que la última completa
    fallida = bd.scalar(select(TiendaGrupoCorrida).where(TiendaGrupoCorrida.estado == "fallida")
                        .order_by(TiendaGrupoCorrida.corrida_id.desc()))
    if fallida and c and fallida.corrida_id < c.corrida_id:
        fallida = None
    tiendas = []
    if c:
        tiendas = [{"almacen": t.almacen, "grupo": t.grupo, "tipicidad": t.tipicidad,
                    "rasgos": json.loads(t.rasgos) if t.rasgos else [],
                    "alertas": json.loads(t.alertas) if t.alertas else [],
                    "metricas": json.loads(t.metricas) if t.metricas else {}}
                   for t in bd.scalars(select(TiendaGrupo).where(TiendaGrupo.corrida_id == c.corrida_id))]
    return {"corrida": _corrida(c), "en_curso": _corrida(gt.en_curso(bd)), "fallida": _corrida(fallida),
            "grupos": json.loads(c.perfiles) if c and c.perfiles else [], "tiendas": tiendas,
            "criterios": [{"clave": k, "nombre": n, "disponible": k != "demografia" or demografia.disponible()}
                          for k, n in gt.CRITERIOS.items()]}


class Calcular(BaseModel):
    grupos: int | None = Field(None, ge=2, le=gt.MAX_PEDIDOS)  # None = el número que mejor separa
    criterios: dict[str, int] | None = None  # criterio → peso de 1 a 3; None = los cuatro con el mismo peso


@router.post("/calcular", status_code=status.HTTP_202_ACCEPTED)
def calcular(request: Request, datos: Calcular | None = None, ctx: Contexto = Depends(CALCULAR),
             bd: Session = Depends(obtener_bd)) -> dict:
    """Vuelve a agrupar las tiendas con la venta cargada hoy. Corre aparte."""
    grupos = datos.grupos if datos else None
    criterios = datos.criterios if datos else None
    if criterios is not None:
        if any(k not in gt.CRITERIOS or not 0 <= w <= 3 for k, w in criterios.items()) or not any(criterios.values()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Elige al menos un criterio (ventas, tendencia, mezcla o demografía) con peso de 1 a 3.")
    if gt.en_curso(bd):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya se están calculando los grupos. Espera a que termine.")
    c = gt.iniciar(bd, ctx.usuario.usuario_id)
    registrar(bd, "grupos_tiendas_calcular", usuario_id=ctx.usuario.usuario_id, entidad="tienda_grupo_corrida",
              entidad_id=c.corrida_id, detalle={"grupos": grupos, "criterios": criterios}, ip=ip_de(request))
    bd.commit()
    gt.en_hilo(c.corrida_id, grupos, criterios)
    return _corrida(c)
