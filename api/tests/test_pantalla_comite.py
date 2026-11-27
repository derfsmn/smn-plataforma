"""Pantalla del comité de producto nuevo (plan aprobado por Diego el 20 nov 2026): pesos de Dirección, Tendencia dentro
de Demanda y los datos de los 4 niveles. Catálogo y venta FICTICIOS (los de las pruebas del reporte)."""
from decimal import Decimal

from fastapi.testclient import TestClient

from modulos.compras import pantalla_comite as pc
from modulos.compras import radar_productos as rp
from modulos.compras.pronostico import Pronostico
from tests.test_productos import sincrono  # noqa: F401
from tests.test_reporte_producto import R, _idea, catalogo_creatinas  # noqa: F401


def test_pesos_de_direccion():
    peso, origen = rp.pesos(None)
    assert origen == "direccion" and sum(peso.values()) == 100
    assert (peso["demanda"], peso["categoria"], peso["rentabilidad"]) == (50, 25, Decimal("12.5"))
    # Diego, 25 nov 2026: el Precio en dos temas de 6.25; el Precio junto ya no pesa
    assert (peso["precio_anaquel"], peso["precio_afuera"], peso["precio"]) == (Decimal("6.25"), Decimal("6.25"), 0)
    assert peso["tendencia"] == 0 and peso["proveedor"] == 0


def test_tendencia_dentro_de_demanda():
    alta, media = rp.Factor(100, "x", ""), rp.Factor(80, "x", "")
    assert rp.ajuste_tendencia(12.0, alta)[0] == 10 and rp.ajuste_tendencia(-15.0, None)[0] == -5
    assert rp.ajuste_tendencia(3.0, media)[0] == 3 and rp.ajuste_tendencia(9.9, rp.Factor(65, "x", ""))[0] == 0
    d = rp.con_tendencia(rp.Factor(18, "Se vende poco", "Detalle.", calculo="Calificación: 18."), 3.0, media)
    assert d.puntaje == 21 and "suma 3 por la x" in d.calculo and "crece 3 %" in d.detalle
    nombrada = rp.Factor(80, "Señal media en el radar de tendencias: «Creatina para mujeres»", "")
    assert "suma 3 por la señal media en el radar de tendencias: «Creatina para mujeres»" in rp.ajuste_tendencia(0, nombrada)[1][0]
    assert "una señal media en internet" in rp.ajuste_tendencia(0, rp.Factor(80, None, ""))[1][0]
    assert rp.con_tendencia(rp.Factor(None, None, ""), 20.0, alta).puntaje is None


def test_escenarios_a_tres_meses():
    p = Pronostico(tramos={"4": [0.5, 0.7, 0.9], "8": [0.6, 0.8, 1.0], "12": [0.6, 0.9, 1.1]})
    pes, esp, opt = pc._escenarios(p, 100, Decimal("116"), Decimal("30"))
    assert [x["clave"] for x in (pes, esp, opt)] == ["pesimista", "esperado", "optimista"]
    assert esp["piezas"] == 240 and esp["venta"] == 24000 and esp["utilidad"] == 7200 and esp["clase"] == "D"
    assert opt["clase"] == "C" and pes["clase"] == "E" and esp["acumulado"] == [7000, 15000, 24000]
    assert pc._escenarios(None, 100, Decimal("116"), None) == []


def test_razon_de_cada_parecido(catalogo_creatinas):
    s = rp.Sujeto(tipo="idea", nombre="Creatina + Inositol", precio=Decimal("599"), contenido="30 sobres de 7.6 g")
    sobre = rp.Producto(descripcion="QUENUT CREATINA CREAPURE SOBRE 5 G", precio_lista_con_impuestos=Decimal("25.50"))
    bote = rp.Producto(descripcion="CREATINA 450 G", precio_lista_con_impuestos=Decimal("502.90"))
    assert rp.razon_cercano(s, sobre) == (False, "El nuevo cuesta 23.5 veces su precio")
    assert rp.razon_cercano(s, bote) == (True, "Precio cercano, por pieza y por gramo")  # 228 g contra 450 g
    s.contenido = "30 g"
    assert rp.razon_cercano(s, bote) == (False, "Por gramo, muy distinto")


