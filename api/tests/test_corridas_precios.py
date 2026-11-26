"""Adecuaciones del radar de precios para su uso diario (Diego, 26 nov 2026): reporte por clasificación y lista de SKU,
corridas a pedido con resumen y acciones, y tablero al día (solo precios). Datos ficticios (EJ)."""
import io
import uuid
from decimal import Decimal

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Producto
from modulos.compras import precios
from modulos.compras import tablero_precios as tb
from modulos.compras.modelos_precios import PrecioCorrida, PrecioVigilado
from nucleo.modelos import Notificacion
from tests.test_precios import correr, item, limpio, producto, vendedor, vigilar  # noqa: F401 - limpio es fixture


def _clase(pid, clase, subcategoria="CORRIDAS EJ"):  # subcategoría propia: no alterar el surtido de otras pruebas
    with Session(motor()) as bd:
        p = bd.get(Producto, pid)
        p.clasificacion, p.subcategoria = clase, subcategoria
        bd.commit()
        return p.sku


def _sincrono(monkeypatch):
    """La corrida corre en el mismo hilo para poder revisarla al momento."""
    def correr_ya(corrida_id):
        with Session(motor()) as bd:
            precios.correr(bd, bd.get(PrecioCorrida, corrida_id))
    monkeypatch.setattr(precios, "correr_aparte", correr_ya)


def test_reporte_por_clasificacion_y_lista_de_skus(limpio, admin):
    marca = f"MARCA EJ {uuid.uuid4().hex[:6]}"  # los productos de otras pruebas se quedan en el catálogo
    a = producto("COLAGENO EJ 300 G", marca=marca)
    b = producto("CREATINA EJ 450 G", marca=marca)
    c = producto("GLUTAMINA EJ 300 G", marca="OTRA EJ")
    sku_a, _, sku_c = _clase(a, " aa "), _clase(b, "B"), _clase(c, "AA", "OTRA CAT EJ")
    opciones = {o["clave"]: o for o in admin.get("/api/compras/precios/reporte/opciones?modo=clasificacion").json()}
    assert opciones["AA"]["nombre"] == "Clase AA" and "productos" in opciones["AA"]["cuenta"]
    contar = lambda sel: admin.post("/api/compras/precios/reporte/contar", json=sel).json()["productos"]
    # La clasificación acota la marca; sola trae toda la clase; los sueltos siempre entran
    assert contar({"marcas": [marca], "clasificaciones": ["AA"]}) == 1
    assert contar({"marcas": [marca]}) == 2
    assert contar({"marcas": [marca], "clasificaciones": ["AA"], "producto_ids": [b]}) == 2
    with Session(motor()) as bd:
        assert {p.producto_id for p in tb.de_seleccion(bd, [], [], [], ["AA"])} >= {a, c}
        assert b not in {p.producto_id for p in tb.de_seleccion(bd, [], [], [], ["AA"])}
    # Lista de SKU pegada (renglones, comas) y en Excel
    r = admin.post("/api/compras/precios/reporte/skus", data={"texto": f"{sku_a}\n{sku_c}, NOEXISTE-EJ"}).json()
    assert {int(x["clave"]) for x in r["encontrados"]} == {a, c} and r["no_encontrados"] == ["NOEXISTE-EJ"]
    libro = Workbook()
    libro.active.append(["SKU"])
    libro.active.append([sku_a])
    buf = io.BytesIO()
    libro.save(buf)
    r = admin.post("/api/compras/precios/reporte/skus", files={"archivo": ("lista.xlsx", buf.getvalue())}).json()
    assert [int(x["clave"]) for x in r["encontrados"]] == [a]
    assert admin.post("/api/compras/precios/reporte/skus", data={"texto": "  "}).status_code == 400
    # El Excel del reporte acepta la clasificación
    sel = {"marcas": [marca], "clasificaciones": ["B"], "hojas": ["resumen", "accion"]}
    x = admin.post("/api/compras/precios/reporte/excel", json=sel)
    assert x.status_code == 200 and "Clase_B" in x.headers["content-disposition"]


