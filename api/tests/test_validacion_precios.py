"""Validación automática, «Está mal», lotes de noche, evaluación y reporte a Excel del Radar de precios (2026-11-17).
DataForSEO y la IA se simulan. Productos, vendedores y precios son ficticios (SKU con prefijo EJP)."""
import io
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos.modelos import CostoArticulo, Producto
from modulos.compras import tablero_precios as tb
from modulos.compras import coincidencia as co
from modulos.compras import evaluacion_precios as ev
from modulos.compras import nocturno_precios as noche
from modulos.compras import precios
from modulos.compras import validacion_precios as val
from modulos.compras.modelos_precios import (PrecioCorrida, PrecioObservacion, PrecioValidacion, PrecioVigilado)
from nucleo.modelos import ahora
from tests.test_precios import correr, fila, item, limpio, producto, vendedor, vigilar  # noqa: F401 - limpio es fixture


def _p(descripcion, marca="NATUREJ", barras=None):
    return Producto(sku="EJ", descripcion=descripcion, marca=marca, codigo_barras=barras)


def _i(titulo, ean=None, persona=False):
    return val.Identidad(titulo=titulo, extra=[], ean=ean, imagen=None, origen="tienda", persona=persona)


def test_comprobaciones_en_palabras():
    marcas = {"naturej", "otramarca"}
    p = _p("PROTEINA EJ VAINILLA 510 G", barras="7500000000123")
    # Mismo código de barras: validado aunque el título no diga más
    c = val.comprobar(p, _i("Proteína EJ", ean="07500000000123"), marcas)
    assert c["codigo"]["estado"] == "ok" and val.decidir(c, False)[0] == val.VALIDADO
    # Otro sabor y otro tamaño no cuentan, con su motivo
    c = val.comprobar(p, _i("Naturej Proteína EJ Chocolate 510 g"), marcas)
    assert val.decidir(c, False) == (val.NO_CUENTA, "Otro sabor (chocolate)")
    c = val.comprobar(p, _i("Naturej Proteína EJ Vainilla 1 kg"), marcas)
    assert val.decidir(c, False)[0] == val.NO_CUENTA and c["contenido"]["estado"] == "no"
    c = val.comprobar(p, _i("Otramarca Proteína EJ Vainilla 510 g"), marcas)
    assert val.decidir(c, False) == (val.NO_CUENTA, "Es de otra marca (otramarca)")
    c = val.comprobar(p, _i("Naturej Proteína EJ Vainilla 510 g + shaker"), marcas)
    assert val.decidir(c, False)[0] == val.NO_CUENTA
    # Marca, sabor, contenido y una pieza: validado
    c = val.comprobar(p, _i("Naturej Proteína EJ Vainilla 510 g"), marcas)
    assert val.decidir(c, False) == (val.VALIDADO, "Misma marca, variante, contenido y piezas")
    # Sin contenido en el título: dudoso (no cuenta, se reintenta)
    c = val.comprobar(p, _i("Naturej Proteína EJ Vainilla"), marcas)
    assert val.decidir(c, False)[0] == val.DUDOSO and "contenido" in val.decidir(c, False)[1]
    # Con la foto igual sí cuenta; si lo eligió una persona, también
    c["foto"] = val._ok("La IA ve el mismo empaque")
    assert val.decidir(c, False)[0] == val.VALIDADO
    assert val.decidir(val.comprobar(p, _i("Naturej Proteína EJ Vainilla"), marcas), True)[0] == val.VALIDADO
    # «Clásico» es la línea base; «Premier» es otra variante si la nuestra dice otra
    d = _p("DEMOGRASS EJ 30 CAP")
    assert val.comprobar(d, _i("Naturej Demograss EJ clásico 30 cápsulas"), marcas)["variante"]["estado"] == "ok"
    assert val.comprobar(_p("DEMOGRASS EJ PLUS 30 CAP"), _i("Naturej Demograss EJ Premier 30 cápsulas"),
                         marcas)["variante"]["estado"] == "no"


