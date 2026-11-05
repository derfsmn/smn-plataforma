"""Radar de productos, fase 1: semáforo de ideas de Compras y de propuestas listas para evaluar (datos ficticios)."""
import json
import random
import string
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Producto
from modulos.compras import radar_productos as rp
from tests.conftest import alta_usuario
from tests.test_propuestas import PNG, lista_para_enviar, subir

R = "/api/compras/productos"


@pytest.fixture
def sincrono(monkeypatch):
    """La evaluación corre en la misma petición en vez de en un hilo, para poder revisar el resultado."""
    def correr(evaluacion_id: int) -> None:
        with rp._sesion() as bd:
            rp.evaluar(bd, evaluacion_id)

    monkeypatch.setattr(rp, "en_hilo", correr)


def catalogo_ficticio() -> tuple[str, list[str]]:
    """Un departamento propio con tres productos parecidos y uno distinto, para no chocar con otras pruebas."""
    depto = f"Depto prueba {uuid.uuid4().hex[:6]}"
    filas = [("Citrato de magnesio 60 caps", "Minerales", "Magnesio", "120.00"),
             ("Magnesio quelado 90 tabletas", "Minerales", "Magnesio", "180.00"),
             ("Cloruro de magnesio 500 g", "Minerales", "Magnesio", "95.00"),
             ("Té verde 25 sobres", "Tés", "Verde", "60.00")]
    skus = []
    with Session(motor()) as bd:
        # La búsqueda de parecidos recorre todo el catálogo: se apagan los productos ficticios de corridas anteriores
        bd.execute(update(Producto).where(Producto.sku.like("RP-%")).values(activo=False))
        for descripcion, sub, seg, precio in filas:
            sku = f"RP-{uuid.uuid4().hex[:8]}"
            skus.append(sku)
            bd.add(Producto(sku=sku, descripcion=descripcion, departamento=depto, rama="Suplementos", subcategoria=sub,
                            segmento=seg, precio_lista_con_impuestos=Decimal(precio), origen="API", activo=True))
        bd.commit()
    return depto, skus


# ---------------------------------------------------------------- reglas

def test_semaforo_y_suma():
    assert rp.color_de(81, "alta") == "verde" and rp.color_de(80, "alta") == "amarillo"
    assert rp.color_de(60, "media") == "amarillo" and rp.color_de(59, "alta") == "rojo"
    assert rp.color_de(95, "baja") == "amarillo"  # sin datos suficientes no hay verde
    peso = {f: Decimal("16.67") for f in rp.FACTORES}
    todos = {f: rp.Factor(70, "x", "x") for f in rp.FACTORES}
    assert rp.sumar(todos, peso) == (70, "alta")
    # Los factores sin datos no cuentan: se reparte el peso entre los que sí tienen
    medio = {**{f: rp.Factor(None, None, "x") for f in rp.FACTORES[:3]}, **{f: rp.Factor(90, "x", "x") for f in rp.FACTORES[3:]}}
    assert rp.sumar(medio, peso) == (90, "media")
    assert rp.sumar({f: rp.Factor(None, None, "x") for f in rp.FACTORES}, peso) == (None, "baja")


def test_oportunidad_sin_proveedor_ni_costo_no_baja_la_confianza():
    peso = {"demanda": Decimal(17), "rentabilidad": Decimal(22), "precio": Decimal(22), "tendencia": Decimal(16),
            "categoria": Decimal(10), "proveedor": Decimal(13)}
    factores = {f: rp.Factor(90, "x", "x") for f in rp.FACTORES}
    factores["rentabilidad"] = rp.Factor(None, None, "Sin datos: falta el costo estimado.")
    factores["proveedor"] = rp.Factor(None, None, "Sin datos: todavía no hay proveedor.")
    assert rp.sumar(dict(factores), peso) == (90, "media")  # como cualquier idea: 65 % del peso con datos
    fuera = rp.marcar_oportunidad(factores)
    assert fuera == {"rentabilidad", "proveedor"}
    assert factores["proveedor"].valor == "Se califica al conseguir proveedor" and factores["proveedor"].puntaje is None
    assert rp.sumar(factores, peso, fuera) == (90, "alta")  # la confianza se mide sobre los 4 que sí se pueden saber
    # Sin precio de mercado ya no hay 80 % del peso: baja a media, pero no a baja
    factores["precio"] = rp.Factor(None, None, "x")
    assert rp.sumar(factores, peso, fuera) == (90, "media")
    # Si Compras ya capturó el costo, la rentabilidad cuenta como siempre
    otra = {f: rp.Factor(70, "x", "x") for f in rp.FACTORES}
    otra["proveedor"] = rp.Factor(None, None, "x")
    assert rp.marcar_oportunidad(otra) == {"proveedor"}


