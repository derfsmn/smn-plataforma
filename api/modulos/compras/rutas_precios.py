"""Rutas del Radar de precios (/api/compras/precios)."""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from datos.modelos import Producto
from modulos.compras import dataforseo as dfs
from modulos.compras import excel_precios as xl
from modulos.compras import precios
from modulos.compras.modelos_precios import (VIGENTES, PrecioCoincidencia, PrecioCorrida, PrecioCorridaProducto,
                                             PrecioEnvio, PrecioObservacion, PrecioTiendaCoincidencia, PrecioVigilado)
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario

router = APIRouter(prefix="/api/compras/precios", tags=["compras · radar de precios"])
VER = requiere(precios.VER)
ADMIN = requiere(precios.ADMINISTRAR)


# ---------------------------------------------------------------- esquemas

class Corrida(BaseModel):
    id: int
    fecha: date
    origen: str
    estado: str
    intentos: int
    usuario: str | None
    productos: int
    con_coincidencia: int
    sin_coincidencia: int
    con_precios: int
    fallidos: int
    alertas: int
    tope_usd: Decimal | None
    costo_usd: Decimal
    avisos: list[str]
    error: str | None
    iniciado_en: datetime
    terminado_en: datetime | None
    fase: str | None = None  # qué hace en este momento, mientras corre
    avance: dict | None = None  # paso (1 a 4), titulo, texto, hechos y total: en qué va la corrida
    archivo: str | None = None  # prueba con Excel: nombre del archivo
    no_encontrados: list[str] = []  # prueba con Excel: SKU que no estaban en el catálogo


def _corrida(bd: Session, c: PrecioCorrida) -> Corrida:
    u = bd.get(Usuario, c.iniciado_por) if c.iniciado_por else None
    return Corrida(id=c.corrida_id, fecha=c.fecha, origen=c.origen, estado=c.estado, intentos=c.intentos,
                   usuario=u.nombre if u else None, productos=c.productos, con_coincidencia=c.con_coincidencia,
                   sin_coincidencia=c.sin_coincidencia, con_precios=c.con_precios, fallidos=c.fallidos, alertas=c.alertas,
                   tope_usd=c.tope_usd, costo_usd=c.costo_usd or Decimal("0"), avisos=json.loads(c.avisos) if c.avisos else [],
                   error=c.error, iniciado_en=c.iniciado_en, terminado_en=c.terminado_en,
                   fase=precios.FASE.get(c.corrida_id) if c.estado == "en_curso" else None,
                   avance=precios.AVANCE.get(c.corrida_id) if c.estado == "en_curso" else None,
                   archivo=xl.datos_lista(c.lista).get("archivo"), no_encontrados=xl.datos_lista(c.lista).get("no_encontrados", []))


