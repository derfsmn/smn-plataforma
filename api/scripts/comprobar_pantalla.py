"""Comprobar a mano los números de la pantalla del comité (Diego, 22 nov 2026: «quiero que pienses y analices en si
ese resultado es verdadero»).

Saca a un Excel los datos crudos con que se armó la pantalla de una evaluación, para rehacer cada número sin la
plataforma: los productos de su subcategoría con su venta, el tamaño de todas las subcategorías (de ahí sale la
«típica»), el inventario, los lanzamientos de 2026 contra los que se compara la Demanda, los parecidos, los precios de
afuera (y cuáles no cuentan) y el margen de la subcategoría. Sin IA, sin internet y sin escribir en la base.

Uso con Docker:
    docker compose exec api python -m scripts.comprobar_pantalla --producto wonu
    docker compose cp api:/app/comprobar_pantalla.xlsx .
Opciones: --producto wonu (o --evaluacion N)   --xlsx /app/comprobar_pantalla.xlsx   --sin-lanzamientos (más rápido)
"""
import argparse
from datetime import timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Inventario, Producto, VentaSemanal
from modulos.compras import pantalla_comite as pc
from modulos.compras import pronostico as pn
from modulos.compras import realidad_producto as rr
from modulos.compras.validacion_demanda import lugar_en
from nucleo.modelos import ahora
from scripts.validar_demanda import buscar_evaluacion


def _v(x):
    return float(x) if isinstance(x, Decimal) else x