def test_palabras_y_margen_de_idea():
    assert rp.palabras("Citrato de Magnésio 60 caps") == {"citrato", "magnesio"}
    i = rp.ProductoIdea(nombre="X", precio_visto=Decimal("116"), costo_estimado=Decimal("60"))
    assert rp.sujeto_de_idea(i).margen == Decimal("40.00")  # 116 con IVA son 100; costo 60


def test_parecidos_en_otro_departamento_y_misma_marca():
    """Caso de la prueba de Diego (2026-10-26): la idea se capturó en un departamento distinto al del catálogo y con
    descripción larga; aun así debe encontrar el producto de la misma marca que ya vendemos."""
    marca = "".join(random.choices(string.ascii_lowercase, k=10))
    with Session(motor()) as bd:
        bd.execute(update(Producto).where(Producto.sku.like("RP-%")).values(activo=False))
        mismo = Producto(sku=f"RP-{uuid.uuid4().hex[:8]}", descripcion=f"{marca.upper()} PLUS C/30 CAPS", marca=marca.upper(),
                         departamento="Control de peso (ejemplo)", precio_lista_con_impuestos=Decimal("95"), origen="API",
                         activo=True)
        bd.add(mismo)
        bd.commit()
        s = rp.Sujeto(tipo="idea", nombre=f"{marca.capitalize()} Plus 30 Cápsulas", marca=marca.upper(),
                      departamento="Prevención y salud (ejemplo)", precio=Decimal("90"),
                      descripcion="Suplemento alimenticio que ayuda a controlar el apetito y a quemar grasa")
        parecidos = rp.buscar_parecidos(bd, s, None)
        assert parecidos[0][0].sku == mismo.sku and parecidos[0][1] >= Decimal("0.8")
        assert "ya vendemos este producto" in rp.f_categoria(bd, s, None, parecidos).detalle
        assert rp.f_precio(s, parecidos).puntaje is not None
        assert rp.f_rentabilidad(bd, s).detalle.startswith("Sin datos: falta el costo estimado.")


# ---------------------------------------------------------------- ideas de Compras

