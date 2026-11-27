"""Corridas a pedido y tablero al día del Radar de precios (Diego, 26 nov 2026, junta con Precios y Costos).

- Corridas a pedido (/api/compras/precios/pedidos): quien usa el radar sube un Excel de SKU o elige marca, clasificación
  y categoría, ve cuánto costaría y la lanza. Si otra corrida está corriendo (un lote de la noche), la suya se forma y
  arranca sola en cuanto quede libre. Al terminar: resumen (con precio confirmado, más caros, más baratos, sin comparar),
  qué conviene con cada producto y su Excel. Usa el mismo tope mensual de DataForSEO que el resto del radar.
- Tablero al día (/api/compras/precios/tablero/dia): solo radar de precios, sin costos (Diego: «no metamos costos»).
"""
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core.bd import obtener_bd
from core.config import configuracion
from core.seguridad import Contexto, ip_de, requiere
from datos.modelos import Producto
from modulos.compras import dataforseo as dfs
from modulos.compras import excel_precios as xl
from modulos.compras import nocturno_precios as noche
from modulos.compras import precios
from modulos.compras import reporte_precios as rep
from modulos.compras import tablero_precios as tb
from modulos.compras.modelos_precios import PrecioCorrida, PrecioCorridaProducto, PrecioVigilado
from modulos.compras.rutas_tablero_precios import (PIDE_ACCION, AvanceNoche, FilaTablero, Seleccion, _fila, _nombre, _por_que_no,
                                                   _texto_avance, titulo_de)
from nucleo.bitacora import registrar
from nucleo.modelos import Usuario, ahora

router = APIRouter(prefix="/api/compras/precios", tags=["compras · radar de precios"])
VER = requiere(precios.VER)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_PRODUCTOS = xl.MAX_SKUS  # 300 por corrida, como la prueba con Excel


# ---------------------------------------------------------------- corridas a pedido

class Pedir(BaseModel):
    producto_ids: list[int] = Field(default=[], max_length=5000)
    marcas: list[str] = Field(default=[], max_length=500)
    categorias: list[str] = Field(default=[], max_length=500)
    clasificaciones: list[str] = Field(default=[], max_length=10)
    archivo: str | None = Field(default=None, max_length=200)  # nombre del Excel de SKU, si vino de uno
    no_encontrados: list[str] = Field(default=[], max_length=5000)  # SKU del Excel que no estaban en el catálogo

    def seleccion(self) -> Seleccion:
        return Seleccion(producto_ids=self.producto_ids, marcas=self.marcas, categorias=self.categorias,
                         clasificaciones=self.clasificaciones)


class Estimado(BaseModel):
    productos: int
    maximo: int
    estimado_usd: Decimal
    gasto_mes_usd: Decimal
    tope_mes_usd: Decimal
    disponible_usd: Decimal
    tope_corrida_usd: Decimal | None  # lo más que puede gastar una sola corrida (None: sin tope)
    cabe: bool  # el costo estimado cabe en lo que queda del mes y en el tope por corrida
    caben: int  # cuántos productos de esta selección sí caben (aproximado)
    ocupado: str | None  # qué corre ahora (la corrida se formará)
    en_espera: int  # corridas a pedido formadas antes que esta
    falta_configurar: list[str]
    puede: bool
    motivo: str | None  # por qué no se puede lanzar


class Pedido(BaseModel):
    id: int
    nombre: str  # qué se buscó
    usuario: str | None
    usuario_id: int | None
    estado: str  # en_espera / en_curso / completa / parcial / fallida
    productos: int
    con_precios: int
    hechos: int  # productos ya revisados (mientras corre)
    avance: dict | None
    fase: str | None
    costo_usd: Decimal
    error: str | None
    avisos: list[str]  # p. ej. que se acabó el presupuesto a media corrida
    archivo: str | None
    no_encontrados: list[str]
    creado_en: datetime
    iniciado_en: datetime
    terminado_en: datetime | None
    origen: str


class Detalle(BaseModel):
    pedido: Pedido
    cuadros: dict[str, int]  # con_precio, mas_caros, mas_baratos, sin_comparar
    acciones: dict[str, int]
    en_juego: Decimal
    sin_comparar: dict[str, int]
    filas: list[FilaTablero]


