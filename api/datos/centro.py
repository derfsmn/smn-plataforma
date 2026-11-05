"""Centro de datos y modelos (pedido de Diego, 2026-10-29: «actualizar el centro de datos y modelos con base en lo que
actualmente ya tenemos en la bd»).

Antes era una maqueta con datos ficticios. Ahora cada tabla y cada modelo es real: los registros salen del conteo de SQL
Server, la última carga de `datos.carga` o de la fecha más reciente de la tabla, los campos del modelo de SQLAlchemy y
las ejecuciones de las corridas de cada módulo.

Lo que no sale de la base (nombre, descripción, origen, frecuencia y posición en el mapa) se escribe aquí a mano.
«Ver datos» enseña hasta 100 renglones, sin RFC, correos, teléfonos ni quién hizo qué; las tablas de Contraloría no se
pueden ver desde aquí.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, func, select, text
from sqlalchemy.orm import Session

from datos.modelos import (Carga, CompraOrden, CostoArticulo, Inventario, Producto, ProductoPrecioHistorial, Proveedor,
                           ProveedorCalificacion, ProveedorEvaluacion, Tienda, TiendaGrupoCorrida, VentaSemanal)
from modulos.compras.modelos import RadarReporte, RadarSenal
from modulos.compras.modelos_conocimiento import ConocimientoPolitica, ConocimientoRegla
from modulos.compras.modelos_precios import PrecioCorrida, PrecioObservacion
from modulos.compras.modelos_productos import Oportunidad, OportunidadCorrida, ProductoEvaluacion, ProductoIdea
from modulos.compras.modelos_propuestas import Propuesta
from modulos.contraloria.modelos_diot import DiotCorrida, DiotPeriodo, DiotTercero
from nucleo.modelos import OrganizacionExterna

MAX_FILAS = 100
LARGO_CELDA = 160
# Nunca se enseñan en «Ver datos»: datos de personas, quién hizo qué y textos largos internos
OCULTAS = {"rfc", "correo", "telefono", "contrasena", "usuario_id", "creado_por", "creada_por", "actualizado_por",
           "actualizada_por", "disparada_por", "iniciada_por", "iniciado_por", "cambiado_por", "procesado_por",
           "respuestas", "revisiones", "comentario", "datos", "diferencias", "txt", "referencia_txt", "contenido"}

DOMINIOS = {
    "cat": "Catálogos",
    "mov": "Movimientos",
    "ext": "Internet",
    "com": "Compras",
    "res": "Resultados",
    "fis": "Contraloría",
}


@dataclass
class TablaCentro:
    id: str
    nombre: str
    modelo: type
    dominio: str
    x: int
    y: int
    descripcion: str
    origen: str
    frecuencia: str
    ruta: str | None = None  # pantalla donde se trabaja
    cargas: tuple[str, ...] = ()  # datos.carga.fuente que la llenan
    fecha: object = None  # columna con la fecha del dato más reciente, si no hay cargas
    refs: dict[str, str] = field(default_factory=dict)  # campo -> id de otra tabla (relaciones lógicas)
    ver_datos: bool = True


TABLAS: list[TablaCentro] = [
    TablaCentro("producto", "Productos", Producto, "cat", 210, 312,
                "Catálogo único por SKU: descripción, estructura, marca, proveedor, precios y si está activo.",
                "API de artículos, tienda en línea y SMNBI (tblArticulos)", "Diaria (API y tienda) y al cargar SMNBI",
                "/datos/productos", ("API", "TIENDA", "SMNBI_ARTICULOS"), refs={"codigo_proveedor": "proveedor"}),
    TablaCentro("tienda", "Tiendas", Tienda, "cat", 16, 312,
                "Almacenes de la venta con nombre, región, categoría (AA a E; MAY es mayoreo), apertura y ubicación en el mapa.",
                "SMNBI (tblAlmacenes)", "Al cargar SMNBI", "/datos/tiendas", ("SMNBI_TIENDAS",)),
    TablaCentro("proveedor", "Proveedores", Proveedor, "cat", 404, 176,
                "Proveedores con condición de pago, descuentos y días de entrega que prometen (sin RFC).",
                "SMNBI (tblProveedores)", "Al cargar SMNBI", "/datos/proveedores", ("SMNBI_PROVEEDORES",)),
    TablaCentro("venta", "Venta semanal", VentaSemanal, "mov", 16, 176,
                "Venta sumada por producto, tienda, semana y empresa: piezas, devoluciones, importe y costo.",
                "SMNBI (tblVenta y tblVentaD)", "Al cargar SMNBI", "/datos/etl", ("ETL_VENTAS",),
                refs={"sku": "producto", "tienda": "tienda"}),
    TablaCentro("inventario", "Inventario", Inventario, "mov", 16, 448,
                "Existencia por producto y almacén en cada fecha de corte.",
                "SMNBI (inventario)", "Al cargar SMNBI", "/datos/etl", ("SMNBI_INVENTARIO",),
                refs={"sku": "producto", "almacen": "tienda"}),
    TablaCentro("compra", "Órdenes de compra", CompraOrden, "mov", 404, 40,
                "Cada orden de compra con lo que se pidió, lo que llegó, lo perdido y lo rechazado.",
                "SMNBI (tblCompra y tblCompraD)", "Al cargar SMNBI", "/datos/etl", ("SMNBI_COMPRAS",),
                refs={"proveedor": "proveedor", "almacen": "tienda"}),
    TablaCentro("costo", "Costo de compra", CostoArticulo, "mov", 210, 176,
                "Último costo por pieza sin IVA de cada artículo y su promedio de 12 meses.",
                "SMNBI (entradas de compra)", "Al cargar SMNBI", "/datos/etl", ("SMNBI_COSTOS",),
                refs={"sku": "producto", "proveedor": "proveedor"}),
    TablaCentro("historial", "Historial de precios", ProductoPrecioHistorial, "mov", 210, 40,
                "Cada cambio de precio lista, membresía o tienda en línea de un producto.",
                "API de artículos y tienda en línea", "Con cada carga del catálogo", "/datos/productos",
                ("API", "TIENDA"), refs={"producto_id": "producto"}),
    TablaCentro("precios", "Precios de la competencia", PrecioObservacion, "ext", 210, 448,
                "Precios que encontró el Radar de precios en Google Shopping y en las tiendas clave.",
                "Radar de precios (DataForSEO y sitios de las tiendas)", "Cada 7 días y en pruebas con Excel",
                "/compras/precios", fecha=PrecioObservacion.creado_en, refs={"producto_id": "producto"}),
    TablaCentro("senal", "Tendencias", RadarSenal, "ext", 210, 584,
                "Señales del Radar de tendencias: qué está creciendo, su nivel y cuántas veces se ha visto.",
                "Radar de tendencias (notas de internet leídas por IA)", "Diaria", "/compras/radar",
                fecha=RadarSenal.ultima_vez),
    TablaCentro("propuesta", "Propuestas de proveedores", Propuesta, "com", 598, 312,
                "Productos que los proveedores proponen desde el portal, con sus presentaciones.",
                "Portal de proveedores", "Continua", "/compras", fecha=Propuesta.actualizada_en,
                refs={"organizacion_id": "organizacion"}),
    TablaCentro("organizacion", "Empresas del portal", OrganizacionExterna, "com", 792, 312,
                "Empresas con acceso al portal de proveedores.", "Plataforma (invitaciones)", "Continua",
                "/admin/usuarios", fecha=OrganizacionExterna.actualizado_en),
    TablaCentro("idea", "Ideas de producto", ProductoIdea, "com", 598, 448,
                "Productos que Compras captura o que manda «Buscar oportunidades» para evaluarlos.",
                "Captura de Compras y Buscar oportunidades", "Continua", "/compras/productos",
                fecha=ProductoIdea.actualizada_en),
    TablaCentro("politica", "Políticas de Compras", ConocimientoPolitica, "com", 792, 448,
                "Políticas de la Base de conocimiento: borrador, vigente o retirada.", "Base de conocimiento",
                "Cuando Compras las cambia", "/compras/conocimiento", fecha=ConocimientoPolitica.actualizado_en),
    TablaCentro("regla", "Reglas de Compras", ConocimientoRegla, "com", 792, 584,
                "Reglas de rechazo, umbrales y metas de éxito que usan los modelos cuando están activas.",
                "Base de conocimiento", "Cuando Compras las cambia", "/compras/conocimiento",
                fecha=ConocimientoRegla.actualizado_en),
    TablaCentro("evaluacion", "Semáforo de productos", ProductoEvaluacion, "res", 404, 448,
                "Cada evaluación de un producto nuevo: puntaje, color, confianza y color final de Compras.",
                "Modelo «Semáforo de producto nuevo»", "Al evaluar", "/compras/productos",
                fecha=ProductoEvaluacion.creada_en, refs={"idea_id": "idea", "propuesta_id": "propuesta"}),
    TablaCentro("calificacion", "Calificación de proveedores", ProveedorCalificacion, "res", 404, 312,
                "Calificación de 0 a 100 de cada proveedor en cada cálculo, con sus cuatro bloques.",
                "Modelo «Calificación de proveedores»", "Al dar «Calcular»", "/datos/proveedores",
                fecha=None, refs={"proveedor": "proveedor"}),
    TablaCentro("oportunidad", "Oportunidades", Oportunidad, "res", 598, 584,
                "Productos recomendados por «Buscar oportunidades» con su prueba de venta y foto.",
                "Modelo «Buscar oportunidades»", "Al buscar", "/compras/productos/oportunidades",
                fecha=None, refs={"idea_id": "idea"}),
    TablaCentro("diot_periodo", "Periodos de la DIOT", DiotPeriodo, "fis", 792, 40,
                "Cada mes y empresa procesados para la DIOT, con su resumen y comparación.", "Reportes de Fiscal",
                "Mensual", "/contraloria/diot", fecha=DiotPeriodo.procesado_en, ver_datos=False),
    TablaCentro("diot_tercero", "Terceros de la DIOT", DiotTercero, "fis", 792, 176,
                "Consolidado por proveedor de cada periodo (con RFC: solo se ve en Contraloría).", "Proceso de la DIOT",
                "Mensual", "/contraloria/diot", refs={"periodo_id": "diot_periodo"}, ver_datos=False),
]
POR_ID = {t.id: t for t in TABLAS}

# Relaciones que no son llave foránea en la base pero sí unen los datos
RELACIONES_EXTRA = [("evaluacion", "producto"), ("evaluacion", "senal"), ("evaluacion", "politica"),
                    ("evaluacion", "regla"), ("evaluacion", "precios")]


def relaciones() -> list[tuple[str, str]]:
    salida = []
    for t in TABLAS:
        for destino in t.refs.values():
            salida.append((t.id, destino))
    for par in RELACIONES_EXTRA:
        if par not in salida and par[::-1] not in salida:
            salida.append(par)
    return salida


def _tipo(t: TablaCentro, c) -> str:
    if c.name in t.refs:
        return f"→ {POR_ID[t.refs[c.name]].nombre}"
    if c.primary_key:
        return "llave"
    if c.name in OCULTAS:
        return "oculto"
    tipo = c.type
    if isinstance(tipo, Boolean):
        return "sí / no"
    if isinstance(tipo, DateTime):
        return "fecha y hora"
    if isinstance(tipo, Date):
        return "fecha"
    if isinstance(tipo, (Integer, Numeric)):
        return "número"
    return "texto"


def campos(t: TablaCentro) -> list[tuple[str, str]]:
    return [(c.name, _tipo(t, c)) for c in t.modelo.__table__.columns if c.name != "carga_id"]


def conteos(bd: Session) -> dict[str, int]:
    """Renglones de cada tabla según SQL Server (sys.partitions: rápido aun con millones de renglones)."""
    filas = bd.execute(text(
        "SELECT s.name + '.' + t.name, SUM(p.rows) FROM sys.tables t "
        "JOIN sys.schemas s ON s.schema_id = t.schema_id "
        "JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1) "
        "GROUP BY s.name, t.name")).all()
    return {nombre: int(n or 0) for nombre, n in filas}


def _ultima(bd: Session, t: TablaCentro) -> datetime | date | None:
    if t.cargas:
        return bd.scalar(select(func.max(Carga.fin_en)).where(Carga.fuente.in_(t.cargas), Carga.estado == "completa"))
    if t.id == "calificacion":
        return bd.scalar(select(func.max(ProveedorEvaluacion.terminada_en)).where(ProveedorEvaluacion.estado == "completa"))
    if t.id == "oportunidad":
        return bd.scalar(select(func.max(OportunidadCorrida.terminada_en)).where(OportunidadCorrida.estado == "lista"))
    if t.fecha is not None:
        return bd.scalar(select(func.max(t.fecha)))
    return None


def tablas(bd: Session) -> list[dict]:
    n = conteos(bd)
    salida = []
    for t in TABLAS:
        registros = n.get(t.modelo.__table__.fullname, 0)
        salida.append({
            "id": t.id, "nombre": t.nombre, "tabla": t.modelo.__table__.fullname, "dominio": t.dominio, "x": t.x, "y": t.y,
            "registros": registros, "estado": "cargado" if registros else "sin", "descripcion": t.descripcion,
            "origen": t.origen, "frecuencia": t.frecuencia, "ruta": t.ruta, "ultima_carga": _ultima(bd, t),
            "campos": campos(t), "ver_datos": t.ver_datos})
    return salida


def _celda(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, (date, Decimal)):
        return str(v)
    s = " ".join(str(v).split())
    return s if len(s) <= LARGO_CELDA else s[:LARGO_CELDA - 1] + "…"


def filas(bd: Session, tabla_id: str) -> tuple[list[str], list[dict[str, str]]] | None:
    """Hasta 100 renglones, los más recientes primero, sin las columnas ocultas. None si no se puede ver."""
    t = POR_ID.get(tabla_id)
    if not t or not t.ver_datos:
        return None
    tabla = t.modelo.__table__
    columnas = [c for c in tabla.columns if c.name not in OCULTAS and c.name != "carga_id"]
    orden = [c.desc() for c in tabla.primary_key.columns]
    renglones = bd.execute(select(*columnas).order_by(*orden).limit(MAX_FILAS)).all()
    nombres = [c.name for c in columnas]
    return nombres, [{k: _celda(v) for k, v in zip(nombres, r)} for r in renglones]


# ---------------------------------------------------------------- modelos

@dataclass
class ModeloCentro:
    id: str
    sigla: str
    nombre: str
    tipo: str
    iniciativa: str
    estado: str  # Idea / En diseño / Piloto / Activo
    descripcion: str
    usa: list[str]
    motor: str
    salida: str
    ruta: str | None


MODELOS: list[ModeloCentro] = [
    ModeloCentro("semaforo", "TD1", "Semáforo de producto nuevo", "Reglas, score e IA", "Compras · TD001", "Piloto",
                 "Califica un producto nuevo de 0 a 100 con seis factores (demanda, rentabilidad, precio, tendencia, "
                 "categoría y proveedor) y los pesos de la Base de conocimiento. Rojo hasta 59, amarillo de 60 a 80, verde "
                 "arriba de 80; una regla de rechazo lo manda a rojo. La IA clasifica, revisa políticas y explica; Compras "
                 "pone el color final.",
                 ["idea", "propuesta", "producto", "venta", "inventario", "costo", "precios", "senal", "politica", "regla",
                  "calificacion"],
                 "Python (motor de reglas) + puerta de IA", "Puntaje, color, confianza y explicación", "/compras/productos"),
    ModeloCentro("proveedores", "PRV", "Calificación de proveedores", "Score", "Datos", "Piloto",
                 "Califica cada proveedor de 0 a 100 con cumplimiento, desempeño comercial, costo y condiciones, e "
                 "inventario. Pesos provisionales hasta que Compras los cambie.",
                 ["proveedor", "compra", "venta", "costo", "inventario", "producto", "regla"],
                 "Python (score)", "Puntaje, color y confianza por proveedor", "/datos/proveedores"),
    ModeloCentro("oportunidades", "OPT", "Buscar oportunidades", "Agente de IA con búsqueda web", "Compras · TD001",
                 "Piloto",
                 "Busca productos nuevos para SMN que ya se venden: más vendidos en México guiados por las tendencias, y lo "
                 "que vende la competencia. Cada uno con prueba de venta, liga y foto.",
                 ["senal", "venta", "producto", "regla", "idea"],
                 "Agente de OpenAI con búsqueda web + DataForSEO", "Hasta 20 productos recomendados", "/compras/productos/oportunidades"),
    ModeloCentro("radar_precios", "$", "Radar de precios", "Búsqueda y coincidencia", "Compras", "Activo",
                 "Busca nuestros productos en Google Shopping y en las tiendas clave, decide cuál resultado es el mismo "
                 "producto y compara contra nuestro precio lista y membresía.",
                 ["producto", "precios"], "DataForSEO + reglas + IA (coincidencias dudosas)",
                 "Precios por tienda y diferencias contra los nuestros", "/compras/precios"),
    ModeloCentro("radar_tendencias", "TND", "Radar de tendencias", "IA", "Compras", "Activo",
                 "Lee notas de internet, decide cuáles importan para una tienda naturista y las agrupa en señales.",
                 ["senal"], "Puerta de IA (Ollama y API)", "Reporte diario y señales", "/compras/radar"),
    ModeloCentro("diot", "DIOT", "Proceso de la DIOT", "Reglas (sin IA)", "Contraloría · TD003", "Piloto",
                 "Sigue los 8 pasos de Fiscal: extrae, consolida, clasifica, concilia, revisa, genera el TXT, valida y entrega.",
                 ["diot_periodo", "diot_tercero"], "Python (reglas)", "TXT de la DIOT, evidencia y bitácora", "/contraloria/diot"),
    ModeloCentro("demanda", "f(t)", "Pronóstico de demanda", "Estadístico", "Sin iniciativa", "Idea",
                 "Estimaría piezas por producto y tienda para las próximas semanas con la venta semanal. Ya hay venta e "
                 "inventario cargados; falta construirlo.",
                 ["venta", "producto", "tienda", "inventario"], "Python (series de tiempo)", "Piezas esperadas por semana", None),
    ModeloCentro("tiendas", "k·n", "Grupos de tiendas", "Agrupamiento + IA local", "Datos", "Piloto",
                 "Agrupa las tiendas que se parecen con los criterios y pesos que se elijan: ventas, tendencia, mezcla por "
                 "departamento y demografía de su localidad (Censo 2020 del INEGI). Marca las que van abajo de sus pares. "
                 "La IA local (Ollama) solo pone nombre y explica cada grupo; nada sale a internet.",
                 ["venta", "tienda", "producto"], "Python (k-medias) + Ollama",
                 "Grupo de cada tienda y tiendas abajo de sus pares",
                 "/datos/tiendas"),
]


def _ejecuciones(bd: Session, modelo: str) -> list[dict]:
    """Las 5 ejecuciones más recientes: {fecha, caso, calificacion, color, estado}."""
    if modelo == "semaforo":
        filas_ = bd.execute(select(ProductoEvaluacion, ProductoIdea.nombre, Propuesta.producto)
                            .outerjoin(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
                            .outerjoin(Propuesta, Propuesta.propuesta_id == ProductoEvaluacion.propuesta_id)
                            .order_by(ProductoEvaluacion.creada_en.desc()).limit(5)).all()
        return [{"fecha": e.creada_en, "caso": idea or propuesta or "Producto", "calificacion": e.puntaje,
                 "color": e.color_final or e.color, "estado": e.estado} for e, idea, propuesta in filas_]
    if modelo == "proveedores":
        return [{"fecha": e.iniciada_en, "caso": f"{e.calificados or 0} de {e.proveedores or 0} proveedores calificados",
                 "calificacion": None, "color": None, "estado": e.estado}
                for e in bd.scalars(select(ProveedorEvaluacion).order_by(ProveedorEvaluacion.iniciada_en.desc()).limit(5))]
    if modelo == "oportunidades":
        cuenta = dict(bd.execute(select(Oportunidad.corrida_id, func.count()).group_by(Oportunidad.corrida_id)).all())
        return [{"fecha": c.creada_en, "caso": f"{cuenta.get(c.corrida_id, 0)} recomendaciones"
                 + (" · con competencia" if c.competencia else ""), "calificacion": None, "color": None, "estado": c.estado}
                for c in bd.scalars(select(OportunidadCorrida).order_by(OportunidadCorrida.creada_en.desc()).limit(5))]
    if modelo == "radar_precios":
        return [{"fecha": c.iniciado_en, "caso": f"{c.productos or 0} productos · {c.con_precios or 0} con precios"
                 + (" · prueba con Excel" if c.origen == "prueba" else ""), "calificacion": None, "color": None,
                 "estado": c.estado}
                for c in bd.scalars(select(PrecioCorrida).order_by(PrecioCorrida.iniciado_en.desc()).limit(5))]
    if modelo == "radar_tendencias":
        return [{"fecha": r.iniciado_en or r.fecha, "caso": f"{r.articulos_relevantes or 0} notas relevantes de "
                 f"{r.articulos_nuevos or 0} nuevas", "calificacion": None, "color": None, "estado": r.estado}
                for r in bd.scalars(select(RadarReporte).order_by(RadarReporte.reporte_id.desc()).limit(5))]
    if modelo == "diot":
        return [{"fecha": c.iniciada_en, "caso": f"Periodo {p.mes:02d}/{p.anio}", "calificacion": None, "color": None,
                 "estado": c.estado}
                for c, p in bd.execute(select(DiotCorrida, DiotPeriodo).join(DiotPeriodo, DiotPeriodo.periodo_id ==
                                                                             DiotCorrida.periodo_id)
                                       .order_by(DiotCorrida.iniciada_en.desc()).limit(5)).all()]
    if modelo == "tiendas":
        return [{"fecha": c.iniciada_en, "caso": f"{c.tiendas or 0} tiendas en {c.grupos or 0} grupos",
                 "calificacion": None, "color": None, "estado": c.estado}
                for c in bd.scalars(select(TiendaGrupoCorrida).order_by(TiendaGrupoCorrida.iniciada_en.desc()).limit(5))]
    return []


def modelos(bd: Session) -> list[dict]:
    return [{"id": m.id, "sigla": m.sigla, "nombre": m.nombre, "tipo": m.tipo, "iniciativa": m.iniciativa,
             "estado": m.estado, "descripcion": m.descripcion, "usa": m.usa, "motor": m.motor, "salida": m.salida,
             "ruta": m.ruta, "ejecuciones": _ejecuciones(bd, m.id)} for m in MODELOS]