def test_pantalla_de_wonu(admin: TestClient, sincrono, catalogo_creatinas):  # noqa: F811
    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina + Inositol", "marca": f"Wonu{c['h']}", "departamento": "DEPORTES (ejemplo)",
                      "ingrediente": "Creatina", "forma": "Sobre", "contenido": "30 sobres de 7.6 g",
                      "precio_nuestro": "599", "precio_visto": "653", "donde_se_vio": "Chedraui",
                      "costo_estimado": "350", "activo_g_porcion": "5", "porciones": 30})
    assert e["estado"] == "lista", e.get("error")
    pesos = {f["factor"]: f["peso"] for f in e["factores"]}
    assert pesos["demanda"] == "50.00" and pesos["tendencia"] == "0.00"
    r = admin.get(f"{R}/evaluaciones/{e['id']}/pantalla")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["pesos_direccion"] and [f["factor"] for f in p["factores"]] == ["demanda", "categoria", "rentabilidad",
                                                                           "precio_anaquel", "precio_afuera"]
    assert p["precio_anaquel"]["lado"] == "anaquel" and p["precio_afuera"]["titular"]["resaltado"]
    con = [f for f in p["factores"] if f["puntaje"] is not None]
    assert abs(sum(f["aporte"] for f in con) - p["puntaje"]) <= 1  # el anillo suma la calificación
    assert p["cifras"]["porciones"] == 30 and p["cifras"]["por_porcion"] == 19.97 and p["cifras"]["margen"] == 32.22
    assert p["precio"]["afuera"] and any(a["vendedor"].startswith("Chedraui") for a in p["precio"]["afuera"])
    assert p["parecidos"] and all("meses" in x and "por_que" in x for x in p["parecidos"])
    sobre = next(x for x in p["parecidos"] if x["sku"] == c["sobre"])
    assert sobre["cuenta"] is False and "veces su precio" in sobre["por_que"] and sobre["meses"]
    assert p["demanda"]["titular"]["antes"] in ("Vendería ", "")
    assert p["rentabilidad"]["titular"]["resaltado"] == "32.2 % de margen"
    # Precio en dos mitades y con quién compite en el anaquel (22 nov 2026)
    m = p["precio"]["mitades"]
    assert "anaquel" in m and isinstance(p["precio"]["compite"], list)
    # Lo que vio Compras (Chedraui) se enseña pero no califica ni entra en Rentabilidad (Diego, 22 nov 2026)
    chedraui = next(a for a in p["precio"]["afuera"] if a["vendedor"].startswith("Chedraui"))
    assert chedraui["cuenta"] is False and chedraui["fuente"] == "compras"
    assert m["afuera"]["puntaje"] is None and "no cuenta" in m["afuera"]["detalle"]
    assert not any("mercado" in x["nombre"] for x in p["rentabilidad"]["escenarios"])
    assert "venta_afuera" in p["demanda"]
    # Mercado Libre no dice «no apareció» si no se buscó, ni enseña fallas de conexión a Compras (26 nov 2026)
    nota_ml = p["precio"]["mercado_libre_nota"]
    assert nota_ml is None or nota_ml == "Mercado Libre: no tiene publicado este mismo producto."
    # La venta que se presenta es la de la prueba en 10 tiendas; cada producto mencionado se puede picar
    assert p["cifras"]["tiendas"] is None or p["cifras"]["tiendas"] <= 10
    assert all(x["sku"] in p["catalogo"] for x in p["parecidos"] + p["categoria"]["mas_vendidos"])
    assert admin.get(f"{R}/evaluaciones/999999/pantalla").status_code == 404
    # La pantalla no vuelve a medir los lanzamientos (con los datos reales tardaba minutos; Diego, 22 nov 2026)
    from modulos.compras import pronostico as pn

    pn._CACHE.clear()
    pc._GUARDADAS.clear()
    original = pn.entrenar
    pn.entrenar = lambda bd: (_ for _ in ()).throw(AssertionError("la pantalla no debe entrenar"))
    try:
        assert admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").status_code == 200
    finally:
        pn.entrenar = original
    # La segunda vez sale de memoria y trae las fotos de la ruta
    pc._GUARDADAS.clear()
    a = admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").json()
    assert len(pc._GUARDADAS) == 1
    assert admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").json() == a


