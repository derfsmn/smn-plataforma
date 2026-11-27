"""Adecuaciones del radar de precios para su uso diario (Diego, 26 nov 2026): reporte por clasificación y lista de SKU,
corridas a pedido con resumen y acciones, y tablero al día (solo precios). Datos ficticios (EJ)."""
import io
import json
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
    from core.config import configuracion
    monkeypatch.setattr(configuracion(), "precios_pedido_prioridad_alta", False)
    normal = Decimal(admin.post("/api/compras/precios/pedidos/estimar", json=pedido).json()["estimado_usd"])
    assert Decimal(e["estimado_usd"]) == normal * 2  # con prioridad alta (de fábrica) el estimado cuenta el doble
    monkeypatch.setattr(configuracion(), "precios_pedido_prioridad_alta", True)
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


def test_corrida_a_pedido_que_falla_avisa_a_quien_la_lanzo(limpio, admin, monkeypatch):
    """Revisión del 26 nov 2026: si la corrida a pedido truena, el aviso iba solo a quien administra el radar y quien la
    lanzó (Precios y Costos, solo con «ver») se quedaba esperando. Ahora también le llega a ella."""
    from tests.conftest import alta_usuario

    _sincrono(monkeypatch)
    a = producto("ESPIRULINA EJ 100 TABLETAS")
    # Otras pruebas cambian los permisos de este rol: aquí se deja con «ver» y sin «administrar», como Precios y Costos
    assert admin.put("/api/nucleo/roles/compras_consulta/permisos",
                     json={"permisos": ["compras.solicitud.ver", "compras.radar.ver", "compras.precios.ver"]}).status_code == 200
    _, consulta, uid = alta_usuario(admin, rol="compras_consulta")

    def truena(self):
        raise RuntimeError("falla de prueba")

    monkeypatch.setattr(precios.Corrida, "correr", truena)
    p = consulta.post("/api/compras/precios/pedidos", json={"producto_ids": [a]})
    assert p.status_code == 202, p.text  # cualquiera con compras.precios.ver la lanza
    d = consulta.get(f"/api/compras/precios/pedidos/{p.json()['id']}").json()
    assert d["pedido"]["estado"] == "fallida" and "RuntimeError" in d["pedido"]["error"]
    with Session(motor()) as bd:
        aviso = bd.scalar(select(Notificacion).where(Notificacion.usuario_id == uid,
                                                     Notificacion.titulo == "Tu corrida del radar de precios no terminó"))
        assert aviso and aviso.liga == f"/compras/precios/pedidos/{p.json()['id']}"


