"""Radar de productos inteligente (plan del 17 nov 2026): memoria del comité, «Aceptado a prueba», revisión a 4, 8 y
12 semanas y el pronóstico por lanzamientos. Datos ficticios."""
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from datos.modelos import Carga, Tienda, VentaSemanal
from datos.modelos import Producto
from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import seguimiento as sg
from modulos.compras.modelos_comite import ComiteProducto, ProductoSeguimiento
from modulos.compras.modelos_productos import ProductoEvaluacion
from tests.test_comite import R, cerrar_pendientes, item_de
from tests.test_productos import catalogo_ficticio, sincrono  # noqa: F401  (fixture)

INICIO = date(2026, 11, 30)  # lunes; antes de la última semana de venta de las demás pruebas (2027-03-29)


def tiendas_ficticias(n: int = 3) -> list[str]:
    claves = [f"P{uuid.uuid4().hex[:5].upper()}" for _ in range(n)]
    with Session(motor()) as bd:
        c = Carga(fuente="SMNBI_INVENTARIO", disparada_por="manual", estado="completa")
        bd.add(c)
        bd.flush()
        bd.add_all([Tienda(almacen=a, nombre=f"Tienda prueba {a}", region=f"Región {k}", categoria="B", carga_id=c.carga_id)
                    for k, a in enumerate(claves)])
        bd.commit()
    return claves


def vender(sku: str, tiendas: dict[str, float], semanas: int = 12) -> None:
    with Session(motor()) as bd:
        c = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(c)
        bd.flush()
        for w in range(semanas):
            lunes = INICIO + timedelta(weeks=w)
            for t, piezas in tiendas.items():
                bd.add(VentaSemanal(mes=lunes.replace(day=1), sku=sku, tienda=t, semana=lunes, empresa="EJ",
                                    piezas=Decimal(str(piezas)), piezas_devueltas=Decimal(0), importe_bruto=Decimal(100),
                                    descuento=Decimal(0), importe=Decimal(100), costo=Decimal(50), tickets=1,
                                    carga_id=c.carga_id))
        bd.commit()


