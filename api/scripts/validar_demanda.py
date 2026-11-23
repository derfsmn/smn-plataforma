"""Validar la Demanda con Wonu y con productos que ya lanzamos en 2026 (Diego, 20 nov 2026: «De cada 100 productos
nuevos que metimos en 2026, 74 vendieron más al arrancar... esa conclusión es muy general. Podríamos ponerlo y a partir
de ahí validar, usaremos WONU y algunos más como ejemplo»).

Hace dos cosas, sin IA, sin internet y sin escribir en la base:

1. Contra quién se compara un producto evaluado (por omisión la más reciente de Wonu): los lanzamientos de 2026 de su
   departamento, los de su misma subcategoría y los de precio parecido, cada uno con su nombre y lo que vendió en sus
   primeras 12 semanas. Con eso la frase deja de ser «74 de cada 100» y dice con qué productos reales se compara.
2. Prueba con lanzamientos reales: a cada uno se le pronostica como si fuera nuevo, con los parecidos que ya existían
   antes de su lanzamiento y su venta de las 26 semanas anteriores, y con lo que aprendió el pronóstico de los demás
   lanzamientos (sin verse a sí mismo). Luego se compara con lo que de verdad vendió en sus semanas 9 a 12.

Uso con Docker:
    docker compose exec api python -m scripts.validar_demanda
    docker compose cp api:/app/validar_demanda.xlsx .
Opciones: --producto wonu (o --evaluacion N)   --n 12 (lanzamientos de prueba)   --skus 12345,67890   --xlsx /app/validar_demanda.xlsx
"""
import argparse
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Producto, VentaSemanal
from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr
from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
from modulos.compras.validacion_demanda import (
    calificacion,
    clase,
    comparacion,
    elegir,
    lugar_en,
    primeras_ventas,
    probar,
    resumen,
)
from nucleo.modelos import ahora


@dataclass
class Fila:
    sku: str
    descripcion: str
    departamento: str | None
    subcategoria: str | None
    precio: Decimal | None
    inicio: date | None
    por_tienda_12: float | None
    grupos: list[str] = field(default_factory=list)


def frase(nombre: str, valor: float, lista: list[pn.Lanzamiento], del_depto: bool, departamento: str | None,
          misma_sub: list[Fila], precio_parecido: list[Fila], subcategoria: str | None) -> list[str]:
    """La frase general y las específicas que propone la pantalla (lo que pidió Diego el 20 nov)."""
    mas = sum(1 for x in lista if x.por_tienda[12] > valor)
    donde = f"del departamento {departamento}" if del_depto else "de toda la cadena"
    lineas = [(f"{nombre} vendería {valor:,.1f} piezas por tienda al mes. De los {len(lista)} productos {donde} que "
               f"lanzamos en 2026, {mas} vendieron más en sus primeras 12 semanas.")]
    if misma_sub:
        mas_sub = [f for f in misma_sub if (f.por_tienda_12 or 0) > valor]
        lineas.append(f"De los {len(misma_sub)} lanzamientos de {subcategoria}, {len(mas_sub)} vendieron más: "
                      + "; ".join(f"{f.descripcion} {f.por_tienda_12:,.1f}" for f in misma_sub[:6]) + ".")
    else:
        lineas.append(f"En 2026 no lanzamos nada de {subcategoria or 'su subcategoría'}: no hay un caso igual para "
                      f"comparar.")
    if precio_parecido:
        lineas.append(f"Los {len(precio_parecido)} lanzamientos de precio parecido vendieron: "
                      + "; ".join(f"{f.descripcion} (${f.precio:,.0f}) {f.por_tienda_12:,.1f}"
                                  for f in precio_parecido[:6]) + ".")
    return lineas