def test_idea_con_foto_se_evalua_y_compras_corrige(admin: TestClient, sincrono):
    depto, skus = catalogo_ficticio()
    foto = subir(admin, "frente.png", PNG)
    datos = {"nombre": "Citrato de magnesio en polvo", "marca": "Marca Ficticia", "departamento": depto,
             "ingrediente": "Magnesio", "forma": "Polvo", "precio_visto": "150", "costo_estimado": "80",
             "donde_se_vio": "Tienda de ejemplo", "fotos": [foto]}

    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post(f"{R}/ideas", json=datos).status_code == 403
    # Solo se ligan fotos que subió quien captura
    otra = subir(consulta, "otra.png", PNG)
    assert admin.post(f"{R}/ideas", json={**datos, "fotos": [otra]}).status_code == 400

    r = admin.post(f"{R}/ideas", json=datos)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    e = admin.get(f"{R}/evaluaciones/{eid}").json()
    assert e["estado"] == "lista", e["error"]
    assert e["sujeto"]["tipo"] == "idea" and e["sujeto"]["estado"] == "nueva"
    # Sin IA en pruebas: la subcategoría se toma de los parecidos, que son todos «Minerales»
    assert e["clasificacion_origen"] == "parecidos" and e["subcategoria"] == "Minerales"
    parecidos = [c["sku"] for c in e["comparables"]]
    assert set(skus[:3]) <= set(parecidos) and skus[3] not in parecidos
    f = {x["factor"]: x for x in e["factores"]}
    assert f["proveedor"]["puntaje"] is None and f["demanda"]["puntaje"] is None
    assert f["rentabilidad"]["valor"] == "Deja 38.1 % de margen (mínimo 30 %)"
    assert f["precio"]["provisional"] and "parecido" in f["precio"]["detalle"]
    assert e["color"] in {"verde", "amarillo", "rojo"} and e["puntaje"] is not None and e["explicacion"]
    assert [x["archivo_id"] for x in e["fotos"]] == [foto]
    # Las fotos las ve Compras aunque no las haya subido; una foto que no es de la idea, no
    _, responsable, _ = alta_usuario(admin, rol="compras_responsable")
    assert responsable.get(f"{R}/ideas/{e['sujeto']['id']}/fotos/{foto}").status_code == 200
    assert responsable.get(f"{R}/ideas/{e['sujeto']['id']}/fotos/{otra}").status_code == 404

    # Compras confirma la clasificación: se recalcula y la anterior queda en el historial
    opciones = admin.get(f"{R}/clasificaciones", params={"departamento": depto}).json()
    assert {"rama": "Suplementos", "subcategoria": "Minerales", "segmento": "Magnesio"} in opciones
    assert admin.put(f"{R}/evaluaciones/{eid}/clasificacion",
                     json={"rama": "Suplementos", "subcategoria": "Inventada", "segmento": "X"}).status_code == 400
    n = admin.put(f"{R}/evaluaciones/{eid}/clasificacion",
                  json={"rama": "Suplementos", "subcategoria": "Minerales", "segmento": "Magnesio"}).json()
    e2 = admin.get(f"{R}/evaluaciones/{n['id']}").json()
    assert e2["clasificacion_origen"] == "compras" and e2["subcategoria"] == "Minerales" and e2["vigente"]
    assert [h["id"] for h in e2["historial"]] == [n["id"], eid]
    assert admin.post(f"{R}/evaluaciones/{eid}/recalcular").status_code == 409  # ya no es la vigente
    cat = {x["factor"]: x for x in e2["factores"]}["categoria"]
    assert cat["valor"] == "3 productos en su subcategoría (una típica tiene 3)"

    # Parecidos: un SKU que no existe se rechaza; los que fija Compras se conservan al recalcular
    assert admin.put(f"{R}/evaluaciones/{n['id']}/comparables", json={"skus": ["NO-EXISTE"]}).status_code == 400
    n = admin.put(f"{R}/evaluaciones/{n['id']}/comparables", json={"skus": [skus[1]]}).json()
    n = admin.post(f"{R}/evaluaciones/{n['id']}/recalcular").json()
    e3 = admin.get(f"{R}/evaluaciones/{n['id']}").json()
    assert [(c["sku"], c["origen"]) for c in e3["comparables"]] == [(skus[1], "compras")]
    assert e3["clasificacion_origen"] == "compras"
    assert [x["sku"] for x in admin.get(f"{R}/catalogo", params={"q": skus[0]}).json()] == [skus[0]]

    # Color final: solo con permiso de ajustar y con motivo
    otro = "rojo" if e3["color"] != "rojo" else "amarillo"
    assert consulta.post(f"{R}/evaluaciones/{n['id']}/color", json={"color": otro, "motivo": "Lo decide el comité"}).status_code == 403
    assert admin.post(f"{R}/evaluaciones/{n['id']}/color", json={"color": otro, "motivo": "corto"}).status_code == 400
    c = admin.post(f"{R}/evaluaciones/{n['id']}/color", json={"color": otro, "motivo": "La marca tuvo problemas de abasto"}).json()
    assert c["color_final"] == otro and c["color"] == e3["color"] and c["motivo_cambio"] and c["cambiado_por"]
    assert n["id"] in [x["id"] for x in admin.get(f"{R}/evaluaciones", params={"color": otro, "tipo": "idea"}).json()]
    vuelta = admin.post(f"{R}/evaluaciones/{n['id']}/color", json={"color": None, "motivo": "Se aclaró el abasto con la marca"}).json()
    assert vuelta["color_final"] is None

    idea = admin.patch(f"{R}/ideas/{e['sujeto']['id']}/estado", json={"estado": "buscar_proveedor"}).json()
    assert idea["estado"] == "buscar_proveedor"