def test_pantalla_guardada_al_evaluar(admin: TestClient, sincrono, catalogo_creatinas, monkeypatch):  # noqa: F811
    """Plan del 22 nov 2026: la pantalla se arma al terminar la evaluación y abrirla solo la lee."""
    import json

    from modulos.compras.modelos_productos import ProductoEvaluacion

    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina monohidratada", "marca": f"Guardada{c['h']}", "departamento": "DEPORTES (ejemplo)",
                      "ingrediente": "Creatina", "forma": "Polvo", "contenido": "300 g", "precio_nuestro": "450",
                      "costo_estimado": "260"})
    assert e["estado"] == "lista", e.get("error")
    with rp._sesion() as bd:
        fila = bd.get(ProductoEvaluacion, e["id"])
        guardada = json.loads(fila.pantalla)
        assert fila.pantalla_venta == guardada["ventana"] and guardada["evaluacion_id"] == e["id"]
    # Abrirla no vuelve a armar nada
    pc._GUARDADAS.clear()
    monkeypatch.setattr(pc, "_armar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe rearmar")))
    p = admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").json()
    assert p["puntaje"] == guardada["puntaje"] and "venta_al" not in p
    # Con venta nueva enseña la guardada, dice con qué venta se armó y la rearma aparte
    aparte = []
    monkeypatch.setattr(pc, "_rearmar_aparte", aparte.append)
    with rp._sesion() as bd:
        fila = bd.get(ProductoEvaluacion, e["id"])
        vieja = {**guardada, "ventana": "venta de SMNBI del 01/01/2026 al 30/06/2026, sin mayoreo", "hasta": "30/06/2026"}
        fila.pantalla, fila.pantalla_venta = json.dumps(vieja), vieja["ventana"]
        bd.commit()
    pc._GUARDADAS.clear()
    p = admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").json()
    assert p["venta_al"] == "30/06/2026" and aparte == [e["id"]]
    # Si Compras cambia el color final, se vuelve a armar en ese momento
    monkeypatch.undo()
    r = admin.post(f"{R}/evaluaciones/{e['id']}/color", json={"color": "verde", "motivo": "Prueba de pantalla guardada"})
    assert r.status_code == 200, r.text
    p = admin.get(f"{R}/evaluaciones/{e['id']}/pantalla").json()
    assert p["color"] == "verde" and "venta_al" not in p


def test_preparar_pantallas(admin: TestClient, sincrono, catalogo_creatinas):  # noqa: F811
    """Una oportunidad sin costo ni proveedor también tiene pantalla; «Preparar» arma las que faltan."""
    from modulos.compras.modelos_productos import ProductoEvaluacion

    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina sabor limón", "marca": f"SinCosto{c['h']}", "departamento": "DEPORTES (ejemplo)",
                      "ingrediente": "Creatina", "forma": "Polvo", "contenido": "250 g", "precio_nuestro": "399"})
    assert e["estado"] == "lista", e.get("error")
    with rp._sesion() as bd:
        fila = bd.get(ProductoEvaluacion, e["id"])
        fila.pantalla = fila.pantalla_venta = None
        bd.commit()
        r = pc.preparar(bd)
        assert r["armadas"] >= 1 and r["fallidas"] == 0
        bd.refresh(fila)
        assert fila.pantalla and pc._leer(fila)["cifras"]["costo"] is None
        assert pc.preparar(bd)["armadas"] == 0  # ya estaban todas
    estado = admin.get(f"{R}/pantallas").json()
    assert estado["sin_pantalla"] == 0 and estado["trabajo"] is None


