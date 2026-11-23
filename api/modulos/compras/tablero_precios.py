"""Lo que muestra la pantalla nueva del Radar de precios y el reporte a Excel (Diego, 2026-11-17: «quiero que ese radar
de precios sea muy fácil de ver»; «un reporte donde seleccione varios productos, individualmente o por marca o por
categoría y se bajaría en excel»).

Con lotes de noche cada producto tiene su último resultado en una corrida distinta: aquí se toma, por producto, su
último renglón terminado de una corrida del radar (no prueba, no radar de productos).
"""
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from datos.modelos import Producto
from modulos.compras import precios
from modulos.compras import validacion_precios as val
from modulos.compras.evaluacion_precios import Evaluacion, Evaluador
from modulos.compras.modelos_precios import (PrecioCorrida, PrecioCorridaProducto, PrecioObservacion, PrecioValidacion,
                                             PrecioVigilado)

PAREJOS_PCT = Decimal("2")  # contra una tienda: ±2 % es estar parejos
LISTA, MEMBRESIA = "lista", "membresia"  # los dos precios contra los que se compara (Diego, 2026-11-17)


def ultimas_filas(bd: Session, hasta: date | None = None, producto_ids: list[int] | None = None
                  ) -> dict[int, tuple[PrecioCorridaProducto, PrecioCorrida]]:
    """{producto: (último renglón, su corrida)} de las corridas del radar ya terminadas (o hasta una fecha)."""
    filtro = [precios.REGULAR, PrecioCorrida.estado != "en_curso",
              PrecioCorridaProducto.estado.not_in(("pendiente",))]
    if hasta:
        filtro.append(PrecioCorrida.fecha <= hasta)
    if producto_ids is not None:
        if not producto_ids:
            return {}
        if len(producto_ids) < 1500:
            filtro.append(PrecioCorridaProducto.producto_id.in_(producto_ids))
    ultimo = (select(func.max(PrecioCorridaProducto.corrida_producto_id).label("id"))
              .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)
              .where(*filtro).group_by(PrecioCorridaProducto.producto_id).subquery())
    filas = bd.execute(select(PrecioCorridaProducto, PrecioCorrida)
                       .join(ultimo, ultimo.c.id == PrecioCorridaProducto.corrida_producto_id)
                       .join(PrecioCorrida, PrecioCorrida.corrida_id == PrecioCorridaProducto.corrida_id)).all()
    ids = set(producto_ids) if producto_ids is not None else None
    return {f.producto_id: (f, c) for f, c in filas if ids is None or f.producto_id in ids}


def precios_que_cuentan(bd: Session, filas: dict[int, tuple[PrecioCorridaProducto, PrecioCorrida]],
                        productos: dict[int, Producto]) -> dict[int, list[tuple[PrecioObservacion, PrecioValidacion | None]]]:
    """Los precios de cada renglón con su validación (todos; el que llama decide cuáles cuentan)."""
    if not filas:
        return {}
    pares = {(f.corrida_id, pid) for pid, (f, _) in filas.items()}
    corridas = sorted({c for c, _ in pares})
    salida: dict[int, list] = {}
    for i in range(0, len(corridas), 500):
        q = (select(PrecioObservacion, PrecioValidacion)
             .outerjoin(PrecioValidacion, PrecioValidacion.observacion_id == PrecioObservacion.observacion_id)
             .where(PrecioObservacion.corrida_id.in_(corridas[i:i + 500])))
        for o, v in bd.execute(q):
            if (o.corrida_id, o.producto_id) not in pares:
                continue
            f = filas[o.producto_id][0]
            if f.coincidencia_id and o.coincidencia_id and o.coincidencia_id != f.coincidencia_id:
                continue  # otra coincidencia del mismo día
            salida.setdefault(o.producto_id, []).append((o, v))
    return salida


def no_cuenta(o: PrecioObservacion, v: PrecioValidacion | None, descripcion: str | None, base: Decimal | None) -> str | None:
    """Por qué un precio no cuenta para la mediana, o None si cuenta."""
    if o.es_propia:
        return "Es nuestra tienda"
    if v and v.resultado != val.VALIDADO:
        return v.motivo or ("Dudoso" if v.resultado == val.DUDOSO else "No es el mismo producto")
    if o.moneda != "MXN":
        return f"Precio en {o.moneda}"
    if any(t in (o.disponibilidad or "").lower() for t in precios.NO_DISPONIBLE):
        return "Agotado"
    return precios.fuera_de_rango(o, descripcion, base)