def hojas(bd: Session, e, con_lanzamientos: bool = True) -> dict[str, list[list]]:
    v = rr.ventana(bd)
    p = pc._armar(bd, e, None, v)
    sub = e.subcategoria
    salida: dict[str, list[list]] = {}

    f = {x["factor"]: x for x in p["factores"]}
    c = p["cifras"]
    r = [["Número", "Valor en pantalla", "Cómo se comprueba"],
         ["Calificación total", p["puntaje"], "Suma de «Aporte» de los 4 factores (hoja Factores)"],
         ["Precio de venta con IVA", c["precio"], "Lo capturado en la idea o propuesta"],
         ["Costo sin IVA", c["costo"], "Lo capturado"],
         ["Margen %", c["margen"], "(precio / 1.16 − costo) / (precio / 1.16) × 100"],
         ["Porciones", c["porciones"], "Ficha técnica"],
         ["Precio por porción", c["por_porcion"], "precio / porciones"],
         [f"Venta 3 meses, prueba en {c['tiendas']} tiendas", c["venta_3m"],
          "Piezas por tienda al mes del pronóstico (mes 1, 2 y 3) × tiendas × precio / 1.16"],
         ["Venta 3 meses en toda la cadena", (p["demanda"].get("cadena") or {}).get("venta"),
          f"Igual, con {c.get('tiendas_cadena') or '—'} tiendas"],
         ["Productos activos en la subcategoría", p["categoria"]["productos"], "Renglones de la hoja Subcategoría"],
         ["Subcategoría típica", p["categoria"]["tipica"], "Mediana por producto de la hoja Tamaño de subcategorías"],
         ["Días de inventario", p["categoria"]["dias_inventario"], "Hoja Inventario"],
         ["Lugar entre lanzamientos (de 100)", p["demanda"]["lugar"], "Hoja Lanzamientos"],
         ["Margen de la subcategoría %", p["rentabilidad"]["margen_sub"], "Hoja Margen de la subcategoría"],
         ["Precio de en medio de afuera", (p["precio"]["mitades"].get("afuera") or {}).get("referencia"),
          "Mediana de los precios que sí cuentan (hoja Precios de afuera)"],
         ["Precio de en medio del anaquel", (p["precio"]["mitades"].get("anaquel") or {}).get("referencia"),
          "Mediana por porción (o por gramo) de los parecidos que cuentan × porciones (hoja Parecidos)"],
         ["Dictamen", p["dictamen"], ""]]
    salida["Resumen"] = r
    salida["Factores"] = [["Factor", "Peso", "Puntaje", "Aporte", "Qué dice", "Cómo se calculó"]] + [
        [x["nombre"], x["peso"], x["puntaje"], x["aporte"], x["valor"], x["calculo"]] for x in f.values()]

    if sub and v:
        productos = bd.scalars(select(Producto).where(Producto.activo == true(), Producto.subcategoria == sub)).all()
        venta = rr.venta_por_sku(bd, v, [x.sku for x in productos])
        filas = [["SKU", "Producto", "Marca", "Precio de lista con IVA", "Piezas al mes", "Tiendas", "Por tienda al mes",
                  "Últimas 13 semanas", "13 anteriores"]]
        for x in sorted(productos, key=lambda x: -(venta[x.sku].al_mes if x.sku in venta else 0)):
            s = venta.get(x.sku)
            filas.append([x.sku, x.descripcion, x.marca, _v(x.precio_lista_con_impuestos),
                          round(s.al_mes, 2) if s else 0, s.tiendas if s else 0, round(s.por_tienda_mes, 2) if s else 0,
                          round(s.recientes) if s else 0, round(s.anteriores) if s else 0])
        salida["Subcategoría"] = filas

        conteos = bd.execute(select(Producto.subcategoria, func.count()).where(
            Producto.activo == true(), Producto.subcategoria.is_not(None)).group_by(Producto.subcategoria)).all()
        por_producto = sorted(n for _, n in conteos for _ in range(n))
        salida["Tamaño de subcategorías"] = (
            [["Subcategoría", "Productos activos"]] + [[s, n] for s, n in sorted(conteos, key=lambda x: -x[1])]
            + [[], ["Mediana por producto (la típica)", median(por_producto) if por_producto else None]])

        corte = bd.scalar(select(func.max(Inventario.fecha_corte)))
        existencia = bd.scalar(select(func.sum(Inventario.existencia)).join(Producto, Producto.sku == Inventario.sku)
                               .where(Inventario.fecha_corte == corte, Producto.subcategoria == sub,
                                      Inventario.existencia > 0)) if corte else None
        desde = v.fin - timedelta(weeks=rr.SEMANAS_TENDENCIA - 1)
        vendidas = bd.scalar(select(func.sum(rr.NETAS)).join(Producto, Producto.sku == VentaSemanal.sku).where(
            VentaSemanal.semana >= desde, VentaSemanal.semana <= v.fin, Producto.subcategoria == sub))
        dias = rr.SEMANAS_TENDENCIA * 7
        salida["Inventario"] = [["Dato", "Valor"], ["Corte de inventario", corte], ["Existencia (piezas)", _v(existencia)],
                                [f"Piezas vendidas del {desde:%d/%m/%Y} al {v.fin:%d/%m/%Y}", _v(vendidas)],
                                ["Días", dias],
                                ["Días de inventario = existencia / (vendidas / días)",
                                 round(float(existencia) / (float(vendidas) / dias)) if existencia and vendidas else None]]

        t = rr.tendencia_subcategoria(bd, v, sub)
        salida["Tendencia de la subcategoría"] = [
            ["Dato", "Valor"], ["Piezas últimas 13 semanas", t[0] if t else None], ["Piezas 13 anteriores", t[1] if t else None],
            ["Cambio %", round((t[0] / t[1] - 1) * 100, 1) if t else None],
            ["Cuenta para la Demanda", "Sí" if t and abs((t[0] / t[1] - 1) * 100) > 10 else "No: el corte es ±10 %"]]

        importe, costo, n = bd.execute(
            select(func.sum(VentaSemanal.importe), func.sum(VentaSemanal.costo), func.count(VentaSemanal.sku.distinct()))
            .join(Producto, Producto.sku == VentaSemanal.sku)
            .where(*v.filtro(), Producto.subcategoria == sub, VentaSemanal.costo.is_not(None))).one()
        salida["Margen de la subcategoría"] = [
            ["Dato", "Valor"], ["Importe sin IVA", _v(importe)], ["Costo", _v(costo)], ["SKU", n],
            ["Margen % = (importe − costo) / importe × 100",
             round(float((importe - costo) / importe * 100), 1) if importe and costo else None]]

    if con_lanzamientos and p["demanda"]["rango"]:
        m = pn.entrenar(bd)
        lanz, del_depto = pn.lanzamientos_contra(bd, e.departamento)
        depto = set(bd.scalars(select(Producto.sku).where(Producto.departamento == e.departamento))) if del_depto else None
        nombres = dict(bd.execute(select(Producto.sku, Producto.descripcion)).all())
        esperado = p["demanda"]["rango"][1]
        filas = [["SKU", "Producto", "Subcategoría", "Primera venta", "Por tienda al mes (sem. 9-12)",
                  "Vendió igual o menos que el pronóstico", "Misma subcategoría"]]
        for x in sorted((x for x in m.lanzamientos if 12 in x.por_tienda and (depto is None or x.sku in depto)),
                        key=lambda x: x.por_tienda[12]):
            filas.append([x.sku, nombres.get(x.sku), x.subcategoria, x.inicio, round(x.por_tienda[12], 2),
                          "Sí" if x.por_tienda[12] <= esperado else "No", "Sí" if x.subcategoria == sub else ""])
        filas += [[], ["Pronóstico del producto", esperado], ["Lanzamientos", len(lanz)],
                  ["Lugar (de 100)", round(lugar_en(esperado, lanz)) if lanz else None],
                  ["Contra", "su departamento" if del_depto else "toda la cadena"]]
        salida["Lanzamientos"] = filas

    campos = ["sku", "descripcion", "marca", "formato", "precio", "precio_lista", "al_mes", "tiendas", "por_tienda",
              "porciones", "por_porcion", "tamano", "similitud", "cuenta", "por_que"]
    salida["Parecidos"] = [campos] + [[x.get(k) for k in campos] for x in p["parecidos"]]
    salida["Precios de afuera"] = [["Vendedor", "Publicación", "Precio", "Cuenta", "De dónde", "Liga"]] + [
        [a["vendedor"], a["titulo"], a["precio"], "Sí" if a.get("cuenta", True) else "No", a["fuente"], a["liga"]]
        for a in p["precio"]["afuera"]]
    return salida