def test_pagina_de_la_marca_no_es_competencia():
    """Wonu 22 nov 2026: wonu.mx a $599 salía como «al mismo precio» afuera."""
    assert rp.es_de_la_marca({"vendedor": "Wonu.mx", "liga": "https://wonu.mx/p/1"}, "Wonu")
    assert rp.es_de_la_marca({"vendedor": "Tienda X", "liga": "https://www.wonu.com.mx/x"}, "WONU")
    assert not rp.es_de_la_marca({"vendedor": "Walmart", "liga": "https://walmart.com.mx/wonu"}, "Wonu")
    assert not rp.es_de_la_marca({"vendedor": "Wonu.mx"}, None)
    from modulos.compras import mercado_producto as mp

    s = rp.Sujeto(tipo="idea", nombre="Creatina + Inositol", marca="Wonu", precio=Decimal("599"),
                  mercado=[(Decimal("653"), "Chedraui")])
    solo_marca = mp.Mercado(precios=[{"precio": "599", "vendedor": "Wonu.mx", "liga": "https://wonu.mx/a"}])
    f = rp.precio_afuera(s, [], solo_marca)
    assert f.puntaje is None and "precio sugerido" in f.detalle and "Chedraui en $653.00" in f.detalle
    con_otro = mp.Mercado(precios=[{"precio": "599", "vendedor": "Wonu.mx"}, {"precio": "660", "vendedor": "Amazon"}])
    f = rp.precio_afuera(s, [], con_otro)
    assert f.meta == Decimal("660") and f.puntaje == rp._por_precio(Decimal("599") / Decimal("660"))
    # El proveedor sí cuenta en una propuesta
    s.tipo = "propuesta"
    assert rp.precio_afuera(s, [], solo_marca).meta == Decimal("653")


def test_precio_que_lo_lleva_a_verde_y_a_competir():
    """«Qué lo subiría» decía $563.06 (lo que pide la mitad de afuera sola); con eso el promedio llegaba a 41."""
    afuera = rp.Factor(75, "En precio: igual", "", meta=Decimal("599"))
    anaquel = rp.Factor(0, "Caro", "", meta=Decimal("284.26"))
    f = rp.juntar_precio(afuera, anaquel, Decimal("599"))
    assert f.puntaje == 38
    meta = rp._precio_para(Decimal("599"), [Decimal("599"), Decimal("284.26")])
    assert round((rp._por_precio(meta / Decimal("599")) + rp._por_precio(meta / Decimal("284.26"))) / 2) > 80
    assert rp._n((1 - meta / Decimal("599")) * 100) in f.mejora and "contra nuestro anaquel" in f.mejora
    assert f.competir is not None and f.competir < Decimal("599")
    d = rp.dictamen(rp.Sujeto(tipo="idea", nombre="X", precio=Decimal("599"), margen=Decimal("40")), "rojo",
                    {"precio": f, "demanda": rp.Factor(70, "", "")}, [], Decimal("30"))
    assert "(hoy $599.00)" in d and "unos $599.00" not in d


def test_misma_linea_solo_de_la_misma_marca():
    s = rp.Sujeto(tipo="idea", nombre="Creatina Colágeno Inositol", marca="Wonu")
    otra = rp.Producto(sku="1", descripcion="UP CREATINA COLAGENO INOSITOL", marca="UP")
    suya = rp.Producto(sku="2", descripcion="WONU CREATINA 300 G", marca="WONU")
    assert rp.misma_linea(s, [(otra, Decimal("0.9")), (suya, Decimal("0.85"))]) == [suya]
    assert rp.misma_linea(s, [(suya, Decimal("0.5"))]) == []