@dataclass
class Renglon:
    producto: Producto
    fila: PrecioCorridaProducto | None
    corrida: PrecioCorrida | None
    vigilado: PrecioVigilado | None
    color: str | None
    dif: Decimal | None
    base: Decimal | None
    limite: Decimal
    evaluacion: Evaluacion
    membresia: Decimal | None = None  # precio membresía con impuestos
    dif_membresia: Decimal | None = None  # membresía contra la mediana
    color_membresia: str | None = None  # mismo semáforo y límite que el precio lista
    tiendas: dict[str, tuple[Decimal, str | None]] = field(default_factory=dict)  # tienda clave: (precio, liga)
    otras: list[tuple[str, Decimal, str | None]] = field(default_factory=list)  # otras tiendas que cuentan
    mediana: Decimal | None = None  # mediana de los precios que cuentan (None si no hay referencia firme)
    aviso: str | None = None  # por qué no se compara (un solo precio, precios que no coinciden)
    apartados: list = field(default_factory=list)  # (observación, motivo) que se salen de los demás

    @property
    def cuadro(self) -> str:
        return self.color or "sin_referencia"

    def segun(self, precio: str = LISTA) -> tuple[Decimal | None, Decimal | None, str | None]:
        """(nuestro precio, diferencia, color) contra el mercado con el precio lista o con el de membresía."""
        if precio == MEMBRESIA:
            return self.membresia, self.dif_membresia, self.color_membresia
        return self.base, self.dif, self.color

    def cuadro_de(self, precio: str = LISTA) -> str:
        return self.segun(precio)[2] or "sin_referencia"


def renglones(bd: Session, productos: list[Producto], hasta: date | None = None) -> list[Renglon]:
    """Todo lo de cada producto: último resultado, color, evaluación y el precio de cada tienda que cuenta."""
    ids = [p.producto_id for p in productos]
    por_id = {p.producto_id: p for p in productos}
    filas = ultimas_filas(bd, hasta, ids)
    vigilados = {}
    for i in range(0, len(ids), 1500):
        for v in bd.scalars(select(PrecioVigilado).where(PrecioVigilado.producto_id.in_(ids[i:i + 1500]))):
            vigilados[v.producto_id] = v
    limites = {pid: v.limite_pct for pid, v in vigilados.items() if v.limite_pct is not None}
    obs = precios_que_cuentan(bd, filas, por_id)
    claves = precios.tiendas_clave()
    ev = Evaluador(bd, productos)
    salida = []
    for p in productos:
        f, c = filas.get(p.producto_id, (None, None))
        base = precios.nuestro(f)[0] if f else None
        cuentan = [o for o, v in obs.get(p.producto_id, []) if not no_cuenta(o, v, p.descripcion, base)]
        quedan, apartados, aviso = mercado_confiable(cuentan)
        # Solo se compara contra los precios que hoy cuentan (los mismos que se ven en la pantalla). Si ninguno cuenta
        # (Compras marcó «Está mal», la noche los dejó dudosos), no hay referencia aunque la corrida guardara una mediana.
        firme = f is not None and f.estado == "con_precios" and not aviso and bool(quedan)
        mediana = _mediana([o.precio_comparable for o in quedan]) if firme else None
        if f is not None and f.estado == "con_precios" and not obs.get(p.producto_id):
            mediana, firme = f.mediana, True  # renglón sin observaciones guardadas (corridas viejas): se queda lo de la corrida
            aviso = None
        ajustada = _FilaAjustada(f, mediana if firme else None, base) if f is not None else None
        dif = precios.diferencia_pct(base, mediana) if firme and mediana else None
        color = precios.color(dif, limites.get(p.producto_id)) if dif is not None else None
        membresia = f.precio_membresia if f else None
        dif_m = precios.diferencia_pct(membresia, mediana) if firme and mediana else None
        e = ev.evaluar(p, ajustada, limites.get(p.producto_id))
        if aviso:
            e.accion, e.accion_texto, e.detalle = "sin_referencia", "Referencia débil", aviso
        r = Renglon(producto=p, fila=f, corrida=c, vigilado=vigilados.get(p.producto_id), color=color, dif=dif, base=base,
                    limite=precios.limite(limites.get(p.producto_id)), evaluacion=e, membresia=membresia,
                    dif_membresia=dif_m,
                    color_membresia=precios.color(dif_m, limites.get(p.producto_id)) if dif_m is not None else None,
                    mediana=mediana if firme else None, aviso=aviso, apartados=apartados)
        for o in quedan:
            t = precios.tienda_clave(o.vendedor, o.dominio, claves)
            if t:
                if t not in r.tiendas or o.precio_comparable < r.tiendas[t][0]:
                    r.tiendas[t] = (o.precio_comparable, o.liga)
            else:
                r.otras.append((o.vendedor, o.precio_comparable, o.liga))
        r.otras.sort(key=lambda x: x[1])
        salida.append(r)
    return salida