def test_validacion_en_la_corrida_esta_mal_y_salto(limpio, monkeypatch, admin):
    a = producto("PROTEINA VEGETAL EJ VAINILLA 510 G", lista="650.00", mem="600.00")
    vigilar(a)
    limpio.resultados["NATUREJ PROTEINA VEGETAL EJ VAINILLA 510 G"] = [item("Naturej Proteína Vegetal EJ Vainilla 510 g", "G-A")]
    limpio.vendedores["G-A"] = [vendedor("Liverpool", 600, "liverpool.com.mx"), vendedor("Amazon", 630, "amazon.com.mx"),
                                vendedor("Farmacia EJ", 610, "farmacia.ej", currency="USD")]
    c = correr()
    f = fila(c.corrida_id, a)
    assert f.estado == "con_precios" and f.vendedores == 2 and f.mediana == Decimal("615.00")
    with Session(motor()) as bd:
        vals = {o.vendedor: v for o, v in bd.execute(
            select(PrecioObservacion, PrecioValidacion).join(PrecioValidacion, PrecioValidacion.observacion_id == PrecioObservacion.observacion_id)
            .where(PrecioObservacion.producto_id == a))}
        assert vals["Liverpool"].resultado == val.VALIDADO and vals["Farmacia EJ"].resultado == val.NO_CUENTA
        v = bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == a))
        assert v.validacion == "validado" and v.proxima_revision > ahora() + timedelta(days=5)
    # La pantalla se calcula una vez y se reutiliza mientras nada cambie
    def mercado():
        return next(x for x in admin.get("/api/compras/precios/tablero?grupo=todos").json()["filas"] if x["producto_id"] == a)["mercado"]
    assert mercado() == "615.00"
    original = tb.renglones
    monkeypatch.setattr(tb, "renglones", lambda *x, **k: (_ for _ in ()).throw(AssertionError("recalculó sin cambios")))
    assert mercado() == "615.00"
    monkeypatch.setattr(tb, "renglones", original)
    # Compras: «Está mal» en Amazon (otro producto): deja de contar al momento
    detalle = admin.get(f"/api/compras/precios/productos/{a}/validacion").json()
    amazon = next(x for x in detalle["precios"] if x["vendedor"] == "Amazon")
    assert amazon["cuenta"] and {x["clave"] for x in amazon["comprobaciones"]} == set(val.COMPROBACIONES)
    assert admin.post(f"/api/compras/precios/productos/{a}/esta-mal",
                      json={"observacion_ids": [amazon["observacion_id"]], "motivo": "otro"}).status_code == 400
    r = admin.post(f"/api/compras/precios/productos/{a}/esta-mal",
                   json={"observacion_ids": [amazon["observacion_id"]], "motivo": "otro_producto"})
    assert r.status_code == 200
    d = r.json()
    assert next(x for x in d["precios"] if x["vendedor"] == "Amazon")["marcado_mal"] and d["marcas"][0]["motivo_texto"] == "Es otro producto"
    assert fila(c.corrida_id, a).mediana == Decimal("600.00")
    # la marca cambió la huella: se recalculó solo. Queda un solo precio: sin color ni acción (referencia débil)
    assert mercado() is None
    renglon = next(x for x in admin.get("/api/compras/precios/tablero?grupo=todos").json()["filas"] if x["producto_id"] == a)
    assert renglon["accion_texto"] == "Referencia débil" and "Solo un precio" in renglon["detalle"]
    # La siguiente noche Amazon sigue sin contar y Liverpool brinca 40 %: esa noche no cuenta
    limpio.vendedores["G-A"] = [vendedor("Liverpool", 840, "liverpool.com.mx"), vendedor("Amazon", 630, "amazon.com.mx"),
                                vendedor("Walmart", 605, "walmart.com.mx"), vendedor("Soriana", 615, "soriana.com")]
    c2 = correr()
    with Session(motor()) as bd:
        vals = {o.vendedor: v for o, v in bd.execute(
            select(PrecioObservacion, PrecioValidacion).join(PrecioValidacion, PrecioValidacion.observacion_id == PrecioObservacion.observacion_id)
            .where(PrecioObservacion.corrida_id == c2.corrida_id))}
    assert vals["Amazon"].resultado == val.NO_CUENTA and vals["Amazon"].motivo.startswith("Compras lo marcó")
    assert vals["Liverpool"].resultado == val.DUDOSO and "brincó" in vals["Liverpool"].motivo
    assert fila(c2.corrida_id, a).mediana == Decimal("610.00")
    # Un lote de la noche no hace esperar: se ve lo anterior y se recalcula aparte
    assert mercado() is None
    for _ in range(100):
        if not tb._CALCULADO["aparte"]:
            break
        time.sleep(0.1)
    assert mercado() == "610.00"
    # A la tercera sigue en 840: ya no brinca contra la anterior y cuenta
    c3 = correr()
    assert fila(c3.corrida_id, a).vendedores == 3
    # Deshacer la marca es de quien administra
    marca = d["marcas"][0]["id"]
    assert admin.delete(f"/api/compras/precios/productos/{a}/esta-mal/{marca}").json()["marcas"][0]["activo"] is False