def test_excel_para_comprobar_la_pantalla(admin: TestClient, sincrono, catalogo_creatinas, tmp_path):  # noqa: F811
    from modulos.compras.modelos_productos import ProductoEvaluacion
    from scripts import comprobar_pantalla as cp

    c = catalogo_creatinas
    e = _idea(admin, {"nombre": "Creatina + Inositol", "marca": f"Excel{c['h']}", "departamento": "DEPORTES (ejemplo)",
                      "ingrediente": "Creatina", "forma": "Sobre", "contenido": "30 sobres de 7.6 g",
                      "precio_nuestro": "599", "costo_estimado": "350", "porciones": 30})
    with rp._sesion() as bd:
        datos = cp.hojas(bd, bd.get(ProductoEvaluacion, e["id"]), con_lanzamientos=False)
        assert {"Resumen", "Factores", "Parecidos", "Precios de afuera"} <= set(datos)
        cp.a_excel(str(tmp_path / "x.xlsx"), "Prueba", datos)
    assert (tmp_path / "x.xlsx").stat().st_size > 0


def test_tienda_bloqueada_se_dice_en_palabras_de_negocio():
    """26 nov 2026 (Diego: «si Walmart no da, ¿cómo lo solucionamos?»): el bloqueo de una tienda no se ve como falla. Si
    su precio llegó por Google Shopping, en su renglón dice «visto en Google Shopping»; la nota va al final en palabras
    de negocio. Datos FICTICIOS."""
    from types import SimpleNamespace

    from modulos.compras import mercado_producto as mp
    from modulos.compras import pantalla_comite as pc
    from modulos.compras import radar_productos as rp

    m = mp.Mercado(buscado_en="2026-11-26T10:00:00", clave="x", notas=[
        "Walmart: bloqueó la consulta automática: pidió verificar identidad",
        "San Pablo: bloqueó la consulta automática (error 403)",
        "Chedraui: no lo tiene.",
        "Google Shopping, se buscó: «b fit colageno inositol 360 g»"],
        precios=[{"precio": 546.77, "vendedor": "Walmart", "fuente": "google", "titulo": "B-Fit Femme 360 g",
                  "liga": "https://www.walmart.com.mx/ip/x"},
                 {"precio": 600.0, "vendedor": "Tienda EJ", "fuente": "google", "titulo": "B-Fit Femme 360 g", "liga": "https://ej.mx/x"}])
    e = SimpleNamespace(mercado=m.a_json())
    notas = pc._notas_busqueda(e)
    assert not any("bloqueó" in n for n in notas)
    assert notas[0] == "Chedraui: no lo tiene." and notas[-2:] == [
        "San Pablo no deja consultar su sitio y no publicó este producto en Google Shopping.",
        "Walmart no deja consultar su sitio; su precio se tomó de Google ($546.77)."]
    afuera = pc._afuera(e, rp.Sujeto(tipo="idea", nombre="B-Fit Femme 360 g", marca="B-FIT"), None)
    por_vendedor = {a["vendedor"]: a for a in afuera}
    assert por_vendedor["Walmart"]["nota"] == "visto en Google Shopping" and por_vendedor["Tienda EJ"]["nota"] is None