def _lista(c: PrecioCorrida) -> dict:
    return xl.datos_lista(c.lista)


def _pedido(bd: Session, c: PrecioCorrida) -> Pedido:
    d = _lista(c)
    u = bd.get(Usuario, c.iniciado_por) if c.iniciado_por else None
    avance = precios.AVANCE.get(c.corrida_id) if c.estado == "en_curso" else None
    if c.estado == "en_curso":
        hechos = bd.scalar(select(func.count()).select_from(PrecioCorridaProducto).where(
            PrecioCorridaProducto.corrida_id == c.corrida_id, PrecioCorridaProducto.estado != "pendiente")) or 0
    else:
        hechos = c.productos or 0
    nombre = d.get("nombre") or ("Prueba con Excel" if c.origen == precios.PRUEBA else
                                 "Revisión de noche" if c.origen == precios.NOCTURNA else "Corrida del radar")
    return Pedido(id=c.corrida_id, nombre=nombre, usuario=u.nombre if u else None, usuario_id=c.iniciado_por, estado=c.estado,
                  productos=len(d.get("producto_ids", [])) or c.productos, con_precios=c.con_precios, hechos=hechos,
                  avance=avance, fase=precios.FASE.get(c.corrida_id) if c.estado == "en_curso" else None,
                  costo_usd=c.costo_usd or Decimal(0), error=c.error,
                  avisos=json.loads(c.avisos) if c.avisos else [], archivo=d.get("archivo"),
                  no_encontrados=d.get("no_encontrados", []), creado_en=datetime.fromisoformat(d["creado"]) if d.get("creado")
                  else c.iniciado_en, iniciado_en=c.iniciado_en, terminado_en=c.terminado_en, origen=c.origen)


def _ocupado(bd: Session) -> str | None:
    c = precios.en_curso(bd)
    if not c:
        return None
    if c.origen == precios.NOCTURNA:
        return "Está corriendo un lote de la revisión de noche"
    if c.origen == precios.PEDIDO:
        return "Está corriendo otra corrida a pedido"
    return "Está corriendo otra corrida del radar"


def _estimar(bd: Session, datos: Pedir) -> tuple[Estimado, list[Producto]]:
    cfg = configuracion()
    ps = tb.de_seleccion(bd, datos.producto_ids, datos.marcas, datos.categorias, datos.clasificaciones)
    vigilados = {}
    ids = [p.producto_id for p in ps]
    for i in range(0, len(ids), 1500):
        for v in bd.scalars(select(PrecioVigilado).where(PrecioVigilado.producto_id.in_(ids[i:i + 1500]))):
            vigilados[v.producto_id] = v
    pares = [(vigilados.get(p.producto_id) or PrecioVigilado(producto_id=p.producto_id), p) for p in ps[:MAX_PRODUCTOS]]
    costo = precios.estimado(bd, pares) if pares else Decimal(0)
    if cfg.precios_pedido_prioridad_alta:  # la corrida a pedido va en la cola rápida: cuesta el doble (26 nov 2026)
        costo *= dfs.POR_PRIORIDAD[2]
    gasto, tope = dfs.gasto_mes(bd), Decimal(str(cfg.precios_tope_mensual_usd or 0))
    disponible = max(Decimal(0), tope - gasto)
    falta = dfs.configurado()
    motivo = None
    if falta:
        motivo = "Falta capturar en Configuración: " + ", ".join(falta) + ". Pídeselo a quien administra la plataforma."
    elif not ps:
        motivo = "Elige al menos un producto, una marca, una clasificación o una categoría."
    elif len(ps) > MAX_PRODUCTOS:
        motivo = f"Son {len(ps):,} productos; una corrida acepta hasta {MAX_PRODUCTOS}. Acota con la clasificación o divide la lista."
    elif disponible <= 0:
        motivo = "Ya se usó todo el presupuesto de búsquedas de este mes."
    # Una corrida que no cabe no se lanza (Diego, 27 nov 2026: una de 113 productos tardó una hora, topó a la mitad y
    # terminó sin un solo precio). Se compara lo más que puede costar contra el tope por corrida y lo que queda del mes.
    tope_corrida = Decimal(str(cfg.precios_tope_corrida_usd)) if cfg.precios_tope_corrida_usd else None
    limite = min(disponible, tope_corrida) if tope_corrida is not None else disponible
    cabe = costo <= limite
    caben = len(pares) if cabe or not costo else int(len(pares) * limite / costo)
    if motivo is None and not cabe:  # sin cifras en dólares: el gasto solo lo ve quien administra (lo trae aparte)
        cual = "del tope por corrida" if tope_corrida is not None and tope_corrida <= disponible else "de lo que queda este mes"
        motivo = (f"Esta corrida no cabe en el presupuesto de búsquedas ({cual}), así que no se lanza para que no se quede a "
                  "medias. " + (f"Caben unos {caben} productos: acota la selección o divídela en varias corridas. " if caben
                                else "Hoy no cabe ni un producto. ")
                  + "Quien administra la plataforma puede subir el tope en Configuración → Radar de precios.")
    return Estimado(productos=len(ps), maximo=MAX_PRODUCTOS, estimado_usd=costo, gasto_mes_usd=gasto, tope_mes_usd=tope,
                    disponible_usd=disponible, tope_corrida_usd=tope_corrida, cabe=cabe, caben=caben, ocupado=_ocupado(bd),
                    en_espera=len(precios.en_espera(bd)), falta_configurar=falta, puede=motivo is None, motivo=motivo), ps