class Fila(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    departamento: str | None
    imagen: str | None
    estado: str
    mensaje: str | None
    precio_lista: Decimal | None
    precio_membresia: Decimal | None
    precio_tienda: Decimal | None
    vendedores: int
    minimo: Decimal | None
    mediana: Decimal | None
    maximo: Decimal | None
    dif_lista_mediana_pct: Decimal | None  # nuestro precio (lista o, si falta, tienda en línea) contra la mediana
    base: str | None = None  # lista / tienda: qué precio nuestro se comparó
    dif_membresia_mediana_pct: Decimal | None
    dif_lista_minimo_pct: Decimal | None
    coincidencia: str | None  # automatica / ia / persona
    limite_pct: Decimal  # semáforo: el del producto o el general
    color: str | None  # verde / amarillo / rojo
    tiendas: dict[str, Decimal] = {}  # precio de cada tienda clave que apareció (Walmart, Chedraui...), el más bajo


class Resumen(BaseModel):
    falta_configurar: list[str]
    automatico: bool
    frecuencia: str
    hora: int
    proxima: datetime | None
    gasto_mes_usd: Decimal
    tope_mes_usd: Decimal
    tope_corrida_usd: Decimal
    estimado_usd: Decimal
    alerta_pct: float
    vigilados: int
    con_coincidencia: int
    en_curso: Corrida | None
    ultima: Corrida | None
    ultima_prueba: Corrida | None = None  # la última prueba con Excel


GRUPOS = ("todos", "verde", "amarillo", "rojo", "revisar", "sin_precios")
Grupo = Literal["todos", "verde", "amarillo", "rojo", "revisar", "sin_precios"]
Orden = Literal["diferencia", "nombre", "vendedores"]


class Lista(BaseModel):
    """Una página de productos de la última corrida (la pantalla principal del radar; con 4,000 productos no se mandan todos)."""
    corrida: Corrida | None
    conteos: dict[str, int]  # por grupo, con la búsqueda y la marca aplicadas
    marcas: list[str]
    total: int  # del grupo elegido
    tiendas: list[str] = []  # tiendas clave
    cobertura: dict[str, int] = {}  # en cuántos productos (con la búsqueda y la marca aplicadas) apareció cada una
    pagina: int
    por_pagina: int
    filas: list[Fila]


# ---------------------------------------------------------------- resumen

def _tiendas(bd: Session, corrida_id: int) -> dict[int, dict[str, Decimal]]:
    """{producto: {tienda clave: precio más bajo que cuenta}} de la corrida, solo de la coincidencia de cada renglón."""
    claves = precios.tiendas_clave()
    if not claves:
        return {}
    consulta = (select(PrecioObservacion, PrecioCorridaProducto, Producto.descripcion).select_from(PrecioObservacion)
                .join(PrecioCorridaProducto, (PrecioCorridaProducto.corrida_id == PrecioObservacion.corrida_id)
                      & (PrecioCorridaProducto.producto_id == PrecioObservacion.producto_id)
                      & precios.del_renglon(PrecioCorridaProducto.coincidencia_id))
                .join(Producto, Producto.producto_id == PrecioObservacion.producto_id)
                .where(PrecioObservacion.corrida_id == corrida_id))
    res: dict[int, dict[str, Decimal]] = {}
    for o, f, descripcion in bd.execute(consulta).all():
        t = precios.tienda_clave(o.vendedor, o.dominio, claves)
        if t and not _no_cuenta(o, descripcion, precios.nuestro(f)[0]):
            actual = res.setdefault(o.producto_id, {}).get(t)
            if actual is None or o.precio_comparable < actual:
                res[o.producto_id][t] = o.precio_comparable
    return res


def _filas(bd: Session, corrida_id: int) -> list[Fila]:
    tiendas = _tiendas(bd, corrida_id)
    filas = bd.execute(select(PrecioCorridaProducto, Producto, PrecioCoincidencia.estado)
                       .join(Producto, Producto.producto_id == PrecioCorridaProducto.producto_id)
                       .outerjoin(PrecioCoincidencia, PrecioCoincidencia.coincidencia_id == PrecioCorridaProducto.coincidencia_id)
                       .where(PrecioCorridaProducto.corrida_id == corrida_id)).all()
    limites = precios.limites_por_producto(bd)
    return [Fila(producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, departamento=p.departamento,
                 imagen=p.liga_imagen, estado=f.estado, mensaje=f.mensaje, precio_lista=f.precio_lista,
                 precio_membresia=f.precio_membresia, precio_tienda=f.precio_tienda, vendedores=f.vendedores,
                 minimo=f.minimo, mediana=f.mediana, maximo=f.maximo, dif_lista_mediana_pct=precios.dif_nuestro(f),
                 base=precios.nuestro(f)[1],
                 dif_membresia_mediana_pct=f.dif_membresia_mediana_pct, dif_lista_minimo_pct=f.dif_lista_minimo_pct,
                 coincidencia=estado if estado in VIGENTES else None,
                 limite_pct=precios.limite(limites.get(p.producto_id)),
                 color=precios.color(precios.dif_nuestro(f), limites.get(p.producto_id)),
                 tiendas=tiendas.get(p.producto_id, {}))
            for f, p, estado in filas]


@router.get("/resumen", response_model=Resumen)
def resumen(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Resumen:
    cfg = configuracion()
    actual = precios.en_curso(bd)
    ultima = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado != "en_curso", precios.REGULAR)
                     .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    prueba = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado != "en_curso", PrecioCorrida.origen == precios.PRUEBA)
                       .order_by(PrecioCorrida.corrida_id.desc()))
    vigilados = bd.scalar(select(func.count()).select_from(PrecioVigilado).where(PrecioVigilado.activo == true())) or 0
    con = bd.scalar(select(func.count(func.distinct(PrecioCoincidencia.producto_id)))
                    .join(PrecioVigilado, PrecioVigilado.producto_id == PrecioCoincidencia.producto_id)
                    .where(PrecioCoincidencia.estado.in_(VIGENTES), PrecioVigilado.activo == true())) or 0
    return Resumen(
        falta_configurar=dfs.configurado(), automatico=cfg.precios_activo, frecuencia=precios.texto_frecuencia(),
        hora=cfg.precios_hora, proxima=precios.proxima(bd), gasto_mes_usd=dfs.gasto_mes(bd),
        tope_mes_usd=Decimal(str(cfg.precios_tope_mensual_usd)), tope_corrida_usd=Decimal(str(cfg.precios_tope_corrida_usd)),
        estimado_usd=precios.estimado(bd), alerta_pct=cfg.precios_alerta_pct, vigilados=vigilados, con_coincidencia=con,
        en_curso=_corrida(bd, actual) if actual else None, ultima=_corrida(bd, ultima) if ultima else None,
        ultima_prueba=_corrida(bd, prueba) if prueba else None)


def _grupo(f: Fila) -> set[str]:
    g = {"todos"}
    if f.color:
        g.add(f.color)
    if f.estado == "sin_coincidencia":
        g.add("revisar")
    if f.estado in ("sin_precios", "fallido", "sin_presupuesto"):
        g.add("sin_precios")
    return g


@router.get("/lista", response_model=Lista)
def lista(q: str = "", marca: str = "", grupo: Grupo = "todos", orden: Orden = "diferencia", pagina: int = 1,
          por_pagina: int = 50, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Lista:
    """Productos de la última corrida, un renglón por producto, filtrados y paginados aquí y no en el navegador."""
    pagina, por_pagina = max(1, pagina), min(max(1, por_pagina), 200)
    ultima = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado != "en_curso", precios.REGULAR)
                       .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    if not ultima:
        return Lista(corrida=None, conteos={g: 0 for g in GRUPOS}, marcas=[], total=0, pagina=1, por_pagina=por_pagina, filas=[])
    todas = _filas(bd, ultima.corrida_id)
    marcas = sorted({f.marca for f in todas if f.marca})
    texto = q.strip().lower()
    filas = [f for f in todas if (not marca or f.marca == marca)
             and (not texto or any(texto in (v or "").lower() for v in (f.sku, f.descripcion, f.marca)))]
    grupos = [(f, _grupo(f)) for f in filas]
    conteos = {g: sum(1 for _, gs in grupos if g in gs) for g in GRUPOS}
    claves = precios.tiendas_clave()
    cobertura = {t: sum(1 for f in filas if t in f.tiendas) for t in claves}
    elegidas = [f for f, gs in grupos if grupo in gs]
    if orden == "nombre":
        elegidas.sort(key=lambda f: (f.descripcion or f.sku).lower())
    elif orden == "vendedores":
        elegidas.sort(key=lambda f: -f.vendedores)
    else:  # primero donde estamos más caros; sin comparación al final
        elegidas.sort(key=lambda f: (f.dif_lista_mediana_pct is None, -(f.dif_lista_mediana_pct or 0)))
    inicio = (pagina - 1) * por_pagina
    return Lista(corrida=_corrida(bd, ultima), conteos=conteos, marcas=marcas, total=len(elegidas), pagina=pagina,
                 tiendas=claves, cobertura=cobertura,
                 por_pagina=por_pagina, filas=elegidas[inicio:inicio + por_pagina])


# ---------------------------------------------------------------- productos