def test_sin_tamano_va_a_la_ia_y_se_muestra_sin_contar(monkeypatch):
    """Decisión de Diego (26 nov 2026, colágeno B-Fit): «no dice el tamaño» no es «dice otro tamaño». Misma marca y mismo
    nombre sin tamaño en el título van a la IA local; confirmado cuenta, sin dato se muestra y no califica; si el título
    dice otro tamaño se sigue rechazando. Datos FICTICIOS, IA simulada."""
    from types import SimpleNamespace

    from modulos.compras import coincidencia as co
    from modulos.compras import mercado_producto as mp

    nombre, marca = "Colágeno + Inositol B-FIT 360 g", "B-FIT"
    items = [{"product_id": "G1", "title": "B FIT Femme Colágeno + Myo D Chiro Inositol en Polvo", "price": 546.77,
              "currency": "MXN", "seller": "Tienda EJ", "url": "https://ej.mx/1"},
             {"product_id": "G2", "title": "B FIT Colágeno Inositol 120 cápsulas", "price": 300, "currency": "MXN",
              "seller": "Otra EJ", "url": "https://ej.mx/2"}]
    cands = [co.candidato_de(i) for i in items]
    co.decidir(nombre, marca, cands, 85, set(), set())  # deja la evaluación en cada candidato
    assert mp._sin_tamano(cands[0]) and not mp._sin_tamano(cands[1])  # el de 120 cápsulas contradice: no va

    def ia(respuesta):
        monkeypatch.setattr(mp.puerta, "ejecutar", lambda *a, **k: SimpleNamespace(texto=respuesta))

    ia('{"mismo_producto": true, "tamano": "sin_dato", "claves": ["G1"], "confianza": 90, "motivo": "mismo producto"}')
    assert mp._revisar_sin_tamano(None, nombre, marca, cands)[:2] == ([], [cands[0]])
    ia('{"mismo_producto": true, "tamano": "confirmado", "claves": ["G1"], "confianza": 90, "motivo": "dice 360 g"}')
    assert mp._revisar_sin_tamano(None, nombre, marca, cands)[:2] == ([cands[0]], [])
    ia('{"mismo_producto": true, "tamano": "distinto", "claves": ["G1"], "confianza": 90, "motivo": "es de 180 g"}')
    assert mp._revisar_sin_tamano(None, nombre, marca, cands)[:2] == ([], [])
    ia('{"mismo_producto": false, "tamano": "sin_dato", "claves": [], "confianza": 90, "motivo": "otra variante"}')
    assert mp._revisar_sin_tamano(None, nombre, marca, cands)[:2] == ([], [])

    def sin_ia(*a, **k):
        raise mp.puerta.ErrorIA("caída")

    monkeypatch.setattr(mp.puerta, "ejecutar", sin_ia)
    assert mp._revisar_sin_tamano(None, nombre, marca, cands)[:2] == ([], [cands[0]])  # sin IA: se muestra, no cuenta

    # Se guarda y la pantalla lo enseña sin que cuente
    m = mp.Mercado(buscado_en="2026-11-26T10:00:00", clave="x", vistos=[
        {"precio": 546.77, "titulo": items[0]["title"], "vendedor": "Tienda EJ", "liga": "https://ej.mx/1", "motivo": ""}])
    m2 = mp.Mercado.de_json(m.a_json())
    assert m2.vistos == m.vistos and not m2.precios
    fila = pc._afuera(SimpleNamespace(mercado=m2.a_json()), rp.Sujeto(tipo="idea", nombre=nombre, marca=marca), None)[0]
    assert fila["cuenta"] is False and "tamaño sin confirmar" in fila["nota"] and fila["precio"] == 546.77


