"""Examen de clasificación contra el catálogo (plan aprobado por Diego, 24 nov 2026)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from openpyxl import load_workbook
from sqlalchemy import update
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, Producto, VentaSemanal
from ia import puerta
from modulos.compras import examen_clasificacion as ex


def test_examen_esconde_al_producto_y_marca_errores_del_catalogo(monkeypatch, tmp_path):
    def sin_ia(*_a, **_k):
        raise puerta.ErrorIA("sin IA en la prueba")
    monkeypatch.setattr(puerta, "ejecutar", sin_ia)
    monkeypatch.setattr(puerta, "vectores", sin_ia)
    h = uuid.uuid4().hex[:6].upper()
    diab, dig, hierbas = f"DIABETES {h}", f"DIGESTIVO {h}", f"HIERBAS {h}"
    filas = [("BERBERINA 60 CAP", f"MA{h}", diab), ("BERBERINA 120 CAP", f"MA{h}", diab),
             ("BERBERINA HCL 90 CAP", f"MB{h}", diab), ("BERBERINA COMPLEX 30 CAP", f"MC{h}", diab),
             ("BERBERINA CANELA 60 CAP", f"MD{h}", diab), ("BERBERINA 60 ML", f"ME{h}", dig),
             ("BERBERINA PLUS 60 CAP", f"MG{h}", hierbas),
             ("AJO NEGRO 500 G", f"MF{h}", hierbas)]
    fin = date(2027, 4, 26)
    with Session(motor()) as bd:
        bd.execute(update(Producto).where(Producto.sku.like("EX-%")).values(activo=False))  # de corridas anteriores
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        prods = []
        for desc, marca, sub in filas:
            p = Producto(sku=f"EX-{uuid.uuid4().hex[:8]}", descripcion=desc, marca=marca, departamento=f"PREVENCION {h}",
                         rama=f"RAMA {sub}", subcategoria=sub, precio_lista_con_impuestos=Decimal("200"), origen="ETL",
                         activo=True)
            bd.add(p)
            prods.append(p)
        bd.flush()
        for semana in range(4):
            lunes = fin - timedelta(weeks=semana)
            for p in prods:
                bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=p.sku, tienda=f"T{h}", semana=lunes, empresa="EJ",
                                    piezas=Decimal(3), piezas_devueltas=Decimal(0), importe_bruto=Decimal(600),
                                    descuento=Decimal(0), importe=Decimal(600), costo=Decimal(300), tickets=1,
                                    carga_id=carga.carga_id))
        bd.commit()
        skus = {p.sku: p for p in prods}
        resultados, universo = ex.examinar(bd, None)
        mios = {r.sku: r for r in resultados if r.sku in skus}
        assert len(mios) == len(prods) and universo["examinables"] >= len(prods)
        primera = mios[prods[0].sku]
        # Se clasifica por su ingrediente aunque su otra presentación (120 cap) quede escondida
        assert primera.origen == "votos" and primera.seguridad == "segura" and primera.bien_sub
        assert primera.ingrediente == "berber"
        assert all(prods[0].producto_id != q.producto_id and prods[1].producto_id != q.producto_id
                   for q, _ in primera.parecidos)
        # Una berberina en cápsula en otra subcategoría que las demás cápsulas: posible error del catálogo, no cuenta
        assert mios[prods[6].sku].posible_error_catalogo
        # La de gotas está en otra subcategoría, pero es otra forma: no es error del catálogo (y no vota por las cápsulas)
        gotas = mios[prods[5].sku]
        assert not gotas.posible_error_catalogo and gotas.error is None
        # El ajo negro no tiene con quién compararse y sin IA queda sin clasificar: falla, no truena
        ajo = mios[prods[7].sku]
        assert ajo.error is None and not ajo.bien_sub and ajo.seguridad == "sin_evidencia"
        res = ex.resumen(list(mios.values()), [])
        assert res["posibles_errores_catalogo"] == 1 and res["contables"] == 7
        bien = sum(r.bien_sub for r in mios.values() if not r.posible_error_catalogo)
        assert res["medidos"]["subcategoria"] == round(bien / 7 * 100, 1) and res["pasa"]["subcategoria"] is False
        ruta = tmp_path / "examen.xlsx"
        ex.a_excel(str(ruta), "prueba", list(mios.values()), res, [], universo)
        wb = load_workbook(ruta)
        assert wb.sheetnames == ["Resumen", "Fallas", "Posibles errores del catálogo", "Parecidos dudosos", "Casos",
                                 "Detalle"]
        assert wb["Posibles errores del catálogo"].max_row == 2 and wb["Fallas"].max_row == 1 + 7 - bien
        # Si se reinicia la API, el examen sigue desde lo guardado y no recalcula (Diego, 25 nov 2026)
        guardado = tmp_path / "avance.json"
        r1, _ = ex.examinar(bd, None, guardar=guardado)
        assert guardado.exists()

        def no_otra_vez(*a, **k):
            raise AssertionError("ya estaba guardado")

        monkeypatch.setattr(ex, "examinar_uno", no_otra_vez)
        r2, _ = ex.examinar(bd, None, guardar=guardado)
        foto = lambda rs: [(r.sku, r.sub, r.origen, r.bien_sub, [q.producto_id for q, _ in r.parecidos]) for r in rs]  # noqa: E731
        assert foto(r2) == foto(r1)
        bd.rollback()