class Observacion(BaseModel):
    vendedor: str
    vendedor_original: str | None
    liga: str | None
    precio_comparable: Decimal
    envio: Decimal | None
    moneda: str
    disponibilidad: str | None
    es_propia: bool
    fuera: str | None = None  # por qué no cuenta para la mediana (otra presentación)
    publicacion: str | None = None  # título de la publicación de Google de donde salió el precio
    tienda_clave: str | None = None  # Walmart, Chedraui... si es una de las tiendas clave
    directa: bool = False  # se leyó en el sitio de la tienda, no en Google


class RenglonTabla(BaseModel):
    """Un precio de un vendedor para uno de nuestros productos (como la tabla del proyecto Radar Precios)."""
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    nuestro_precio: Decimal | None
    vendedor: str
    publicacion: str | None
    precio: Decimal
    envio: Decimal | None
    moneda: str
    disponibilidad: str | None
    liga: str | None
    dif_pct: Decimal | None  # nuestro precio contra el de este vendedor
    cuenta: bool  # entra a la mediana
    motivo: str | None  # por qué no cuenta
    tienda_clave: str | None = None  # Walmart, Chedraui... si es una de las tiendas clave


class Tabla(BaseModel):
    corrida: Corrida | None
    alerta_pct: float
    renglones: list[RenglonTabla]


class Publicacion(BaseModel):
    titulo: str | None
    vendedor: str | None
    precio: Decimal | None
    liga: str | None


class Coincidencia(BaseModel):
    id: int
    google_id: str | None
    titulo: str | None
    liga: str | None
    imagen: str | None
    estado: str
    confianza: Decimal | None
    motivo: str | None
    estrategia: str | None
    decidido_por: str | None
    creado_en: datetime
    verificado_en: datetime | None
    iguales: list[Publicacion] = []  # otras publicaciones del mismo producto; sus vendedores también cuentan


class Punto(BaseModel):
    fecha: date
    precio_lista: Decimal | None
    precio_membresia: Decimal | None
    minimo: Decimal | None
    mediana: Decimal | None


class CandidatoGoogle(BaseModel):
    """Un resultado de Google Shopping de la última búsqueda del producto."""
    clave: str
    titulo: str
    precio: Decimal | None
    moneda: str | None
    vendedor: str | None
    liga: str | None
    imagen: str | None
    posicion: int | None
    estrategias: list[str]
    calificacion: float | None
    aceptada: bool
    dudosa: bool
    motivo: str | None
    elegida: bool


class TiendaDirecta(BaseModel):
    tienda: str
    estado: str  # encontrado / sin_precio / no_lo_tiene / dudoso / error
    mensaje: str | None
    titulo: str | None = None
    liga: str | None = None
    precio: Decimal | None = None
    id: int | None = None  # para decir «no es este producto»


class DetalleProducto(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    codigo_barras: str | None
    imagen: str | None
    liga_tienda: str | None
    vigilado: bool
    consulta: str | None
    limite_propio_pct: Decimal | None  # vacío = el general
    limite_pct: Decimal
    consultas: list[str]  # lo que se busca en Google Shopping
    coincidencia: Coincidencia | None
    anteriores: list[Coincidencia]
    ultima: Fila | None
    ultima_fecha: date | None
    ultima_iniciada: datetime | None = None  # hora en que empezó esa corrida (UTC)
    observaciones: list[Observacion]
    serie: list[Punto]
    candidatos: list[CandidatoGoogle] = []  # lo que regresó Google en la última búsqueda
    candidatos_fecha: date | None = None
    tiendas: list[str] = []  # tiendas clave, para mostrar también las que no aparecieron
    directas: list[TiendaDirecta] = []  # qué pasó al buscar en el sitio de cada tienda en la última corrida


def _directas(texto: str | None) -> list[TiendaDirecta]:
    datos = _json(texto) or {}
    return [TiendaDirecta(tienda=t, estado=str(d.get("estado") or ""), mensaje=d.get("mensaje"), titulo=d.get("titulo"),
                          liga=d.get("liga"), precio=_decimal(d.get("precio")), id=d.get("id"))
            for t, d in datos.items() if isinstance(d, dict)] if isinstance(datos, dict) else []


def _coincidencia(bd: Session, m: PrecioCoincidencia) -> Coincidencia:
    u = bd.get(Usuario, m.decidido_por) if m.decidido_por else None
    return Coincidencia(id=m.coincidencia_id, google_id=m.google_id, titulo=m.titulo, liga=m.liga, imagen=m.imagen, estado=m.estado,
                        confianza=m.confianza, motivo=m.motivo, estrategia=m.estrategia, decidido_por=u.nombre if u else None,
                        creado_en=m.creado_en, verificado_en=m.verificado_en,
                        iguales=[Publicacion(titulo=d.get("titulo"), vendedor=d.get("vendedor"), precio=_decimal(d.get("precio")),
                                             liga=d.get("liga")) for d in precios.iguales(m)])


def _producto(bd: Session, producto_id: int) -> Producto:
    p = bd.get(Producto, producto_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no existe en el catálogo.")
    return p


@router.get("/productos/{producto_id}", response_model=DetalleProducto)
def producto(producto_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> DetalleProducto:
    p = _producto(bd, producto_id)
    v = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == producto_id))
    m = precios.vigente(bd, producto_id)
    todas = bd.scalars(select(PrecioCoincidencia).where(PrecioCoincidencia.producto_id == producto_id)
                       .order_by(PrecioCoincidencia.coincidencia_id.desc()).limit(20)).all()
    ultima = bd.execute(select(PrecioCorridaProducto, PrecioCorrida.fecha, PrecioCorrida.iniciado_en)
                        .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
                        .where(PrecioCorridaProducto.producto_id == producto_id, PrecioCorrida.estado != "en_curso")
                        .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc())).first()
    fila = None
    obs: list[PrecioObservacion] = []
    if ultima:
        fila = next((f for f in _filas(bd, ultima[0].corrida_id) if f.producto_id == producto_id), None)
        # Si el mismo día se repitió con otra coincidencia, solo cuentan los vendedores de la vigente en esa fila
        # (y los de los sitios de las tiendas)
        obs = bd.scalars(select(PrecioObservacion).where(PrecioObservacion.producto_id == producto_id,
                                                         PrecioObservacion.corrida_id == ultima[0].corrida_id,
                                                         precios.del_renglon(ultima[0].coincidencia_id))
                         .order_by(PrecioObservacion.precio_comparable)).all()
    serie = bd.execute(select(PrecioCorrida.fecha, PrecioCorridaProducto)
                       .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
                       .where(PrecioCorridaProducto.producto_id == producto_id, PrecioCorridaProducto.estado == "con_precios")
                       .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()).limit(60)).all()
    from modulos.compras import coincidencia as co

    cands, cands_fecha = precios.ultimos_candidatos(bd, producto_id)

    return DetalleProducto(
        producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, codigo_barras=p.codigo_barras,
        imagen=p.liga_imagen, liga_tienda=p.liga_producto, vigilado=bool(v and v.activo), consulta=v.consulta if v else None,
        limite_propio_pct=v.limite_pct if v else None, limite_pct=precios.limite(v.limite_pct if v else None),
        consultas=[t for _, t in co.consultas(p.descripcion, p.marca, p.codigo_barras, v.consulta if v else None)],
        coincidencia=_coincidencia(bd, m) if m else None,
        anteriores=[_coincidencia(bd, x) for x in todas if not m or x.coincidencia_id != m.coincidencia_id],
        ultima=fila, ultima_fecha=ultima[1] if ultima else None, ultima_iniciada=ultima[2] if ultima else None,
        observaciones=[Observacion(vendedor=o.vendedor, vendedor_original=o.vendedor_original, liga=o.liga,
                                   precio_comparable=o.precio_comparable, envio=o.envio, moneda=o.moneda,
                                   disponibilidad=o.disponibilidad, es_propia=o.es_propia,
                                   fuera=precios.fuera_de_rango(o, p.descripcion, precios.nuestro(fila)[0] if fila else None),
                                   publicacion=_publicacion(o), tienda_clave=precios.tienda_clave(o.vendedor, o.dominio),
                                   directa=o.tienda_coincidencia_id is not None)
                      for o in obs],
        tiendas=precios.tiendas_clave(), directas=_directas(ultima[0].tiendas) if ultima else [],
        serie=[Punto(fecha=f, precio_lista=r.precio_lista, precio_membresia=r.precio_membresia, minimo=r.minimo, mediana=r.mediana)
               for f, r in {f: r for f, r in reversed(serie)}.items()],  # una por día: la última
        candidatos=[_candidato(c, m) for c in cands], candidatos_fecha=cands_fecha)