def test_corrida_a_pedido_busca_las_tiendas_de_compras_en_google(limpio, admin, monkeypatch):
    """Diego (26 nov 2026): las tiendas de Compras sin conector (Farmacias del Ahorro, HEB…) se buscan en Google limitado
    a su sitio, varias por búsqueda, solo en corridas a pedido. Cuentan como esa tienda, una vez. Datos FICTICIOS."""
    from core.config import configuracion
    from modulos.compras import tiendas as td

    _sincrono(monkeypatch)
    cfg = configuracion()
    monkeypatch.setattr(cfg, "tiendas_google_activo", True)
    monkeypatch.setattr(cfg, "tiendas_google_sitios", "Farmacias del Ahorro=fahorro.com; HEB=heb.com.mx; GNC=gnc.com.mx")
    monkeypatch.setattr(cfg, "tiendas_google_por_busqueda", 3)
    monkeypatch.setattr(cfg, "precios_tiendas_clave", "Walmart, Farmacias del Ahorro, HEB, GNC")
    a = producto("COLAGENO EJ 300 G", lista="389.00", marca="PEDIDO EJ")
    q = "PEDIDO EJ COLAGENO EJ 300 G"
    limpio.resultados[q] = [item("Pedido EJ Colágeno EJ 300 g", "G-COL")]
    limpio.vendedores["G-COL"] = [vendedor("Walmart", 300, "walmart.com.mx")]
    limpio.organico[f"site:fahorro.com OR site:heb.com.mx OR site:gnc.com.mx {q}"] = [
        {"url": "https://www.fahorro.com/colageno-ej.html", "domain": "www.fahorro.com", "title": "Pedido EJ Colágeno EJ 300 g",
         "price": {"current": 320.0, "currency": "MXN"}},
        {"url": "https://www.heb.com.mx/colageno-ej", "domain": "www.heb.com.mx", "title": "Pedido EJ Colágeno EJ 300 g",
         "description": "Precio $310.00"}]
    e = admin.post("/api/compras/precios/pedidos/estimar", json={"producto_ids": [a]}).json()
    assert Decimal(e["estimado_usd"]) > 0
    p = admin.post("/api/compras/precios/pedidos", json={"producto_ids": [a]}).json()
    # Las tiendas vía Google se mandan primero, junto con Google Shopping (no esperan a que terminen las demás)
    assert [t for t, _ in limpio.envios][:2] == ["organic", "products"], limpio.envios
    with Session(motor()) as bd:
        from modulos.compras.modelos_precios import PrecioCorridaProducto, PrecioObservacion
        f = bd.scalar(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == p["id"]))
        estados = json.loads(f.tiendas)
        assert estados["Farmacias del Ahorro"]["estado"] == "encontrado" and estados["HEB"]["estado"] == "encontrado"
        assert estados["GNC"]["estado"] == "no_lo_tiene"  # no aparece en Google: no es una falla
        obs = {o.vendedor: o for o in bd.scalars(select(PrecioObservacion).where(PrecioObservacion.corrida_id == p["id"]))}
        assert {"Walmart", "Farmacias del Ahorro", "HEB"} <= set(obs)
        assert json.loads(obs["HEB"].datos)["_publicacion"] == "Google (sitio de HEB)"
        assert f.vendedores == 3 and f.mediana == Decimal("310.00")  # 300, 310 y 320: tres tiendas, una vez cada una
    # Una corrida que no es a pedido (la del programa o la noche) no las busca
    organicas = sum(1 for tp, _ in limpio.tareas.values() if tp == "organic")
    with Session(motor()) as bd:  # el pedido lo dejó vigilado para la noche; aquí entra a la corrida del programa
        bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == a)).origen = "pantalla"
        bd.commit()
    correr()
    assert sum(1 for tp, _ in limpio.tareas.values() if tp == "organic") == organicas


def test_corrida_a_pedido_prioridad_alta_solo_si_se_enciende(monkeypatch):
    """26 nov 2026: la corrida a pedido de 10 productos tardó 39 min en la cola normal de DataForSEO. Con el ajuste
    encendido va en la cola rápida (cuesta el doble); apagado de fábrica. La noche nunca."""
    from core.config import configuracion
    from modulos.compras import dataforseo as dfs
    from types import SimpleNamespace

    vistas = []
    monkeypatch.setattr(precios, "_correr", lambda bd, c: vistas.append(dfs.PRIORIDAD.get()) or c)
    assert configuracion().__class__().precios_pedido_prioridad_alta is True  # encendido de fábrica (Diego)
    monkeypatch.setattr(configuracion(), "precios_pedido_prioridad_alta", False)
    precios.correr(None, SimpleNamespace(origen=precios.PEDIDO))
    monkeypatch.setattr(configuracion(), "precios_pedido_prioridad_alta", True)
    precios.correr(None, SimpleNamespace(origen=precios.PEDIDO))
    precios.correr(None, SimpleNamespace(origen=precios.NOCTURNA))
    assert vistas == [1, 2, 1] and dfs.PRIORIDAD.get() == 1


