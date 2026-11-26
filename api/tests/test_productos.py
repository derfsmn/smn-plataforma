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
        assert "misma marca y línea" in rp.f_categoria(bd, s, None, parecidos).detalle
        assert rp.f_precio(s, parecidos).puntaje is not None
        assert rp.f_rentabilidad(bd, s).detalle.startswith("Sin datos: falta el costo estimado.")


# ---------------------------------------------------------------- ideas de Compras

def test_idea_con_foto_se_evalua_y_compras_corrige(admin: TestClient, sincrono):
    depto, skus = catalogo_ficticio()
    foto = subir(admin, "frente.png", PNG)
    # Marca única: otra idea con la misma marca y nombre (de una corrida anterior) daría su subcategoría («variante»)
    datos = {"nombre": "Citrato de magnesio en polvo", "marca": f"Marca Ficticia {depto[-4:]}", "departamento": depto,
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
    # Sin proveedor: si sale verde o amarillo se abre sola su búsqueda de proveedor
    esperado = "buscar_proveedor" if e["color"] in {"verde", "amarillo"} else "nueva"
    assert e["sujeto"]["tipo"] == "idea" and e["sujeto"]["estado"] == esperado
    # Sin IA en pruebas: los productos parecidos votan, y todos son «Minerales» (v0.5.4)
    assert e["clasificacion_origen"] == "votos" and e["subcategoria"] == "Minerales"
    assert "Clasificación automática: Minerales (segura" in e["explicacion"]
    parecidos = [c["sku"] for c in e["comparables"]]
    assert set(skus[:3]) <= set(parecidos) and skus[3] not in parecidos
    f = {x["factor"]: x for x in e["factores"]}
    assert f["proveedor"]["puntaje"] is None and f["demanda"]["puntaje"] is None
    assert f["rentabilidad"]["valor"] == "Deja 38.1 % de margen, 8.1 puntos arriba del mínimo (30 %)"
    assert not f["precio"]["provisional"] and "parecido" in f["precio"]["detalle"]  # anaquel es una mitad del Precio (22 nov 2026)
    assert e["color"] in {"verde", "amarillo", "rojo"} and e["puntaje"] is not None and e["explicacion"]
    assert [x["archivo_id"] for x in e["fotos"]] == [foto]
    # Las fotos las ve Compras aunque no las haya subido; una foto que no es de la idea, no
    _, responsable, _ = alta_usuario(admin, rol="compras_responsable")
    assert responsable.get(f"{R}/ideas/{e['sujeto']['id']}/fotos/{foto}").status_code == 200
    assert responsable.get(f"{R}/ideas/{e['sujeto']['id']}/fotos/{otra}").status_code == 404

    # v0.5.4: la clasificación ya no se confirma a mano (Diego, 24 nov 2026); al recalcular se vuelve a votar
    r = admin.put(f"{R}/evaluaciones/{eid}/clasificacion",
                  json={"rama": "Suplementos", "subcategoria": "Minerales", "segmento": "Magnesio"})
    assert r.status_code == 410 and "automática" in r.json()["detail"]
    n = admin.post(f"{R}/evaluaciones/{eid}/recalcular").json()
    e2 = admin.get(f"{R}/evaluaciones/{n['id']}").json()
    assert e2["clasificacion_origen"] == "votos" and e2["subcategoria"] == "Minerales" and e2["vigente"]
    assert [h["id"] for h in e2["historial"]] == [n["id"], eid]
    assert admin.post(f"{R}/evaluaciones/{eid}/recalcular").status_code == 409  # ya no es la vigente
    cat = {x["factor"]: x for x in e2["factores"]}["categoria"]
    assert cat["valor"] == "Surtido normal: 3 productos en su subcategoría, una normal tiene 3"

    # Parecidos: un SKU que no existe se rechaza; los que fija Compras se conservan al recalcular
    assert admin.put(f"{R}/evaluaciones/{n['id']}/comparables", json={"skus": ["NO-EXISTE"]}).status_code == 400
    n = admin.put(f"{R}/evaluaciones/{n['id']}/comparables", json={"skus": [skus[1]]}).json()
    n = admin.post(f"{R}/evaluaciones/{n['id']}/recalcular").json()
    e3 = admin.get(f"{R}/evaluaciones/{n['id']}").json()
    assert [(c["sku"], c["origen"]) for c in e3["comparables"]] == [(skus[1], "compras")]
    assert e3["clasificacion_origen"] == "votos"
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
    admin.patch(f"/api/compras/propuestas/{pid}/margen", json={"lista_margen": "A"})
    assert admin.post(f"/api/compras/propuestas/{pid}/estado", json={"estado": "lista"}).status_code == 200

    e = admin.get(f"{R}/propuestas/{pid}").json()
    assert e["estado"] == "lista", e["error"]
    assert e["sujeto"]["tipo"] == "propuesta" and e["sujeto"]["folio"].startswith("PN-")
    assert e["sujeto"]["proveedor"] == "Proveedor de Prueba S.A."
    f = {x["factor"]: x for x in e["factores"]}
    assert f["rentabilidad"]["valor"] == "Deja 50 % de margen, 19 puntos arriba del mínimo (31 %)"
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
    assert "10 % más barato que en internet" in f["valor"] and "nuestro anaquel" in f["valor"] and not f["provisional"] and "Walmart" in f["detalle"]  # dos mitades (22 nov 2026)

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
            {"id": ids[0], "resultado": "no_cumple", "motivo": "Precio visto 1,500 (ficticio)", "dato": "$1,500"},
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
            assert "sin mayoreo" in d.detalle and "+100 %" not in d.detalle and "se venden en 2 de " in d.detalle  # el total depende de otras pruebas

            r = rp.f_rentabilidad(bd, s, sub, v)
            assert f"«{sub.capitalize()}» (2 productos) deja 40 %" in r.detalle  # (100 − 60) / 100

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
    assert "15 % más caro: 60" in calc and "$94.00" in mejora
    for palabra in ("mediana", "percentil", "umbral"):
        assert palabra not in texto + calc + mejora


def test_recalibracion_9_nov():
    """Escalas recalibradas con productos que ya vendemos (9 nov 2026): igual al mercado = 75, 1 punto por 1 %;
    tendencia sin señal no cuenta ni baja la confianza; demanda abierta alrededor de 50."""
    assert rp._por_precio(Decimal("1")) == 75 and rp._por_precio(Decimal("0.94")) == 81
    assert rp._por_precio(Decimal("1.20")) == 55
    assert rp._percentil_para(81) == 74
    peso = {f: Decimal(100) / 6 for f in rp.FACTORES}
    factores = {f: rp.Factor(84, "dato", "x") for f in rp.FACTORES}
    factores["tendencia"] = rp.Factor(None, rp.SIN_SENAL, "Ninguna señal habla de él")
    fuera = rp.sin_senal(factores)
    assert fuera == {"tendencia"} and rp.sumar(factores, peso, fuera) == (84, "alta")
    assert rp.sin_senal({"tendencia": rp.Factor(None, None, "Sin datos")}) == set()
    s = rp.Sujeto(tipo="idea", nombre="Producto ficticio")
    texto = rp.explicacion_simple(s, 84, "verde", "alta", factores, peso, fuera)
    assert f"{len(rp.FACTORES) - 1} de {len(rp.FACTORES) - 1} factores" in texto and "no cuenta: ni lo sube ni lo baja" in texto
    assert "Es una oportunidad" not in texto and "Faltan datos de tendencia" not in texto


def test_precio_no_compara_presentaciones_distintas():
    """Sin tamaño, si los parecidos cuestan 5 veces más (otra presentación), no se califica el precio contra ellos."""
    s = rp.Sujeto(tipo="idea", nombre="Creatina chica", precio=Decimal("100"))
    caro = Producto(sku="X9", descripcion="Creatina grande", precio_lista_con_impuestos=Decimal("624"))
    f = rp.f_precio(s, [(caro, Decimal("0.6"))])
    assert f.puntaje is None and "no parecen la misma presentación" in f.detalle


def test_precio_por_unidad_y_tamano_cercano():
    """Diego (11 nov 2026): 120 g a $184 no se compara contra 60 g a $131 por el total, sino por gramo; y si hay
    parecidos de tamaño cercano, solo esos (un bote de 2 kg siempre sale más barato por gramo). Datos ficticios."""
    assert rp.tamano("15 tabletas de 5.3g c/u") == {"pz": Decimal("15"), "g": Decimal("79.5")}
    assert rp.tamano(None, "Shampoo 1 L") == {"ml": Decimal("1000")}
    assert rp.tamano("30 cápsulas de 413mg") == {"pz": Decimal("30")}  # los mg son dosis
    assert rp.tamano("8 piezas de 100g")["g"] == Decimal("800")
    s = rp.Sujeto(tipo="idea", nombre="Desodorante ficticio 120g", contenido="120 G", precio=Decimal("120"))
    cercano = Producto(sku="A", descripcion="DESODORANTE FICTICIO 100 G", precio_lista_con_impuestos=Decimal("100"))
    granel = Producto(sku="B", descripcion="DESODORANTE FICTICIO 2 KG", precio_lista_con_impuestos=Decimal("1600"))
    f = rp.f_precio(s, [(cercano, Decimal("0.6")), (granel, Decimal("0.5"))])
    assert f.puntaje == 75 and "$1.00 por gramo" in f.detalle and "por gramo" in f.valor
    solo_granel = rp.f_precio(s, [(granel, Decimal("0.5"))])
    assert "por gramo" in solo_granel.valor  # sin cercanos, por gramo contra el que haya


def test_rentabilidad_baja_parejo_hasta_15():
    """Diego (11 nov 2026): abajo del mínimo baja parejo hasta 0 con 15 % de margen (antes 30.4 % contra 31 % ya
    perdía mucho y 18 % valía 0); además dice a qué precio o costo llegaría al mínimo."""
    class SinReglas:
        def scalars(self, *_):
            return self

        def all(self):
            return []

    bd = SinReglas()
    minimo = rp.margen_minimo(bd, None)[0]
    def puntos(margen):
        s = rp.Sujeto(tipo="idea", nombre="x", precio=Decimal("300"), costo=Decimal("210"), margen=Decimal(margen))
        return rp.f_rentabilidad(bd, s)
    assert puntos(minimo).puntaje == 60 and puntos("15").puntaje == 0 and puntos("10").puntaje == 0
    medio = (minimo + 15) / 2
    assert puntos(medio).puntaje == 30
    r = puntos("18.8")
    assert r.puntaje > 0 and r.valor.startswith("Margen bajo") and "venderlo en $" in r.mejora


def test_parecidos_sin_repetir_y_de_su_subcategoria():
    """11 nov 2026: con subcategoría conocida solo entran los de esa (si son menos de 3, se completan con su rama) y la
    misma descripción no se repite."""
    def p(sku, desc, sub, rama="R1"):
        return Producto(sku=sku, descripcion=desc, subcategoria=sub, rama=rama, precio_lista_con_impuestos=Decimal(50))
    lista = [(p("1", "CINTA KINESIO 5 M", "VENDAS"), Decimal("0.9")), (p("2", "CINTA KINESIO 5 M", "VENDAS"), Decimal("0.8")),
             (p("3", "PRE WORKOUT AZUL", "PRE-ENTRENO", "R2"), Decimal("0.7")), (p("4", "VENDA ELASTICA", "RODILLERAS"), Decimal("0.4"))]
    salida = [x.sku for x, _ in rp._depurar(lista, "VENDAS", "R1")]
    assert salida == ["1", "4"]
    assert "azul" not in rp.palabras("Cinta Kinesiológica Azul Pre-cortada")


def test_rechazo_solo_con_prueba_y_de_su_tipo():
    """11 nov 2026: una regla de suplementos no aplica a un shaker; sin el dato que lo pruebe es aviso, no rechazo."""
    from modulos.compras import politicas_producto as pp

    shaker = {"nombre": "Smart Shaker Vaso Mezclador 500 ml", "departamento": "DEPORTES", "precio_venta_con_impuestos": 210}
    regla = {"titulo": "Suplementos sin registro sanitario", "descripcion": None}
    assert pp.tipo_que_no_es(regla, shaker) == "suplemento"
    assert pp.tipo_que_no_es(regla, {"nombre": "Glicinato de magnesio 60 cápsulas"}) is None
    assert pp.dato_comprobado("Smart Shaker", shaker) and pp.dato_comprobado("$210", shaker)
    assert not pp.dato_comprobado("tiene azúcar", shaker) and not pp.dato_comprobado(None, shaker)


def test_dictamen_de_comprador():
    """11 nov 2026: una línea de comprador: negociar a qué costo o precio y contra qué se compara (datos ficticios)."""
    s = rp.Sujeto(tipo="idea", nombre="Producto ficticio", precio=Decimal("300"), costo=Decimal("210"), margen=Decimal("18.8"))
    factores = {f: rp.Factor(70, "x", "x") for f in rp.FACTORES}
    par = [(Producto(sku="A", descripcion="PARECIDO FICTICIO 100 G", precio_lista_con_impuestos=Decimal("250")), Decimal("0.6"))]
    d = rp.dictamen(s, "amarillo", factores, par, Decimal("31"))
    assert d.startswith("Dictamen: Negociar: pedir costo de $178.45") and "PARECIDO FICTICIO 100 G ($250.00)" in d
    factores["precio"] = rp.Factor(30, "Caro", "x")
    assert "subirle el precio no conviene" in rp.dictamen(s, "rojo", factores, par, Decimal("31"))
    assert rp.dictamen(s, "rojo", factores, [], Decimal("31"), {"titulo": "Regla X"}).startswith("Dictamen: No meter")
    assert rp.dictamen(rp.Sujeto(tipo="idea", nombre="x"), "verde", factores, [], None) == "Dictamen: Meter."


def test_rentabilidad_con_lista_de_margen_y_membresia():
    """Diego, 22 nov 2026: el tipo de producto (lista A–F) fija el mínimo, y cuenta también el precio de membresía."""
    from decimal import Decimal as D

    from modulos.compras import radar_productos as rp

    ls = rp.listas()
    assert (ls["D"].lista, ls["D"].membresia) == (D(36), D(31)) and (ls["B"].lista, ls["B"].membresia) == (D(45), D(35))
    # membresía = lista × (1 − 36 %) / (1 − 31 %): con la regla deja justo los dos mínimos
    assert rp.membresia_de(D("100"), ls["D"]) == D("92.75")
    s = rp._con_lista(rp.Sujeto(tipo="idea", nombre="Proteína ficticia", precio=D("100"), margen=D("36")), "D", None)
    assert s.membresia_calculada and s.precio_membresia == D("92.75") and abs(s.margen_membresia - D("31")) < D("0.05")
    f = rp.f_rentabilidad(None, s)
    assert f.puntaje == 60 and "lista D, Nutrición deportiva nacional" in f.detalle and "cuenta el de lista" in f.calculo
    # Compras capturó una membresía más baja: cuenta la peor de las dos
    s2 = rp._con_lista(rp.Sujeto(tipo="idea", nombre="Proteína ficticia", precio=D("100"), margen=D("40")), "D", D("80"))
    assert not s2.membresia_calculada and s2.margen_membresia == D("25.00")
    f2 = rp.f_rentabilidad(None, s2)
    assert f2.puntaje < 60 and f2.valor.startswith("Margen bajo con membresía: deja 25 %")
    assert "al precio de lista deja 40 % (mínimo 36 %)" in f2.valor


def test_precio_mitad_lista_y_mitad_membresia():
    from decimal import Decimal as D

    from modulos.compras import mercado_producto as mp
    from modulos.compras import radar_productos as rp

    internet = mp.Mercado(precios=[{"vendedor": "Tienda ficticia", "precio": 100.0, "titulo": "x", "liga": None}])
    s = rp.Sujeto(tipo="idea", nombre="Producto ficticio", precio=D("100"), precio_membresia=D("90"))
    f = rp.f_precio(s, [], internet)
    # lista igual al mercado = 75; membresía 10 % abajo = 85; promedio 80
    assert f.puntaje == 80 and "con membresía" in f.valor and "Con precio de membresía ($90" in f.detalle
    sin = rp.f_precio(rp.Sujeto(tipo="idea", nombre="Producto ficticio", precio=D("100")), [], internet)
    assert sin.puntaje == 75


def test_ingrediente_principal_clasifica_y_no_se_queda_fuera():
    """Caso BDM Life Berberina (24 nov 2026): las berberinas que ya vendemos están en «Auxiliar en la diabetes»; la IA lo
    puso en «Hierbas suecas» y se quedó sin parecidos."""
    def prod(i, desc, sub, rama, precio="200", marca=None):
        return Producto(producto_id=i, sku=f"B{i}", descripcion=desc, marca=marca, subcategoria=sub, rama=rama,
                        precio_lista_con_impuestos=Decimal(precio), activo=True)
    hep, diab = "SISTEMA HEPATICO", "AUXILIAR EN LA DIABETES"
    activos = [prod(1, "BERBERINA 60 CAP", diab, hep), prod(2, "BERBERINA HCL 90 CAP", diab, hep, "545"),
               prod(3, "PURE BERBERINE 180 CAP", diab, hep, "712"), prod(4, "BERBERINA MAS CANELA 30 CAP", diab, hep),
               prod(5, "BERBERINA 60 ML", "AUXILIAR EN LA DIGESTION", "SISTEMA DIGESTIVO"),
               prod(6, "LIFE OMEGA 3 60 CAP", "OMEGAS", "ACEITES"), prod(7, "LIFE COLAGENO", "BELLEZA", "PIEL"),
               prod(8, "LIFE MAGNESIO", "MINERALES", "MINERALES"), prod(9, "OMEGA 9 60 CAP", "OMEGAS", "ACEITES"),
               prod(10, "JUVETERNAL VITAMINA E FACIAL 90 CAP", "FACIAL", "PIEL", marca="JUVETERNAL")]
    s = rp.Sujeto(tipo="propuesta", nombre="BDM Life Berberina + Piperina + Omega 9 – Metabolismo", marca="JUVETERNAL",
                  ingrediente="Berberina HCl")
    x = rp.por_ingrediente(s, activos)
    assert x and x.palabra == "berber" and x.subcategoria == diab and x.rama == hep
    assert x.ids == {1, 2, 3, 4, 5} and x.de_acuerdo == 4
    # Sin ingrediente capturado, sale del nombre: «life» es corta y «bdm» también; berberina va antes que omega
    s.ingrediente = None
    assert rp.por_ingrediente(s, activos).palabra == "berber"
    # Con otra subcategoría, los del ingrediente no se tiran (ni el de otra subcategoría con el mismo ingrediente)
    lista = [(p, Decimal("0.5")) for p in activos[:5]] + [(activos[9], Decimal("0.4"))]
    salida = {p.producto_id for p, _ in rp._depurar(lista, "HIERBAS SUECAS", "PLANTAS", x.ids)}
    assert salida == {1, 2, 3, 4, 5}
    # Sin acuerdo de subcategoría no decide: tres productos en tres subcategorías
    regados = [prod(20, "CURCUMA 60 CAP", "A", "R"), prod(21, "CURCUMA POLVO", "B", "R"), prod(22, "CURCUMA TE", "C", "R")]
    assert rp.por_ingrediente(rp.Sujeto(tipo="idea", nombre="Curcuma Forte 90 cap"), regados) is None


def test_revisar_parecidos_no_quita_los_del_ingrediente(monkeypatch):
    class R:
        texto = '{"revision": [{"n": 1, "mismo_tipo": false, "motivo": "no"}]}'
    llamadas = []
    monkeypatch.setattr(rp.puerta, "ejecutar", lambda *a, **k: llamadas.append(k["mensaje"]) or R())
    monkeypatch.setattr(rp.puerta, "ventana", lambda *a, **k: None)
    a = Producto(producto_id=1, sku="A", descripcion="BERBERINA 60 CAP")
    b = Producto(producto_id=2, sku="B", descripcion="HIERBAS SUECAS 500 ML")
    s = rp.Sujeto(tipo="idea", nombre="Berberina forte")
    quedan, quitados = rp.revisar_parecidos(None, s, [(a, Decimal("0.5")), (b, Decimal("0.3"))], None, {1})
    assert [p.sku for p, _ in quedan] == ["A"] and [p.sku for p, _ in quitados] == ["B"]
    assert "BERBERINA" not in llamadas[0]  # al de su ingrediente ni se le pregunta a la IA


def test_colageno_con_inositol_no_se_queda_sin_parecidos(monkeypatch):
    """Diego, 26 nov 2026: Colágeno + Inositol B-FIT 360 g salió «sin parecidos» y Demanda 7 aunque vendemos más de 200
    colágenos. Los colágenos están regados en varias subcategorías (no hay 60 % de acuerdo), la idea quedó en otra
    subcategoría y los de otro tamaño se tiraban: ahora los de su ingrediente principal nunca se tiran."""
    def prod(i, desc, sub, rama, precio="300"):
        return Producto(producto_id=i, sku=f"C{i}", descripcion=desc, subcategoria=sub, rama=rama,
                        precio_lista_con_impuestos=Decimal(precio), activo=True)
    activos = [prod(1, "COLAGENO HIDROLIZADO 300 G", "BELLEZA", "PIEL"),
               prod(2, "COLAGENO HIDROLIZADO CON BIOTINA 300 G", "BELLEZA", "PIEL"),
               prod(3, "COLAGENO TIPO II 30 CAP", "ARTICULACIONES", "HUESOS"),
               prod(4, "COLAGENO MARINO 60 CAP", "ARTICULACIONES", "HUESOS"),
               prod(5, "PEPTIDOS DE COLAGENO 250 G", "PROTEINA", "DEPORTE"),
               prod(6, "COLAGENO HIDROLIZADO 1.1 KG", "PROTEINA", "DEPORTE", "210"),
               prod(7, "MYO INOSITOL 60 CAP", "SALUD FEMENINA", "MUJER"),
               prod(8, "FEMME BALANCE 30 SOBRES", "SALUD FEMENINA", "MUJER"),
               prod(9, "MAGNESIO 60 CAP", "MINERALES", "MINERALES")]
    monkeypatch.setattr(rp, "catalogo_activo", lambda bd: activos)
    monkeypatch.setattr(rp, "cargar_fichas", lambda bd, ps: None)
    monkeypatch.setattr(rp, "ficha_de", lambda p: None)
    monkeypatch.setattr(rp.fi, "cercanos_por_funcion", lambda bd, ficha: [])
    s = rp.Sujeto(tipo="idea", nombre="COLAGENO + INOSITOL", marca="B-FIT", contenido="360 G", forma="Polvo", precio=Decimal("749"))
    assert rp.por_ingrediente(s, activos) is None  # regados: no decide la subcategoría
    palabra, ids = rp.del_ingrediente(s, activos)
    assert palabra == "colage" and ids == {1, 2, 3, 4, 5, 6}
    antes = {p.producto_id for p, _ in rp.buscar_parecidos(None, s, "SALUD FEMENINA", "MUJER")}
    assert not antes & ids  # así se quedaba: ni un colágeno
    ahora = {p.producto_id for p, _ in rp.buscar_parecidos(None, s, "SALUD FEMENINA", "MUJER", ids)}
    assert {1, 2, 5, 6} <= ahora  # los colágenos en polvo; los de cápsulas salen porque hay 3 o más de su forma
    # Una palabra que sale en casi todo el catálogo no cuenta como ingrediente
    muchos = ([prod(100 + i, f"HIDROLIZADO MARCA{i} 300 G", "X", "Y") for i in range(30)]
              + [prod(200 + i, f"OTRO PRODUCTO{i}", "X", "Y") for i in range(270)])
    assert rp.del_ingrediente(rp.Sujeto(tipo="idea", nombre="Hidrolizado"), muchos) is None


def test_revision_parecidos_por_lote(admin):
    """Cuenta las evaluaciones vigentes con pocos parecidos teniendo productos con su ingrediente (26 nov 2026)."""
    from sqlalchemy import select as sel

    from core.bd import _fabrica
    from modulos.compras.modelos_productos import ProductoEvaluacion, ProductoIdea
    from nucleo.modelos import Usuario

    with _fabrica()() as bd:
        i = ProductoIdea(nombre="COLAGENO + INOSITOL revisión", creada_por=bd.scalar(sel(Usuario.usuario_id).limit(1)))
        bd.add(i)
        bd.flush()
        e = ProductoEvaluacion(idea_id=i.idea_id, estado="lista", vigente=True, puntaje=31)
        bd.add(e)
        bd.commit()
        try:
            r = admin.get("/api/compras/productos/revision-parecidos")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["evaluaciones"] >= 1 and d["sin_parecidos"] >= 1 and "afectadas" in d
            x = admin.get("/api/compras/productos/revision-parecidos/excel")
            assert x.status_code == 200 and x.content[:2] == b"PK"
        finally:
            bd.delete(e)
            bd.delete(i)
            bd.commit()