# ---------------------------------------------------------------- propuestas

def test_propuesta_lista_se_evalua_sola(admin: TestClient, sincrono):
    _, prov, _ = alta_usuario(admin, tipo="externo", rol="proveedor")
    pid = lista_para_enviar(prov)["id"]
    prov.post(f"/api/compras/propuestas/{pid}/enviar")
    assert admin.get(f"{R}/propuestas/{pid}").json() is None
    assert admin.post(f"/api/compras/propuestas/{pid}/estado", json={"estado": "lista"}).status_code == 200

    e = admin.get(f"{R}/propuestas/{pid}").json()
    assert e["estado"] == "lista", e["error"]
    assert e["sujeto"]["tipo"] == "propuesta" and e["sujeto"]["folio"].startswith("PN-")
    assert e["sujeto"]["proveedor"] == "Proveedor de Prueba S.A."
    f = {x["factor"]: x for x in e["factores"]}
    assert f["rentabilidad"]["valor"] == "Deja 50 % de margen (mínimo 30 %)"
    # Proveedor nuevo 50 + registro sanitario 10 + un apoyo de lanzamiento 5
    assert f["proveedor"]["puntaje"] == 65 and f["proveedor"]["provisional"]
    assert e["id"] in [x["id"] for x in admin.get(f"{R}/evaluaciones", params={"tipo": "propuesta"}).json()]
    assert prov.get(f"{R}/propuestas/{pid}").status_code == 403  # el proveedor no ve el semáforo


def test_producto_nuevo_se_busca_en_internet(admin: TestClient, sincrono, monkeypatch):
    """Diego (2026-10-26): el producto nuevo se busca como en el radar de precios y se compara contra internet."""
    from core.config import configuracion
    from modulos.compras import tiendas as td
    from tests.test_precios import TiendaSimulada, con_tiendas

    depto, _ = catalogo_ficticio()
    marca = f"Marcaej{uuid.uuid4().hex[:4]}"
    nombre = "Magnesio quelado en polvo 300 g"
    class Cualquiera(TiendaSimulada):  # contesta lo mismo a cualquier búsqueda
        def buscar(self, texto):
            self.consultas.append(texto)
            return self.resultados["*"]

    walmart = Cualquiera("Walmart", "walmart.com.mx", {"*": [
        td.Resultado("W-1", f"{marca} Magnesio quelado en polvo 300 g", Decimal("200.00"), "https://www.walmart.com.mx/ip/w1"),
        td.Resultado("W-2", "Otra marca Té verde 25 sobres", Decimal("40.00"), "https://www.walmart.com.mx/ip/w2")]})
    soriana = TiendaSimulada("Soriana", "soriana.com", falla="bloqueó la consulta automática")
    con_tiendas(monkeypatch, walmart, soriana)
    monkeypatch.setattr(configuracion(), "radar_productos_buscar_mercado", True)

    datos = {"nombre": nombre, "marca": marca, "departamento": depto, "forma": "Polvo", "precio_visto": "180"}
    e = admin.get(f"{R}/evaluaciones/{admin.post(f'{R}/ideas', json=datos).json()['id']}").json()
    assert e["estado"] == "lista", e["error"]
    m = e["mercado"]
    assert [(p["vendedor"], p["fuente"]) for p in m["precios"]] == [("Walmart", "sitio")], m
    assert Decimal(m["mediana"]) == Decimal("200")
    notas = " ".join(m["notas"])
    assert "Google Shopping: no se buscó" in notas and "Soriana: bloqueó" in notas
    f = {x["factor"]: x for x in e["factores"]}["precio"]
    assert f["valor"] == "10 % más barato que en internet" and not f["provisional"] and "Walmart" in f["detalle"]

    # Recalcular dentro de la semana reusa la búsqueda: no se vuelve a consultar la tienda
    antes = len(walmart.consultas)
    r = admin.post(f"{R}/evaluaciones/{e['id']}/recalcular")
    assert r.status_code == 200, r.text
    e2 = admin.get(f"{R}/evaluaciones/{r.json()['id']}").json()
    assert e2["id"] != e["id"] and e2["mercado"]["precios"] == m["precios"] and len(walmart.consultas) == antes


