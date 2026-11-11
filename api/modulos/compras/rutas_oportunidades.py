"""«Buscar oportunidades» (/api/compras/oportunidades): productos que no tenemos y convendría buscar.

Una corrida corre aparte y la pantalla consulta su avance. Cada recomendación se manda al semáforo como idea de Compras
(«Evaluar») o se descarta. Motor en oportunidades.py.
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, requiere
from modulos.compras import dataforseo as dfs
from modulos.compras import oportunidades as op
from modulos.compras import radar_productos as rp
from modulos.compras.modelos_productos import Oportunidad, OportunidadCorrida
from modulos.compras.rutas_productos import EVALUAR, VER, _bitacora
from nucleo.modelos import Usuario, ahora

router = APIRouter(prefix="/api/compras/oportunidades", tags=["compras · oportunidades"])


class EvidenciaSalida(BaseModel):
    clave: str
    fuente: str
    texto: str
    puertas: list[str] = []


class OportunidadSalida(BaseModel):
    id: int
    orden: int
    nombre: str
    marca: str | None
    departamento: str | None
    subcategoria: str | None
    forma: str | None
    por_que: str
    prioridad: str
    evidencia: list[EvidenciaSalida]
    precio_visto: Decimal | None
    donde_se_vio: str | None
    imagen: str | None  # liga de la foto del producto
    imagen_de: str | None  # de dónde salió la foto
    estado: str
    evaluacion_id: int | None  # la evaluación vigente de la idea que se creó
    evaluacion_estado: str | None = None  # en_curso / lista / fallida
    color: str | None = None  # el del semáforo (o el que puso Compras)
    puntaje: int | None = None
    puertas: list[str] = []  # tendencia / mas_vendido (2026-11-09)
    busqueda_id: int | None = None  # su búsqueda de proveedor, si se abrió
    busqueda_estado: str | None = None
    tipo_cliente: str | None = None  # para qué tipo de cliente (Datos → Clientes)
    encaje: str | None = None  # si / dudoso contra «Nuestro cliente»
    encaje_motivo: str | None = None


class CorridaResumen(BaseModel):
    id: int
    estado: str
    paso: str | None
    competencia: bool
    con_ia: bool
    costo_usd: Decimal
    error: str | None
    disparada_por: str | None
    programada: bool = False
    creada_en: datetime
    terminada_en: datetime | None
    total: int


class CorridaDetalle(CorridaResumen):
    notas: list[str]
    fuentes: dict[str, int]  # cuántos datos de cada fuente se juntaron
    oportunidades: list[OportunidadSalida]


class Estado(BaseModel):
    costo_maximo_competencia_usd: Decimal
    busquedas_competencia: int
    falta_configurar: list[str]  # lo que falta para buscar en la competencia
    programa: str | None = None  # «Corre sola cada lunes a las 8:00»; None = solo con el botón
    corridas: list[CorridaResumen]


def _resumen(bd: Session, c: OportunidadCorrida) -> CorridaResumen:
    u = bd.get(Usuario, c.disparada_por) if c.disparada_por else None
    return CorridaResumen(id=c.corrida_id, estado=c.estado, paso=c.paso, competencia=c.competencia, con_ia=c.con_ia,
                          costo_usd=c.costo_usd or Decimal("0"), error=c.error, disparada_por=u.nombre if u else None,
                          programada=op.es_programada(c),
                          creada_en=c.creada_en, terminada_en=c.terminada_en, total=len(c.oportunidades))


def _oportunidad(bd: Session, o: Oportunidad) -> OportunidadSalida:
    from modulos.compras import busquedas as bq

    e = rp.vigente(bd, idea_id=o.idea_id) if o.idea_id else None
    b = bq.de_idea(bd, o.idea_id) if o.idea_id else None
    evidencia = json.loads(o.evidencia)
    return OportunidadSalida(id=o.oportunidad_id, orden=o.orden, nombre=o.nombre, marca=o.marca,
                             departamento=o.departamento, subcategoria=o.subcategoria, forma=o.forma, por_que=o.por_que,
                             prioridad=o.prioridad, evidencia=[EvidenciaSalida(**x) for x in evidencia],
                             precio_visto=o.precio_visto, donde_se_vio=o.donde_se_vio, imagen=o.imagen,
                             imagen_de=o.imagen_de, estado=o.estado,
                             evaluacion_id=e.evaluacion_id if e else None,
                             evaluacion_estado=e.estado if e else None,
                             color=bq.color_de(e) if e and e.estado == "lista" else None,
                             puntaje=e.puntaje if e and e.estado == "lista" else None,
                             puertas=op.puertas(evidencia), busqueda_id=b.busqueda_id if b else None,
                             busqueda_estado=bq.ESTADOS[b.estado] if b else None, tipo_cliente=o.tipo_cliente, encaje=o.encaje,
                             encaje_motivo=o.encaje_motivo)


def _detalle(bd: Session, c: OportunidadCorrida) -> CorridaDetalle:
    fuentes = json.loads(c.fuentes) if c.fuentes else {}
    cuenta = {nombre: sum(1 for k in fuentes if k[0] == letra) for letra, nombre in op.FUENTE.items()}
    cuenta = {n: x for (letra, n), x in zip(op.FUENTE.items(), cuenta.values()) if x or letra not in op.VIEJAS}
    return CorridaDetalle(**_resumen(bd, c).model_dump(), notas=json.loads(c.notas) if c.notas else [], fuentes=cuenta,
                          oportunidades=[_oportunidad(bd, o) for o in c.oportunidades])


@router.get("", response_model=Estado)
def estado(_: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> Estado:
    n = configuracion().oportunidades_busquedas
    corridas = bd.scalars(select(OportunidadCorrida).order_by(OportunidadCorrida.corrida_id.desc()).limit(10)).all()
    return Estado(costo_maximo_competencia_usd=dfs.maximo_tarea("productos", configuracion().precios_profundidad) * n,
                  busquedas_competencia=n, falta_configurar=dfs.configurado(), programa=op.texto_programa(),
                  corridas=[_resumen(bd, c) for c in corridas])


class Buscar(BaseModel):
    competencia: bool = False


@router.post("", response_model=CorridaDetalle, status_code=status.HTTP_202_ACCEPTED)
def buscar(datos: Buscar, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
           bd: Session = Depends(obtener_bd)) -> CorridaDetalle:
    c = op.iniciar(bd, ctx.usuario.usuario_id, datos.competencia)
    if not c:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una búsqueda de oportunidades en curso. Espera a que termine.")
    _bitacora(bd, "buscar_oportunidades", ctx, request, "oportunidad_corrida", c.corrida_id,
              {"competencia": datos.competencia})
    bd.commit()
    op.en_hilo(c.corrida_id)
    return _detalle(bd, c)


def _corrida(bd: Session, corrida_id: int) -> OportunidadCorrida:
    c = bd.get(OportunidadCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa búsqueda no existe.")
    return c


@router.get("/corridas/{corrida_id}", response_model=CorridaDetalle)
def corrida(corrida_id: int, _: Contexto = Depends(requiere(VER)), bd: Session = Depends(obtener_bd)) -> CorridaDetalle:
    return _detalle(bd, _corrida(bd, corrida_id))


def _de(bd: Session, oportunidad_id: int) -> Oportunidad:
    o = bd.get(Oportunidad, oportunidad_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa recomendación no existe.")
    return o


@router.post("/{oportunidad_id}/evaluar", response_model=OportunidadSalida)
def evaluar(oportunidad_id: int, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
            bd: Session = Depends(obtener_bd)) -> OportunidadSalida:
    """La recomendación pasa al semáforo como idea de Compras, con la evidencia en la descripción."""
    o = _de(bd, oportunidad_id)
    if o.idea_id:
        return _oportunidad(bd, o)
    i = op.a_idea(bd, o, ctx.usuario.usuario_id)
    _bitacora(bd, "evaluar_oportunidad", ctx, request, "oportunidad", o.oportunidad_id, {"idea": i.idea_id})
    bd.commit()
    e = rp.iniciar(bd, idea_id=i.idea_id, usuario_id=ctx.usuario.usuario_id)
    rp.en_hilo(e.evaluacion_id)
    return _oportunidad(bd, o)


class CambioEstado(BaseModel):
    estado: Literal["nueva", "descartada"]


@router.patch("/{oportunidad_id}", response_model=OportunidadSalida)
def cambiar(oportunidad_id: int, datos: CambioEstado, request: Request, ctx: Contexto = Depends(requiere(EVALUAR)),
            bd: Session = Depends(obtener_bd)) -> OportunidadSalida:
    o = _de(bd, oportunidad_id)
    if o.idea_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ya se mandó al semáforo; ahí se le cambia el estado a la idea.")
    o.estado, o.actualizada_por, o.actualizada_en = datos.estado, ctx.usuario.usuario_id, ahora()
    _bitacora(bd, "cambiar_oportunidad", ctx, request, "oportunidad", o.oportunidad_id, {"estado": datos.estado})
    bd.commit()
    return _oportunidad(bd, o)


class Instruccion(BaseModel):
    paso: str
    que_hace: str
    texto: str  # las instrucciones tal cual las recibe la IA


def _legible(t: str) -> str:
    """Quita los saltos de línea que solo cortan el texto a lo ancho del código; deja párrafos y viñetas."""
    salida: list[str] = []
    for linea in t.strip().split("\n"):
        corta = linea.strip()
        nuevo = not salida or not corta or not salida[-1] or corta.startswith("- ") or salida[-1].endswith(":") \
            or (corta[:1].isupper() and salida[-1].endswith((".", "»")))
        if nuevo:
            salida.append(corta)
        else:
            salida[-1] += " " + corta
    return "\n".join(salida)


@router.get("/instrucciones", response_model=list[Instruccion])
def instrucciones(_: Contexto = Depends(requiere(VER))) -> list[Instruccion]:
    """Las instrucciones que sigue la IA en cada paso, tal cual están en oportunidades.py (Diego, 2026-11-03: «en donde
    puedo ver la descripción del agente?»). Solo lectura: se cambian en el código."""
    return [
        Instruccion(paso="1a. Agente que busca por tendencia",
                    que_hace=f"Una búsqueda por cada una de las {configuracion().oportunidades_tendencias} tendencias más "
                             "fuertes del radar: productos que ya se venden en México con esa tendencia. Recibe la "
                             "tendencia, nuestras subcategorías y lo que más vendemos para no proponerlo.",
                    texto=_legible(op.INSTRUCCIONES_TENDENCIA)),
        Instruccion(paso="1b. Agente que busca lo más vendido",
                    que_hace=f"Una búsqueda por cada uno de los {configuracion().oportunidades_departamentos} departamentos "
                             "que más vendemos: lo más vendido en México de ese departamento, esté o no de moda.",
                    texto=_legible(op.INSTRUCCIONES_DEPARTAMENTO)),
        Instruccion(paso="2. Comprador que arma la lista final",
                    que_hace="Junta lo que trajo el agente, la competencia (si se pidió), las tendencias, los huecos del "
                             "surtido y las reglas y casos que Compras rechazó, y propone hasta 20 productos.",
                    texto=_legible(op.INSTRUCCIONES)),
        Instruccion(paso="Respaldo: pasar a lista",
                    que_hace="Solo si el agente contestó en texto y no en lista: lo acomoda sin agregar nada.",
                    texto=_legible(op.INSTRUCCIONES_A_JSON)),
    ]
