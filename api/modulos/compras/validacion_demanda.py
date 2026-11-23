"""Prueba de la Demanda con lanzamientos reales (Diego, 20 nov 2026: «esa conclusión es muy general... validar»;
aprobó los cambios con «si, dale»).

A un lanzamiento de 2026 se le pronostica como si fuera nuevo: los parecidos que ya existían antes de su lanzamiento,
su venta de las 26 semanas anteriores y lo que aprendió el pronóstico de los demás lanzamientos (sin verse a sí mismo).
Luego se compara con lo que de verdad vendió en sus semanas 9 a 12. La usan el pronóstico (para decir «atinó el color
en X de N») y `scripts/validar_demanda.py`. Sin IA y sin escribir en la base."""
import logging
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datos.modelos import Producto, VentaSemanal
from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr

log = logging.getLogger("smn.compras.validacion_demanda")

SEMANAS_ANTES = 26
MIN_AJUSTE = 20  # lanzamientos probados para ajustar el rango con los errores reales
# Regla de clasificación de abril 2026 (suplementos deportivos, piezas por sucursal al mes); se usa igual para todos
CLASES = ((5, "AA"), (2.5, "A"), (1.75, "B"), (1, "C"), (0.75, "D"))


def clase(por_tienda_mes: float | None) -> str:
    if por_tienda_mes is None:
        return ""
    return next((c for corte, c in CLASES if por_tienda_mes >= corte), "E")


def calificacion(lugar: float) -> int:
    return max(0, min(100, round(50 + (lugar - 50) * rp.ESTIRA_DEMANDA)))


def zona(puntaje: int) -> str:
    return "rojo" if puntaje < 60 else "verde" if puntaje > 80 else "amarillo"


def lugar_en(valor: float, lista: list[float]) -> float:
    return sum(1 for x in lista if x <= valor) / len(lista) * 100 if lista else 0.0


def comparacion(lanzamientos: list[pn.Lanzamiento], productos: dict[str, Producto], departamento: str | None
                ) -> tuple[list[pn.Lanzamiento], bool]:
    """Los mismos lanzamientos con los que se califica la Demanda: los del departamento si son 20 o más; si no, todos."""
    todos = [x for x in lanzamientos if 12 in x.por_tienda]
    if departamento:
        suyos = [x for x in todos if (p := productos.get(x.sku)) and p.departamento == departamento]
        if len(suyos) >= 20:
            return suyos, True
    return todos, False


def primeras_ventas(bd: Session) -> dict[str, date]:
    return dict(bd.execute(select(VentaSemanal.sku, func.min(VentaSemanal.semana)).group_by(VentaSemanal.sku)).all())


def probar(bd: Session, x: pn.Lanzamiento, m: pn.Modelo, productos: dict[str, Producto], primera: dict[str, date],
           inicio_hist: date, mayoreo: set[str]) -> tuple[dict, list[dict]] | None:
    """Pronostica un lanzamiento como si fuera nuevo, con lo que había antes de su lanzamiento."""
    p = productos.get(x.sku)
    if not p or 12 not in x.por_tienda:
        return None
    s = rp.Sujeto(tipo="idea", nombre=p.descripcion or p.sku, marca=p.marca, departamento=p.departamento,
                  precio=p.precio_lista_con_impuestos)
    parecidos = [(q, sim) for q, sim in rp.buscar_parecidos(bd, s, p.subcategoria)
                 if q.sku != p.sku and not rp.es_mismo(s, q) and primera.get(q.sku, date.max) < x.inicio]
    usados = rp.parecidos_para_demanda(s, parecidos, None)
    antes = rr.Ventana(desde=max(inicio_hist, x.inicio - timedelta(weeks=SEMANAS_ANTES)),
                       fin=x.inicio - timedelta(weeks=1), mayoreo=mayoreo)
    venta = rr.venta_por_sku(bd, antes, [q.sku for q in usados]) if usados else {}
    base, base_de = None, ""
    if venta:
        base = sum(v.por_tienda_mes for v in venta.values()) / len(venta)
        base_de = f"{len(venta)} parecido(s)"
    elif p.subcategoria:
        de_sub = rr.venta_por_sku(bd, antes, [q.sku for q in productos.values()
                                              if q.subcategoria == p.subcategoria and q.sku != p.sku])
        if de_sub:
            base = median(v.por_tienda_mes for v in de_sub.values())
            base_de = f"lo típico de {p.subcategoria}"
    razones = pn._banda([y.razon[12] for y in m.lanzamientos if y is not x and 12 in y.razon])
    detalle = [{"lanzamiento": x.sku, "parecido": q.sku, "descripcion": q.descripcion,
                "precio": q.precio_lista_con_impuestos, "usado": q in usados,
                "por_tienda_antes": round(venta[q.sku].por_tienda_mes, 2) if q.sku in venta else None}
               for q, _ in parecidos]
    if not base or not razones:
        return None
    bajo, medio, alto = (base * r for r in razones)
    real = x.por_tienda[12]
    otros, del_depto = comparacion([y for y in m.lanzamientos if y is not x], productos, p.departamento)
    contra = [y.por_tienda[12] for y in otros]
    lp, lr = lugar_en(medio, contra), lugar_en(real, contra)
    dp, dr = calificacion(lp), calificacion(lr)
    return {"sku": p.sku, "descripcion": p.descripcion, "departamento": p.departamento,
            "subcategoria": p.subcategoria, "precio": p.precio_lista_con_impuestos, "lanzamiento": x.inicio,
            "base": round(base, 2), "base_de": base_de, "pron_bajo": round(bajo, 2), "pron_medio": round(medio, 2),
            "pron_alto": round(alto, 2), "real": round(real, 2), "dentro_rango": bajo <= real <= alto,
            "error_pct": round((medio - real) / real * 100) if real else None,
            "comparado_con": f"{len(contra)} del depto." if del_depto else f"{len(contra)} de la cadena",
            "lugar_pron": round(lp), "lugar_real": round(lr), "demanda_pron": dp, "demanda_real": dr,
            "zona_pron": zona(dp), "zona_real": zona(dr), "misma_zona": zona(dp) == zona(dr),
            "clase_pron": clase(medio), "clase_real": clase(real)}, detalle