def test_corrida_que_no_cabe_no_se_lanza_y_lo_que_alcanza_sale_con_precio(limpio, admin, monkeypatch):
    """Diego, 27 nov 2026: una corrida de 113 productos tardó una hora, topó con el tope por corrida y terminó sin un
    solo precio. Ahora no se lanza si no cabe y, si el dinero se acaba, lo que alcanzó sale completo."""
    from core.config import configuracion
    from modulos.compras import dataforseo as dfs
    cfg = configuracion()
    a = producto("COLAGENO EJ 300 G", lista="389.00", mem="300.00", marca="TOPE EJ")
    b = producto("CREATINA EJ 450 G", lista="599.00", marca="TOPE EJ")
    limpio.resultados["TOPE EJ COLAGENO EJ 300 G"] = [item("Tope EJ Colágeno EJ 300 g", "G-TOPE")]
    limpio.resultados["TOPE EJ CREATINA EJ 450 G"] = [item("Tope EJ Creatina EJ 450 g", "G-TOPE-B")]
    limpio.vendedores["G-TOPE"] = [vendedor("Walmart", 300, "walmart.com.mx"), vendedor("Chedraui", 310, "chedraui.com.mx")]
    limpio.vendedores["G-TOPE-B"] = [vendedor("Walmart", 500, "walmart.com.mx"), vendedor("Chedraui", 510, "chedraui.com.mx")]
    pedido = {"marcas": ["TOPE EJ"]}
    e = admin.post("/api/compras/precios/pedidos/estimar", json=pedido).json()
    assert e["puede"] and e["cabe"] and e["caben"] == 2
    costo = Decimal(e["estimado_usd"])
    # No cabe en el tope por corrida: no se lanza y dice cuántos caben
    monkeypatch.setattr(cfg, "precios_tope_corrida_usd", float(costo * Decimal("0.6")))
    e = admin.post("/api/compras/precios/pedidos/estimar", json=pedido).json()
    assert not e["puede"] and not e["cabe"] and e["caben"] == 1 and "tope por corrida" in e["motivo"]
    assert admin.post("/api/compras/precios/pedidos", json=pedido).status_code == 400
    # Si el tope baja con la corrida ya lanzada: alcanza para lo esencial de un producto y ese sale con precio
    monkeypatch.setattr(cfg, "precios_tope_corrida_usd", float(costo))
    monkeypatch.setattr(precios, "correr_aparte", lambda corrida_id: None)
    pid = admin.post("/api/compras/precios/pedidos", json=pedido).json()["id"]
    por = dfs.POR_PRIORIDAD[2 if cfg.precios_pedido_prioridad_alta else 1]
    with Session(motor()) as bd:
        consultas = len(precios.co.consultas("COLAGENO EJ 300 G", "TOPE EJ", None, None))
    uno = dfs.maximo_producto(consultas, cfg.precios_max_publicaciones) * por
    monkeypatch.setattr(cfg, "precios_tope_corrida_usd", float(uno * Decimal("1.5")))
    token = dfs.PRIORIDAD.set(2 if cfg.precios_pedido_prioridad_alta else 1)
    try:
        with Session(motor()) as bd:
            precios.correr(bd, bd.get(PrecioCorrida, pid))
    finally:
        dfs.PRIORIDAD.reset(token)
    d = admin.get(f"/api/compras/precios/pedidos/{pid}").json()
    assert d["pedido"]["estado"] == "parcial" and any("tope de gasto por corrida" in x for x in d["pedido"]["avisos"])
    assert d["cuadros"]["con_precio"] == 1 and d["cuadros"]["sin_comparar"] == 1
    assert d["sin_comparar"] == {"Se acabó el presupuesto de búsquedas antes de revisarlo": 1}
    assert Decimal(d["pedido"]["costo_usd"]) <= uno * Decimal("1.5")
    # «Continuar corrida»: la misma corrida retoma lo que faltó, sin volver a pagar lo ya encontrado, y sigue a su nombre
    monkeypatch.setattr(cfg, "precios_tope_corrida_usd", float(uno * Decimal("0.5")))
    r = admin.get(f"/api/compras/precios/pedidos/{pid}/continuar").json()
    assert r["faltan"] == 1 and not r["puede"] and "tope por corrida" in r["motivo"]
    assert admin.post(f"/api/compras/precios/pedidos/{pid}/continuar").status_code == 400
    monkeypatch.setattr(cfg, "precios_tope_corrida_usd", float(costo))
    _sincrono(monkeypatch)
    gastado = Decimal(d["pedido"]["costo_usd"])
    r = admin.post(f"/api/compras/precios/pedidos/{pid}/continuar")
    assert r.status_code == 202 and r.json()["id"] == pid and r.json()["usuario_id"] == d["pedido"]["usuario_id"]
    d = admin.get(f"/api/compras/precios/pedidos/{pid}").json()
    assert d["pedido"]["estado"] == "completa" and d["cuadros"]["con_precio"] == 2 and d["pedido"]["avisos"] == []
    assert Decimal(d["pedido"]["costo_usd"]) - gastado <= uno
    assert admin.post(f"/api/compras/precios/pedidos/{pid}/continuar").status_code == 400  # ya no quedó a medias