def a_excel(ruta: str, titulo: str, datos: dict[str, list[list]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in datos.items():
        h = wb.create_sheet(nombre[:31])
        if nombre == "Resumen":
            h.append([titulo])
            h["A1"].font = Font(bold=True, size=14)
            h.append([])
        for f in filas:
            h.append([_v(x) for x in f])
        encabezado = 3 if nombre == "Resumen" else 1
        for celda in h[encabezado]:
            celda.font = Font(bold=True)
        h.column_dimensions["A"].width = 40
        h.column_dimensions["B"].width = 48
        h.column_dimensions["C"].width = 60
    wb.save(ruta)


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--evaluacion", type=int, default=None)
    a.add_argument("--producto", default="wonu")
    a.add_argument("--xlsx", default="/app/comprobar_pantalla.xlsx")
    a.add_argument("--sin-lanzamientos", action="store_true")
    args = a.parse_args()
    with Session(motor()) as bd:
        e = buscar_evaluacion(bd, args.evaluacion, args.producto)
        print(f"Evaluación {e.evaluacion_id}.")
        datos = hojas(bd, e, not args.sin_lanzamientos)
        bd.rollback()
    a_excel(args.xlsx, f"Comprobación de la pantalla · evaluación {e.evaluacion_id} · {ahora():%d/%m/%Y}", datos)
    print(f"Excel en {args.xlsx}")


if __name__ == "__main__":
    main()