def test_que_se_busco_afuera_en_palabras_de_negocio():
    """26 nov 2026: sin calificaciones internas ni la lista de resultados que no tienen que ver; lo guardado no cambia."""
    from types import SimpleNamespace

    from modulos.compras import mercado_producto as mp

    s = rp.Sujeto(tipo="idea", nombre="Colágeno + Inositol B-FIT 360 g", marca="B-FIT", ingrediente="Colágeno")
    notas = [
        "Google Shopping: ningún resultado es claramente el mismo producto.",
        "Google Shopping, lo más parecido: «Biotina 5000mcg Colageno Uñas 120 Caps» (calificación 18; nombre 52; marca no "
        "comprobada; el título no trae «INOSITOL»; presentación distinta (360 g contra 120 capsulas)) | «B Fit Colágeno + Myo "
        "D Chiro Inositol en Polvo» (calificación 68; nombre 100; marca coincide; presentación no comprobada)",
        "Google Shopping, se buscó: «7503050636982» · «B FIT Colágeno Inositol 360 g»",
        "Google Shopping regresó 98: «Batidora ultra power KitchenAid» · «Refrigerador French Door Samsung»",
        "Google Shopping regresó 40: «B fit Colágeno con Astaxantina» · «Patines Roller en Linea Niños Talla»",
        "Google Shopping no aceptó la búsqueda «x y z» (40501 Invalid Field).",
    ]
    m = mp.Mercado(buscado_en="2026-11-26T10:00:00", clave="x", notas=notas)
    vistas = pc._notas_busqueda(SimpleNamespace(mercado=m.a_json()), s)
    texto = " ".join(vistas)
    assert "calificación" not in texto and "nombre 100" not in texto and "Batidora" not in texto and "Patines" not in texto
    assert "Lo más parecido en Google Shopping, que no se tomó: «Biotina 5000mcg Colageno Uñas 120 Caps» (no menciona " \
           "inositol, dice otra presentación); «B Fit Colágeno + Myo D Chiro Inositol en Polvo» (no dice el tamaño)." in vistas
    assert "Google Shopping regresó 98 resultados; ninguno era de esta marca ni de su ingrediente." in vistas
    assert "Google Shopping regresó 40 resultados; de esta marca o ingrediente: «B fit Colágeno con Astaxantina»." in vistas
    assert "Se buscó en Google Shopping: «7503050636982», «B FIT Colágeno Inositol 360 g»." in vistas
    assert "Google Shopping no aceptó la búsqueda «x y z»." in vistas
    assert mp.Mercado.de_json(m.a_json()).notas == notas  # lo guardado queda completo para diagnóstico


def test_tienda_bloqueada_vista_en_google_shopping_sin_tamano_no_dice_que_no_lo_publico():
    """Colágeno B-Fit en la laptop (26 nov 2026): la nota decía «Walmart no publicó este producto en Google Shopping»
    mientras arriba salía Walmart México a $576.80 (tamaño sin confirmar). Datos FICTICIOS."""
    from types import SimpleNamespace

    from modulos.compras import mercado_producto as mp

    m = mp.Mercado(buscado_en="2026-11-26T10:00:00", clave="x",
                   notas=["Walmart: bloqueó la consulta automática: pidió verificar identidad",
                          "Google Shopping regresó 40: «" + "B FIT Femme Colágeno + Myo D Chiro Inositol 40:1 en Polvo"[:60] + "»"],
                   vistos=[{"precio": 576.8, "titulo": "B-Fit Femme", "vendedor": "Walmart México", "liga": None, "motivo": ""}])
    notas = pc._notas_busqueda(SimpleNamespace(mercado=m.a_json()), rp.Sujeto(tipo="idea", nombre="Colágeno B-FIT", marca="B-FIT"))
    assert notas[-1] == "Walmart no deja consultar su sitio; en Google Shopping lo vimos a $576.80, sin el tamaño confirmado."
    assert any(n.endswith("Inositol 40:1 en Polvo».") or "…»" in n for n in notas)


def test_mercado_libre_en_pantalla_solo_en_palabras_de_negocio():
    """Revisión de usabilidad (26 nov 2026): «token rechazado» o «sin conectar» no se enseñan a Compras ni a Dirección."""
    from types import SimpleNamespace

    from modulos.compras import mercado_producto as mp
    from modulos.compras import pantalla_comite as pc

    def con(notas):
        m = mp.Mercado()
        m.notas = notas
        return SimpleNamespace(mercado=m.a_json())

    assert pc._nota_ml(con(["Mercado Libre: sin conectar (falta registrar la aplicación en Configuración)."]), []) is None
    assert pc._nota_ml(con(["Mercado Libre: rechazó el token (error 401)."]), []) is None
    assert pc._nota_ml(con([]), []) is None
    assert pc._nota_ml(con(["Mercado Libre: no regresó resultados."]), []) == "Mercado Libre: no tiene publicado este mismo producto."
    assert pc._nota_ml(con(["Mercado Libre: ningún resultado es claramente el mismo producto."]), []).startswith("Mercado Libre: no tiene")