def _publicacion(o: PrecioObservacion) -> str | None:
    try:
        return json.loads(o.datos or "{}").get("_publicacion")
    except (ValueError, AttributeError):
        return None


def _no_cuenta(o: PrecioObservacion, descripcion: str | None, base: Decimal | None) -> str | None:
    if o.es_propia:
        return "Es nuestra tienda"
    if o.moneda != "MXN":
        return f"Precio en {o.moneda}"
    if any(t in (o.disponibilidad or "").lower() for t in precios.NO_DISPONIBLE):
        return "Agotado"
    return precios.fuera_de_rango(o, descripcion, base)


def _renglones(bd: Session, corrida_id: int) -> list[RenglonTabla]:
    filas = bd.execute(select(PrecioObservacion, PrecioCorridaProducto, Producto).select_from(PrecioObservacion)
                       .join(PrecioCorridaProducto, (PrecioCorridaProducto.corrida_id == PrecioObservacion.corrida_id)
                             & (PrecioCorridaProducto.producto_id == PrecioObservacion.producto_id)
                             & precios.del_renglon(PrecioCorridaProducto.coincidencia_id))
                       .join(Producto, Producto.producto_id == PrecioObservacion.producto_id)
                       .where(PrecioObservacion.corrida_id == corrida_id)
                       .order_by(Producto.descripcion, PrecioObservacion.precio_comparable)).all()
    renglones = []
    for o, f, p in filas:
        base = precios.nuestro(f)[0]
        motivo = _no_cuenta(o, p.descripcion, base)
        renglones.append(RenglonTabla(
            producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, nuestro_precio=base,
            vendedor=o.vendedor, publicacion=_publicacion(o), precio=o.precio_comparable, envio=o.envio, moneda=o.moneda,
            disponibilidad=o.disponibilidad, liga=o.liga,
            dif_pct=precios.diferencia_pct(base, o.precio_comparable) if o.moneda == "MXN" else None,
            cuenta=motivo is None, motivo=motivo, tienda_clave=precios.tienda_clave(o.vendedor, o.dominio)))
    return renglones


@router.get("/tabla", response_model=Tabla)
def tabla(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Tabla:
    """Todos los precios de la última corrida: vendedor, producto de Google y precio, producto por producto."""
    # La última corrida que trajo precios (una detenida o sin vendedores dejaría la tabla vacía)
    con_precios = select(PrecioObservacion.observacion_id).where(PrecioObservacion.corrida_id == PrecioCorrida.corrida_id).exists()
    c = bd.scalar(select(PrecioCorrida).where(PrecioCorrida.estado != "en_curso", con_precios, precios.REGULAR)
                  .order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()))
    if not c:
        return Tabla(corrida=None, alerta_pct=configuracion().precios_alerta_pct, renglones=[])
    renglones = _renglones(bd, c.corrida_id)
    return Tabla(corrida=_corrida(bd, c), alerta_pct=configuracion().precios_alerta_pct, renglones=renglones)


def _decimal(v) -> Decimal | None:
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except (ArithmeticError, ValueError):
        return None