def test_aceptado_a_prueba_memoria_y_seguimiento(admin: TestClient, sincrono):  # noqa: F811
    cerrar_pendientes()
    depto, _ = catalogo_ficticio()
    rid = admin.post(f"{R}/reuniones", json={"fecha": f"2028-{uuid.uuid4().int % 12 + 1:02d}-{uuid.uuid4().int % 28 + 1:02d}"}).json()["id"]
    idea = admin.post("/api/compras/productos/ideas", json={
        "nombre": "Ashwagandha en cápsulas 60", "marca": "Marca Ficticia", "departamento": depto,
        "precio_visto": "220", "costo_estimado": "110"}).json()["sujeto"]["id"]
    otra = admin.post("/api/compras/productos/ideas", json={
        "nombre": "Té verde matcha 100 g", "marca": "Otra Ficticia", "departamento": depto,
        "precio_visto": "180", "costo_estimado": "90"}).json()["sujeto"]["id"]
    admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": idea})
    reunion = admin.post(f"{R}/reuniones/{rid}/productos", json={"idea_id": otra}).json()
    i1, i2 = item_de(reunion, tipo="idea", sujeto_id=idea), item_de(reunion, tipo="idea", sujeto_id=otra)
    r = admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "prefiltro"})
    assert r.status_code == 200, r.text
    for i in (i1, i2):
        r = admin.put(f"{R}/productos/{i['id']}/prefiltro", json={"resultado": "pasa", "motivo": "Vale la pena verlo"})
        assert r.status_code == 200, r.text
    for x in admin.get(f"{R}/reuniones/{rid}").json()["productos"]:  # lo que dejaron otras pruebas «En espera»
        if not x["prefiltro"]:
            admin.put(f"{R}/productos/{x['id']}/prefiltro", json={"resultado": "no_pasa", "motivo": "De otra prueba"})
    r = admin.post(f"{R}/reuniones/{rid}/estado", json={"estado": "comite"})
    assert r.status_code == 200, r.text

    # «Aceptado a prueba» pide tiendas conocidas y fecha de revisión
    url = f"{R}/productos/{i1['id']}/decision"
    base = {"decision": "a_prueba", "motivo": "Probarlo antes de surtir toda la cadena"}
    assert admin.put(url, json=base).status_code == 400
    assert admin.put(url, json={**base, "prueba_tiendas": ["NOEXISTE"], "prueba_revision": "2027-03-01"}).status_code == 400
    tiendas = tiendas_ficticias()
    assert admin.get(f"{R}/productos/{i1['id']}/tiendas-prueba").status_code == 200
    r = admin.put(url, json={
        **base, "prueba_tiendas": tiendas[:2], "prueba_revision": "2027-03-01", "prueba_precio": "199",
        "prueba_condicion": "Si no vende, el proveedor recoge sin costo",
        "indicadores": [{"factor": "sabor", "sentido": "a_favor"},
                        {"factor": "precio", "sentido": "en_contra", "motivo": "Más caro que el de la competencia"}],
        "radar_error_factor": "demanda", "radar_error_motivo": "Este tipo de producto se vende más de lo que dice"})
    assert r.status_code == 200, r.text
    x = item_de(r.json(), id=i1["id"])
    assert x["decision"] == "a_prueba" and x["prueba_tiendas"] == tiendas[:2]
    assert x["radar_error_factor"] == "demanda" and len(x["indicadores"]) == 2
    assert x["prueba_condicion"].startswith("Si no vende")
    # Denegado no guarda datos de prueba
    r = admin.put(f"{R}/productos/{i2['id']}/decision", json={
        "decision": "denegado", "motivo": "Ya tenemos uno igual", "prueba_tiendas": tiendas[:1],
        "indicadores": [{"factor": "ya_tenemos", "sentido": "en_contra"}], "radar_error_factor": "categoria"})
    assert r.status_code == 200 and item_de(r.json(), id=i2["id"])["prueba_tiendas"] == []

    # Lo que aprende el radar del comité
    a = admin.get(f"{R}/aprendizaje").json()
    assert {"demanda", "categoria"} <= {e["factor"] for e in a["errores"]}
    demanda = next(e for e in a["errores"] if e["factor"] == "demanda")
    assert "Este tipo de producto se vende más de lo que dice" in demanda["ejemplos"]
    assert {"sabor", "precio", "ya_tenemos"} <= {i["factor"] for i in a["indicadores"]}

    # SKU de alta: solo para aceptados
    assert admin.put(f"{R}/productos/{i2['id']}/sku", json={"sku": "X1"}).status_code == 409
    sku = f"EJSEG{uuid.uuid4().hex[:6].upper()}"
    assert item_de(admin.put(f"{R}/productos/{i1['id']}/sku", json={"sku": sku}).json(), id=i1["id"])["sku"] == sku

    # Revisión a 4, 8 y 12 semanas: solo cuenta la venta de las tiendas de la prueba; 1 pieza a la semana por tienda
    vender(sku, {tiendas[0]: 1, tiendas[1]: 1, tiendas[2]: 50})
    with Session(motor()) as bd:
        i = bd.get(ComiteProducto, i1["id"])
        i.decision_en = datetime(2026, 12, 1, 10, 0)
        e = bd.scalar(select(ProductoEvaluacion).where(ProductoEvaluacion.idea_id == idea, ProductoEvaluacion.estado == "lista")
                      .order_by(ProductoEvaluacion.evaluacion_id.desc()))
        e.pronostico = pn.Pronostico(base=1.0, tramos={"4": [0.5, 1, 2], "8": [5, 8, 12], "12": [1, 2, 3]}).a_json()
        e.creada_en = datetime(2026, 11, 20)
        bd.commit()
        eid = e.evaluacion_id
        sg.revisar(bd)
        filas = {s.semana: s for s in bd.scalars(select(ProductoSeguimiento).where(ProductoSeguimiento.item_id == i1["id"]))}
    assert set(filas) == {4, 8, 12}
    assert all(f.tiendas == 2 for f in filas.values())
    assert abs(float(filas[4].real) - 4.35) < 0.05  # 1 pieza a la semana = 4.35 al mes
    assert filas[4].resultado == "arriba" and filas[4].propuesta == "mantener"
    assert filas[8].resultado == "abajo" and filas[8].propuesta == "mantener"
    assert filas[12].resultado == "arriba" and filas[12].propuesta == "ampliar"
    assert "ampliarlo" in filas[12].texto
    s = item_de(admin.get(f"{R}/reuniones/{rid}").json(), id=i1["id"])["seguimiento"]
    assert [x["semana"] for x in s] == [4, 8, 12] and s[0]["rango"] == [0.5, 1.0, 2.0]
    d = admin.get(f"/api/compras/productos/evaluaciones/{eid}").json()
    assert d["pronostico"]["tramos"]["12"] == [1, 2, 3]
    assert admin.get(f"/api/compras/productos/evaluaciones/{eid}/reporte").status_code == 200
    with Session(motor()) as bd:  # no repite
        sg.revisar(bd)
        assert len(list(bd.scalars(select(ProductoSeguimiento).where(ProductoSeguimiento.item_id == i1["id"])))) == 3
    cerrar_pendientes()


