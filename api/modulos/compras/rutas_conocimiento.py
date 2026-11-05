"""Rutas de la Base de conocimiento de Compras (/api/compras/conocimiento).

Compras escribe aquí sus políticas, los motivos de rechazo directo, los umbrales, el peso de cada factor, qué es un
lanzamiento exitoso y los casos pasados. El semáforo de productos lo leerá de aquí.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.seguridad import Contexto, ip_de, requiere
from datos.modelos import Producto
from modulos.compras.modelos_conocimiento import (ConocimientoCaso, ConocimientoPeso, ConocimientoPesoProveedor,
                                                  ConocimientoPolitica, ConocimientoRegla)
from nucleo.bitacora import registrar
from nucleo.modelos import Modulo, Usuario

router = APIRouter(prefix="/api/compras/conocimiento", tags=["compras · base de conocimiento"])
VER = requiere("compras.conocimiento.ver")
EDITAR = requiere("compras.conocimiento.editar")

Tema = Literal["alta_productos", "proveedores", "regulatorio", "precios", "comite", "proceso", "otra"]
EstadoPolitica = Literal["borrador", "vigente", "archivada"]
TipoRegla = Literal["rechazo", "umbral", "exito"]
Decision = Literal["aprobado", "rechazado", "condicionado"]
Resultado = Literal["funciono", "no_funciono", "sin_dato", "no_aplica"]

# Los seis componentes del semáforo (modelo_semaforo_v3: evaluacion_componente)
FACTORES = {
    "demanda": ("Demanda", "Venta de productos parecidos en SMN"),
    "rentabilidad": ("Rentabilidad", "Margen esperado"),
    "precio": ("Precio", "Precio contra la competencia"),
    "tendencia": ("Tendencia", "Señales del radar de tendencias"),
    "categoria": ("Categoría", "Si el surtido lo necesita o ya está cubierto"),
    "proveedor": ("Proveedor", "Cumplimiento, condiciones y antigüedad del proveedor"),
}
CASOS_PARA_CALIBRAR = 20


def _modulo_id(bd: Session) -> int | None:
    return bd.scalar(select(Modulo.modulo_id).where(Modulo.codigo == "compras"))


def _nombres(bd: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(bd.execute(select(Usuario.usuario_id, Usuario.nombre).where(Usuario.usuario_id.in_(ids))).all())


def _texto(v: str | None) -> str | None:
    return (v or "").strip() or None


def _bitacora(bd: Session, accion: str, ctx: Contexto, request: Request, entidad: str, entidad_id, detalle: dict) -> None:
    registrar(bd, accion, usuario_id=ctx.usuario.usuario_id, modulo_id=_modulo_id(bd), entidad=entidad,
              entidad_id=entidad_id, detalle=detalle, ip=ip_de(request))


# ---------------------------------------------------------------- resumen

class Seccion(BaseModel):
    clave: str
    titulo: str
    cuantos: int
    lista: bool
    falta: str | None


class Resumen(BaseModel):
    secciones: list[Seccion]
    listas: int
    total: int
    actualizado_en: datetime | None


@router.get("/resumen", response_model=Resumen)
def resumen(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Resumen:
    """Qué tan completa está la base: lo que falta para que el semáforo la pueda usar."""
    def vigentes(*temas: str, excepto: bool = False) -> int:
        q = select(func.count()).select_from(ConocimientoPolitica).where(ConocimientoPolitica.estado == "vigente")
        q = q.where(ConocimientoPolitica.tema.not_in(temas) if excepto else ConocimientoPolitica.tema.in_(temas))
        return bd.scalar(q) or 0

    def reglas(tipo: str) -> int:
        return bd.scalar(select(func.count()).select_from(ConocimientoRegla)
                         .where(ConocimientoRegla.tipo == tipo, ConocimientoRegla.activa)) or 0

    puntos = bd.scalar(select(func.sum(ConocimientoPeso.puntos))) or 0
    casos = bd.scalar(select(func.count()).select_from(ConocimientoCaso)) or 0
    con_resultado = bd.scalar(select(func.count()).select_from(ConocimientoCaso)
                              .where(ConocimientoCaso.resultado.in_(("funciono", "no_funciono")))) or 0
    n_politicas, n_proceso = vigentes("proceso", excepto=True), vigentes("proceso")
    n_rechazo, n_umbral, n_exito = reglas("rechazo"), reglas("umbral"), reglas("exito")
    secciones = [
        Seccion(clave="politicas", titulo="Políticas", cuantos=n_politicas, lista=n_politicas > 0,
                falta=None if n_politicas else "Escribir al menos una política y marcarla como vigente."),
        Seccion(clave="rechazo", titulo="Rechazo directo", cuantos=n_rechazo, lista=n_rechazo > 0,
                falta=None if n_rechazo else "Anotar qué hace que un producto se rechace de inmediato."),
        Seccion(clave="criterios", titulo="Criterios y umbrales", cuantos=n_umbral, lista=n_umbral > 0,
                falta=None if n_umbral else "Anotar los valores que se revisan (margen, vida útil, etc.)."),
        Seccion(clave="pesos", titulo="Peso de cada factor", cuantos=puntos, lista=puntos == 100,
                falta=None if puntos == 100 else f"Repartir 100 puntos entre los seis factores (van {puntos})."),
        Seccion(clave="exito", titulo="Lanzamiento exitoso", cuantos=n_exito, lista=n_exito > 0,
                falta=None if n_exito else "Definir cómo se sabe que un producto nuevo funcionó."),
        Seccion(clave="casos", titulo="Casos pasados", cuantos=casos,
                lista=casos >= CASOS_PARA_CALIBRAR and con_resultado > 0,
                falta=None if casos >= CASOS_PARA_CALIBRAR and con_resultado > 0 else
                f"Registrar al menos {CASOS_PARA_CALIBRAR} productos evaluados antes, con su resultado (van {casos})."),
        Seccion(clave="proceso", titulo="Cómo se decide hoy", cuantos=n_proceso, lista=n_proceso > 0,
                falta=None if n_proceso else "Describir quién propone, revisa y aprueba, y con qué información."),
    ]
    fechas = [bd.scalar(select(func.max(t.actualizado_en)))
              for t in (ConocimientoPolitica, ConocimientoRegla, ConocimientoPeso, ConocimientoCaso)]
    fechas = [f for f in fechas if f]
    return Resumen(secciones=secciones, listas=sum(s.lista for s in secciones), total=len(secciones),
                   actualizado_en=max(fechas) if fechas else None)


@router.get("/departamentos", response_model=list[str])
def departamentos(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[str]:
    """Departamentos del catálogo, para elegir a cuál aplica una regla."""
    return [d for d in bd.scalars(select(Producto.departamento).where(Producto.departamento.is_not(None))
                                  .distinct().order_by(Producto.departamento)).all() if d.strip()]


# ---------------------------------------------------------------- políticas

class PoliticaEntrada(BaseModel):
    tema: Tema
    titulo: str = Field(min_length=2, max_length=200)
    contenido: str = Field(default="", max_length=60000)
    departamento: str | None = Field(default=None, max_length=300)
    estado: EstadoPolitica = "borrador"


class PoliticaSalida(PoliticaEntrada):
    id: int
    version: int
    actualizado_por: str | None
    actualizado_en: datetime


def _politica(p: ConocimientoPolitica, nombres: dict[int, str]) -> PoliticaSalida:
    return PoliticaSalida(id=p.politica_id, tema=p.tema, titulo=p.titulo, contenido=p.contenido, departamento=p.departamento,
                          estado=p.estado, version=p.version, actualizado_por=nombres.get(p.actualizado_por),
                          actualizado_en=p.actualizado_en)


@router.get("/politicas", response_model=list[PoliticaSalida])
def politicas(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[PoliticaSalida]:
    filas = bd.scalars(select(ConocimientoPolitica).order_by(ConocimientoPolitica.tema, ConocimientoPolitica.titulo)).all()
    nombres = _nombres(bd, {p.actualizado_por for p in filas})
    return [_politica(p, nombres) for p in filas]


@router.post("/politicas", response_model=PoliticaSalida, status_code=status.HTTP_201_CREATED)
def crear_politica(datos: PoliticaEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
                   bd: Session = Depends(obtener_bd)) -> PoliticaSalida:
    uid = ctx.usuario.usuario_id
    p = ConocimientoPolitica(tema=datos.tema, titulo=datos.titulo.strip(), contenido=datos.contenido.strip(),
                             departamento=_texto(datos.departamento), estado=datos.estado, version=1,
                             creado_por=uid, actualizado_por=uid)
    bd.add(p)
    bd.flush()
    _bitacora(bd, "conocimiento_politica_crear", ctx, request, "conocimiento_politica", p.politica_id,
              {"titulo": p.titulo, "estado": p.estado})
    bd.commit()
    return _politica(p, _nombres(bd, {uid}))


@router.put("/politicas/{politica_id}", response_model=PoliticaSalida)
def editar_politica(politica_id: int, datos: PoliticaEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
                    bd: Session = Depends(obtener_bd)) -> PoliticaSalida:
    p = bd.get(ConocimientoPolitica, politica_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa política.")
    if p.contenido != datos.contenido.strip() or p.titulo != datos.titulo.strip():
        p.version += 1
    p.tema, p.titulo, p.contenido = datos.tema, datos.titulo.strip(), datos.contenido.strip()
    p.departamento, p.estado, p.actualizado_por = _texto(datos.departamento), datos.estado, ctx.usuario.usuario_id
    # La bitácora guarda el texto de cada versión: así queda el histórico de cómo cambió la política
    _bitacora(bd, "conocimiento_politica_editar", ctx, request, "conocimiento_politica", politica_id,
              {"titulo": p.titulo, "estado": p.estado, "version": p.version, "contenido": p.contenido[:4000]})
    bd.commit()
    return _politica(p, _nombres(bd, {p.actualizado_por}))


@router.delete("/politicas/{politica_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_politica(politica_id: int, request: Request, ctx: Contexto = Depends(EDITAR),
                    bd: Session = Depends(obtener_bd)) -> None:
    p = bd.get(ConocimientoPolitica, politica_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa política.")
    _bitacora(bd, "conocimiento_politica_borrar", ctx, request, "conocimiento_politica", politica_id,
              {"titulo": p.titulo, "contenido": p.contenido[:4000]})
    bd.delete(p)
    bd.commit()


# ---------------------------------------------------------------- reglas (rechazo, umbral, éxito)

class ReglaEntrada(BaseModel):
    tipo: TipoRegla
    criterio: str = Field(min_length=2, max_length=200)
    departamento: str | None = Field(default=None, max_length=300)
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    unidad: str | None = Field(default=None, max_length=40)
    periodo_meses: int | None = Field(default=None, ge=1, le=60)
    descripcion: str | None = Field(default=None, max_length=1000)
    activa: bool = True

    @model_validator(mode="after")
    def _rango(self) -> "ReglaEntrada":
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError("El mínimo no puede ser mayor que el máximo.")
        return self


class ReglaSalida(ReglaEntrada):
    id: int
    actualizado_por: str | None
    actualizado_en: datetime


def _regla(r: ConocimientoRegla, nombres: dict[int, str]) -> ReglaSalida:
    return ReglaSalida(id=r.regla_id, tipo=r.tipo, criterio=r.criterio, departamento=r.departamento, minimo=r.minimo,
                       maximo=r.maximo, unidad=r.unidad, periodo_meses=r.periodo_meses, descripcion=r.descripcion,
                       activa=r.activa, actualizado_por=nombres.get(r.actualizado_por), actualizado_en=r.actualizado_en)


def _llenar_regla(r: ConocimientoRegla, datos: ReglaEntrada, uid: int) -> None:
    r.tipo, r.criterio, r.departamento = datos.tipo, datos.criterio.strip(), _texto(datos.departamento)
    # Rechazo directo es solo texto; el periodo solo aplica a la meta de un lanzamiento exitoso
    numerico = datos.tipo != "rechazo"
    r.minimo = datos.minimo if numerico else None
    r.maximo = datos.maximo if numerico else None
    r.unidad = _texto(datos.unidad) if numerico else None
    r.periodo_meses = datos.periodo_meses if datos.tipo == "exito" else None
    r.descripcion, r.activa, r.actualizado_por = _texto(datos.descripcion), datos.activa, uid


@router.get("/reglas", response_model=list[ReglaSalida])
def reglas(tipo: TipoRegla | None = None, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[ReglaSalida]:
    q = select(ConocimientoRegla).order_by(ConocimientoRegla.tipo, ConocimientoRegla.criterio)
    if tipo:
        q = q.where(ConocimientoRegla.tipo == tipo)
    filas = bd.scalars(q).all()
    nombres = _nombres(bd, {r.actualizado_por for r in filas})
    return [_regla(r, nombres) for r in filas]


@router.post("/reglas", response_model=ReglaSalida, status_code=status.HTTP_201_CREATED)
def crear_regla(datos: ReglaEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
                bd: Session = Depends(obtener_bd)) -> ReglaSalida:
    r = ConocimientoRegla()
    _llenar_regla(r, datos, ctx.usuario.usuario_id)
    bd.add(r)
    bd.flush()
    _bitacora(bd, "conocimiento_regla_crear", ctx, request, "conocimiento_regla", r.regla_id,
              {"tipo": r.tipo, "criterio": r.criterio})
    bd.commit()
    return _regla(r, _nombres(bd, {r.actualizado_por}))


@router.put("/reglas/{regla_id}", response_model=ReglaSalida)
def editar_regla(regla_id: int, datos: ReglaEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
                 bd: Session = Depends(obtener_bd)) -> ReglaSalida:
    r = bd.get(ConocimientoRegla, regla_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa regla.")
    _llenar_regla(r, datos, ctx.usuario.usuario_id)
    _bitacora(bd, "conocimiento_regla_editar", ctx, request, "conocimiento_regla", regla_id,
              datos.model_dump(mode="json"))
    bd.commit()
    return _regla(r, _nombres(bd, {r.actualizado_por}))


@router.delete("/reglas/{regla_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_regla(regla_id: int, request: Request, ctx: Contexto = Depends(EDITAR), bd: Session = Depends(obtener_bd)) -> None:
    r = bd.get(ConocimientoRegla, regla_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe esa regla.")
    _bitacora(bd, "conocimiento_regla_borrar", ctx, request, "conocimiento_regla", regla_id,
              {"tipo": r.tipo, "criterio": r.criterio})
    bd.delete(r)
    bd.commit()


# ---------------------------------------------------------------- pesos

class Peso(BaseModel):
    factor: str
    nombre: str
    que_mide: str
    puntos: int = Field(ge=0, le=100)
    nota: str | None = Field(default=None, max_length=600)


class Pesos(BaseModel):
    factores: list[Peso]
    total: int
    actualizado_por: str | None = None
    actualizado_en: datetime | None = None


class PesoEntrada(BaseModel):
    factor: str
    puntos: int = Field(ge=0, le=100)
    nota: str | None = Field(default=None, max_length=600)


def _pesos(bd: Session) -> Pesos:
    guardados = {p.factor: p for p in bd.scalars(select(ConocimientoPeso)).all()}
    factores = [Peso(factor=f, nombre=nombre, que_mide=que, puntos=guardados[f].puntos if f in guardados else 0,
                     nota=guardados[f].nota if f in guardados else None)
                for f, (nombre, que) in FACTORES.items()]
    ultimo = max(guardados.values(), key=lambda p: p.actualizado_en, default=None)
    return Pesos(factores=factores, total=sum(f.puntos for f in factores),
                 actualizado_por=_nombres(bd, {ultimo.actualizado_por}).get(ultimo.actualizado_por) if ultimo else None,
                 actualizado_en=ultimo.actualizado_en if ultimo else None)


@router.get("/pesos", response_model=Pesos)
def pesos(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Pesos:
    return _pesos(bd)


@router.put("/pesos", response_model=Pesos)
def guardar_pesos(datos: list[PesoEntrada], request: Request, ctx: Contexto = Depends(EDITAR),
                  bd: Session = Depends(obtener_bd)) -> Pesos:
    por_factor = {d.factor: d for d in datos}
    if set(por_factor) != set(FACTORES) or len(datos) != len(FACTORES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Hay que mandar los seis factores, una vez cada uno.")
    total = sum(d.puntos for d in datos)
    if total != 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Los puntos deben sumar 100; suman {total}.")
    for f, d in por_factor.items():
        p = bd.get(ConocimientoPeso, f) or ConocimientoPeso(factor=f)
        p.puntos, p.nota, p.actualizado_por = d.puntos, _texto(d.nota), ctx.usuario.usuario_id
        bd.add(p)
    _bitacora(bd, "conocimiento_pesos", ctx, request, "conocimiento_peso", None, {f: d.puntos for f, d in por_factor.items()})
    bd.commit()
    return _pesos(bd)


# ---------------------------------------------------------------- pesos de la calificación de proveedores (0027)

class PesosProveedor(BaseModel):
    bloques: list[Peso]
    total: int
    de: str  # compras / provisionales: cuáles usa hoy la calificación


def _pesos_proveedor(bd: Session) -> PesosProveedor:
    from datos import proveedores as pv

    guardados = {p.bloque: p for p in bd.scalars(select(ConocimientoPesoProveedor))}
    usados, de = pv.pesos(bd)
    bloques = [Peso(factor=b, nombre=nombre, que_mide=que, puntos=guardados[b].puntos if b in guardados else usados[b],
                    nota=guardados[b].nota if b in guardados else None)
               for b, (nombre, que) in pv.BLOQUES.items()]
    return PesosProveedor(bloques=bloques, total=sum(b.puntos for b in bloques), de=de)


@router.get("/pesos-proveedor", response_model=PesosProveedor)
def pesos_proveedor(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> PesosProveedor:
    return _pesos_proveedor(bd)


@router.put("/pesos-proveedor", response_model=PesosProveedor)
def guardar_pesos_proveedor(datos: list[PesoEntrada], request: Request, ctx: Contexto = Depends(EDITAR),
                            bd: Session = Depends(obtener_bd)) -> PesosProveedor:
    from datos import proveedores as pv

    por_bloque = {d.factor: d for d in datos}
    if set(por_bloque) != set(pv.BLOQUES) or len(datos) != len(pv.BLOQUES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Hay que mandar los cuatro bloques, una vez cada uno.")
    total = sum(d.puntos for d in datos)
    if total != 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Los puntos deben sumar 100; suman {total}.")
    for b, d in por_bloque.items():
        p = bd.get(ConocimientoPesoProveedor, b) or ConocimientoPesoProveedor(bloque=b)
        p.puntos, p.nota, p.actualizado_por = d.puntos, _texto(d.nota), ctx.usuario.usuario_id
        bd.add(p)
    _bitacora(bd, "conocimiento_pesos_proveedor", ctx, request, "conocimiento_peso_proveedor", None,
              {b: d.puntos for b, d in por_bloque.items()})
    bd.commit()
    return _pesos_proveedor(bd)


# ---------------------------------------------------------------- casos pasados

class CasoEntrada(BaseModel):
    producto: str = Field(min_length=2, max_length=300)
    sku: str | None = Field(default=None, max_length=60)
    proveedor: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=300)
    fecha_decision: date | None = None
    decision: Decision
    motivo: str | None = Field(default=None, max_length=1000)
    resultado: Resultado = "sin_dato"
    notas: str | None = Field(default=None, max_length=1000)


class CasoSalida(CasoEntrada):
    id: int
    actualizado_por: str | None
    actualizado_en: datetime


def _caso(c: ConocimientoCaso, nombres: dict[int, str]) -> CasoSalida:
    return CasoSalida(id=c.caso_id, producto=c.producto, sku=c.sku, proveedor=c.proveedor, departamento=c.departamento,
                      fecha_decision=c.fecha_decision, decision=c.decision, motivo=c.motivo, resultado=c.resultado,
                      notas=c.notas, actualizado_por=nombres.get(c.actualizado_por), actualizado_en=c.actualizado_en)


def _llenar_caso(c: ConocimientoCaso, d: CasoEntrada, uid: int) -> None:
    c.producto, c.sku, c.proveedor = d.producto.strip(), _texto(d.sku), _texto(d.proveedor)
    c.departamento, c.fecha_decision, c.decision = _texto(d.departamento), d.fecha_decision, d.decision
    c.motivo, c.resultado, c.notas, c.actualizado_por = _texto(d.motivo), d.resultado, _texto(d.notas), uid


@router.get("/casos", response_model=list[CasoSalida])
def casos(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[CasoSalida]:
    filas = bd.scalars(select(ConocimientoCaso).order_by(ConocimientoCaso.fecha_decision.desc(),
                                                         ConocimientoCaso.caso_id.desc())).all()
    nombres = _nombres(bd, {c.actualizado_por for c in filas})
    return [_caso(c, nombres) for c in filas]


@router.post("/casos", response_model=CasoSalida, status_code=status.HTTP_201_CREATED)
def crear_caso(datos: CasoEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
               bd: Session = Depends(obtener_bd)) -> CasoSalida:
    c = ConocimientoCaso(creado_por=ctx.usuario.usuario_id)
    _llenar_caso(c, datos, ctx.usuario.usuario_id)
    bd.add(c)
    bd.flush()
    _bitacora(bd, "conocimiento_caso_crear", ctx, request, "conocimiento_caso", c.caso_id,
              {"producto": c.producto, "decision": c.decision})
    bd.commit()
    return _caso(c, _nombres(bd, {c.actualizado_por}))


@router.put("/casos/{caso_id}", response_model=CasoSalida)
def editar_caso(caso_id: int, datos: CasoEntrada, request: Request, ctx: Contexto = Depends(EDITAR),
                bd: Session = Depends(obtener_bd)) -> CasoSalida:
    c = bd.get(ConocimientoCaso, caso_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese caso.")
    _llenar_caso(c, datos, ctx.usuario.usuario_id)
    _bitacora(bd, "conocimiento_caso_editar", ctx, request, "conocimiento_caso", caso_id, datos.model_dump(mode="json"))
    bd.commit()
    return _caso(c, _nombres(bd, {c.actualizado_por}))


@router.delete("/casos/{caso_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_caso(caso_id: int, request: Request, ctx: Contexto = Depends(EDITAR), bd: Session = Depends(obtener_bd)) -> None:
    c = bd.get(ConocimientoCaso, caso_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese caso.")
    _bitacora(bd, "conocimiento_caso_borrar", ctx, request, "conocimiento_caso", caso_id, {"producto": c.producto})
    bd.delete(c)
    bd.commit()
