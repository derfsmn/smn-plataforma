"""Rutas de la pantalla nueva del Radar de precios, «Está mal» y el reporte a Excel (/api/compras/precios/...).

Diego, 2026-11-17: Compras es usuario final; solo consulta y marca «Está mal». Cualquiera con permiso de ver el radar
puede marcarlo; deshacer una marca es de quien administra el radar.
"""
import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from datos.modelos import Producto
from modulos.compras import excel_precios as xl
from modulos.compras import nocturno_precios as noche
from modulos.compras import precios
from modulos.compras import reporte_precios as rep
from modulos.compras import tablero_precios as tb
from modulos.compras import validacion_precios as val
from modulos.compras.modelos_precios import (PrecioMarcaMal, PrecioObservacion, PrecioSeleccion, PrecioTiendaCoincidencia,
                                             PrecioValidacion, PrecioVigilado)
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario, ahora

router = APIRouter(prefix="/api/compras/precios", tags=["compras · radar de precios"])
VER = requiere(precios.VER)
ADMIN = requiere(precios.ADMINISTRAR)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- tablero

class FilaTablero(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    categoria: str | None
    imagen: str | None
    clase: str | None
    venta_importe: Decimal
    venta_piezas: Decimal
    nuestro: Decimal | None
    mercado: Decimal | None
    dif_pct: Decimal | None
    indice: Decimal | None
    color: str | None
    membresia: Decimal | None = None  # precio membresía con impuestos
    dif_membresia_pct: Decimal | None = None
    color_membresia: str | None = None
    limite_pct: Decimal
    tiendas: dict[str, Decimal]
    otras: int  # otras tiendas que cuentan
    accion: str
    accion_texto: str
    detalle: str
    precio_sugerido: Decimal | None
    margen: Decimal | None
    margen_minimo: Decimal
    tendencia: str | None
    tendencia_pct: Decimal | None
    validacion: str | None  # validado / dudoso / sin_referencia / None (nunca revisado)
    revisado_en: datetime | None
    agente: str | None = None  # comprador del proveedor (tblProveedores.Agente)
    venta_mes: Decimal = Decimal(0)
    en_juego: Decimal = Decimal(0)  # venta del mes × diferencia del precio lista contra el mercado
    aviso: str | None = None  # por qué no se compara


class AvanceNoche(BaseModel):
    total: int
    validados: int
    dudosos: int
    sin_referencia: int
    sin_revisar: int
    al_dia: int
    por_clase: dict[str, dict[str, int]]
    ritmo_noche: int
    noches_faltan: int | None
    activo: bool
    desde: int
    hasta: int
    lote: int
    texto: str


class Tienda(BaseModel):
    nombre: str
    productos: int
    mas_caros: int
    parejos: int
    mas_baratos: int
    frase: str


class Tablero(BaseModel):
    actualizado: datetime | None
    en_curso: bool
    avance: AvanceNoche
    alerta_pct: float
    cuadros: dict[str, int]  # rojo / amarillo / verde / sin_referencia
    acciones: dict[str, int]  # cuántos piden bajar, negociar, subir
    tiendas: list[Tienda]
    clases: list[str]
    agentes: list[str] = []
    comparados: int = 0  # productos con precio del mercado firme
    sin_comparar: dict[str, int] = {}  # por qué no se comparan (para «Cómo va el radar»)
    catalogo: int = 0  # productos del radar con resultado
    total: int
    pagina: int
    por_pagina: int
    filas: list[FilaTablero]


def _texto_avance(a: noche.Avance) -> str:
    if not a.total:
        return "Todavía no hay productos en el radar"
    partes = []
    pendientes = [k for k, d in a.por_clase.items() if d["validados"] < d["total"]]
    completas = [k for k, d in a.por_clase.items() if d["total"] and d["validados"] == d["total"]]
    if completas:
        partes.append(" y ".join(completas[:3]) + (" completos" if len(completas) > 1 else " completos"))
    if pendientes:
        partes.append(f"siguen los {pendientes[0]}")
    if a.noches_faltan:
        partes.append(f"faltan unas {a.noches_faltan} noches al ritmo de anoche ({a.ritmo_noche} productos)")
    elif a.noches_faltan == 0 and a.total:
        partes.append("todos revisados; sigue la rotación")
    return " · ".join(partes)


def _fila(r: tb.Renglon) -> FilaTablero:
    p, e = r.producto, r.evaluacion
    return FilaTablero(
        producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, categoria=p.subcategoria,
        imagen=p.liga_imagen, clase=e.clase, venta_importe=e.venta_importe, venta_piezas=e.venta_piezas, nuestro=r.base,
        mercado=r.mediana if r.color else None, dif_pct=r.dif, indice=e.indice, color=r.color,
        membresia=r.membresia, dif_membresia_pct=r.dif_membresia, color_membresia=r.color_membresia,
        limite_pct=r.limite, tiendas={t: v[0] for t, v in r.tiendas.items()}, otras=len(r.otras), accion=e.accion,
        accion_texto=e.accion_texto, detalle=e.detalle, precio_sugerido=e.precio_sugerido, margen=e.margen,
        margen_minimo=e.margen_minimo, tendencia=e.tendencia, tendencia_pct=e.tendencia_pct,
        validacion=r.vigilado.validacion if r.vigilado else None, revisado_en=r.vigilado.revisado_en if r.vigilado else None,
        agente=r.agente, venta_mes=r.venta_mes, en_juego=r.en_juego, aviso=r.aviso)


Grupo = Literal["accion", "rojo", "amarillo", "verde", "sin_referencia", "subir", "todos"]
PIDE_ACCION = ("bajar", "bajar_y_negociar", "negociar", "subir")


def _por_que_no(r: tb.Renglon) -> str:
    a = (r.aviso or "").lower()
    if a.startswith("solo un precio"):
        return "Un solo precio confirmado; falta una segunda tienda"
    if "no coinciden" in a or "muy distintos" in a:
        return "Los precios encontrados no coinciden entre sí"
    if "mercados en línea" in a:
        return "Solo hay precios de mercados en línea"
    estado = r.fila.estado if r.fila else None
    if estado == "sin_coincidencia":
        return "No se encontró el mismo producto en internet"
    if estado in ("sin_precios", "con_precios"):
        return "Sin precios validados"
    if estado == "sin_presupuesto":
        return "Se acabó el presupuesto de búsquedas antes de revisarlo"
    return "No se pudo revisar (falla de la búsqueda)"


def _filtrar(todos: list, grupo: str, clase: str, q: str, marca: str, agente: str, orden: str, precio: str):
    """(renglones del agente elegido, los que cumplen los filtros, ya ordenados). Lo usan la pantalla y su Excel."""
    sin_agente = agente == "sin_agente"
    rs = [r for r in todos if not agente or (sin_agente and not r.agente) or r.agente == agente]
    texto = q.strip().lower()
    if texto:
        grupo = "todos"  # el buscador encuentra cualquier producto, pida acción o no
    elegidas = [r for r in rs
                if (grupo == "todos" or (grupo == "accion" and r.evaluacion.accion in PIDE_ACCION)
                    or (grupo == "subir" and r.evaluacion.accion == "subir") or r.cuadro_de(precio) == grupo)
                and (not clase or r.evaluacion.clase == clase.upper()) and (not marca or r.producto.marca == marca)
                and (not texto or any(texto in (v or "").lower() for v in (r.producto.sku, r.producto.descripcion,
                                                                            r.producto.marca, r.producto.codigo_barras)))]
    if orden == "venta":
        elegidas.sort(key=lambda r: (-r.evaluacion.venta_importe, r.producto.descripcion or ""))
    else:
        elegidas.sort(key=lambda r: (-r.en_juego, -r.evaluacion.venta_importe, r.producto.descripcion or ""))
    return rs, elegidas


Orden = Literal["en_juego", "venta"]


@router.get("/tablero", response_model=Tablero)
def tablero(grupo: Grupo = "accion", clase: str = "", q: str = "", marca: str = "", agente: str = "", pagina: int = 1,
            por_pagina: int = 20, orden: Orden = "en_juego", precio: Literal["lista", "membresia"] = "lista",
            _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Tablero:
    """Precios contra el mercado (Diego, 2026-11-25): de inicio los 20 con más dinero en juego al mes; filtros por agente,
    clase y marca; con el buscador, cualquier producto del radar. Los botones cuentan sobre el agente elegido."""
    pagina, por_pagina = max(1, pagina), min(max(1, por_pagina), 200)
    a = noche.avance(bd)
    todos = tb.renglones_vigentes(bd)
    rs, elegidas = _filtrar(todos, grupo, clase, q, marca, agente, orden, precio)
    cuadros = {k: sum(1 for r in rs if r.cuadro_de(precio) == k) for k in ("rojo", "amarillo", "verde", "sin_referencia")}
    acciones = {k: sum(1 for r in rs if r.evaluacion.accion == k) for k in ("bajar", "bajar_y_negociar", "negociar", "subir")}
    clases = sorted({r.evaluacion.clase for r in todos if r.evaluacion.clase},
                    key=lambda c: noche.CLASES.index(c) if c in noche.CLASES else 99)
    inicio = (pagina - 1) * por_pagina
    return Tablero(actualizado=tb.actualizado(bd), en_curso=precios.en_curso(bd) is not None,
                   avance=AvanceNoche(**a.__dict__, texto=_texto_avance(a)), alerta_pct=configuracion().precios_alerta_pct,
                   cuadros=cuadros, acciones=acciones, tiendas=[Tienda(**t) for t in tb.contra_tiendas(rs, precio)], clases=clases,
                   agentes=sorted({r.agente for r in todos if r.agente}), comparados=sum(1 for r in rs if r.color),
                   sin_comparar=dict(Counter(_por_que_no(r) for r in rs if not r.color).most_common()),
                   catalogo=len(rs), total=len(elegidas), pagina=pagina, por_pagina=por_pagina,
                   filas=[_fila(r) for r in elegidas[inicio:inicio + por_pagina]])


@router.get("/tablero/producto/{producto_id}", response_model=FilaTablero)
def tablero_producto(producto_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> FilaTablero:
    """El renglón de un producto para el panel de detalle (aunque no tenga resultado todavía)."""
    r = next((x for x in tb.renglones_vigentes(bd) if x.producto.producto_id == producto_id), None)
    if r is None:
        p = bd.get(Producto, producto_id)
        if not p:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no existe en el catálogo.")
        r = tb.renglones(bd, [p])[0]
    return _fila(r)


@router.get("/tablero/excel")
def tablero_excel(request: Request, grupo: Grupo = "accion", clase: str = "", q: str = "", marca: str = "", agente: str = "",
                  orden: Orden = "en_juego", ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    """«Descargar Excel»: todo lo que cumple los filtros de la pantalla (no solo la página que se ve)."""
    _, elegidas = _filtrar(tb.renglones_vigentes(bd), grupo, clase, q, marca, agente, orden, "lista")
    if not elegidas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No hay productos con estos filtros.")
    hoy = precios.hoy_local()
    titulo = f"Agente {agente}" if agente and agente != "sin_agente" else "Precios contra el mercado"
    contenido = rep.armar(bd, elegidas, list(rep.POR_OMISION), hoy, titulo)
    registrar(bd, "precios_excel_pantalla", usuario_id=ctx.usuario.usuario_id, ip=ip_de(request),
              detalle={"productos": len(elegidas), "grupo": grupo, "agente": agente or None})
    bd.commit()
    nombre = f"Radar_de_precios_{_nombre(titulo)}_{hoy:%Y-%m-%d}.xlsx"
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ---------------------------------------------------------------- precios de un producto con su validación

class Comprobacion(BaseModel):
    clave: str
    nombre: str
    estado: str  # ok / no / sin_dato / no_aplica
    texto: str


class PrecioValidado(BaseModel):
    observacion_id: int
    vendedor: str
    tienda_clave: str | None
    titulo: str | None
    liga: str | None
    precio: Decimal
    cuenta: bool
    resultado: str | None  # validado / dudoso / no_cuenta / None (de antes de la validación)
    motivo: str | None
    comprobaciones: list[Comprobacion]
    vendedor_tipo: str | None  # oficial / marketplace / tienda
    promocion: bool
    marcado_mal: bool


class MarcaMal(BaseModel):
    id: int
    vendedor: str
    titulo: str | None
    liga: str | None
    precio: Decimal | None
    motivo: str
    motivo_texto: str
    nota: str | None
    usuario: str | None
    creado_en: datetime
    activo: bool


class ValidacionProducto(BaseModel):
    producto_id: int
    validacion: str | None
    validado_en: datetime | None
    revisado_en: datetime | None
    proxima_revision: datetime | None
    precios: list[PrecioValidado]
    marcas: list[MarcaMal]


def _marca(bd: Session, m: PrecioMarcaMal) -> MarcaMal:
    u = bd.get(Usuario, m.usuario_id) if m.usuario_id else None
    return MarcaMal(id=m.marca_id, vendedor=m.vendedor, titulo=m.titulo, liga=m.liga, precio=m.precio, motivo=m.motivo,
                    motivo_texto=val.MOTIVOS_MAL.get(m.motivo, m.motivo), nota=m.nota, usuario=u.nombre if u else None,
                    creado_en=m.creado_en, activo=m.activo)


@router.get("/productos/{producto_id}/validacion", response_model=ValidacionProducto)
def validacion(producto_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> ValidacionProducto:
    p = bd.get(Producto, producto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no existe en el catálogo.")
    filas = tb.ultimas_filas(bd, producto_ids=[producto_id])
    obs = tb.precios_que_cuentan(bd, filas, {producto_id: p}).get(producto_id, [])
    f = filas.get(producto_id, (None, None))[0]
    base = precios.nuestro(f)[0] if f else None
    malas = val.marcas_mal(bd, producto_id)
    cache: dict = {}
    salida = []
    # Mismas reglas que la pantalla: una tienda cuenta una vez y lo que se sale de los demás se aparta
    pasan = [o for o, v in obs if not tb.no_cuenta(o, v, p.descripcion, base)]
    unicos = tb.una_por_tienda(pasan)
    _, apartados, _ = tb.mercado_confiable(unicos)
    por_apartar = {id(o): m for o, m in apartados}
    ids_unicos = {id(o) for o in unicos}
    for o, v in sorted(obs, key=lambda x: x[0].precio_comparable):
        if o.es_propia:
            continue
        ident = val.identidad(bd, o, cache)
        comp = json.loads(v.comprobaciones or "{}") if v else {}
        sello = json.loads(v.sello or "{}") if v else {}
        motivo = tb.no_cuenta(o, v, p.descripcion, base)
        if motivo is None and id(o) not in ids_unicos:
            motivo = "Ya cuenta el precio más bajo de esta misma tienda"
        elif motivo is None and id(o) in por_apartar:
            motivo = por_apartar[id(o)]
        salida.append(PrecioValidado(
            observacion_id=o.observacion_id, vendedor=o.vendedor, tienda_clave=precios.tienda_clave(o.vendedor, o.dominio),
            titulo=ident.titulo, liga=o.liga, precio=o.precio_comparable, cuenta=motivo is None,
            resultado=v.resultado if v else None, motivo=motivo,
            comprobaciones=[Comprobacion(clave=k, nombre=val.NOMBRES[k], estado=comp[k]["estado"], texto=comp[k]["texto"])
                            for k in val.COMPROBACIONES if isinstance(comp.get(k), dict)],
            vendedor_tipo=sello.get("vendedor"), promocion=bool(sello.get("promocion")),
            marcado_mal=val.es_mal(o, ident.titulo, malas) is not None))
    vig = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == producto_id))
    todas = bd.scalars(select(PrecioMarcaMal).where(PrecioMarcaMal.producto_id == producto_id)
                       .order_by(PrecioMarcaMal.marca_id.desc())).all()
    return ValidacionProducto(producto_id=producto_id, validacion=vig.validacion if vig else None,
                              validado_en=vig.validado_en if vig else None, revisado_en=vig.revisado_en if vig else None,
                              proxima_revision=vig.proxima_revision if vig else None, precios=salida,
                              marcas=[_marca(bd, m) for m in todas])


Motivo = Literal["otro_sabor", "otro_tamano", "otro_producto", "precio_equivocado", "otro"]


class EstaMal(BaseModel):
    observacion_ids: list[int] = Field(min_length=1, max_length=50)
    motivo: Motivo
    nota: str | None = Field(default=None, max_length=400)


@router.post("/productos/{producto_id}/esta-mal", response_model=ValidacionProducto)
def esta_mal(producto_id: int, datos: EstaMal, request: Request, ctx: Contexto = Depends(VER),
             bd: Session = Depends(obtener_bd)) -> ValidacionProducto:
    """Compras marca uno o varios precios: dejan de contar al momento y nunca se vuelven a elegir."""
    if datos.motivo == "otro" and not (datos.nota or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escribe qué está mal.")
    obs = bd.scalars(select(PrecioObservacion).where(PrecioObservacion.observacion_id.in_(datos.observacion_ids),
                                                     PrecioObservacion.producto_id == producto_id)).all()
    if not obs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esos precios no son de este producto.")
    cache: dict = {}
    for o in obs:
        ident = val.identidad(bd, o, cache)
        bd.add(PrecioMarcaMal(producto_id=producto_id, observacion_id=o.observacion_id, vendedor=o.vendedor, dominio=o.dominio,
                              liga=o.liga, titulo=(ident.titulo or "")[:400] or None, precio=o.precio_comparable,
                              motivo=datos.motivo, nota=(datos.nota or "").strip() or None, usuario_id=ctx.usuario.usuario_id))
        # Si salió del sitio de una tienda, esa coincidencia no se vuelve a elegir (la tienda se busca de nuevo)
        if datos.motivo != "precio_equivocado" and o.tienda_coincidencia_id:
            t = bd.get(PrecioTiendaCoincidencia, o.tienda_coincidencia_id)
            if t and t.estado != "rechazada":
                t.estado, t.decidido_por = "rechazada", ctx.usuario.usuario_id
                t.motivo = f"Compras: {val.MOTIVOS_MAL[datos.motivo]}"[:600]
        if (v := bd.get(PrecioValidacion, o.observacion_id)):
            v.resultado, v.motivo = val.NO_CUENTA, f"Compras lo marcó: {val.MOTIVOS_MAL[datos.motivo]}"[:400]
    registrar(bd, "precios_esta_mal", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              detalle={"observaciones": [o.observacion_id for o in obs], "motivo": datos.motivo, "nota": datos.nota},
              ip=ip_de(request))
    bd.commit()
    _recalcular(bd, producto_id)
    tb.olvidar()
    return validacion(producto_id, None, bd)


def _recalcular(bd: Session, producto_id: int) -> None:
    """Saca otra vez la mediana con lo que sigue contando, en el último renglón del producto (aunque sea de un lote)."""
    filas = tb.ultimas_filas(bd, producto_ids=[producto_id])
    if producto_id not in filas:
        return
    f, _ = filas[producto_id]
    obs = list(bd.scalars(select(PrecioObservacion).where(PrecioObservacion.corrida_id == f.corrida_id,
                                                          PrecioObservacion.producto_id == producto_id,
                                                          precios.del_renglon(f.coincidencia_id))))
    p = bd.get(Producto, producto_id)
    f.minimo = f.maximo = f.promedio = f.mediana = None
    f.dif_lista_mediana_pct = f.dif_membresia_mediana_pct = f.dif_lista_minimo_pct = None
    precios.Corrida.calcular(f, precios.sin_repetir(val.cuentan(bd, obs)), p.descripcion if p else None)
    bd.commit()


@router.delete("/productos/{producto_id}/esta-mal/{marca_id}", response_model=ValidacionProducto)
def deshacer(producto_id: int, marca_id: int, request: Request, ctx: Contexto = Depends(ADMIN),
             bd: Session = Depends(obtener_bd)) -> ValidacionProducto:
    """Se marcó por error: vuelve a contar desde la siguiente revisión (la marca queda en el historial)."""
    m = bd.get(PrecioMarcaMal, marca_id)
    if not m or m.producto_id != producto_id or not m.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa marca no existe.")
    m.activo = False
    registrar(bd, "precios_esta_mal_deshacer", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              detalle={"marca_id": marca_id}, ip=ip_de(request))
    bd.commit()
    tb.olvidar()
    return validacion(producto_id, None, bd)


@router.get("/casos-de-prueba")
def casos_de_prueba(_: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> list[dict]:
    """Lo que Compras marcó: sirve para medir la validación y para probar cambios de reglas."""
    filas = bd.execute(select(PrecioMarcaMal, Producto).join(Producto, Producto.producto_id == PrecioMarcaMal.producto_id)
                       .order_by(PrecioMarcaMal.marca_id.desc()).limit(500)).all()
    return [{"producto_id": p.producto_id, "sku": p.sku, "descripcion": p.descripcion, "codigo_barras": p.codigo_barras,
             "vendedor": m.vendedor, "titulo": m.titulo, "liga": m.liga, "precio": str(m.precio) if m.precio else None,
             "motivo": m.motivo, "nota": m.nota, "activo": m.activo, "creado_en": m.creado_en.isoformat()} for m, p in filas]


# ---------------------------------------------------------------- reporte a Excel

class Opcion(BaseModel):
    clave: str  # producto_id, marca o categoría
    nombre: str
    detalle: str | None
    cuenta: str


@router.get("/reporte/opciones", response_model=list[Opcion])
def opciones(modo: Literal["producto", "marca", "categoria", "clasificacion"] = "producto", q: str = "",
             _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[Opcion]:
    texto = q.strip()
    if modo == "clasificacion":  # AA a E (Diego, 2026-11-26), con cuántos productos activos tiene cada una
        cuenta: dict[str, int] = {}
        for k, n in bd.execute(select(Producto.clasificacion, func.count()).where(Producto.activo == true())
                               .group_by(Producto.clasificacion)):
            k = (k or "").strip().upper()
            cuenta[k] = cuenta.get(k, 0) + n
        sin = sum(n for k, n in cuenta.items() if k not in tb.CLASES)
        return [Opcion(clave=k, nombre=f"Clase {k}" if k != tb.SIN_CLASE else k, detalle=None,
                       cuenta=f"{n:,} productos") for k, n in [(k, cuenta.get(k, 0)) for k in tb.CLASES] + [(tb.SIN_CLASE, sin)] if n]
    if modo == "producto":
        consulta = select(Producto).where(Producto.activo == true())
        if texto:
            like = f"%{texto}%"
            consulta = consulta.where(or_(Producto.sku == texto, Producto.codigo_barras == texto,
                                          Producto.descripcion.ilike(like), Producto.marca.ilike(like)))
        ps = bd.scalars(consulta.order_by(Producto.descripcion).limit(40)).all()
        return [Opcion(clave=str(p.producto_id), nombre=p.descripcion or p.sku,
                       detalle=" · ".join(x for x in (f"SKU {p.sku}", p.marca, (p.clasificacion or "").strip() or None) if x),
                       cuenta=f"${p.precio_lista_con_impuestos:,.2f}" if p.precio_lista_con_impuestos else "")
                for p in ps]
    columna = Producto.marca if modo == "marca" else Producto.subcategoria
    consulta = (select(columna, func.count(), func.max(Producto.departamento)).where(Producto.activo == true(),
                                                                                    columna.is_not(None))
                .group_by(columna))
    if texto:
        consulta = consulta.where(columna.ilike(f"%{texto}%"))
    filas = bd.execute(consulta.order_by(func.count().desc()).limit(60)).all()
    if modo == "categoria":
        return [Opcion(clave=n, nombre=n, detalle=d, cuenta=f"{c:,} productos") for n, c, d in filas]
    # Por marca: cómo va cada una (de la última revisión de sus productos)
    colores: dict[str, dict[str, int]] = {}
    nombres = [n for n, _, _ in filas]
    if nombres:
        ps = list(bd.scalars(select(Producto).where(Producto.marca.in_(nombres), Producto.activo == true())))
        ultimas = tb.ultimas_filas(bd, producto_ids=[p.producto_id for p in ps])
        limites = precios.limites_por_producto(bd)
        for p in ps:
            f = ultimas.get(p.producto_id, (None, None))[0]
            c = precios.color(precios.dif_nuestro(f), limites.get(p.producto_id)) if f and f.estado == "con_precios" else None
            d = colores.setdefault(p.marca, {"rojo": 0, "amarillo": 0, "verde": 0, "sin": 0})
            d[c or "sin"] += 1
    salida = []
    for n, c, _ in filas:
        d = colores.get(n, {})
        partes = [f"{d['rojo']} más caros" if d.get("rojo") else None, f"{d['verde'] + d.get('amarillo', 0)} parejos o abajo"
                  if d.get("verde") or d.get("amarillo") else None, f"{d['sin']} sin referencia" if d.get("sin") else None]
        salida.append(Opcion(clave=n, nombre=n, detalle=" · ".join(x for x in partes if x) or None, cuenta=f"{c:,} productos"))
    return salida


class Seleccion(BaseModel):
    producto_ids: list[int] = Field(default=[], max_length=5000)
    marcas: list[str] = Field(default=[], max_length=500)
    categorias: list[str] = Field(default=[], max_length=500)
    clasificaciones: list[str] = Field(default=[], max_length=10)  # AA, A, B, C, D, E o «Sin clase»
    hojas: list[Literal["resumen", "tiendas", "accion", "historial"]] = list(rep.POR_OMISION)
    fecha: date | None = None  # vacío = la última actualización


class Conteo(BaseModel):
    productos: int


class ListaSkus(BaseModel):
    """Lo que se encontró de una lista de SKU subida en Excel o pegada."""
    skus: int
    encontrados: list[Opcion]
    no_encontrados: list[str]


MAX_SKUS_REPORTE = 5000


async def leer_lista(archivo: UploadFile | None, texto: str | None, maximo: int) -> list[str]:
    try:
        if archivo is not None and archivo.filename:
            nombre = archivo.filename[:200]
            if not nombre.lower().endswith((".xlsx", ".csv")):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube un Excel (.xlsx) o un CSV.")
            contenido = await archivo.read(5 * 1024 * 1024 + 1)
            if len(contenido) > 5 * 1024 * 1024:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo pasa de 5 MB.")
            return xl.leer_skus(nombre, contenido, maximo)
        return xl.skus_de_texto(texto or "", maximo)
    except xl.ErrorArchivo as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


def opcion_de(p: Producto) -> Opcion:
    return Opcion(clave=str(p.producto_id), nombre=p.descripcion or p.sku,
                  detalle=" · ".join(x for x in (f"SKU {p.sku}", p.marca, (p.clasificacion or "").strip() or None) if x),
                  cuenta=f"${p.precio_lista_con_impuestos:,.2f}" if p.precio_lista_con_impuestos else "")


@router.post("/reporte/skus", response_model=ListaSkus)
async def lista_skus(archivo: UploadFile | None = File(None), texto: str | None = Form(None),
                     _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> ListaSkus:
    """SKU (o códigos de barras) de un Excel o pegados: cuáles están en el catálogo. La pantalla los suma como sueltos."""
    skus = await leer_lista(archivo, texto, MAX_SKUS_REPORTE)
    productos, faltan = xl.buscar(bd, skus)
    return ListaSkus(skus=len(skus), encontrados=[opcion_de(p) for p in productos], no_encontrados=faltan)


@router.post("/reporte/contar", response_model=Conteo)
def contar(datos: Seleccion, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Conteo:
    return Conteo(productos=len(tb.de_seleccion(bd, datos.producto_ids, datos.marcas, datos.categorias, datos.clasificaciones)))


def _nombre(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _-]+", "", texto).strip().replace(" ", "_")[:60] or "reporte"


def _excel(bd: Session, datos: Seleccion, titulo: str) -> Response:
    ps = tb.de_seleccion(bd, datos.producto_ids, datos.marcas, datos.categorias, datos.clasificaciones)
    if not ps:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige al menos un producto, una marca o una categoría.")
    if not datos.hojas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige qué lleva el Excel.")
    hasta = datos.fecha or precios.hoy_local()
    if datos.fecha:
        rs = tb.renglones(bd, ps, datos.fecha)
    else:  # precios de la última actualización: lo ya calculado para la pantalla
        ids = {p.producto_id for p in ps}
        calculados = {r.producto.producto_id: r for r in tb.renglones_vigentes(bd) if r.producto.producto_id in ids}
        faltan = [p for p in ps if p.producto_id not in calculados]
        rs = [calculados[p.producto_id] for p in ps if p.producto_id in calculados] + (tb.renglones(bd, faltan) if faltan else [])
    contenido = rep.armar(bd, rs, list(datos.hojas), hasta, titulo)
    nombre = f"Radar_de_precios_{_nombre(titulo)}_{hasta:%Y-%m-%d}.xlsx"
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _titulo(datos: Seleccion) -> str:
    partes = []
    if datos.marcas:
        partes.append("Marcas: " + ", ".join(datos.marcas[:3]) + ("…" if len(datos.marcas) > 3 else ""))
    if datos.categorias:
        partes.append("Categorías: " + ", ".join(datos.categorias[:3]) + ("…" if len(datos.categorias) > 3 else ""))
    if datos.clasificaciones:
        partes.append("Clase " + ", ".join(datos.clasificaciones))
    if datos.producto_ids:
        partes.append(f"{len(datos.producto_ids)} productos sueltos")
    return " · ".join(partes) or "Selección"


def titulo_de(datos: "Seleccion") -> str:
    return _titulo(datos)


@router.post("/reporte/excel")
def reporte_excel(datos: Seleccion, request: Request, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    registrar(bd, "precios_reporte", usuario_id=ctx.usuario.usuario_id, entidad="reporte",
              detalle={"productos": len(datos.producto_ids), "marcas": datos.marcas[:20], "categorias": datos.categorias[:20],
                       "clasificaciones": datos.clasificaciones,
                       "hojas": list(datos.hojas)}, ip=ip_de(request))
    bd.commit()
    return _excel(bd, datos, _titulo(datos))


class SeleccionGuardada(BaseModel):
    id: int
    nombre: str
    seleccion: Seleccion
    productos: int
    creado_en: datetime
    usado_en: datetime | None


class Guardar(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    seleccion: Seleccion


def _guardada(bd: Session, s: PrecioSeleccion) -> SeleccionGuardada:
    sel = Seleccion(**{k: v for k, v in tb.contenido(s.contenido).items() if k != "fecha"})
    return SeleccionGuardada(id=s.seleccion_id, nombre=s.nombre, seleccion=sel,
                             productos=len(tb.de_seleccion(bd, sel.producto_ids, sel.marcas, sel.categorias, sel.clasificaciones)),
                             creado_en=s.creado_en, usado_en=s.usado_en)


@router.get("/selecciones", response_model=list[SeleccionGuardada])
def selecciones(ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[SeleccionGuardada]:
    """Las selecciones de cada persona."""
    return [_guardada(bd, s) for s in bd.scalars(select(PrecioSeleccion).where(PrecioSeleccion.usuario_id == ctx.usuario.usuario_id)
                                                 .order_by(PrecioSeleccion.seleccion_id.desc()))]


@router.post("/selecciones", response_model=SeleccionGuardada)
def guardar(datos: Guardar, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> SeleccionGuardada:
    sel = datos.seleccion.model_dump(exclude={"fecha"})
    if not (sel["producto_ids"] or sel["marcas"] or sel["categorias"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La selección está vacía.")
    s = PrecioSeleccion(nombre=datos.nombre.strip(), contenido=json.dumps(sel, ensure_ascii=False),
                        usuario_id=ctx.usuario.usuario_id)
    bd.add(s)
    bd.commit()
    return _guardada(bd, s)


def _propia(bd: Session, seleccion_id: int, ctx: Contexto) -> PrecioSeleccion:
    s = bd.get(PrecioSeleccion, seleccion_id)
    if not s or s.usuario_id != ctx.usuario.usuario_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa selección no existe.")
    return s


@router.delete("/selecciones/{seleccion_id}")
def borrar(seleccion_id: int, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> dict:
    bd.delete(_propia(bd, seleccion_id, ctx))
    bd.commit()
    return {"ok": True}


@router.get("/selecciones/{seleccion_id}/excel")
def seleccion_excel(seleccion_id: int, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    """Un clic: la selección guardada con los precios del día."""
    s = _propia(bd, seleccion_id, ctx)
    s.usado_en = ahora()
    bd.commit()
    return _excel(bd, Seleccion(**{k: v for k, v in tb.contenido(s.contenido).items() if k != "fecha"}), s.nombre)