def _candidato(c: dict, m: PrecioCoincidencia | None) -> CandidatoGoogle:
    return CandidatoGoogle(
        clave=str(c.get("clave")), titulo=str(c.get("titulo") or ""), precio=_decimal(c.get("precio")), moneda=c.get("moneda"),
        vendedor=c.get("vendedor"), liga=c.get("liga"), imagen=c.get("imagen"),
        posicion=c.get("posicion") if isinstance(c.get("posicion"), int) else None, estrategias=c.get("estrategias") or [],
        calificacion=c.get("calificacion"), aceptada=bool(c.get("aceptada")), dudosa=bool(c.get("dudosa")),
        motivo=c.get("motivo"), elegida=bool(m and m.google_id == str(c.get("clave"))[:80]))


class ProductoCatalogo(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    imagen: str | None
    precio_lista_con_impuestos: Decimal | None
    vigilado: bool
    limite_propio_pct: Decimal | None = None  # vacío = el general
    limite_pct: Decimal | None = None
    dif_pct: Decimal | None = None  # última corrida: nuestro lista contra la mediana
    color: str | None = None
    ultima_fecha: date | None = None


class Vigilados(BaseModel):
    total: int
    productos: list[ProductoCatalogo]


@router.get("/catalogo", response_model=Vigilados)
def catalogo(q: str = "", marca: str = "", solo_vigilados: bool = False, _: Contexto = Depends(VER),
             bd: Session = Depends(obtener_bd)) -> Vigilados:
    """Busca en el catálogo para elegir qué vigilar. Con solo_vigilados, la lista de lo que se vigila."""
    filtro = (select(Producto, PrecioVigilado.vigilado_id, PrecioVigilado.limite_pct)
              .outerjoin(PrecioVigilado, (PrecioVigilado.producto_id == Producto.producto_id) & (PrecioVigilado.activo == true()))
              .where(Producto.activo == true()))
    if solo_vigilados:
        filtro = filtro.where(PrecioVigilado.vigilado_id.is_not(None))
    if q.strip():
        t = f"%{q.strip()}%"
        filtro = filtro.where(or_(Producto.sku.like(t), Producto.descripcion.like(t), Producto.marca.like(t), Producto.codigo_barras.like(t)))
    if marca:
        filtro = filtro.where(Producto.marca == marca)
    total = bd.scalar(select(func.count()).select_from(filtro.subquery())) or 0
    filas = bd.execute(filtro.order_by(Producto.descripcion).limit(500 if solo_vigilados else 60)).all()
    ultimas = _ultimas(bd, [p.producto_id for p, vid, _ in filas if vid is not None])
    productos = []
    for p, vid, propio in filas:
        u = ultimas.get(p.producto_id)
        dif = precios.dif_nuestro(u[0]) if u else None
        productos.append(ProductoCatalogo(
            producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, imagen=p.liga_imagen,
            precio_lista_con_impuestos=p.precio_lista_con_impuestos, vigilado=vid is not None,
            limite_propio_pct=propio if vid is not None else None, limite_pct=precios.limite(propio) if vid is not None else None,
            dif_pct=dif, color=precios.color(dif, propio), ultima_fecha=u[1] if u else None))
    return Vigilados(total=total, productos=productos)


def _ultimas(bd: Session, ids: list[int]) -> dict[int, tuple[PrecioCorridaProducto, date]]:
    """Último resultado con precios de cada producto (corridas terminadas)."""
    if not ids:
        return {}
    orden = func.row_number().over(partition_by=PrecioCorridaProducto.producto_id, order_by=(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc())).label("n")
    sub = (select(PrecioCorridaProducto.corrida_producto_id, PrecioCorrida.fecha, orden)
           .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
           .where(PrecioCorridaProducto.producto_id.in_(ids), PrecioCorrida.estado != "en_curso",
                  PrecioCorridaProducto.mediana.is_not(None))
           .subquery())
    filas = bd.execute(select(PrecioCorridaProducto, sub.c.fecha)
                       .join(sub, sub.c.corrida_producto_id == PrecioCorridaProducto.corrida_producto_id)
                       .where(sub.c.n == 1)).all()
    return {f.producto_id: (f, fecha) for f, fecha in filas}


class Agregar(BaseModel):
    producto_ids: list[int] = Field(default_factory=list, max_length=2000)
    marca: str | None = None  # agrega todos los productos activos de esa marca


@router.post("/vigilados")
def agregar(datos: Agregar, request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> dict:
    ids = set(datos.producto_ids)
    if datos.marca:
        ids |= set(bd.scalars(select(Producto.producto_id).where(Producto.marca == datos.marca, Producto.activo == true())))
    if not ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige al menos un producto.")
    existentes = {v.producto_id: v for v in bd.scalars(select(PrecioVigilado).where(PrecioVigilado.producto_id.in_(ids)))}
    validos = set(bd.scalars(select(Producto.producto_id).where(Producto.producto_id.in_(ids), Producto.activo == true())))
    nuevos = 0
    for pid in validos:
        v = existentes.get(pid)
        if v and v.activo:
            continue
        if v:
            v.activo = True
        else:
            bd.add(PrecioVigilado(producto_id=pid, origen="pantalla", agregado_por=ctx.usuario.usuario_id))
        nuevos += 1
    registrar(bd, "precios_vigilar", usuario_id=ctx.usuario.usuario_id, entidad="producto",
              detalle={"agregados": nuevos, "marca": datos.marca}, ip=ip_de(request))
    bd.commit()
    return {"agregados": nuevos}


class Cambio(BaseModel):
    consulta: str | None = Field(default=None, max_length=300)
    limite_pct: Decimal | None = Field(default=None, ge=0, le=100)  # vacío = el general


@router.patch("/vigilados/{producto_id}")
def cambiar(producto_id: int, datos: Cambio, request: Request, ctx: Contexto = Depends(ADMIN),
            bd: Session = Depends(obtener_bd)) -> dict:
    """Búsqueda escrita a mano o límite del semáforo. Al cambiar la búsqueda, la coincidencia actual se invalida."""
    v = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == producto_id))
    if not v:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no se vigila.")
    if "consulta" in datos.model_fields_set:
        nueva = (datos.consulta or "").strip() or None
        if nueva != v.consulta:
            v.consulta = nueva
            if (m := precios.vigente(bd, producto_id)) and m.estado != "persona":
                m.estado = "invalidada"
        registrar(bd, "precios_consulta", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
                  detalle={"consulta": nueva}, ip=ip_de(request))
    if "limite_pct" in datos.model_fields_set:
        v.limite_pct = datos.limite_pct
        registrar(bd, "precios_limite", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
                  detalle={"limite_pct": str(datos.limite_pct) if datos.limite_pct is not None else None}, ip=ip_de(request))
    bd.commit()
    return {"ok": True}


