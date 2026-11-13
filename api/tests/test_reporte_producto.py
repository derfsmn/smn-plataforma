"""Reporte de producto nuevo en PDF (Diego, 2026-11-13: «este reporte ayudaría mucho a entregarlo para cada producto
validado»). Casos fijos: Wonu Creatina + Inositol y Creanatomy creatina 390 g, con un catálogo y una venta FICTICIOS que
copian la forma del caso real (sobres de creatina que se venden bien, creatinas para mujer en bote que se venden lento
y otro producto de la misma marca en sobre)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import update
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, Producto, Tienda, VentaSemanal
from modulos.compras import radar_productos as rp
from modulos.compras import reporte_producto as rep
from tests.test_productos import sincrono  # noqa: F401

R = "/api/compras/productos"
FIN = date(2027, 3, 29)  # lunes; la misma última semana que usan las pruebas del radar


def _texto(pdf: bytes) -> str:
    return " ".join((p.extract_text() or "") for p in PdfReader(BytesIO(pdf)).pages).replace("\n", " ")


@pytest.fixture(scope="module")
def catalogo_creatinas(base_de_pruebas):
    """Catálogo ficticio de creatinas. Devuelve {nombre corto: sku}. Piezas por tienda al mes como en SMNBI jul–sep:
    sobre de creatina 8, sobre de la marca 6, creatina para mujer en bote 2, creatina líder 16."""
    h = uuid.uuid4().hex[:5]
    filas = {  # nombre: (descripción, marca, subcategoría, clasificación, precio, piezas por tienda por semana, tiendas)
        "sobre": (f"QUENUT{h} CREATINA CREAPURE SOBRE 5 G", f"QUENUT{h}", "CREATINA", "A", "25.50", 2, 6),
        "mujer": (f"BIRD{h} CREATINE FOR WOMEN 348 G", f"BIRD{h}", "CREATINA", "D", "578.10", 0.5, 3),
        "inositol": (f"UPX{h} CREATINA COLAGENO INOSITOL 545 G", f"UPX{h}", "CREATINA", "E", "420.60", 0.5, 3),
        "lider": (f"BIRD{h} CREATINA MONOHIDRATADA 450 G", f"BIRD{h}", "CREATINA", "AA", "502.90", 4, 6),
        "marca": (f"WONU{h} COLAGENO ELECTROLITOS SOBRE 12 G", f"WONU{h}", "ELECTROLITOS", "B", "26.50", 1.5, 6),
        "capsulas": (f"OREG{h} OREGANO 60 CAPS", f"OREG{h}", "DIGESTIVO", "C", "180", 1, 2),
    }
    skus = {}
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        tiendas = [f"W{h}{i}" for i in range(6)]
        bd.add_all([Tienda(almacen=t, nombre=f"Tienda ficticia {i}", categoria=("AA", "A", "A", "B", "B", "C")[i],
                           carga_id=carga.carga_id) for i, t in enumerate(tiendas)])
        for clave, (desc, marca, sub, clas, precio, ritmo, n) in filas.items():
            sku = f"RW-{uuid.uuid4().hex[:8]}"
            skus[clave] = sku
            bd.add(Producto(sku=sku, descripcion=desc, marca=marca, departamento="DEPORTES (ejemplo)", rama="NUTRICION DEPORTIVA",
                            subcategoria=sub, clasificacion=clas, precio_lista_con_impuestos=Decimal(precio), origen="ETL",
                            activo=True))
            base = Decimal(precio) / Decimal("1.16")
            for semana in range(26):
                lunes = FIN - timedelta(weeks=semana)
                for t in tiendas[:n]:
                    pz = Decimal(str(ritmo))
                    bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=sku, tienda=t, semana=lunes, empresa="EJ",
                                        piezas=pz, piezas_devueltas=Decimal(0), importe_bruto=pz * base, descuento=Decimal(0),
                                        importe=pz * base, costo=pz * base * Decimal("0.66"), tickets=1, carga_id=carga.carga_id))
        bd.commit()
    yield {**skus, "h": h}
    with Session(motor()) as bd:
        bd.execute(update(Producto).where(Producto.sku.in_(list(skus.values()))).values(activo=False))
        bd.commit()


def _wonu(h: str) -> rp.Sujeto:
    return rp.Sujeto(tipo="idea", nombre="Creatina + Inositol", marca=f"Wonu{h}", forma="Sobre",
                     contenido="30 sobres de 7.6 g", precio=Decimal("599"), costo=Decimal("350"),
                     margen=Decimal("32.22"), ingrediente="Creatina")


def test_formato_sobre_contra_sobre():
    assert rp.formato("Sobre") == "sobre" and rp.formato("QUENUT CREATINA CREAPURE SOBRE 5 G") == "sobre"
    assert rp.formato("BIRDMAN CREATINE FOR WOMEN 348 G") == "polvo"
    assert rp.formato("OREGANO 60 CAPS") == "capsula" and rp.formato("Shampoo 1 L") == "liquido"
    assert rp.GRUPO_FORMATO["sobre"] == rp.GRUPO_FORMATO["polvo"] != rp.GRUPO_FORMATO["capsula"]
    assert rp.raices({"creatina"}) == rp.raices({"creatine"})


def test_wonu_encuentra_sus_parecidos_y_su_marca(catalogo_creatinas):
    """El radar del 13 nov no encontró parecidos de Wonu (30 sobres contra «sobre 5 g» o «348 g» se descartaban por la
    unidad, y «creatine» no era «creatina»): Demanda quedó vacía y Categoría en 90 «hueco»."""
    c = catalogo_creatinas
    with Session(motor()) as bd:
        parecidos = rp.buscar_parecidos(bd, _wonu(c["h"]), None)
        skus = [p.sku for p, _ in parecidos]
        assert {c["sobre"], c["mujer"], c["inositol"], c["lider"]} <= set(skus)
        assert c["capsulas"] not in skus
        assert skus.index(c["sobre"]) < skus.index(c["lider"])  # sobre contra sobre va primero
        # El colágeno de la marca no es parecido, pero sale como «lo que ya vendemos de la marca»
        assert c["marca"] not in skus
        assert c["marca"] in {p.sku for p in rep.de_la_marca(bd, f"Wonu{c['h']}", set(skus))}


def test_precio_meta_nunca_pasa_del_mercado():
    """Con costo de $500 el radar proponía vender Wonu en $840.58 cuando afuera está en $599 a $660."""
    s = rp.Sujeto(tipo="idea", nombre="Creatina + Inositol", marca="Wonu", precio=Decimal("599"), costo=Decimal("500"),
                  margen=Decimal("3.16"))
    costo, precio_meta, costo_meta, pasa = rp.metas(s, Decimal("31"), Decimal("653"))
    assert pasa and round(precio_meta, 2) == Decimal("840.58") and round(costo_meta, 2) == Decimal("356.30")
    texto = rp._para_llegar(s, Decimal("31"), Decimal("653"))
    assert "La salida es el costo" in texto and "$356.30" in texto
    dic = rp.dictamen(s, "rojo", {"precio": rp.Factor(83, "x", "x", meta=Decimal("653")),
                                  "demanda": rp.Factor(60, "x", "x")}, [], Decimal("31"))
    assert "la salida es el costo" in dic and "$356.30" in dic
    # Sin mercado sigue proponiendo las dos salidas
    assert "venderlo en" in rp._para_llegar(s, Decimal("31"))


def _idea(admin: TestClient, datos: dict) -> dict:
    r = admin.post(f"{R}/ideas", json=datos)
    assert r.status_code == 201, r.text
    return admin.get(f"{R}/evaluaciones/{r.json()['id']}").json()


def test_reporte_de_wonu(admin: TestClient, sincrono, catalogo_creatinas):  # noqa: F811
    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina + Inositol", "marca": f"Wonu{c['h']}", "departamento": "DEPORTES (ejemplo)",
                      "ingrediente": "Creatina", "forma": "Sobre", "contenido": "30 sobres de 7.6 g",
                      "precio_nuestro": "599", "precio_visto": "653", "donde_se_vio": "Chedraui",
                      "costo_estimado": "350", "codigo_barras": "7503053821217", "activo_g_porcion": "5",
                      "porciones": 30})
    assert e["estado"] == "lista", e.get("error")
    assert e["precio_nuestro"] == "599.00" and e["codigo_barras"] == "7503053821217" and e["porciones"] == 30
    factores = {f["factor"]: f for f in e["factores"]}
    assert factores["demanda"]["puntaje"] is not None  # ya tiene parecidos con venta
    assert "Chedraui" in factores["precio"]["detalle"]  # el precio visto cuenta como precio del mercado
    assert factores["rentabilidad"]["valor"].startswith("Deja 32.2 % de margen")

    r = admin.get(f"{R}/evaluaciones/{e['id']}/reporte")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert len(r.content) < 400_000
    t = _texto(r.content)
    for esperado in ("Creatina + Inositol", "de 100", "¿Qué es exactamente?", "¿Cuánto ganamos?", "32.2 %",
                     "$599.00", "Chedraui", "¿Qué vendemos hoy parecido?", f"QUENUT{c['h']}", f"WONU{c['h']}",
                     "misma marca", "$3.99 por gramo de creatina", "Lo que proponemos a Compras", "Calificación del radar"):
        assert esperado in t, esperado
    # Lo que va a Compras no lleva notas de método ni pendientes (Diego, 13 nov 2026)
    for prohibido in ("por confirmar", "no se pudo", "validar con", "Sin datos"):
        assert prohibido not in t, prohibido


def test_reporte_de_creanatomy(admin: TestClient, sincrono, catalogo_creatinas):  # noqa: F811
    """Creanatomy creatina 390 g (aprobada por el comité): costo $263.21 y precio $449 dejan 32.0 %."""
    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina monohidratada 390 g", "marca": f"Creanatomy{c['h']}",
                      "departamento": "DEPORTES (ejemplo)", "ingrediente": "Creatina", "forma": "Polvo",
                      "contenido": "390 g", "precio_nuestro": "449", "costo_estimado": "263.21"})
    assert e["estado"] == "lista", e.get("error")
    skus = {x["sku"] for x in e["comparables"]}
    assert {c["lider"], c["mujer"]} <= skus
    t = _texto(admin.get(f"{R}/evaluaciones/{e['id']}/reporte").content)
    assert "32.0 %" in t and "Precio mínimo para el 30 %" in t and f"BIRD{c['h']} CREATINA MONOHIDRATADA 450 G" in t
    assert "$1.15 por gramo" in t  # 449 / 390


def test_reporte_sin_terminar_no_sale(admin: TestClient):
    with Session(motor()) as bd:
        e = bd.scalar(rp.select(rp.ProductoEvaluacion).where(rp.ProductoEvaluacion.estado == "lista"))
    assert admin.get(f"{R}/evaluaciones/999999999/reporte").status_code == 404
    assert e is None or admin.get(f"{R}/evaluaciones/{e.evaluacion_id}/reporte").status_code == 200