def test_mercado_confiable_un_precio_y_precios_que_se_salen():
    """Diagnóstico de producción (23 nov): la mayoría de los errores grandes venían de un solo precio o de uno que se salía."""
    from types import SimpleNamespace as N

    def o(vendedor, precio, dominio=""):
        return N(vendedor=vendedor, dominio=dominio, precio_comparable=Decimal(precio))
    # Un solo precio: se muestra pero no se compara
    quedan, apartados, aviso = tb.mercado_confiable([o("Mercado Libre", 399, "mercadolibre.com.mx")])
    assert len(quedan) == 1 and "Solo un precio" in aviso and "mercado en línea" in aviso
    # Dos muy distintos: falta un tercero
    assert "muy distintos" in tb.mercado_confiable([o("Chedraui", 79), o("Walmart", 160)])[2]
    # Dos solo de mercados en línea: falta una tienda
    assert "mercados en línea" in tb.mercado_confiable([o("Amazon", 100, "amazon.com.mx"), o("SHEIN", 105)])[2]
    # Tres o más: el que se sale mucho de los demás se aparta y no cuenta
    quedan, apartados, aviso = tb.mercado_confiable([o("Walmart", 131), o("Soriana", 140), o("Chedraui", 150), o("Amazon", 399)])
    assert aviso is None and [x.vendedor for x, _ in apartados] == ["Amazon"] and len(quedan) == 3
    assert tb._mediana([x.precio_comparable for x in quedan]) == Decimal("140.00")
    # Todos distintos entre sí: no hay mercado claro
    assert "no coinciden" in tb.mercado_confiable([o("A", 50), o("B", 120), o("C", 300)])[2]
    # Una tienda cuenta una vez, con su precio más bajo (plan del 24 nov, caso 3 Mag Blend)
    unicos = tb.una_por_tienda([o("Walmart", 349, "walmart.com.mx"), o("Walmart Express", 220, "walmart.com.mx"),
                                o("Chedraui", 250), o("chedraui ", 260), o("Farmacia Ficticia EJ", 240)], ["Walmart", "Chedraui"])
    assert [(x.vendedor, x.precio_comparable) for x in unicos] == [("Walmart Express", 220), ("Chedraui", 250),
                                                                  ("Farmacia Ficticia EJ", 240)]