class _Bd:
    """Solo lo que usa entrenar(): la subcategoría de cada SKU."""

    def __init__(self, sub: dict):
        self.sub = sub

    def execute(self, _):
        sub = self.sub

        class _R:
            def all(self):
                return list(sub.items())

        return _R()


def test_pronostico_aprende_de_los_lanzamientos(monkeypatch):
    """5 productos que ya estaban venden 10 piezas por tienda a la semana; 6 lanzamientos arrancan con 0.5 a 1.5
    veces eso. El modelo debe decir «un nuevo arranca vendiendo ~1 vez lo típico» y el examen debe ser honesto."""
    inicio = date(2026, 1, 5)
    datos, sub = {}, {}
    for k in range(5):
        datos[f"V{k}"] = {inicio + timedelta(weeks=w): (10.0 * 4, 4) for w in range(40)}
        sub[f"V{k}"] = "S"
    for k, factor in enumerate((0.5, 0.75, 1.0, 1.0, 1.25, 1.5)):
        ini = inicio + timedelta(weeks=10 + k)
        datos[f"N{k}"] = {ini + timedelta(weeks=w): (10.0 * factor * 4, 4) for w in range(14)}
        sub[f"N{k}"] = "S"
    monkeypatch.setattr(pn, "_semanales", lambda bd: (datos, inicio, inicio + timedelta(weeks=39)))
    monkeypatch.setattr(pn, "_por_tienda_como_demanda", lambda *a: None)  # sin base real de tiendas
    pn._CACHE.clear()
    m = pn.entrenar(_Bd(sub))
    pn._CACHE.clear()
    assert len(m.lanzamientos) == 6
    bajo, medio, alto = m.razones[12]
    assert bajo < 1.0 < alto and abs(medio - 1.0) < 0.01
    assert m.examen["suficientes"] and 0 <= m.examen["dentro_pct"] <= 100
    p = pn.Pronostico(base=2.0, tramos={"12": [round(2 * bajo, 2), 2.0, round(2 * alto, 2)]})
    assert pn.Pronostico.de_json(p.a_json()).rango(12) == p.rango(12)
    assert json.loads(p.a_json())["base"] == 2.0