def test_regla_de_rechazo_de_compras_pone_rojo(admin: TestClient, sincrono, monkeypatch):
    """Diego (2026-10-26): cruzar con las políticas de Compras; si cae en un rechazo directo, rojo con el motivo."""
    from ia import puerta
    from modulos.compras import politicas_producto as pp
    from modulos.compras.modelos_conocimiento import ConocimientoCaso, ConocimientoPolitica, ConocimientoRegla

    depto, _ = catalogo_ficticio()
    with Session(motor()) as bd:
        rechazo = ConocimientoRegla(tipo="rechazo", criterio="Regla ficticia: precio arriba de 1,000 pesos", departamento=depto)
        otro = ConocimientoRegla(tipo="rechazo", criterio="Regla ficticia de otro departamento", departamento="Otro depto")
        politica = ConocimientoPolitica(tema="alta_productos", titulo="Política ficticia", contenido="Texto ficticio",
                                        departamento=depto, estado="vigente")
        bd.add_all([rechazo, otro, politica,
                    ConocimientoCaso(producto="Citrato de magnesio en polvo 500 g", departamento=depto, decision="rechazado",
                                     motivo="Caso ficticio")])
        bd.commit()
        ids = (f"R{rechazo.regla_id}", f"P{politica.politica_id}", f"R{otro.regla_id}")
    vistos = []

    class Respuesta:
        def __init__(self, texto):
            self.texto = texto

    def ia(bd, tarea, **kw):
        if tarea != pp.TAREA_IA:
            raise puerta.ErrorIA("sin IA en pruebas")
        vistos.append(json.loads(kw["mensaje"]))
        return Respuesta(json.dumps({"hallazgos": [
            {"id": ids[0], "resultado": "no_cumple", "motivo": "Precio visto 1,500 (ficticio)"},
            {"id": ids[1], "resultado": "sin_datos", "motivo": "Falta el dato ficticio"},
            {"id": "R999999", "resultado": "no_cumple", "motivo": "no existe"}]}))

    monkeypatch.setattr(puerta, "ejecutar", ia)
    datos = {"nombre": "Citrato de magnesio en polvo", "departamento": depto, "precio_visto": "1500", "costo_estimado": "100"}
    e = admin.get(f"{R}/evaluaciones/{admin.post(f'{R}/ideas', json=datos).json()['id']}").json()
    assert e["estado"] == "lista", e["error"]
    # Solo se mandan las reglas del departamento (o generales)
    enviados = {x["id"] for x in vistos[0]["reglas_y_politicas"]}
    assert ids[0] in enviados and ids[1] in enviados and ids[2] not in enviados
    p = e["politicas"]
    assert [h["id"] for h in p["hallazgos"]] == [ids[0], ids[1]]  # la IA no puede citar una regla que no existe
    assert p["rechazo"]["id"] == ids[0] and p["revisada_ia"]
    assert e["color"] == "rojo" and e["explicacion"].startswith("Rechazo directo por la regla «Regla ficticia")
    assert p["casos"][0]["producto"] == "Citrato de magnesio en polvo 500 g"