def test_lote_de_noche_por_clase_y_venta(limpio, monkeypatch):
    cfg = configuracion()
    hora = datetime.now(precios.zona()).hour
    monkeypatch.setattr(cfg, "precios_nocturno_desde", hora)
    monkeypatch.setattr(cfg, "precios_nocturno_hasta", (hora + 1) % 24)
    monkeypatch.setattr(cfg, "precios_nocturno_lote", 2)
    monkeypatch.setattr(cfg, "precios_nocturno_catalogo", False)
    ids = [producto(f"PRODUCTO NOCHE EJ {n} 100 G") for n in range(3)]
    vigilar(*ids)
    with Session(motor()) as bd:
        for pid, clase in zip(ids, ("C", "AA", "A")):
            bd.get(Producto, pid).clasificacion = clase
        bd.commit()
        assert noche.candidatos(bd, 3) == [ids[1], ids[2], ids[0]]
    for n in range(3):
        limpio.resultados[f"NATUREJ PRODUCTO NOCHE EJ {n} 100 G"] = [item(f"Naturej Producto Noche EJ {n} 100 g", f"G-{n}")]
        limpio.vendedores[f"G-{n}"] = [vendedor("Walmart", 120, "walmart.com.mx")]
    lanzadas = []
    monkeypatch.setattr(precios, "correr_aparte", lambda cid: lanzadas.append(cid))
    with Session(motor(), expire_on_commit=False) as bd:
        c = noche.revisar_nocturno(bd)
        assert c and c.origen == noche.ORIGEN and precios.de_lista(bd, c)[0][1].producto_id == ids[1]
        precios.correr(bd, c)
        # Otro lote ya no toma a los validados: sigue el que faltaba
        assert noche.candidatos(bd, 3) == [ids[0]]
        a = noche.avance(bd)
        assert a.validados == 2 and a.sin_revisar == 1 and a.por_clase["AA"] == {"total": 1, "validados": 1}
    # Fuera de la ventana no arranca nada
    monkeypatch.setattr(cfg, "precios_nocturno_desde", (hora + 2) % 24)
    monkeypatch.setattr(cfg, "precios_nocturno_hasta", (hora + 3) % 24)
    with Session(motor()) as bd:
        assert noche.revisar_nocturno(bd) is None
    assert noche.en_ventana(23, 18, 6) and noche.en_ventana(5, 18, 6) and not noche.en_ventana(6, 18, 6)


def test_evaluacion_accion_sugerida():
    p = Producto(sku="EJP-EV", descripcion="EJ", departamento=None, precio_lista=Decimal("100"),
                 precio_lista_con_impuestos=Decimal("116"), clasificacion="AA")

    class F:  # renglón de corrida mínimo
        estado, precio_lista, precio_tienda, precio_membresia = "con_precios", Decimal("116"), None, None
        dif_lista_mediana_pct = None

    def evaluar(mediana, costo, minimo=Decimal("31")):
        f = F()
        f.mediana = Decimal(mediana)
        f.dif_lista_mediana_pct = precios.diferencia_pct(f.precio_lista, f.mediana)
        e = ev.Evaluador.__new__(ev.Evaluador)
        e.ventas, e.costos, e.medianas, e.minimos = {}, ({"EJP-EV": Decimal(costo)} if costo else {}), {}, {None: minimo}
        return e.evaluar(p, f, Decimal("5"))
    # 16 % más caros, con margen de sobra: bajar a la mediana
    r = evaluar("100", "50")
    assert r.accion == "bajar" and r.precio_sugerido == Decimal("99.90") and r.indice == Decimal("116.0")
    # Bajar a la mediana rompe el 31 %: bajar hasta el mínimo y negociar costo
    r = evaluar("100", "60")
    assert r.accion == "bajar_y_negociar" and r.precio_sugerido == Decimal("100.87") and r.costo_meta == Decimal("59.48")
    # Sin espacio: negociar costo
    assert evaluar("100", "75").accion == "negociar"
    # 15 % abajo del mercado con margen bajo: revisar si se sube
    assert evaluar("136.47", "75").accion == "subir"
    assert evaluar("116", "50").accion == "mantener"
    assert co  # el módulo de coincidencia sigue importable para las reglas