def test_y_si_se_calcula_con_codigo(admin: TestClient, sincrono):  # noqa: F811
    from modulos.compras import asistente_comite as ac

    assert ac.pide_y_si("¿y si lo vendemos a 199?") == (Decimal("199"), None)
    assert ac.pide_y_si("¿qué pasa si el costo baja a $1,050.50?") == (None, Decimal("1050.50"))
    assert ac.pide_y_si("precio 250 y costo 120") == (Decimal("250"), Decimal("120"))
    assert ac.pide_y_si("¿por qué salió rojo?") == (None, None)
    depto, _ = catalogo_ficticio()
    idea = admin.post("/api/compras/productos/ideas", json={
        "nombre": "Colágeno hidrolizado 300 g", "marca": "Marca Ficticia", "departamento": depto,
        "precio_visto": "232", "costo_estimado": "150"}).json()["sujeto"]["id"]
    with Session(motor()) as bd:
        ev = bd.scalar(select(ProductoEvaluacion).where(ProductoEvaluacion.idea_id == idea)
                       .order_by(ProductoEvaluacion.evaluacion_id.desc()))
        sec = ac.y_si(bd, ev, "¿y si el costo baja a 100?")
        assert sec and "margen queda en 50 %" in sec.texto and "Rentabilidad: de" in sec.texto
        secciones = ac.ficha_evaluacion(bd, ev, {"nombre": "x"})
        assert any(x.titulo == "Dónde dice el comité que el radar se equivoca" for x in secciones)


def test_rechazo_por_promesa_exige_una_promesa():
    """Wonu, 17 nov 2026: «Creatina monohidratada con mioinositol y ácido fólico» no es promesa terapéutica."""
    from modulos.compras import politicas_producto as pp

    regla = {"titulo": "Suplemento con nombre, promesa o alusión terapéutica improcedente", "descripcion": ""}
    assert not pp.dato_de_la_regla("Creatina monohidratada con mioinositol y ácido fólico", regla)
    assert pp.dato_de_la_regla("Ayuda a reducir la ansiedad y cura el insomnio", regla)
    assert pp.dato_de_la_regla("FDA Approved", regla)
    aviso = {"titulo": "Sin aviso de funcionamiento", "descripcion": "Proveedor sin aviso de funcionamiento"}
    assert pp.dato_de_la_regla("No tiene aviso de funcionamiento", aviso)
    assert not pp.dato_de_la_regla("Caja con sobres individuales", aviso)


def test_reglas_con_numeros_las_calcula_el_sistema():
    """Diego, 17 nov 2026: la IA decía que 2.4 piezas al mes no llegan a 3 en 6 meses. Ahora la cuenta es de código."""
    from modulos.compras import politicas_producto as pp

    venta = {"piezas_por_tienda_mes": 2.4, "de": "el pronóstico"}
    baja = {"tipo": "rechazo", "titulo": "Baja a 6 meses", "minimo": 3, "maximo": None,
            "unidad": "piezas por sucursal en 6 meses"}
    c = pp.calcular(baja, {"venta_esperada": venta})
    assert c["resultado"] == "cumple" and "14.4" in c["motivo"]
    assert pp.calcular(baja, {"venta_esperada": {"piezas_por_tienda_mes": 0.3, "de": "x"}})["resultado"] == "no_cumple"
    assert pp.calcular(baja, {})["resultado"] == "sin_datos"

    margen = {"tipo": "umbral", "titulo": "Margen mínimo", "minimo": 31, "maximo": None, "unidad": "%"}
    assert pp.calcular(margen, {"margen_pct": 32.2})["resultado"] == "cumple"
    assert pp.calcular(margen, {"margen_pct": 20})["resultado"] == "no_cumple"

    caja = {"tipo": "umbral", "titulo": "Piezas por caja master", "minimo": None, "maximo": 30, "unidad": "piezas"}
    assert pp.calcular(caja, {"piezas_por_caja": None})["resultado"] == "sin_datos"
    assert pp.calcular(caja, {"piezas_por_caja": 48})["resultado"] == "no_cumple"

    # Sin número o unidad desconocida: la revisa la IA
    assert pp.calcular({"tipo": "rechazo", "titulo": "Sin registro", "minimo": None, "maximo": None, "unidad": None}, {}) is None
    assert pp.calcular({"tipo": "umbral", "titulo": "Vida de anaquel", "minimo": 12, "maximo": None, "unidad": "meses"}, {}) is None