def buscar_evaluacion(bd: Session, evaluacion_id: int | None, texto: str) -> ProductoEvaluacion:
    """Por número de evaluación o, si no se da, la evaluación vigente más reciente de la idea cuyo nombre o marca
    contiene el texto (por omisión «wonu»)."""
    if evaluacion_id:
        e = bd.get(ProductoEvaluacion, evaluacion_id)
        if not e:
            raise SystemExit(f"No existe la evaluación {evaluacion_id}.")
        return e
    patron = f"%{texto}%"
    e = bd.scalar(select(ProductoEvaluacion).join(ProductoIdea, ProductoIdea.idea_id == ProductoEvaluacion.idea_id)
                  .where(ProductoEvaluacion.estado == "lista", ProductoEvaluacion.pronostico.is_not(None),
                         (ProductoIdea.nombre.like(patron)) | (ProductoIdea.marca.like(patron)))
                  .order_by(ProductoEvaluacion.vigente.desc(), ProductoEvaluacion.evaluacion_id.desc()))
    if not e:
        raise SystemExit(f"No encontré una evaluación terminada con pronóstico de una idea con «{texto}».")
    return e


def contra_lanzamientos(bd: Session, e: ProductoEvaluacion, m: pn.Modelo, productos: dict[str, Producto]
                        ) -> tuple[dict, list[Fila]]:
    from modulos.compras.reporte_producto import _sujeto

    evaluacion_id = e.evaluacion_id
    s, _, _ = _sujeto(bd, e)
    pron = pn.Pronostico.de_json(e.pronostico)
    rango = pron.rango(12) if pron else None
    if not rango:
        raise SystemExit(f"La evaluación {evaluacion_id} no tiene pronóstico a 12 semanas. Recalcúlala primero.")
    depto = s.departamento or e.departamento  # el mismo que usa la Demanda
    lista, del_depto = comparacion(m.lanzamientos, productos, depto)
    filas = []
    for x in sorted(lista, key=lambda x: -x.por_tienda[12]):
        p = productos.get(x.sku)
        f = Fila(x.sku, (p.descripcion if p else x.sku) or x.sku, p.departamento if p else None, x.subcategoria,
                 p.precio_lista_con_impuestos if p else None, x.inicio, x.por_tienda[12])
        if e.subcategoria and x.subcategoria == e.subcategoria:
            f.grupos.append("misma subcategoría")
        if p and e.subcategoria and x.subcategoria == e.subcategoria and rp.precio_cercano(s, p):
            f.grupos.append("precio parecido")
        f.grupos.append("vendió más" if x.por_tienda[12] > rango[1] else "vendió igual o menos")
        filas.append(f)
    misma = [f for f in filas if "misma subcategoría" in f.grupos]
    parecido = [f for f in filas if "precio parecido" in f.grupos]
    lugar = lugar_en(rango[1], [x.por_tienda[12] for x in lista])
    datos = {"nombre": s.nombre, "precio": s.precio, "departamento": depto, "subcategoria": e.subcategoria,
             "pronostico": rango, "base_de": pron.base_de, "lugar": lugar, "demanda": calificacion(lugar),
             "comparados": len(lista), "del_depto": del_depto,
             "frases": frase(s.nombre, rango[1], lista, del_depto, depto, misma, parecido, e.subcategoria)}
    return datos, filas