def test_factores_con_ventas_compras_e_inventario_de_smnbi():
    """Diego (2026-10-26): demanda, margen, inventario y proveedor salen de lo que se cargó de SMNBI (datos ficticios)."""
    from datetime import date, timedelta

    from sqlalchemy import delete

    from datos.modelos import Carga, CompraOrden, Inventario, Proveedor, Tienda, VentaSemanal
    from modulos.compras import realidad_producto as rr

    h = uuid.uuid4().hex[:6]
    depto, sub, marca, prov = f"Depto real {h}", f"Sub real {h}", f"MARCA{h}".upper(), f"PR{h}"
    fin = date(2027, 3, 29)  # lunes; más reciente que cualquier otra venta de las pruebas
    tiendas = [f"T{h}A", f"T{h}B", f"M{h}"]
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        cid = carga.carga_id
        bd.execute(update(Producto).where(Producto.sku.like("RP-%")).values(activo=False))
        filas = [("Magnesio quelado polvo 300 g", sub, 10), ("Citrato de magnesio polvo 200 g", sub, 6),
                 ("Té verde 25 sobres", "Otra", 4), ("Té de manzanilla 25 sobres", "Otra", 2),
                 ("Moringa 60 caps", "Otra", 1)]
        prods = []
        for desc, s_, ritmo in filas:
            p = Producto(sku=f"RP-{uuid.uuid4().hex[:8]}", descripcion=desc, departamento=depto, subcategoria=s_,
                         marca=marca, codigo_proveedor=prov, precio_lista_con_impuestos=Decimal("150"), origen="ETL", activo=True)
            bd.add(p)
            prods.append((p, ritmo))
        bd.add_all([Tienda(almacen=tiendas[0], nombre="Tienda ficticia A", categoria="C", carga_id=cid),
                    Tienda(almacen=tiendas[1], nombre="Tienda ficticia B", categoria="B", carga_id=cid),
                    Tienda(almacen=tiendas[2], nombre="Mayoreo ficticio", categoria="MAY", carga_id=cid),
                    Proveedor(proveedor=prov, nombre="Proveedor Real Ficticio, S.A. de C.V.", dias_entrega=5, carga_id=cid)])
        for semana in range(26):
            lunes = fin - timedelta(weeks=semana)
            for p, ritmo in prods:
                # Las últimas 13 semanas venden el doble; el mayoreo no cuenta
                piezas = Decimal(ritmo * (2 if semana < 13 else 1))
                for t in tiendas[:1] if ritmo < 5 else tiendas:
                    pz = piezas * 100 if t == tiendas[2] else piezas
                    bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=p.sku, tienda=t, semana=lunes, empresa="EJ",
                                        piezas=pz, piezas_devueltas=Decimal(0), importe_bruto=pz * 100, descuento=Decimal(0),
                                        importe=pz * 100, costo=pz * 60, tickets=1, carga_id=cid))
        for p, _ in prods[:2]:
            bd.add(Inventario(fecha_corte=fin, empresa="EJ", almacen=tiendas[0], sku=p.sku, existencia=Decimal(2000), carga_id=cid))
        for i in range(2):
            bd.add(CompraOrden(empresa="EJ", orden=f"OC{h}{i}", proveedor=prov, almacen=tiendas[0], fecha_orden=fin - timedelta(days=20),
                               piezas_pedidas=Decimal(100), primera_entrada=fin - timedelta(days=6), piezas_recibidas=Decimal(90),
                               piezas_perdidas=Decimal(10), piezas_rechazadas=Decimal(0), carga_id=cid))
        bd.commit()
        try:
            v = rr.ventana(bd)
            assert v.fin == fin and tiendas[2] in v.mayoreo
            s = rp.Sujeto(tipo="idea", nombre="Magnesio quelado en polvo sabor limón", marca=marca, departamento=depto,
                          forma="Polvo", precio=Decimal("150"), costo=Decimal("80"), margen=Decimal("38.13"))
            parecidos = rp.buscar_parecidos(bd, s, sub)
            assert parecidos[0][0].sku == prods[0][0].sku

            # Prueba de calibración: califica un producto que ya vendemos como si fuera nuevo, sin escribir nada
            from scripts import calibrar_radar as cal
            fila = cal.calificar(bd, prods[0][0], v, date.today())
            assert fila["sku"] == prods[0][0].sku and fila["margen_real"] == Decimal("40.0")
            assert fila["demanda"] is not None and fila["puntaje"] is not None
            assert cal.muestra(bd, v, 2)

            d = rp.f_demanda(bd, s, parecidos, v)
            assert d.puntaje is not None and not d.provisional, d.detalle
            assert "sin mayoreo" in d.detalle and "+100 %" in d.detalle and "de 2 tiendas" in d.detalle

            r = rp.f_rentabilidad(bd, s, sub, v)
            assert f"«{sub}» dejan en realidad 40.0 %" in r.detalle  # (100 − 60) / 100

            c = rp.f_categoria(bd, s, sub, parecidos, v)
            assert "días de venta" in c.detalle and "Podría quitarle venta" in c.detalle

            pr_ = rp.f_proveedor(bd, s, parecidos)
            # Surte 90 % (80 puntos) y tarda 9 días hábiles (14 naturales, con el 15 de marzo festivo) contra 5 (−10)
            assert pr_.puntaje == 70 and "surtió 90 %" in pr_.detalle and "tarda 9 días hábiles" in pr_.detalle
            assert "ya nos surte la marca" in pr_.detalle
            # Una propuesta se reconoce por su razón social, sin importar «S.A. de C.V.»
            s2 = rp.Sujeto(tipo="propuesta", nombre="Otro", proveedor_nombres=["PROVEEDOR REAL FICTICIO SA DE CV"])
            assert rp.f_proveedor(bd, s2, []).detalle.startswith("Con su historial real de compras")
        finally:
            for tabla in (VentaSemanal, Inventario, CompraOrden, Tienda, Proveedor):
                bd.execute(delete(tabla).where(tabla.carga_id == cid))
            bd.execute(delete(Carga).where(Carga.carga_id == cid))
            bd.commit()