def test_gs1_se_decide_con_lo_capturado_no_con_el_codigo():
    """Wonu, 17 nov 2026: la IA decía «No cumple» por el código 750…; el prefijo no prueba ni descarta la acreditación."""
    from modulos.compras import politicas_producto as pp

    regla = {"tipo": "politica", "titulo": "GS1 y códigos de barras"}
    assert pp.gs1(regla, {"codigo_barras": "7503053821217"})["resultado"] == "sin_datos"
    assert pp.gs1(regla, {"inscrito_gs1": "si"})["resultado"] == "cumple"
    assert pp.gs1(regla, {"inscrito_gs1": "no"})["resultado"] == "no_cumple"
    assert pp.gs1({"tipo": "politica", "titulo": "Ficha técnica"}, {}) is None


def test_demanda_cuenta_tiendas_surtidas_y_semanas_desde_la_primera_venta():
    """Plan de Demanda (19 nov 2026): 1 pieza en 1 tienda en 1 semana ya no sale como 4.3 piezas por tienda al mes."""
    from datetime import date, timedelta

    from datos.modelos import Carga, Inventario, VentaSemanal
    from modulos.compras import realidad_producto as rr

    h = uuid.uuid4().hex[:6]
    fin, sku = date(2020, 6, 1), f"DM-{h}"  # antes de todo: no mueve la ventana de otras pruebas
    tiendas = [f"D{h}{i}" for i in range(4)]
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        # Otro producto vende en las 4 tiendas (así cuentan como tiendas); el nuestro, 1 pieza hace 9 semanas
        for i, t in enumerate(tiendas):
            bd.add(VentaSemanal(mes=fin.replace(day=1), sku=f"OT-{h}", tienda=t, semana=fin, empresa="EJ", piezas=Decimal(1),
                                piezas_devueltas=Decimal(0), importe_bruto=Decimal(10), descuento=Decimal(0),
                                importe=Decimal(10), costo=Decimal(6), tickets=1, carga_id=carga.carga_id))
        semana = fin - timedelta(weeks=9)
        bd.add(VentaSemanal(mes=semana.replace(day=1), sku=sku, tienda=tiendas[0], semana=semana, empresa="EJ",
                            piezas=Decimal(1), piezas_devueltas=Decimal(0), importe_bruto=Decimal(10),
                            descuento=Decimal(0), importe=Decimal(10), costo=Decimal(6), tickets=1, carga_id=carga.carga_id))
        from sqlalchemy import func

        corte = bd.scalar(select(func.max(Inventario.fecha_corte))) or date(2020, 6, 5)  # el último corte que exista
        for t in tiendas[1:3]:
            bd.add(Inventario(fecha_corte=corte, empresa="EJ", almacen=t, sku=sku, existencia=Decimal(3), carga_id=carga.carga_id))
        bd.commit()
        v = rr.Ventana(desde=fin - timedelta(weeks=25), fin=fin, mayoreo=set())
        x = rr.venta_por_sku(bd, v, [sku])[sku]
        assert x.tiendas == 3 and x.semanas == 10  # vendió en 1 y tenía existencia en 2; 10 semanas desde la venta
        assert round(x.por_tienda_mes, 3) == round(1 / 3 / 10 * rr.SEMANAS_MES, 3)