@router.post("/pedidos/estimar", response_model=Estimado)
def estimar(datos: Pedir, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Estimado:
    """Cuántos productos son y lo más que costaría, antes de lanzarla."""
    return _estimar(bd, datos)[0]


@router.post("/pedidos", response_model=Pedido, status_code=status.HTTP_202_ACCEPTED)
def pedir(datos: Pedir, request: Request, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Pedido:
    """Lanza una corrida a pedido. Si otra está corriendo, queda formada y arranca sola al terminar la otra."""
    e, ps = _estimar(bd, datos)
    if not e.puede:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.motivo)
    ids = [p.producto_id for p in ps]
    noche._vigilar(bd, ids)  # quedan en el radar: la noche los vuelve a revisar en su rotación
    nombre = (f"Excel {datos.archivo}" if datos.archivo and not (datos.marcas or datos.categorias or datos.clasificaciones)
              else titulo_de(datos.seleccion()))
    contenido = {"nombre": nombre[:200], "producto_ids": ids, "archivo": datos.archivo, "no_encontrados": datos.no_encontrados[:500],
                 "seleccion": {"marcas": datos.marcas, "categorias": datos.categorias, "clasificaciones": datos.clasificaciones,
                               "sueltos": len(datos.producto_ids)},
                 "estimado_usd": str(e.estimado_usd), "creado": ahora().isoformat()}
    c = None if precios.en_espera(bd) else precios.tomar_corrida(bd, precios.hoy_local(), precios.PEDIDO, ctx.usuario.usuario_id, forzar=True)
    arranca = c is not None
    if not c:  # algo corre (o ya hay otras formadas): se forma
        c = PrecioCorrida(fecha=precios.hoy_local(), origen=precios.PEDIDO, iniciado_por=ctx.usuario.usuario_id,
                          estado=precios.EN_ESPERA)
        bd.add(c)
    c.lista = json.dumps(contenido, ensure_ascii=False)
    bd.commit()
    registrar(bd, "precios_pedido", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              detalle={"nombre": nombre[:200], "productos": len(ids), "estimado_usd": str(e.estimado_usd), "formada": not arranca},
              ip=ip_de(request))
    bd.commit()
    if arranca:
        precios.correr_aparte(c.corrida_id)
    return _pedido(bd, c)


@router.get("/pedidos", response_model=list[Pedido])
def pedidos(todas: bool = False, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> list[Pedido]:
    """Las corridas a pedido, de la más nueva a la más vieja. Con «todas», también las de noche y las del programa."""
    q = select(PrecioCorrida)
    if todas:
        q = q.where(PrecioCorrida.origen.not_in((precios.PRODUCTO, precios.OPORTUNIDAD, precios.WEB)))
    else:
        q = q.where(PrecioCorrida.origen.in_((precios.PEDIDO, precios.PRUEBA)))
    return [_pedido(bd, c) for c in bd.scalars(q.order_by(PrecioCorrida.corrida_id.desc()).limit(80))]


def _de(bd: Session, corrida_id: int) -> PrecioCorrida:
    c = bd.get(PrecioCorrida, corrida_id)
    if not c or c.origen in (precios.PRODUCTO, precios.OPORTUNIDAD, precios.WEB):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa corrida no existe.")
    return c


def _productos(bd: Session, c: PrecioCorrida) -> list[Producto]:
    ids = _lista(c).get("producto_ids") or list(bd.scalars(select(PrecioCorridaProducto.producto_id)
                                                           .where(PrecioCorridaProducto.corrida_id == c.corrida_id)))
    salida = []
    for i in range(0, len(ids), 1500):
        salida += list(bd.scalars(select(Producto).where(Producto.producto_id.in_(ids[i:i + 1500]))))
    return salida


def _orden(rs: list[tb.Renglon]) -> list[tb.Renglon]:
    """Primero lo que pide acción con más dinero en juego; luego el resto por venta."""
    return sorted(rs, key=lambda r: (r.evaluacion.accion not in PIDE_ACCION, -r.en_juego, -r.evaluacion.venta_importe,
                                     r.producto.descripcion or ""))


@router.get("/pedidos/{corrida_id}", response_model=Detalle)
def pedido(corrida_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Detalle:
    """Resumen de lo que encontró y qué conviene con cada producto (con lo último que se sabe de cada uno)."""
    c = _de(bd, corrida_id)
    rs = _orden(tb.renglones(bd, _productos(bd, c))) if c.estado not in ("en_espera",) else []
    cuadros = {"con_precio": sum(1 for r in rs if r.color), "mas_caros": sum(1 for r in rs if r.color in ("rojo", "amarillo")),
               "mas_baratos": sum(1 for r in rs if r.color == "verde"), "sin_comparar": sum(1 for r in rs if not r.color)}
    acciones = {k: sum(1 for r in rs if r.evaluacion.accion == k) for k in ("bajar", "bajar_y_negociar", "negociar", "subir")}
    return Detalle(pedido=_pedido(bd, c), cuadros=cuadros, acciones=acciones,
                   en_juego=sum((r.en_juego for r in rs if r.evaluacion.accion in PIDE_ACCION), Decimal(0)),
                   sin_comparar=dict(sorted(_contar(_por_que_no(r) for r in rs if not r.color).items(), key=lambda kv: -kv[1])),
                   filas=[_fila(r) for r in rs])


def _contar(valores) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for v in valores:
        d[v] += 1
    return dict(d)


@router.get("/pedidos/{corrida_id}/excel")
def pedido_excel(corrida_id: int, request: Request, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Response:
    c = _de(bd, corrida_id)
    if c.estado in ("en_curso", precios.EN_ESPERA):
        raise HTTPException(status.HTTP_409_CONFLICT, "La corrida no ha terminado; descarga el Excel cuando termine.")
    rs = _orden(tb.renglones(bd, _productos(bd, c)))
    if not rs:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta corrida no tiene productos.")
    titulo = _lista(c).get("nombre") or f"Corrida {c.corrida_id}"
    contenido = rep.armar(bd, rs, list(rep.POR_OMISION), precios.hoy_local(), titulo)
    registrar(bd, "precios_pedido_excel", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              ip=ip_de(request))
    bd.commit()
    nombre = f"Radar_de_precios_corrida_{c.corrida_id}_{_nombre(titulo)}.xlsx"
    return Response(contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/pedidos/{corrida_id}/detener", response_model=Pedido)
def detener(corrida_id: int, request: Request, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Pedido:
    """Quien la lanzó (o quien administra el radar) la puede detener o sacar de la fila."""
    c = _de(bd, corrida_id)
    if c.origen != precios.PEDIDO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se detienen aquí las corridas a pedido.")
    if c.iniciado_por != ctx.usuario.usuario_id and not ctx.puede(precios.ADMINISTRAR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien la lanzó puede detenerla.")
    if c.estado == precios.EN_ESPERA:
        c.estado, c.error, c.terminado_en = "fallida", f"{precios.DETENIDA} {ctx.usuario.nombre} antes de arrancar.", ahora()
        bd.commit()
    elif c.estado == "en_curso":
        precios.detener(bd, c, ctx.usuario.nombre)
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa corrida ya terminó.")
    registrar(bd, "precios_detener", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              ip=ip_de(request))
    bd.commit()
    return _pedido(bd, c)


class Continuar(BaseModel):
    faltan: int  # productos que se quedaron sin precio y se retoman
    estimado_usd: Decimal  # lo más que cuesta lo indispensable de esos productos
    puede: bool
    motivo: str | None


def _continuar(bd: Session, c: PrecioCorrida) -> tuple[Continuar, list[int]]:
    """Qué falta de una corrida a pedido que terminó a medias y si alcanza para retomarla."""
    cfg = configuracion()
    # Lo que ya tiene precio y lo que ya se buscó sin encontrarlo en internet no se repite
    con = set(bd.scalars(select(PrecioCorridaProducto.producto_id).where(
        PrecioCorridaProducto.corrida_id == c.corrida_id, PrecioCorridaProducto.estado.in_(("con_precios", "sin_coincidencia")))))
    ps = [p for p in _productos(bd, c) if p.producto_id not in con]
    vigilados = {}
    ids = [p.producto_id for p in ps]
    for i in range(0, len(ids), 1500):
        for v in bd.scalars(select(PrecioVigilado).where(PrecioVigilado.producto_id.in_(ids[i:i + 1500]))):
            vigilados[v.producto_id] = v
    costo = precios.esencial(bd, [(vigilados.get(p.producto_id) or PrecioVigilado(producto_id=p.producto_id), p) for p in ps])
    if cfg.precios_pedido_prioridad_alta:
        costo *= dfs.POR_PRIORIDAD[2]
    disponible = max(Decimal(0), Decimal(str(cfg.precios_tope_mensual_usd or 0)) - dfs.gasto_mes(bd))
    tope = Decimal(str(cfg.precios_tope_corrida_usd)) if cfg.precios_tope_corrida_usd else None
    limite = min(disponible, tope) if tope is not None else disponible
    motivo = None
    if c.origen != precios.PEDIDO:
        motivo = "Solo se continúan aquí las corridas a pedido."
    elif c.estado not in ("parcial", "fallida"):
        motivo = "Esta corrida no quedó a medias."
    elif not ps:
        motivo = "No quedó ningún producto por retomar."
    elif falta := dfs.configurado():
        motivo = "Falta capturar en Configuración: " + ", ".join(falta) + "."
    elif costo > limite:
        cual = "del tope por corrida" if tope is not None and tope <= disponible else "de lo que queda este mes"
        motivo = (f"Lo que falta no cabe en el presupuesto de búsquedas ({cual}). Quien administra la plataforma puede subir "
                  "el tope en Configuración → Radar de precios; después se continúa.")
    return Continuar(faltan=len(ps), estimado_usd=costo, puede=motivo is None, motivo=motivo), ids


@router.get("/pedidos/{corrida_id}/continuar", response_model=Continuar)
def por_continuar(corrida_id: int, _: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Continuar:
    return _continuar(bd, _de(bd, corrida_id))[0]


@router.post("/pedidos/{corrida_id}/continuar", response_model=Pedido, status_code=status.HTTP_202_ACCEPTED)
def continuar(corrida_id: int, request: Request, ctx: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> Pedido:
    """Retoma la misma corrida con lo que faltó (Diego, 27 nov 2026: «debería ser esta misma que se pueda lanzar»).
    Sigue siendo de quien la pidió; lo ya encontrado no se vuelve a pagar. Si algo corre, se forma."""
    c = _de(bd, corrida_id)
    if c.iniciado_por != ctx.usuario.usuario_id and not ctx.puede(precios.ADMINISTRAR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo quien la pidió o quien administra el radar puede continuarla.")
    e, _ids = _continuar(bd, c)
    if not e.puede:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, e.motivo)
    cambio = bd.execute(update(PrecioCorrida).where(PrecioCorrida.corrida_id == c.corrida_id, PrecioCorrida.estado == c.estado)
                        .values(estado=precios.EN_ESPERA, terminado_en=None, error=None, avisos=None,
                                intentos=(c.intentos or 0) + 1))
    registrar(bd, "precios_pedido_continuar", usuario_id=ctx.usuario.usuario_id, entidad="precio_corrida", entidad_id=c.corrida_id,
              detalle={"faltan": e.faltan, "estimado_usd": str(e.estimado_usd)}, ip=ip_de(request))
    bd.commit()
    if cambio.rowcount == 1:
        precios.arrancar_en_espera(bd)  # si nada corre arranca ya; si no, espera su turno
    bd.refresh(c)
    return _pedido(bd, c)


# ---------------------------------------------------------------- tablero al día

class Agente(BaseModel):
    agente: str
    productos: int
    comparados: int
    bajar: int
    negociar: int
    subir: int
    en_juego: Decimal


class Movimiento(BaseModel):
    producto_id: int
    sku: str
    descripcion: str | None
    marca: str | None
    imagen: str | None
    antes: Decimal
    ahora: Decimal
    cambio_pct: Decimal
    fecha: datetime | None
    nuestro: Decimal | None
    color: str | None


class Noche(BaseModel):
    lotes: int
    productos: int
    con_precios: int
    costo_usd: Decimal
    desde: datetime | None
    hasta: datetime | None


class Dia(BaseModel):
    fecha: str
    productos: int


class TableroDia(BaseModel):
    actualizado: datetime | None
    en_curso: str | None
    catalogo: int
    comparados: int
    mas_caros: int
    un_poco_caros: int
    mas_baratos: int
    sin_comparar: int
    en_juego_caros: Decimal  # al mes, por estar más caros que el mercado
    en_juego_subir: Decimal  # al mes, en productos donde conviene revisar si se sube
    acciones: dict[str, int]
    agentes: list[Agente]
    subieron: int
    bajaron: int
    movimientos: list[Movimiento]
    avance: AvanceNoche
    noche: Noche
    dias: list[Dia]  # productos revisados por día (últimos 14)


MOVIMIENTO_PCT = Decimal(5)


def _movimientos(bd: Session, rs: dict[int, tb.Renglon]) -> list[Movimiento]:
    """Productos cuyo precio del mercado cambió 5 % o más entre sus dos últimas revisiones (la última en 14 días)."""
    desde = ahora() - timedelta(days=60)
    q = (select(PrecioCorridaProducto.producto_id, PrecioCorridaProducto.mediana, PrecioCorrida.terminado_en)
         .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
         .where(precios.REGULAR, PrecioCorrida.iniciado_en >= desde, PrecioCorridaProducto.estado == "con_precios",
                PrecioCorridaProducto.mediana.is_not(None))
         .order_by(PrecioCorridaProducto.corrida_producto_id.desc()))
    ultimas: dict[int, list] = {}
    for pid, mediana, cuando in bd.execute(q):
        lista = ultimas.setdefault(pid, [])
        if len(lista) < 2:
            lista.append((Decimal(mediana), cuando))
    reciente = ahora() - timedelta(days=14)
    salida = []
    for pid, lista in ultimas.items():
        r = rs.get(pid)
        if len(lista) < 2 or not r or not r.color or not lista[1][0]:
            continue
        (nuevo, cuando), (viejo, _) = lista
        if cuando and cuando < reciente:
            continue
        cambio = ((nuevo - viejo) / viejo * 100).quantize(Decimal("0.1"))
        if abs(cambio) < MOVIMIENTO_PCT:
            continue
        p = r.producto
        salida.append(Movimiento(producto_id=pid, sku=p.sku, descripcion=p.descripcion, marca=p.marca, imagen=p.liga_imagen,
                                 antes=viejo, ahora=nuevo, cambio_pct=cambio, fecha=cuando, nuestro=r.base, color=r.color))
    # Primero lo que más pesa: venta del producto por el tamaño del cambio
    salida.sort(key=lambda m: -(abs(m.cambio_pct) * (rs[m.producto_id].venta_mes or 1)))
    return salida


@router.get("/tablero/dia", response_model=TableroDia)
def tablero_dia(_: Contexto = Depends(VER), bd: Session = Depends(obtener_bd)) -> TableroDia:
    """Tablero del radar de precios al día (solo precios, sin costos)."""
    todos = tb.renglones_vigentes(bd)
    por_id = {r.producto.producto_id: r for r in todos}
    por_agente: dict[str, dict] = {}
    for r in todos:
        d = por_agente.setdefault(r.agente or "Sin agente", {"productos": 0, "comparados": 0, "bajar": 0, "negociar": 0,
                                                               "subir": 0, "en_juego": Decimal(0)})
        d["productos"] += 1
        d["comparados"] += 1 if r.color else 0
        a = r.evaluacion.accion
        if a in ("bajar", "bajar_y_negociar"):
            d["bajar"] += 1
        elif a == "negociar":
            d["negociar"] += 1
        elif a == "subir":
            d["subir"] += 1
        if a in PIDE_ACCION:
            d["en_juego"] += r.en_juego
    agentes = sorted((Agente(agente=k, **v) for k, v in por_agente.items()),
                     key=lambda a: (a.agente == "Sin agente", -a.en_juego, -(a.bajar + a.negociar + a.subir)))
    movs = _movimientos(bd, por_id)
    # Lo que hizo la última noche
    a = noche.avance(bd)
    local = datetime.now(precios.zona())
    inicio = noche.inicio_noche(local, a.desde)  # de día, la noche que pasó; de noche, la que corre
    lotes = list(bd.scalars(select(PrecioCorrida).where(PrecioCorrida.origen == noche.ORIGEN, PrecioCorrida.iniciado_en >= inicio)))
    n = Noche(lotes=len(lotes), productos=sum(c.productos or 0 for c in lotes), con_precios=sum(c.con_precios or 0 for c in lotes),
              costo_usd=sum((c.costo_usd or Decimal(0) for c in lotes), Decimal(0)),
              desde=min((c.iniciado_en for c in lotes), default=None), hasta=max((c.terminado_en for c in lotes if c.terminado_en), default=None))
    # Productos revisados por día (últimos 14), por la fecha local en que corrió
    hace = precios.hoy_local() - timedelta(days=13)
    dias = dict(bd.execute(select(PrecioCorrida.fecha, func.sum(PrecioCorrida.productos)).where(
        precios.REGULAR, PrecioCorrida.fecha >= hace).group_by(PrecioCorrida.fecha)).all())
    serie = [Dia(fecha=(hace + timedelta(days=i)).isoformat(), productos=int(dias.get(hace + timedelta(days=i)) or 0)) for i in range(14)]
    actual = precios.en_curso(bd)
    return TableroDia(
        actualizado=tb.actualizado(bd), en_curso=_ocupado(bd) if actual else None, catalogo=len(todos),
        comparados=sum(1 for r in todos if r.color), mas_caros=sum(1 for r in todos if r.color == "rojo"),
        un_poco_caros=sum(1 for r in todos if r.color == "amarillo"), mas_baratos=sum(1 for r in todos if r.color == "verde"),
        sin_comparar=sum(1 for r in todos if not r.color),
        en_juego_caros=sum((r.en_juego for r in todos if r.color in ("rojo", "amarillo")), Decimal(0)),
        en_juego_subir=sum((r.en_juego for r in todos if r.evaluacion.accion == "subir"), Decimal(0)),
        acciones={k: sum(1 for r in todos if r.evaluacion.accion == k) for k in ("bajar", "bajar_y_negociar", "negociar", "subir")},
        agentes=agentes, subieron=sum(1 for m in movs if m.cambio_pct > 0), bajaron=sum(1 for m in movs if m.cambio_pct < 0),
        movimientos=movs[:15], avance=AvanceNoche(**a.__dict__, texto=_texto_avance(a)), noche=n, dias=serie)