# ---------------------------------------------------------------- cuándo el mercado es confiable
# Diagnóstico de producción (2026-11-23): de los 80 productos con más diferencia (35 % o más), 55 tenían un solo precio,
# casi siempre de un mercado en línea (paquetes y revendedores) o de una tienda con otra presentación. Con un solo precio
# no se pinta color ni se sugiere acción; un precio que se sale mucho de los demás no cuenta.
MIN_PRECIOS = 2
SALTO_MAXIMO = Decimal("1.6")  # un precio 60 % arriba o abajo de la mediana de los demás se aparta
MERCADOS_EN_LINEA = ("mercado libre", "mercadolibre", "amazon", "shein", "uber eats", "ubereats", "rappi", "didi food",
                     "coppel", "suburbia", "temu", "aliexpress", "ebay", "linio", "claro shop", "claroshop")


def es_mercado_en_linea(o) -> bool:
    texto = f"{o.vendedor or ''} {o.dominio or ''}".lower()
    return any(m in texto or m.replace(" ", "") in texto for m in MERCADOS_EN_LINEA)


def _mediana(valores: list) -> Decimal | None:
    v = sorted(Decimal(x) for x in valores if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return (v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2).quantize(Decimal("0.01"))


def mercado_confiable(cuentan: list) -> tuple[list, list[tuple], str | None]:
    """(precios que quedan, [(precio apartado, motivo)], aviso si no alcanza para comparar)."""
    vivos = [o for o in cuentan if o.precio_comparable]
    apartados: list[tuple] = []
    if len(vivos) >= 3:
        quedan = []
        for o in vivos:
            otros = _mediana([x.precio_comparable for x in vivos if x is not o])
            if otros and (o.precio_comparable > otros * SALTO_MAXIMO or o.precio_comparable * SALTO_MAXIMO < otros):
                apartados.append((o, "Se sale mucho de los demás precios: parece otra presentación o un paquete"))
            else:
                quedan.append(o)
        if len(quedan) < MIN_PRECIOS:  # todos muy distintos: no hay mercado claro
            return [], [(o, "Los precios no coinciden entre sí") for o in vivos], \
                "Los precios que encontramos no coinciden entre sí; no se compara hasta tener uno más"
        vivos = quedan
    if not vivos:
        return [], apartados, None
    if len(vivos) < MIN_PRECIOS:
        o = vivos[0]
        donde = "un mercado en línea" if es_mercado_en_linea(o) else "una tienda"
        return vivos, apartados, (f"Solo un precio confirmado ({o.vendedor}, {donde}); "
                                  "falta un segundo para comparar")
    if len(vivos) == 2:
        a, b = sorted(x.precio_comparable for x in vivos)
        if b > a * SALTO_MAXIMO:
            return vivos, apartados, "Los dos precios que encontramos son muy distintos; falta un tercero para comparar"
        if all(es_mercado_en_linea(o) for o in vivos):
            return vivos, apartados, "Solo hay precios de mercados en línea; falta una tienda para comparar"
    return vivos, apartados, None


class _FilaAjustada:
    """El renglón de la corrida con la mediana de los precios que de verdad cuentan."""

    def __init__(self, fila, mediana, base):
        self._fila, self.mediana = fila, mediana
        self.estado = fila.estado if mediana else ("sin_precios" if fila.estado == "con_precios" else fila.estado)
        self.dif_lista_mediana_pct = precios.diferencia_pct(base, mediana) if mediana else None
        self.dif_membresia_mediana_pct = precios.diferencia_pct(fila.precio_membresia, mediana) if mediana else None

    def __getattr__(self, nombre):
        return getattr(self._fila, nombre)


# ---------------------------------------------------------------- lo calculado, reutilizado
# La pantalla y el reporte calculaban todo el catálogo (precios, validaciones, venta de 26 semanas) en cada clic, filtro y
# búsqueda (Diego, 2026-11-23: «es muy lenta la carga»; en producción 10 s por clic). Ahora se calcula una vez y se
# reutiliza mientras no cambie nada de lo que lo alimenta: renglones de corridas, marcas «Está mal», vigilados, venta
# cargada y costos; a los MINUTOS_VIGENCIA se recalcula aunque nada haya cambiado.
# Cuando cambia algo que no hizo una persona en la pantalla (un lote de la noche), se sigue mostrando lo anterior y se
# recalcula aparte; lo que hace una persona («Está mal», límite, vigilar) llama a olvidar() y se recalcula al momento.
MINUTOS_VIGENCIA = 15
_CALCULADO: dict = {"llave": None, "renglones": None, "hora": 0.0, "forzar": False, "aparte": False}
_CANDADO = threading.Lock()


def _llave(bd: Session) -> tuple:
    """Huella barata de todo lo que cambia el resultado (CHECKSUM_AGG de SQL Server)."""
    from datos.modelos import CostoArticulo, VentaSemanal
    from modulos.compras.modelos_precios import PrecioMarcaMal
    renglones = bd.execute(select(func.count(), func.max(PrecioCorridaProducto.corrida_producto_id),
                                  func.checksum_agg(func.binary_checksum(PrecioCorridaProducto.corrida_producto_id,
                                                                         PrecioCorridaProducto.estado,
                                                                         PrecioCorridaProducto.mediana)))).one()
    corridas = bd.execute(select(func.count(), func.checksum_agg(func.binary_checksum(
        PrecioCorrida.corrida_id, PrecioCorrida.estado)))).one()
    marcas = bd.execute(select(func.count(), func.max(PrecioMarcaMal.marca_id))).one()
    vigilados = bd.execute(select(func.count(), func.checksum_agg(func.binary_checksum(
        PrecioVigilado.producto_id, PrecioVigilado.activo, PrecioVigilado.limite_pct, PrecioVigilado.validacion)))).one()
    venta = bd.scalar(select(func.max(VentaSemanal.semana)))
    costos = bd.execute(select(func.count(), func.checksum_agg(func.binary_checksum(
        CostoArticulo.sku, CostoArticulo.costo_ultimo)))).one()
    return tuple(renglones) + tuple(corridas) + tuple(marcas) + tuple(vigilados) + (venta,) + tuple(costos)


def olvidar() -> None:
    """Una persona cambió algo («Está mal», un límite, vigilar): la siguiente consulta recalcula y espera el resultado."""
    _CALCULADO["llave"], _CALCULADO["forzar"] = None, True


def _vigente(llave: tuple) -> bool:
    return (_CALCULADO["llave"] == llave and _CALCULADO["renglones"] is not None
            and time.monotonic() - _CALCULADO["hora"] < MINUTOS_VIGENCIA * 60)


def _calcular(bd: Session, llave: tuple) -> list[Renglon]:
    con_resultado = set(ultimas_filas(bd))
    rs = renglones(bd, [p for p in universo(bd) if p.producto_id in con_resultado])
    for r in rs:  # que no dependan de la sesión de esta consulta
        for obj in (r.producto, r.fila, r.corrida, r.vigilado):
            if obj is not None and obj in bd:
                bd.expunge(obj)
    _CALCULADO.update(llave=llave, renglones=rs, hora=time.monotonic(), forzar=False)
    return rs


def _calcular_aparte() -> None:
    def tarea():
        from core.bd import _fabrica
        try:
            with _CANDADO, _fabrica()() as bd:
                llave = _llave(bd)
                if not _vigente(llave):
                    _calcular(bd, llave)
        except Exception:  # noqa: BLE001 - la siguiente consulta lo vuelve a intentar
            import logging
            logging.getLogger(__name__).exception("No se pudo recalcular el radar de precios aparte")
        finally:
            _CALCULADO["aparte"] = False

    if not _CALCULADO["aparte"]:
        _CALCULADO["aparte"] = True
        threading.Thread(target=tarea, name="radar-precios-tablero", daemon=True).start()


def renglones_vigentes(bd: Session) -> list[Renglon]:
    """Los renglones de todos los productos del radar con resultado, calculados una vez y reutilizados."""
    llave = _llave(bd)
    if _vigente(llave):
        return _CALCULADO["renglones"]
    if _CALCULADO["renglones"] is not None and not _CALCULADO["forzar"]:
        _calcular_aparte()  # cambió por la noche o venció: se ve lo anterior mientras se recalcula
        return _CALCULADO["renglones"]
    with _CANDADO:  # una sola consulta calcula; las demás esperan y usan lo mismo
        llave = _llave(bd)
        if _vigente(llave):
            return _CALCULADO["renglones"]
        return _calcular(bd, llave)


def universo(bd: Session) -> list[Producto]:
    """Productos del radar: los vigilados a mano y, con la noche sobre todo el catálogo, todos los activos."""
    from core.config import configuracion
    if configuracion().precios_nocturno_catalogo:
        q = (select(Producto).outerjoin(PrecioVigilado, PrecioVigilado.producto_id == Producto.producto_id)
             .where(Producto.activo == true(), (PrecioVigilado.vigilado_id.is_(None)) | (PrecioVigilado.activo == true())))
    else:
        q = (select(Producto).join(PrecioVigilado, PrecioVigilado.producto_id == Producto.producto_id)
             .where(PrecioVigilado.activo == true(), Producto.activo == true()))
    return list(bd.scalars(q))


def contra_tiendas(rs: list[Renglon], precio: str = LISTA) -> list[dict]:
    salida = []
    for t in precios.tiendas_clave():
        caros = baratos = parejos = 0
        for r in rs:
            base = r.segun(precio)[0]
            if t not in r.tiendas or not base:
                continue
            d = precios.diferencia_pct(base, r.tiendas[t][0])
            if d is None:
                continue
            if d > PAREJOS_PCT:
                caros += 1
            elif d < -PAREJOS_PCT:
                baratos += 1
            else:
                parejos += 1
        total = caros + baratos + parejos
        if not total:
            frase = "Todavía sin productos en común"
        elif caros >= baratos:
            frase = f"Más caros en {round(caros * 100 / total)} %"
        else:
            frase = f"Más baratos en {round(baratos * 100 / total)} %"
        salida.append({"nombre": t, "productos": total, "mas_caros": caros, "parejos": parejos, "mas_baratos": baratos,
                       "frase": frase})
    return salida


def actualizado(bd: Session) -> datetime | None:
    return bd.scalar(select(func.max(PrecioCorrida.terminado_en)).where(precios.REGULAR, PrecioCorrida.estado != "en_curso"))


def de_seleccion(bd: Session, producto_ids: list[int], marcas: list[str], categorias: list[str]) -> list[Producto]:
    """Productos sueltos, marcas completas y categorías completas, sin repetir."""
    vistos: dict[int, Producto] = {}
    if producto_ids:
        for i in range(0, len(producto_ids), 1500):
            for p in bd.scalars(select(Producto).where(Producto.producto_id.in_(producto_ids[i:i + 1500]))):
                vistos[p.producto_id] = p
    if marcas:
        for p in bd.scalars(select(Producto).where(Producto.marca.in_(marcas), Producto.activo == true())):
            vistos[p.producto_id] = p
    if categorias:
        for p in bd.scalars(select(Producto).where(Producto.subcategoria.in_(categorias), Producto.activo == true())):
            vistos[p.producto_id] = p
    return sorted(vistos.values(), key=lambda p: (p.marca or "", p.descripcion or p.sku))


def contenido(texto: str | None) -> dict:
    try:
        d = json.loads(texto or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}