def test_precio_cercano_por_pieza_y_por_gramo():
    """Un sobre de $47 se compara con un sobre de $45, no con un bote de 5 lb ni con un sobre de $25 de creatina."""
    s = rp.Sujeto(tipo="idea", nombre="Proteína sobre", contenido="40 g", precio=Decimal("47"))

    def prod(desc, precio):
        p = Producto(sku="x", descripcion=desc, precio_lista_con_impuestos=Decimal(precio))
        p._ficha = None
        return p

    assert rp.precio_cercano(s, prod("PROWINNER PROTEINA SOBRE 50 G", "44.80"))
    assert not rp.precio_cercano(s, prod("MGN WHEY PROTEIN 2270 G", "810"))  # por pieza, muy lejos
    assert not rp.precio_cercano(s, prod("PROTEINA SOBRE 200 G", "45"))  # por pieza cerca, por gramo 4 veces


def test_demanda_sale_del_pronostico(monkeypatch):
    """Una sola cifra: la Demanda califica el pronóstico a 12 semanas contra los lanzamientos de 2026."""
    from datetime import date

    from modulos.compras import pronostico as pn
    from modulos.compras import realidad_producto as rr

    monkeypatch.setattr(rr, "venta_por_sku", lambda *a, **k: {})
    monkeypatch.setattr(pn, "lugar_entre_lanzamientos", lambda bd, x, depto=None: (80.0, 120, True))
    pron = pn.Pronostico(base=2.0, base_de="2 parecido(s) que ya vendemos", tramos={"12": [1.5, 2.0, 2.6]})
    s = rp.Sujeto(tipo="idea", nombre="Proteína", departamento="DEPORTES", precio=Decimal("47"))
    f = rp.f_demanda(None, s, [], rr.Ventana(date(2026, 4, 6), date(2026, 9, 28), set()), None, pron)
    assert f.puntaje == 89  # 50 + (80 − 50) × 1.3, sin ajuste por tendencia
    assert "2.0 piezas por tienda" in f.valor and "lanzamientos" in f.valor and "entre 1.5 y 2.6" in f.detalle


def test_lanzamientos_se_miden_como_la_demanda(monkeypatch):
    """Caso Wonu (19 nov 2026): el lanzamiento se divide entre las tiendas que ya lo habían vendido, no entre las de su
    mejor semana; así el pronóstico de un nuevo y los lanzamientos se comparan en la misma unidad."""
    from datetime import date, timedelta

    from datos.modelos import Carga, VentaSemanal
    from modulos.compras import pronostico as pn
    from modulos.compras import realidad_producto as rr

    h = uuid.uuid4().hex[:6]
    ini, sku = date(2019, 1, 7), f"LZ-{h}"
    with Session(motor()) as bd:
        carga = Carga(fuente="ETL_VENTAS", disparada_por="manual", estado="completa")
        bd.add(carga)
        bd.flush()
        # Tienda A desde la semana 0, B desde la 2, C hasta la 10: a las 4 semanas lo habían vendido 2 tiendas
        for t, w in (("A", 0), ("B", 2), ("C", 10)):
            semana = ini + timedelta(weeks=w)
            bd.add(VentaSemanal(mes=semana.replace(day=1), sku=sku, tienda=f"L{h}{t}", semana=semana, empresa="EJ",
                                piezas=Decimal(2), piezas_devueltas=Decimal(0), importe_bruto=Decimal(10),
                                descuento=Decimal(0), importe=Decimal(10), costo=Decimal(6), tickets=1,
                                carga_id=carga.carga_id))
        bd.commit()
        monkeypatch.setattr(rr, "ventana", lambda bd, semanas=0: rr.Ventana(ini, ini + timedelta(weeks=30), set()))
        x = type("L", (), {})()
        x.sku, x.inicio, x.por_tienda = sku, ini, {4: 0.0}
        datos = {sku: {ini: (2.0, 1), ini + timedelta(weeks=2): (2.0, 1), ini + timedelta(weeks=10): (2.0, 1)}}
        pn._por_tienda_como_demanda(bd, [x], datos, ini + timedelta(weeks=30))
    assert round(x.por_tienda[4], 2) == round(4 / 2 / 4 * rr.SEMANAS_MES, 2)  # 4 piezas, 2 tiendas, 4 semanas
