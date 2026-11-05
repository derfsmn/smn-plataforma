"""Prueba de calibración del radar de productos (pedido de Diego, 2026-10-27: «sigo viendo muy bajos todos los
productos, puedes validar»).

Califica productos que ya vendemos como si fueran nuevos: se quitan a sí mismos de los parecidos, su precio es el de
lista y su margen el real de SMNBI. Si las escalas están bien, los que más venden deberían salir verdes o amarillos.
Toma 20 del cuarto que más vende, 20 de en medio y 20 del cuarto que menos vende. No escribe nada en la base, no
busca en internet ni usa la IA (la tendencia se calcula con palabras en común).

Uso con Docker:  docker compose exec api python -m scripts.calibrar_radar
Opciones:        --por-grupo 20   --csv /app/calibracion.csv
"""
import argparse
import csv
import random
from collections import Counter
from datetime import date
from statistics import mean, median

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Producto
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr

GRUPOS = ("más vendidos", "en medio", "menos vendidos")


def muestra(bd: Session, v: rr.Ventana, por_grupo: int) -> list[tuple[str, Producto]]:
    venta = rr.venta_por_sku(bd, v)
    activos = {p.sku: p for p in bd.scalars(select(Producto).where(Producto.activo == true()))}
    orden = sorted((s for s in venta if s in activos), key=lambda s: -venta[s].por_tienda_mes)
    n = len(orden)
    cortes = (orden[: n // 4], orden[n * 3 // 8: n * 5 // 8], orden[n * 3 // 4:])
    azar = random.Random(27)
    return [(g, activos[s]) for g, skus in zip(GRUPOS, cortes) for s in azar.sample(skus, min(por_grupo, len(skus)))]


def calificar(bd: Session, p: Producto, v: rr.Ventana, hoy: date) -> dict:
    s = rp.Sujeto(tipo="idea", nombre=p.descripcion or p.sku, marca=p.marca, departamento=p.departamento,
                  precio=p.precio_lista_con_impuestos, margen=rr.margen_sku(bd, v, p.sku))
    parecidos = [(x, sim) for x, sim in rp.buscar_parecidos(bd, s, p.subcategoria)
                 if x.producto_id != p.producto_id and not rp.es_mismo(s, x)]
    factores = {
        "demanda": rp.f_demanda(bd, s, parecidos, v),
        "rentabilidad": rp.f_rentabilidad(bd, s, p.subcategoria, v),
        "precio": rp.f_precio(s, parecidos),
        "tendencia": rp.f_tendencia(bd, s, hoy, p.subcategoria),
        "categoria": rp.f_categoria(bd, s, p.subcategoria, parecidos, v),
        "proveedor": rp.f_proveedor(bd, s, parecidos),
    }
    peso, _ = rp.pesos(bd)
    puntaje, confianza = rp.sumar(factores, peso)
    return {"sku": p.sku, "descripcion": p.descripcion, "subcategoria": p.subcategoria, "margen_real": s.margen,
            "puntaje": puntaje, "color": rp.color_de(puntaje, confianza), "confianza": confianza,
            **{f: x.puntaje for f, x in factores.items()}, **{f"{f}_dato": x.valor for f, x in factores.items()}}


def _resumen(valores: list) -> str:
    hay = [x for x in valores if x is not None]
    if not hay:
        return "sin datos"
    return f"prom {mean(hay):5.1f}  mediana {median(hay):5.1f}  ({len(hay)}/{len(valores)} con datos)"


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--por-grupo", type=int, default=20)
    a.add_argument("--csv", default="")
    args = a.parse_args()
    rp._senales_ia = lambda *_, **__: None  # sin IA: no gasta y no escribe en la base
    with Session(motor()) as bd:
        v = rr.ventana(bd)
        if not v:
            raise SystemExit("No hay ventas cargadas de SMNBI.")
        print(f"Calibración con la {v.texto()}.\n")
        filas = []
        for grupo, p in muestra(bd, v, args.por_grupo):
            filas.append({"grupo": grupo, **calificar(bd, p, v, date.today())})
        bd.rollback()
    if not filas:
        raise SystemExit("No hay productos activos con venta para la prueba.")

    for grupo in GRUPOS:
        g = [f for f in filas if f["grupo"] == grupo]
        if not g:
            continue
        colores = Counter(f["color"] for f in g)
        print(f"== {grupo} ({len(g)} productos): verde {colores['verde']}, amarillo {colores['amarillo']}, "
              f"rojo {colores['rojo']}")
        print(f"   puntaje       {_resumen([f['puntaje'] for f in g])}")
        for factor in rp.FACTORES:
            print(f"   {factor:<13} {_resumen([f[factor] for f in g])}")
        margenes = [float(f["margen_real"]) for f in g if f["margen_real"] is not None]
        if margenes:
            print(f"   margen real   prom {mean(margenes):5.1f} %  mediana {median(margenes):5.1f} %")
        print()
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
        print(f"Detalle por producto en {args.csv}")


if __name__ == "__main__":
    main()