def test_corrida_a_pedido_resumen_acciones_y_excel(limpio, admin, monkeypatch):
    _sincrono(monkeypatch)
    a = producto("COLAGENO EJ 300 G", lista="389.00", mem="300.00", marca="PEDIDO EJ")
    b = producto("CREATINA EJ 450 G", lista="599.00", marca="PEDIDO EJ")
    _clase(a, "AA"), _clase(b, "AA")
    limpio.resultados["PEDIDO EJ COLAGENO EJ 300 G"] = [item("Pedido EJ Colágeno EJ 300 g", "G-COL")]
    limpio.resultados["PEDIDO EJ CREATINA EJ 450 G"] = []
    limpio.vendedores["G-COL"] = [vendedor("Walmart", 300, "walmart.com.mx"), vendedor("Chedraui", 310, "chedraui.com.mx")]
    pedido = {"marcas": ["PEDIDO EJ"], "clasificaciones": ["AA"]}
    e = admin.post("/api/compras/precios/pedidos/estimar", json=pedido).json()
    assert e["productos"] == 2 and e["puede"] and Decimal(e["estimado_usd"]) > 0 and e["ocupado"] is None
    assert not admin.post("/api/compras/precios/pedidos/estimar", json={}).json()["puede"]
    p = admin.post("/api/compras/precios/pedidos", json=pedido)
    assert p.status_code == 202
    pid = p.json()["id"]
    d = admin.get(f"/api/compras/precios/pedidos/{pid}").json()
    assert d["pedido"]["estado"] in ("completa", "parcial") and d["pedido"]["nombre"] == "Marcas: PEDIDO EJ · Clase AA"
    assert d["cuadros"] == {"con_precio": 1, "mas_caros": 1, "mas_baratos": 0, "sin_comparar": 1}
    assert d["filas"][0]["producto_id"] == a and d["filas"][0]["accion"] == "bajar" and d["acciones"]["bajar"] == 1
    assert sum(d["sin_comparar"].values()) == 1
    # Quedan en el radar (la noche los vuelve a revisar) y cuentan para la pantalla principal
    with Session(motor()) as bd:
        assert {v.producto_id for v in bd.scalars(select(PrecioVigilado))} >= {a, b}
        assert bd.scalar(select(Notificacion).where(Notificacion.titulo == "Tu corrida del radar de precios terminó"))
        # No adelanta ni frena la corrida del programa
        assert precios.ultima_del_dia(bd, precios.hoy_local()) is None
    tb.olvidar()
    assert any(x["producto_id"] == a and x["color"] == "rojo"
               for x in admin.get("/api/compras/precios/tablero?grupo=todos").json()["filas"])
    assert [x["id"] for x in admin.get("/api/compras/precios/pedidos").json()] == [pid]
    r = admin.get(f"/api/compras/precios/pedidos/{pid}/excel")
    assert r.status_code == 200
    assert "Qué conviene" in load_workbook(io.BytesIO(r.content)).sheetnames
    assert admin.post(f"/api/compras/precios/pedidos/{pid}/detener").status_code == 409


def test_corrida_a_pedido_se_forma_si_otra_corre(limpio, admin, monkeypatch):
    _sincrono(monkeypatch)
    a = producto("MORINGA EJ 100 CAPSULAS")
    limpio.resultados["NATUREJ MORINGA EJ 100 CAPSULAS"] = []
    with Session(motor(), expire_on_commit=False) as bd:
        otra = precios.tomar_corrida(bd, precios.hoy_local(), precios.NOCTURNA, forzar=True)
    e = admin.post("/api/compras/precios/pedidos/estimar", json={"producto_ids": [a]}).json()
    assert e["ocupado"] == "Está corriendo un lote de la revisión de noche"
    p = admin.post("/api/compras/precios/pedidos", json={"producto_ids": [a], "archivo": "mis skus.xlsx",
                                                          "no_encontrados": ["X-EJ"]}).json()
    assert p["estado"] == "en_espera" and p["nombre"] == "Excel mis skus.xlsx" and p["no_encontrados"] == ["X-EJ"]
    assert admin.get(f"/api/compras/precios/pedidos/{p['id']}/excel").status_code == 409
    segunda = admin.post("/api/compras/precios/pedidos", json={"producto_ids": [a]}).json()
    assert segunda["estado"] == "en_espera"
    with Session(motor()) as bd:
        assert precios.arrancar_en_espera(bd) is None  # la otra sigue corriendo
        bd.get(PrecioCorrida, otra.corrida_id).estado = "completa"
        bd.commit()
    # Sacar la segunda de la fila; la primera arranca sola al quedar libre
    assert admin.post(f"/api/compras/precios/pedidos/{segunda['id']}/detener").json()["estado"] == "fallida"
    with Session(motor()) as bd:
        assert precios.arrancar_en_espera(bd).corrida_id == p["id"]
        assert precios.arrancar_en_espera(bd) is None
    assert admin.get(f"/api/compras/precios/pedidos/{p['id']}").json()["pedido"]["estado"] in ("completa", "parcial")
    # Todas: también la de noche
    assert otra.corrida_id in {x["id"] for x in admin.get("/api/compras/precios/pedidos?todas=true").json()}


def test_tablero_al_dia(limpio, admin):
    a = producto("COLAGENO EJ 300 G", lista="389.00")
    vigilar(a)
    limpio.resultados["NATUREJ COLAGENO EJ 300 G"] = [item("Naturej Colágeno EJ 300 g", "G-COL")]
    limpio.vendedores["G-COL"] = [vendedor("Walmart", 300, "walmart.com.mx"), vendedor("Chedraui", 310, "chedraui.com.mx")]
    correr()
    limpio.vendedores["G-COL"] = [vendedor("Walmart", 340, "walmart.com.mx"), vendedor("Chedraui", 350, "chedraui.com.mx")]
    correr()
    tb.olvidar()
    t = admin.get("/api/compras/precios/tablero/dia").json()
    assert t["comparados"] == 1 and t["mas_caros"] == 1 and t["sin_comparar"] == 0
    assert t["subieron"] == 1 and t["movimientos"][0]["producto_id"] == a
    assert Decimal(t["movimientos"][0]["antes"]) == Decimal("305.00") and Decimal(t["movimientos"][0]["ahora"]) == Decimal("345.00")
    assert t["agentes"][0]["agente"] == "Sin agente" and t["agentes"][0]["bajar"] == 1
    assert len(t["dias"]) == 14 and t["dias"][-1]["productos"] == 2
    assert "costo" not in " ".join(t.keys())  # solo radar de precios