def a_excel(ruta: str, contexto: dict, filas: list[Fila], prueba: list[dict], parecidos: list[dict]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    h = wb.active
    h.title = "Resumen"
    h.append([f"Validación de la Demanda · {ahora():%d/%m/%Y}"])
    h["A1"].font = Font(bold=True, size=14)
    h.append([])
    h.append(["Producto evaluado", contexto["nombre"]])
    h.append(["Pronóstico a 12 semanas (piezas por tienda al mes)",
              f"{contexto['pronostico'][1]:,.2f} (de {contexto['pronostico'][0]:,.2f} a {contexto['pronostico'][2]:,.2f})"])
    h.append(["Sale de", contexto["base_de"]])
    h.append(["Lugar entre lanzamientos", f"{contexto['lugar']:.0f} de 100 ({contexto['comparados']} lanzamientos)"])
    h.append(["Demanda", contexto["demanda"]])
    h.append([])
    h.append(["Frases propuestas para la pantalla"])
    for linea in contexto["frases"]:
        h.append(["", linea])
    if prueba:
        h.append([])
        h.append(["Prueba con lanzamientos reales"])
        r = resumen(prueba)
        n = r["probados"]
        h.append(["Lanzamientos probados", n])
        h.append(["Cayeron dentro del rango (pesimista a optimista)", f"{r['en_rango']} de {n}"])
        h.append(["Misma zona de Demanda (rojo / amarillo / verde)", f"{r['color']} de {n}"])
        h.append(["Misma clase AA–E", f"{r['clase']} de {n}"])
        if r["error_tipico_pct"] is not None:
            h.append(["Error típico del pronóstico medio", f"{r['error_tipico_pct']} %"])
    h.column_dimensions["A"].width = 48
    h.column_dimensions["B"].width = 120

    c = wb.create_sheet("Contra quién se compara")
    c.append(["SKU", "Producto", "Departamento", "Subcategoría", "Precio", "Primera venta",
              "Piezas por tienda al mes (sem. 9-12)", "Clase", "Grupos"])
    for f in filas:
        c.append([f.sku, f.descripcion, f.departamento, f.subcategoria, float(f.precio) if f.precio else None,
                  f.inicio, round(f.por_tienda_12 or 0, 2), clase(f.por_tienda_12), ", ".join(f.grupos)])

    if prueba:
        t = wb.create_sheet("Prueba con lanzamientos")
        t.append(list(prueba[0]))
        for f in prueba:
            t.append([float(v) if isinstance(v, Decimal) else v for v in f.values()])
    if parecidos:
        q = wb.create_sheet("Parecidos usados")
        q.append(list(parecidos[0]))
        for f in parecidos:
            q.append([float(v) if isinstance(v, Decimal) else v for v in f.values()])
    for hoja in wb.worksheets[1:]:
        for celda in hoja[1]:
            celda.font = Font(bold=True)
    wb.save(ruta)


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--evaluacion", type=int, default=None)
    a.add_argument("--producto", default="wonu")
    a.add_argument("--n", type=int, default=12)
    a.add_argument("--skus", default="")
    a.add_argument("--xlsx", default="/app/validar_demanda.xlsx")
    args = a.parse_args()
    with Session(motor()) as bd:
        m = pn.entrenar(bd)
        if len(m.lanzamientos) < pn.MIN_LANZAMIENTOS:
            raise SystemExit(f"Solo hay {len(m.lanzamientos)} lanzamientos en la venta cargada.")
        productos = {p.sku: p for p in bd.scalars(select(Producto))}
        e = buscar_evaluacion(bd, args.evaluacion, args.producto)
        print(f"Evaluación {e.evaluacion_id} (idea {e.idea_id}).")
        contexto, filas = contra_lanzamientos(bd, e, m, productos)
        print("\n".join(contexto["frases"]), "\n")

        inicio_hist = bd.scalar(select(func.min(VentaSemanal.semana)))
        v = rr.ventana(bd)
        primera = primeras_ventas(bd)
        if args.skus:
            pedidos = {s.strip() for s in args.skus.split(",") if s.strip()}
            elegidos = [x for x in m.lanzamientos if x.sku in pedidos]
        else:
            elegidos = elegir(m, {k: p for k, p in productos.items() if p.activo}, contexto["departamento"], args.n)
        prueba, parecidos = [], []
        for x in elegidos:
            r = probar(bd, x, m, productos, primera, inicio_hist, v.mayoreo if v else set())
            if r:
                prueba.append(r[0])
                parecidos += r[1]
                f = r[0]
                print(f"{f['sku']} {str(f['descripcion'])[:40]:<40} pronóstico {f['pron_medio']:>5.1f} "
                      f"({f['pron_bajo']:.1f}–{f['pron_alto']:.1f})  real {f['real']:>5.1f}  "
                      f"Demanda {f['demanda_pron']:>3} vs {f['demanda_real']:>3}  {'✓' if f['misma_zona'] else '✗'}")
        bd.rollback()
    a_excel(args.xlsx, contexto, filas, prueba, parecidos)
    print(f"\nExcel en {args.xlsx}")


if __name__ == "__main__":
    main()