def test_reconoce_el_mismo_producto_y_su_presentacion():
    """«Demograss Plus 30 Cápsulas» es el SKU «DEMOGRASS PLUS 30 CAP» aunque la marca del catálogo sea el proveedor;
    la de 90 cápsulas y la de otra marca no lo son (datos ficticios)."""
    s = rp.Sujeto(tipo="idea", nombre="Demograss Plus 30 Cápsulas", marca="Demograss")
    mismo = Producto(sku="X1", descripcion="DEMOGRASS PLUS C/30 CAPS", marca="GRUPO EJEMPLO", subcategoria="ELIMINADOR")
    otra_pres = Producto(sku="X2", descripcion="DEMOGRASS PLUS 90 CAP", marca="GRUPO EJEMPLO", subcategoria="ELIMINADOR")
    otra_marca = Producto(sku="X3", descripcion="PLUS 30 CAP", marca="OTRA", subcategoria="ELIMINADOR")
    assert rp.presentacion("Demograss Plus 30 Cápsulas") == rp.presentacion("DEMOGRASS PLUS C/30 CAPS")
    assert rp.es_mismo(s, mismo) and not rp.es_mismo(s, otra_pres) and not rp.es_mismo(s, otra_marca)
    parecidos = [(otra_pres, Decimal("0.9")), (mismo, Decimal("0.8")), (otra_marca, Decimal("0.5"))]
    assert rp.mismo_de(s, parecidos) is mismo
    assert rp.subcategoria_de_parecidos(parecidos).subcategoria == "ELIMINADOR"
    assert rp.subcategoria_de_parecidos([(mismo, Decimal("0.9"))]) is None  # con uno solo no se infiere


