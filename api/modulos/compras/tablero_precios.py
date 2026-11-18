"""Lo que muestra la pantalla nueva del Radar de precios y el reporte a Excel (Diego, 2026-11-17: «quiero que ese radar
de precios sea muy fácil de ver»; «un reporte donde seleccione varios productos, individualmente o por marca o por
categoría y se bajaría en excel»).

Con lotes de noche cada producto tiene su último resultado en una corrida distinta: aquí se toma, por producto, su
último renglón terminado de una corrida del radar (no prueba, no radar de productos).
"""
import json
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
        dif = precios.dif_nuestro(f) if f and f.estado == "con_precios" else None
        base = precios.nuestro(f)[0] if f else None
        color = precios.color(dif, limites.get(p.producto_id)) if dif is not None else None
        membresia = f.precio_membresia if f else None
        dif_m = (f.dif_membresia_mediana_pct if f.dif_membresia_mediana_pct is not None
                 else precios.diferencia_pct(membresia, f.mediana)) if f and f.estado == "con_precios" else None
        r = Renglon(producto=p, fila=f, corrida=c, vigilado=vigilados.get(p.producto_id), color=color, dif=dif, base=base,
                    limite=precios.limite(limites.get(p.producto_id)),
                    evaluacion=ev.evaluar(p, f, limites.get(p.producto_id)), membresia=membresia, dif_membresia=dif_m,
                    color_membresia=precios.color(dif_m, limites.get(p.producto_id)) if dif_m is not None else None)
        for o, v in obs.get(p.producto_id, []):
            if no_cuenta(o, v, p.descripcion, base):
                continue
            t = precios.tienda_clave(o.vendedor, o.dominio, claves)
            if t:
                if t not in r.tiendas or o.precio_comparable < r.tiendas[t][0]:
                    r.tiendas[t] = (o.precio_comparable, o.liga)
            else:
                r.otras.append((o.vendedor, o.precio_comparable, o.liga))
        r.otras.sort(key=lambda x: x[1])
        salida.append(r)
    return salida


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