def test_tablero_y_reporte_a_excel(limpio, admin, tmp_path):
    a = producto("COLAGENO EJ 300 G", lista="389.00", mem="300.00")
    b = producto("CREATINA EJ 450 G", lista="599.00", mem="550.00", marca="BIRDMAN EJ")
    producto("GLUTAMINA EJ\x0b 300 G", lista="450.00", marca="BIRDMAN EJ")  # carácter de control del catálogo, sin revisar
    vigilar(a, b)
    with Session(motor()) as bd:
        for pid in (a, b):
            bd.get(Producto, pid).subcategoria = "PROTEINAS EJ"
        bd.commit()
    limpio.resultados["NATUREJ COLAGENO EJ 300 G"] = [item("Naturej Colágeno EJ 300 g", "G-COL")]
    limpio.resultados["BIRDMAN EJ CREATINA EJ 450 G"] = [item("Birdman EJ Creatina EJ 450 g", "G-CRE")]
    limpio.vendedores["G-COL"] = [vendedor("Walmart", 300, "walmart.com.mx"), vendedor("Chedraui", 310, "chedraui.com.mx")]
    limpio.vendedores["G-CRE"] = [vendedor("Soriana", 600, "soriana.com")]
    correr()
    t = admin.get("/api/compras/precios/tablero?grupo=todos").json()
    assert t["cuadros"]["rojo"] >= 1 and {x["nombre"] for x in t["tiendas"]} >= {"Walmart", "Chedraui"}
    col = next(x for x in t["filas"] if x["producto_id"] == a)
    assert col["color"] == "rojo" and col["tiendas"]["Walmart"] == "300.00" and col["accion"] == "bajar"
    assert any(x["producto_id"] == a for x in admin.get("/api/compras/precios/tablero").json()["filas"])
    # Segunda comparación: el precio membresía contra el mismo mercado
    assert col["membresia"] == "300.00" and col["color_membresia"] == "verde" and "Con membresía ($300.00)" in col["detalle"]
    rojos = lambda precio: {x["producto_id"] for x in admin.get(f"/api/compras/precios/tablero?grupo=rojo&precio={precio}").json()["filas"]}
    assert a in rojos("lista") and a not in rojos("membresia")
    m = admin.get("/api/compras/precios/tablero?grupo=todos&precio=membresia").json()
    assert m["cuadros"]["verde"] > t["cuadros"]["verde"]
    # Por agente (Diego, 25 nov): el proveedor del producto trae el agente de tblProveedores
    from datos.modelos import Carga, Proveedor
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        bd.merge(Proveedor(proveedor="PEJ01", nombre="Proveedor Ficticio EJ", agente="AGEJ", carga_id=carga.carga_id))
        bd.get(Producto, a).codigo_proveedor = "PEJ01"
        bd.commit()
    tb.olvidar()
    g = admin.get("/api/compras/precios/tablero?grupo=todos&agente=AGEJ").json()
    assert g["agentes"] == ["AGEJ"] and [x["producto_id"] for x in g["filas"]] == [a] and g["filas"][0]["agente"] == "AGEJ"
    assert g["catalogo"] == 1 and g["comparados"] == 1
    assert sum(t["sin_comparar"].values()) == t["cuadros"]["sin_referencia"]
    assert b in {x["producto_id"] for x in admin.get("/api/compras/precios/tablero?grupo=todos&agente=sin_agente").json()["filas"]}
    # Dinero en juego: venta del mes × diferencia; sin referencia, 0. De inicio vienen 20, ordenados por eso
    assert Decimal(col["en_juego"]) >= 0 and admin.get("/api/compras/precios/tablero").json()["por_pagina"] == 20
    # El buscador encuentra cualquier producto aunque no pida acción
    assert [x["producto_id"] for x in admin.get("/api/compras/precios/tablero?q=CREATINA EJ").json()["filas"]] == [b]
    d = admin.get(f"/api/compras/precios/tablero/producto/{a}").json()
    assert d["producto_id"] == a and d["agente"] == "AGEJ" and d["mercado"] == col["mercado"]
    assert admin.get("/api/compras/precios/tablero/producto/999999").status_code == 404
    # «Descargar Excel» lleva todo lo filtrado
    r = admin.get("/api/compras/precios/tablero/excel?grupo=todos&agente=AGEJ")
    assert r.status_code == 200 and "Agente_AGEJ" in r.headers["content-disposition"]
    assert admin.get("/api/compras/precios/tablero/excel?agente=NADIE").status_code == 400
    with Session(motor()) as bd:  # no dejar el proveedor ficticio a otras pruebas
        bd.get(Producto, a).codigo_proveedor = None
        bd.delete(bd.get(Proveedor, "PEJ01"))
        bd.commit()
    tb.olvidar()
    # Reporte: una marca completa más la categoría (sin repetir) y un producto suelto
    opciones = admin.get("/api/compras/precios/reporte/opciones?modo=marca&q=BIRDMAN EJ").json()
    assert opciones and opciones[0]["clave"] == "BIRDMAN EJ"
    sel = {"marcas": ["BIRDMAN EJ"], "categorias": ["PROTEINAS EJ"], "producto_ids": [a], "hojas": ["resumen", "tiendas", "accion", "historial"]}
    assert admin.post("/api/compras/precios/reporte/contar", json=sel).json()["productos"] == 3
    r = admin.post("/api/compras/precios/reporte/excel", json=sel)
    assert r.status_code == 200
    libro = load_workbook(io.BytesIO(r.content))
    assert libro.sheetnames == ["Portada", "Resumen por marca", "Resumen por categoría", "Precio por tienda", "Qué conviene",
                                "Historial 8 semanas"]
    h = libro["Precio por tienda"]
    encabezados = [c.value for c in h[1]]
    fila_col = next(r for r in h.iter_rows(min_row=2) if r[1].value == "COLAGENO EJ 300 G")
    assert fila_col[encabezados.index("Walmart")].value == 300
    assert fila_col[encabezados.index("Cómo estamos")].value == "Más caro"
    assert fila_col[encabezados.index("Precio membresía")].value == 300
    assert fila_col[encabezados.index("Cómo estamos con membresía")].value == "Igual o más barato"
    assert fila_col[encabezados.index("Walmart liga")].hyperlink.target == "https://walmart.com.mx/p"
    # Guardar la selección y bajarla con un clic
    g = admin.post("/api/compras/precios/selecciones", json={"nombre": "Proteínas EJ", "seleccion": sel}).json()
    assert g["productos"] == 3
    assert admin.get(f"/api/compras/precios/selecciones/{g['id']}/excel").status_code == 200
    assert [s["nombre"] for s in admin.get("/api/compras/precios/selecciones").json()] == ["Proteínas EJ"]
    assert admin.delete(f"/api/compras/precios/selecciones/{g['id']}").status_code == 200
    # El diagnóstico de producción corre sobre los mismos datos (solo lee)
    from scripts import diagnostico_radar_precios as dg
    dg.SALIDA = str(tmp_path / "diag.json")
    dg.main()
    diag = json.loads((tmp_path / "diag.json").read_text(encoding="utf-8"))
    assert diag["conteos"]["con_resultado"] >= 2 and "pantalla_resumen_completa" in diag["tiempos_seg"]
    assert isinstance(diag["tiempos_seg"]["pantalla_resumen_completa"], float)
    with Session(motor()) as bd:
        assert bd.scalar(select(PrecioCorrida).where(PrecioCorrida.origen == "manual"))
        assert CostoArticulo  # el costo se toma de la tabla de SMNBI cuando existe