def test_precio_descarta_internet_fuera_de_rango_y_usa_el_que_ya_vendemos():
    """Un precio 9 veces mayor no es la misma presentación: se descarta (datos ficticios)."""
    from modulos.compras import mercado_producto as mp

    internet = mp.Mercado(precios=[{"precio": 699, "vendedor": "Tienda A", "fuente": "sitio"},
                                   {"precio": 95, "vendedor": "Tienda B", "fuente": "sitio"},
                                   {"precio": 105, "vendedor": "Tienda C", "fuente": "sitio"}])
    s = rp.Sujeto(tipo="idea", nombre="Demograss Plus 30 Cápsulas", marca="Demograss", precio=Decimal("90"))
    mismo = Producto(sku="X1", descripcion="DEMOGRASS PLUS 30 CAP", precio_lista_con_impuestos=Decimal("83"))
    f = rp.f_precio(s, [(mismo, Decimal("1"))], internet, mismo)
    assert "Ya lo vendemos (X1)" in f.detalle and "Se descartaron 1" in f.detalle
    assert "$95" in f.detalle or "95" in f.detalle  # mediana de 95, 105 y 90
    sin_mismo = rp.f_precio(s, [(mismo, Decimal("0.8"))], internet)
    assert "Se descartaron 1" in sin_mismo.detalle and "en internet" in sin_mismo.valor


def test_mismo_producto_con_palabras_de_mas():
    """Compras escribe «Bebida hidratante … sabor …» y el catálogo no; otra presentación u otro sabor no es el mismo
    (datos ficticios)."""
    s = rp.Sujeto(tipo="idea", nombre="Bebida Hidratante Marcax Mineral Sabor Fresa Kiwi 355 ml", marca="MARCAX")
    assert rp.es_mismo(s, Producto(sku="A", descripcion="MARCAX MINERAL FRESA KIWI 355 ML", marca="MARCAX"))
    assert not rp.es_mismo(s, Producto(sku="B", descripcion="MARCAX FRESA KIWI 630 ML", marca="MARCAX"))
    assert not rp.es_mismo(s, Producto(sku="C", descripcion="MARCAX MINERAL 355 ML", marca="MARCAX"))
    assert not rp.es_mismo(s, Producto(sku="D", descripcion="MARCAX MINERAL MORA AZUL 355 ML", marca="MARCAX"))


def test_explicacion_entendible():
    """El resumen dice cuántos puntos faltan, qué sube, qué baja y qué lo haría cambiar, sin palabras técnicas."""
    s = rp.Sujeto(tipo="idea", nombre="Producto ficticio")
    peso = {f: Decimal(100) / 6 for f in rp.FACTORES}
    factores = {f: rp.Factor(70, "dato", "x") for f in rp.FACTORES}
    factores["demanda"] = rp.Factor(90, "12 piezas por tienda al mes", "x")
    factores["precio"] = rp.Factor(40, "+15 % contra internet", "x", False, "c",
                                   "Para verde tendría que venderse en $95 o menos.")
    factores["tendencia"] = rp.Factor(None, None, "Sin datos")
    texto = rp.explicacion_simple(s, 68, "amarillo", "alta", factores, peso)
    assert "Le faltan 13 puntos para verde" in texto
    assert "**Lo que lo sube:** demanda (90)" in texto and "**Lo que lo baja:** precio (40)" in texto
    assert "Precio: para verde tendría que venderse en $95 o menos" in texto and "Faltan datos de tendencia" in texto
    calc, mejora = rp._precio_explicado(Decimal("1.15"), Decimal("100"), "el mercado")
    assert "15 % más caro: 40" in calc and "$94.90" in mejora
    for palabra in ("mediana", "percentil", "umbral"):
        assert palabra not in texto + calc + mejora


def test_precio_no_compara_presentaciones_distintas():
    """Si los parecidos cuestan 5 veces más (otra presentación), no se califica el precio contra ellos."""
    s = rp.Sujeto(tipo="idea", nombre="Creatina 300 g", precio=Decimal("100"))
    caro = Producto(sku="X9", descripcion="Creatina 2 kg", precio_lista_con_impuestos=Decimal("624"))
    f = rp.f_precio(s, [(caro, Decimal("0.6"))])
    assert f.puntaje is None and "no parecen la misma presentación" in f.detalle