@router.delete("/vigilados/{producto_id}")
def quitar(producto_id: int, request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> dict:
    v = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == producto_id))
    if not v or not v.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto no se vigila.")
    v.activo = False  # su histórico se conserva
    registrar(bd, "precios_dejar_de_vigilar", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              ip=ip_de(request))
    bd.commit()
    return {"ok": True}


Accion = Literal["confirmar", "rechazar"]


@router.post("/productos/{producto_id}/coincidencia/{accion}", response_model=DetalleProducto)
def decidir(producto_id: int, accion: Accion, request: Request, ctx: Contexto = Depends(ADMIN),
            bd: Session = Depends(obtener_bd)) -> DetalleProducto:
    """Opcional: nada espera esto. Confirmar fija la coincidencia; rechazar la descarta para siempre
    y la siguiente corrida busca otra."""
    m = precios.vigente(bd, producto_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este producto no tiene una coincidencia vigente.")
    m.estado = "persona" if accion == "confirmar" else "rechazada"
    m.decidido_por = ctx.usuario.usuario_id
    registrar(bd, f"precios_coincidencia_{accion}", usuario_id=ctx.usuario.usuario_id, entidad="producto",
              entidad_id=producto_id, detalle={"google_id": m.google_id, "titulo": m.titulo}, ip=ip_de(request))
    bd.commit()
    return producto(producto_id, ctx, bd)


class Eleccion(BaseModel):
    clave: str = Field(min_length=1, max_length=120)


@router.post("/productos/{producto_id}/elegir", response_model=DetalleProducto)
def elegir(producto_id: int, datos: Eleccion, request: Request, ctx: Contexto = Depends(ADMIN),
           bd: Session = Depends(obtener_bd)) -> DetalleProducto:
    """Opcional: una persona elige, entre lo que regresó Google en la última búsqueda, cuál es nuestro producto.
    La coincidencia anterior queda rechazada y los vendedores del elegido se piden en ese momento (si otra corrida
    está corriendo, en la siguiente)."""
    cands, _ = precios.ultimos_candidatos(bd, producto_id)
    c = next((x for x in cands if str(x.get("clave")) == datos.clave), None)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese resultado no está en la última búsqueda de este producto.")
    actual = precios.vigente(bd, producto_id)
    cambio = not actual or actual.google_id != datos.clave[:80]
    if not cambio:
        actual.estado, actual.decidido_por = "persona", ctx.usuario.usuario_id
    else:
        if actual:
            actual.estado, actual.decidido_por = "rechazada", ctx.usuario.usuario_id
        bd.add(PrecioCoincidencia(
            producto_id=producto_id, google_id=datos.clave[:80], titulo=str(c.get("titulo") or "")[:400],
            liga=(c.get("liga") or "")[:800] or None, imagen=(c.get("imagen") or "")[:800] or None, estado="persona",
            motivo="Elegido por una persona entre los resultados de Google", estrategia=",".join(c.get("estrategias") or [])[:40],
            candidato=json.dumps({k: c.get(k) for k in ("product_id", "data_docid", "titulo", "liga", "precio")}, ensure_ascii=False,
                                 default=str),
            decidido_por=ctx.usuario.usuario_id))
    registrar(bd, "precios_coincidencia_elegir", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              detalle={"google_id": datos.clave, "titulo": c.get("titulo")}, ip=ip_de(request))
    bd.commit()
    if cambio and (corrida_id := precios.preparar_actualizacion(bd, producto_id)):
        precios.actualizar_aparte(corrida_id, producto_id)
    return producto(producto_id, ctx, bd)


@router.post("/productos/{producto_id}/actualizar", response_model=DetalleProducto)
def actualizar(producto_id: int, request: Request, ctx: Contexto = Depends(ADMIN),
               bd: Session = Depends(obtener_bd)) -> DetalleProducto:
    """Vuelve a pedir en ese momento los vendedores de la coincidencia vigente de un solo producto."""
    if not precios.vigente(bd, producto_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este producto no tiene coincidencia: elige primero la publicación con «Usar este».")
    corrida_id = precios.preparar_actualizacion(bd, producto_id)
    if not corrida_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ahora no se puede: hay una corrida en curso o ya se están trayendo sus precios.")
    registrar(bd, "precios_actualizar_producto", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              ip=ip_de(request))
    bd.commit()
    precios.actualizar_aparte(corrida_id, producto_id)
    return producto(producto_id, ctx, bd)


@router.post("/productos/{producto_id}/tiendas/{tienda_coincidencia_id}/rechazar", response_model=DetalleProducto)
def rechazar_tienda(producto_id: int, tienda_coincidencia_id: int, request: Request, ctx: Contexto = Depends(ADMIN),
                    bd: Session = Depends(obtener_bd)) -> DetalleProducto:
    """«No es este producto» para lo que se eligió en el sitio de una tienda: su precio deja de contar ya y nunca se vuelve
    a elegir; la siguiente corrida busca otro en esa tienda."""
    m = bd.get(PrecioTiendaCoincidencia, tienda_coincidencia_id)
    if not m or m.producto_id != producto_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese producto de la tienda no está ligado a este producto.")
    m.estado, m.decidido_por = "rechazada", ctx.usuario.usuario_id
    registrar(bd, "precios_tienda_rechazar", usuario_id=ctx.usuario.usuario_id, entidad="producto", entidad_id=producto_id,
              detalle={"tienda": m.tienda, "clave": m.clave, "titulo": m.titulo}, ip=ip_de(request))
    bd.commit()
    precios.recalcular(bd, producto_id)
    return producto(producto_id, ctx, bd)


# ---------------------------------------------------------------- corridas

class Envio(BaseModel):
    tipo: str
    tareas: int
    estado: str
    estimado_usd: Decimal
    costo_usd: Decimal | None
    creado_en: datetime


class CorridaDetalle(Corrida):
    envios: list[Envio]


@router.get("/corridas", response_model=list[Corrida])
def corridas(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[Corrida]:
    return [_corrida(bd, c) for c in bd.scalars(select(PrecioCorrida).order_by(PrecioCorrida.fecha.desc(), PrecioCorrida.corrida_id.desc()).limit(60))]


@router.get("/corridas/{corrida_id}", response_model=CorridaDetalle)
def corrida(corrida_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> CorridaDetalle:
    c = bd.get(PrecioCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    envios = bd.scalars(select(PrecioEnvio).where(PrecioEnvio.corrida_id == corrida_id).order_by(PrecioEnvio.envio_id)).all()
    return CorridaDetalle(**_corrida(bd, c).model_dump(), envios=[
        Envio(tipo=e.tipo, tareas=e.tareas, estado=e.estado, estimado_usd=e.estimado_usd, costo_usd=e.costo_usd, creado_en=e.creado_en)
        for e in envios])


def _json(texto: str | None):
    try:
        return json.loads(texto) if texto else None
    except ValueError:
        return texto


@router.get("/corridas/{corrida_id}/diagnostico")
def diagnostico(corrida_id: int, _: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> JSONResponse:
    """Todo lo que hizo una corrida en un archivo: lo que regresó Google, qué se eligió y por qué, y cada precio.
    Sirve para revisar casos fuera del equipo de Diego. No lleva usuario ni contraseña de DataForSEO."""
    c = bd.get(PrecioCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    ajustes = {k: v for k, v in configuracion().model_dump().items() if k.startswith("precios_")}
    filas = bd.execute(select(PrecioCorridaProducto, Producto).join(Producto, Producto.producto_id == PrecioCorridaProducto.producto_id)
                       .where(PrecioCorridaProducto.corrida_id == corrida_id).order_by(Producto.descripcion)).all()
    observaciones: dict[int, list[PrecioObservacion]] = {}
    for o in bd.scalars(select(PrecioObservacion).where(PrecioObservacion.corrida_id == corrida_id)
                        .order_by(PrecioObservacion.precio_comparable)):
        observaciones.setdefault(o.producto_id, []).append(o)
    productos = []
    for f, p in filas:
        m = bd.get(PrecioCoincidencia, f.coincidencia_id) if f.coincidencia_id else None
        base = precios.nuestro(f)[0]
        productos.append({
            "producto": {"sku": p.sku, "descripcion": p.descripcion, "marca": p.marca, "codigo_barras": p.codigo_barras,
                         "precio_lista": p.precio_lista, "precio_membresia": p.precio_membresia, "iva_pct": p.iva_pct,
                         "ieps_pct": p.ieps_pct, "precio_tienda_en_linea": p.precio_tienda_en_linea, "liga": p.liga_producto},
            "estado": f.estado, "mensaje": f.mensaje, "nuestro_precio": base, "precio_lista": f.precio_lista,
            "precio_membresia": f.precio_membresia, "precio_tienda": f.precio_tienda, "vendedores": f.vendedores,
            "minimo": f.minimo, "mediana": f.mediana, "maximo": f.maximo, "dif_lista_mediana_pct": f.dif_lista_mediana_pct,
            "lo_que_regreso_google": _json(f.candidatos), "tiendas_directas": _json(f.tiendas),
            "coincidencia": m and {"estado": m.estado, "titulo": m.titulo, "liga": m.liga, "confianza": m.confianza,
                                   "motivo": m.motivo, "estrategia": m.estrategia, "candidato": _json(m.candidato),
                                   "iguales": _json(m.iguales)},
            "precios": [{"vendedor": o.vendedor, "vendedor_original": o.vendedor_original, "dominio": o.dominio,
                         "precio": o.precio_comparable, "envio": o.envio, "moneda": o.moneda,
                         "disponibilidad": o.disponibilidad, "es_propia": o.es_propia,
                         "no_cuenta": _no_cuenta(o, p.descripcion, base), "del_sitio_de_la_tienda": o.tienda_coincidencia_id is not None,
                         "datos": _json(o.datos)}
                        for o in observaciones.get(p.producto_id, [])]})
    envios = [{"tipo": e.tipo, "tareas": e.tareas, "estado": e.estado, "estimado_usd": e.estimado_usd,
               "costo_usd": e.costo_usd, "respuesta": _json(e.respuesta)}
              for e in bd.scalars(select(PrecioEnvio).where(PrecioEnvio.corrida_id == corrida_id).order_by(PrecioEnvio.envio_id))]
    contenido = {"generado_en": datetime.now(), "corrida": _corrida(bd, c).model_dump(), "ajustes": ajustes,
                 "productos": productos, "envios": envios}
    return JSONResponse(json.loads(json.dumps(contenido, ensure_ascii=False, default=str)), headers={
        "Content-Disposition": f'attachment; filename="diagnostico-precios-{c.fecha}-{c.corrida_id}.json"'})


@router.post("/corridas", response_model=Corrida, status_code=status.HTTP_202_ACCEPTED)
def correr_ahora(request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> Corrida:
    if falta := dfs.configurado():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta capturar en Configuración: " + ", ".join(falta) + ".")
    if not bd.scalar(select(func.count()).select_from(PrecioVigilado).where(PrecioVigilado.activo == true())):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Primero agrega productos a vigilar.")
    c = precios.tomar_corrida(bd, precios.hoy_local(), "manual", ctx.usuario.usuario_id, forzar=True)
    if not c:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una corrida en curso. Espera a que termine.")
    registrar(bd, "precios_correr", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              ip=ip_de(request))
    bd.commit()
    precios.correr_aparte(c.corrida_id)
    return _corrida(bd, c)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Prueba(BaseModel):
    """Lo que se leyó del Excel de una prueba; con «revisar» todavía no se corre nada."""
    skus: int
    encontrados: list[ProductoCatalogo]
    no_encontrados: list[str]
    estimado_usd: Decimal
    corrida: Corrida | None = None


@router.get("/prueba/plantilla")
def plantilla_prueba(_: Contexto = Depends(ADMIN)) -> Response:
    return Response(xl.plantilla(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="plantilla-prueba-radar-precios.xlsx"'})


@router.post("/prueba", response_model=Prueba)
async def prueba(request: Request, archivo: UploadFile = File(...), revisar: bool = Query(False),
                 ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> Prueba:
    """Prueba con Excel (Diego, 2026-10-26): corre el radar solo con los SKU del archivo. No cambia la lista de vigilados
    ni cuenta como la última corrida; la coincidencia que encuentre para cada producto sí queda guardada."""
    nombre = (archivo.filename or "lista.xlsx")[:200]
    if not nombre.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sube un Excel (.xlsx) o un CSV.")
    contenido = await archivo.read(5 * 1024 * 1024 + 1)
    if len(contenido) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo pasa de 5 MB.")
    try:
        skus = xl.leer_skus(nombre, contenido)
    except xl.ErrorArchivo as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    productos, faltan = xl.buscar(bd, skus)
    vigilados = {v.producto_id: v for v in bd.scalars(select(PrecioVigilado).where(
        PrecioVigilado.producto_id.in_([p.producto_id for p in productos] or [0])))}
    pares = [(vigilados.get(p.producto_id) or PrecioVigilado(producto_id=p.producto_id), p) for p in productos]
    salida = Prueba(skus=len(skus), no_encontrados=faltan, estimado_usd=precios.estimado(bd, pares), encontrados=[
        ProductoCatalogo(producto_id=p.producto_id, sku=p.sku, descripcion=p.descripcion, marca=p.marca, imagen=p.liga_imagen,
                         precio_lista_con_impuestos=p.precio_lista_con_impuestos, vigilado=p.producto_id in vigilados)
        for p in productos])
    if revisar:
        return salida
    if falta := dfs.configurado():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta capturar en Configuración: " + ", ".join(falta) + ".")
    if not productos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ningún SKU del archivo está en el catálogo.")
    c = precios.tomar_corrida(bd, precios.hoy_local(), precios.PRUEBA, ctx.usuario.usuario_id, forzar=True)
    if not c:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una corrida en curso. Espera a que termine.")
    c.lista = json.dumps({"archivo": nombre, "producto_ids": [p.producto_id for p in productos], "no_encontrados": faltan},
                         ensure_ascii=False)
    registrar(bd, "precios_prueba", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              detalle={"archivo": nombre, "productos": len(productos), "no_encontrados": len(faltan)}, ip=ip_de(request))
    bd.commit()
    precios.correr_aparte(c.corrida_id)
    salida.corrida = _corrida(bd, c)
    return salida


@router.get("/corridas/{corrida_id}/excel")
def excel(corrida_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    """La salida de una corrida en Excel: resumen por producto, cada precio y, si fue prueba, los SKU no encontrados."""
    c = bd.get(PrecioCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    if c.estado == "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "La corrida sigue en curso; descarga el Excel cuando termine.")
    lista = xl.datos_lista(c.lista)
    filas = _filas(bd, corrida_id)
    orden = {pid: i for i, pid in enumerate(lista.get("producto_ids", []))}  # la prueba sale en el orden del archivo
    filas.sort(key=lambda f: (orden.get(f.producto_id, 10**6), f.descripcion or ""))
    publicaciones = {pid: (titulo, liga) for pid, titulo, liga in bd.execute(
        select(PrecioCorridaProducto.producto_id, PrecioCoincidencia.titulo, PrecioCoincidencia.liga)
        .join(PrecioCoincidencia, PrecioCoincidencia.coincidencia_id == PrecioCorridaProducto.coincidencia_id)
        .where(PrecioCorridaProducto.corrida_id == corrida_id))}
    u = bd.get(Usuario, c.iniciado_por) if c.iniciado_por else None
    info = {
        "Corrida": c.corrida_id, "Tipo": "Prueba con Excel" if c.origen == precios.PRUEBA else "Corrida del radar",
        "Archivo": lista.get("archivo"), "Fecha": f"{c.iniciado_en:%d/%m/%Y %H:%M}", "Quién la lanzó": u.nombre if u else "Programada",
        "Estado": c.estado, "Productos": c.productos, "Con precios": c.con_precios, "Sin coincidencia": c.sin_coincidencia,
        "Fallidos": c.fallidos, "SKU no encontrados": len(lista.get("no_encontrados", [])),
        "Costo DataForSEO (USD)": float(c.costo_usd or 0), "Error": c.error,
        "Avisos": " | ".join(json.loads(c.avisos)) if c.avisos else None,
        "Cómo leerlo": "Nuestro precio con impuestos contra la mediana de los vendedores que cuentan. Positivo = estamos más caros.",
    }
    contenido = xl.armar({k: v for k, v in info.items() if v is not None}, filas, _renglones(bd, corrida_id), publicaciones,
                         lista.get("no_encontrados", []))
    nombre = xl.nombre_archivo(c.fecha, c.corrida_id, c.origen == precios.PRUEBA)
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/corridas/{corrida_id}/detener", response_model=Corrida)
def detener(corrida_id: int, request: Request, ctx: Contexto = Depends(ADMIN), bd: Session = Depends(obtener_bd)) -> Corrida:
    """Detiene una corrida en curso. Lo que ya se pagó a DataForSEO no se recupera; lo que falte no se envía."""
    c = bd.get(PrecioCorrida, corrida_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    if c.estado != "en_curso":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa corrida ya terminó.")
    precios.detener(bd, c, ctx.usuario.nombre)
    registrar(bd, "precios_detener", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              ip=ip_de(request))
    bd.commit()
    return _corrida(bd, c)