def elegir(m: pn.Modelo, productos: dict[str, Producto], departamento: str | None, n: int) -> list[pn.Lanzamiento]:
    """Hasta la mitad del departamento pedido y el resto de toda la cadena, repartidos de los que más vendieron a los
    que menos (no solo los fáciles)."""
    con = sorted((x for x in m.lanzamientos if 12 in x.por_tienda and x.sku in productos),
                 key=lambda x: -x.por_tienda[12])

    def repartidos(lista: list[pn.Lanzamiento], k: int) -> list[pn.Lanzamiento]:
        if len(lista) <= k:
            return lista
        return [lista[round(i * (len(lista) - 1) / max(1, k - 1))] for i in range(k)]

    del_depto = repartidos([x for x in con if productos[x.sku].departamento == departamento], n // 2) if departamento else []
    resto = [x for x in con if x not in del_depto]
    return del_depto + repartidos(resto, n - len(del_depto))


def resumen(filas: list[dict]) -> dict:
    """Qué tan seguido atina: color de la Demanda, clase AA–E, dentro del rango y error típico."""
    n = len(filas)
    errores = [abs(f["error_pct"]) for f in filas if f["error_pct"] is not None]
    r = {"probados": n, "color": sum(f["misma_zona"] for f in filas),
         "clase": sum(f["clase_pron"] == f["clase_real"] for f in filas),
         "en_rango": sum(f["dentro_rango"] for f in filas),
         "error_tipico_pct": round(median(errores)) if errores else None}
    # Cuánto se equivocó de verdad (vendió ÷ pronóstico medio): con esto se ensancha el rango para que el pesimista y
    # el optimista cubran a 8 de cada 10 (20 nov 2026: con 100 lanzamientos iba de 0.36 a 2.27 veces el pronóstico)
    veces = [f["real"] / f["pron_medio"] for f in filas if f["pron_medio"]]
    if len(veces) >= MIN_AJUSTE:
        bajo, _, alto = pn._banda(veces)
        r["ajuste"] = [round(bajo, 2), round(alto, 2)]
    return r


def prueba(bd: Session, m: pn.Modelo, n: int = 40) -> dict | None:
    """La prueba con `n` lanzamientos repartidos de toda la cadena. La guarda el pronóstico un día junto al modelo."""
    productos = {p.sku: p for p in bd.scalars(select(Producto))}
    v = rr.ventana(bd)
    inicio = bd.scalar(select(func.min(VentaSemanal.semana)))
    if not v or not inicio:
        return None
    primera = primeras_ventas(bd)
    filas = []
    for x in elegir(m, {k: p for k, p in productos.items() if p.activo}, None, n):
        try:
            if r := probar(bd, x, m, productos, primera, inicio, v.mayoreo):
                filas.append(r[0])
        except Exception as ex:  # noqa: BLE001  un lanzamiento raro no tumba la prueba
            log.warning("Prueba de la Demanda: no se pudo probar %s: %s", x.sku, ex)
    return resumen(filas) if len(filas) >= pn.MIN_LANZAMIENTOS else None
