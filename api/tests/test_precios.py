"""Radar de precios. DataForSEO y la IA se simulan: nunca se llama a los reales.
Productos, vendedores y precios son ficticios (SKU con prefijo EJP)."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from core.bd import motor
from core.config import configuracion
from datos.modelos import Producto, ProductoFuente
from ia import puerta
from modulos.compras import coincidencia as co
from modulos.compras import dataforseo as dfs
from modulos.compras import imagenes as img
from modulos.compras import precios
from modulos.compras import tiendas as td
from modulos.compras.modelos_precios import (PrecioCoincidencia, PrecioCorrida, PrecioCorridaProducto, PrecioEnvio,
                                             PrecioObservacion, PrecioTiendaCoincidencia, PrecioVigilado)
from nucleo.modelos import Notificacion, ahora
from tests.conftest import alta_usuario

MARCA = "NATUREJ/VITAMINAS"


class DataForSEOSimulado:
    """Responde como DataForSEO con tareas en memoria. resultados[keyword] = items de Google Shopping;
    vendedores[product_id] = items de Sellers."""

    def __init__(self):
        self.resultados: dict[str, list[dict]] = {}
        self.vendedores: dict[str, list[dict]] = {}
        self.tareas: dict[str, tuple[str, dict]] = {}
        self.envios: list[tuple[str, int]] = []
        self.falla_post = False

    def __call__(self, metodo, ruta, cuerpo=None):
        tipo = "products" if "/products/" in ruta else "sellers"
        if ruta.endswith("task_post"):
            self.envios.append((tipo, len(cuerpo)))
            if self.falla_post:
                raise dfs.EnvioIncierto("sin respuesta")
            tareas = []
            for t in cuerpo:
                id_ = f"{tipo}-{uuid.uuid4().hex[:8]}"
                self.tareas[id_] = (tipo, t)
                tareas.append({"id": id_, "status_code": 20100, "cost": 0.001, "data": t})
            return {"status_code": 20000, "tasks": tareas}
        if ruta.endswith("tasks_ready"):
            return {"status_code": 20000, "tasks": [{"result": [{"id": i} for i, (tp, _) in self.tareas.items() if tp == tipo]}]}
        id_ = ruta.rsplit("/", 1)[1]
        _, t = self.tareas[id_]
        items = self.resultados.get(t["keyword"], []) if tipo == "products" else self.vendedores.get(t.get("product_id") or t.get("data_docid"), [])
        return {"status_code": 20000, "tasks": [{"status_code": 20000, "result": [{"items": items}]}]}


@pytest.fixture
def limpio(base_de_pruebas, monkeypatch):
    with Session(motor()) as bd:
        for t in (PrecioObservacion, PrecioCorridaProducto, PrecioEnvio, PrecioCorrida, PrecioCoincidencia, PrecioTiendaCoincidencia,
                  PrecioVigilado):
            bd.execute(delete(t))
        bd.execute(delete(Notificacion).where(Notificacion.titulo.like("Radar de precios%")))
        bd.commit()
    cfg = configuracion()
    for clave, valor in (("dataforseo_usuario", "usuario-ej"), ("dataforseo_contrasena", "contrasena-ej"),
                         ("precios_tope_mensual_usd", 5.0), ("precios_tope_corrida_usd", 2.0), ("precios_umbral", 85),
                         ("precios_ia_siempre", False), ("precios_buscar_siempre", False), ("precios_max_publicaciones", 1),  # las pruebas de reglas; la IA que elige siempre tiene la suya
                         ("precios_alerta_pct", 10.0), ("precios_tarifa_usd", 0.001), ("precios_comparar_imagenes", False),
                         ("precios_tiendas_directas", "")):  # los sitios de las tiendas tienen sus pruebas (simulados)
        monkeypatch.setattr(cfg, clave, valor)
    monkeypatch.setattr(dfs, "ESPERA", 0)
    simulado = DataForSEOSimulado()
    monkeypatch.setattr(dfs, "_peticion", simulado)

    def actualizar_ya(corrida_id, producto_id):  # en la API corre aparte; aquí al momento
        with Session(motor()) as bd:
            precios.actualizar_producto(bd, corrida_id, producto_id)
    monkeypatch.setattr(precios, "actualizar_aparte", actualizar_ya)
    return simulado


def producto(descripcion, barras=None, lista="116.00", mem="104.40", marca=MARCA, tienda=None) -> int:
    with Session(motor()) as bd:
        p = Producto(sku=f"EJP-{uuid.uuid4().hex[:8]}", descripcion=descripcion, marca=marca, codigo_barras=barras,
                     precio_lista_con_impuestos=Decimal(lista) if lista else None,
                     precio_membresia_con_impuestos=Decimal(mem) if mem else None, precio_tienda_en_linea=Decimal(tienda) if tienda else None,
                     origen="API")
        bd.add(p)
        bd.commit()
        return p.producto_id


def vigilar(*ids):
    with Session(motor()) as bd:
        bd.add_all(PrecioVigilado(producto_id=i, origen="pantalla") for i in ids)
        bd.commit()


def correr(forzar=True) -> PrecioCorrida:
    with Session(motor(), expire_on_commit=False) as bd:
        c = precios.tomar_corrida(bd, precios.hoy_local(), "manual", forzar=forzar)
        assert c
        return precios.correr(bd, c)


def fila(corrida_id, producto_id) -> PrecioCorridaProducto:
    with Session(motor(), expire_on_commit=False) as bd:
        return bd.scalar(select(PrecioCorridaProducto).where(PrecioCorridaProducto.corrida_id == corrida_id,
                                                             PrecioCorridaProducto.producto_id == producto_id))


def item(titulo, pid, rank=1):
    return {"title": titulo, "product_id": pid, "rank_absolute": rank, "seller": "Tienda EJ", "url": "https://shopping.ejemplo/p"}


def vendedor(nombre, precio, dominio=None, **extra):
    return {"seller_name": nombre, "price": precio, "currency": "MXN", "domain": dominio, "url": f"https://{dominio or 'ej.mx'}/p", **extra}


def test_corrida_completa_sin_intervencion(limpio, monkeypatch):
    """Código de barras se acepta solo; presentación distinta se descarta; lo dudoso lo decide la IA."""
    a = producto("MORINGA EJ 500 MG 100 CAPSULAS", barras="7500000000017")
    b = producto("CURCUMA EJ 100 CAPSULAS")
    c = producto("CHIA EJ 500 G")
    vigilar(a, b, c)
    limpio.resultados["7500000000017"] = [item("Naturej Moringa EJ 500mg 100 cápsulas", "G-A")]
    limpio.resultados["NATUREJ MORINGA EJ 500 MG 100 CAPSULAS"] = []
    limpio.resultados["NATUREJ CURCUMA EJ 100 CAPSULAS"] = [item("Naturej Curcuma EJ 60 cápsulas", "G-B")]
    # Dos casi iguales: la IA desempata
    limpio.resultados["NATUREJ CHIA EJ 500 G"] = [item("Naturej Chia EJ 500 g", "G-C1"), item("Naturej Chia EJ 500 g", "G-C2")]
    limpio.vendedores["G-A"] = [vendedor("Amazon MX", 100, "amazon.com.mx"), vendedor("Walmart", 120, "walmart.com.mx"),
                                vendedor("Súper Naturista", 116, "supernaturista.com"),
                                vendedor("Otro EJ", 90, "otro.ej", availability="Agotado")]
    limpio.vendedores["G-C1"] = [vendedor("Tienda EJ", 130)]
    preguntas = []

    def ia(bd, tarea, **k):
        preguntas.append(json.loads(k["mensaje"]))
        assert tarea == "compras.precios_coincidencia"
        return type("R", (), {"texto": '{"decision":"match","clave":"G-C1","confianza":92,"motivo":"Misma marca y 500 g"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    corrida = correr()
    assert corrida.estado == "completa", corrida.error
    assert (corrida.productos, corrida.con_coincidencia, corrida.sin_coincidencia, corrida.con_precios) == (3, 2, 1, 2)

    fa = fila(corrida.corrida_id, a)
    assert fa.estado == "con_precios" and fa.vendedores == 2  # sin la tienda propia ni el agotado
    assert (fa.minimo, fa.mediana, fa.maximo) == (Decimal("100.00"), Decimal("110.00"), Decimal("120.00"))
    assert fa.dif_lista_mediana_pct == Decimal("5.45") and fa.dif_lista_minimo_pct == Decimal("16.00")
    fb = fila(corrida.corrida_id, b)
    assert fb.estado == "sin_coincidencia" and "presentación distinta" in fb.mensaje
    fc = fila(corrida.corrida_id, c)
    assert fc.estado == "con_precios" and fc.dif_lista_mediana_pct == Decimal("-10.77")
    assert len(preguntas) == 1 and {x["clave"] for x in preguntas[0]["candidatos"]} == {"G-C1", "G-C2"}

    with Session(motor()) as bd:
        estados = dict(bd.execute(select(PrecioCoincidencia.producto_id, PrecioCoincidencia.estado)).all())
        assert estados == {a: "automatica", c: "ia"}
        obs = bd.scalars(select(PrecioObservacion).where(PrecioObservacion.producto_id == a)).all()
        assert {o.vendedor for o in obs} == {"Amazon", "Walmart", "Súper Naturista", "Otro EJ"}
        assert [o.es_propia for o in obs if o.vendedor == "Súper Naturista"] == [True]
        envios = bd.scalars(select(PrecioEnvio)).all()
        assert all(e.estado == "confirmado" for e in envios)
        assert sum(e.costo_usd for e in envios) == corrida.costo_usd > 0
        # Una sola ronda: código de barras de A y descripción de B y C; luego vendedores de A y C
        # Primero la descripción de los tres; el código de barras solo para el que no quedó resuelto.
        # Vendedores: A, y las dos publicaciones de C (G-C2 es el mismo producto y también cuenta)
        assert limpio.envios == [("products", 3), ("products", 1), ("sellers", 2)]  # una publicación por producto, como Radar Precios


def test_reusa_coincidencia_y_rechazo_de_una_persona(limpio, admin):
    a = producto("ASHWAGANDHA EJ 60 CAPSULAS", barras="7500000000024", lista="200.00", mem="180.00")
    vigilar(a)
    limpio.resultados["7500000000024"] = [item("Naturej Ashwagandha EJ 60 caps", "G-1"), item("Naturej Ashwagandha EJ 60 cápsulas", "G-2", 2)]
    limpio.vendedores["G-1"] = [vendedor("Amazon", 150, "amazon.com.mx")]
    limpio.vendedores["G-2"] = [vendedor("Walmart", 160, "walmart.com.mx")]
    c1 = correr()
    assert c1.alertas == 1  # 200 contra 150: más caros por más del 10 %
    with Session(motor()) as bd:
        assert bd.scalar(select(func.count()).select_from(Notificacion).where(Notificacion.titulo == "Radar de precios: productos en rojo"))
    envios_antes = len(limpio.envios)

    # Otra corrida: ya tiene coincidencia, solo paga vendedores
    with Session(motor()) as bd:
        bd.execute(delete(PrecioCorridaProducto))
        bd.commit()
    correr()
    assert [t for t, _ in limpio.envios[envios_antes:]] == ["sellers"]

    # Una persona dice que no es: la siguiente corrida elige otra y nunca la rechazada
    r = admin.post(f"/api/compras/precios/productos/{a}/coincidencia/rechazar")
    assert r.status_code == 200 and r.json()["coincidencia"] is None
    with Session(motor()) as bd:
        bd.execute(delete(PrecioCorridaProducto))
        bd.commit()
    correr()
    with Session(motor()) as bd:
        m = precios.vigente(bd, a)
        assert m.google_id == "G-2"


def test_semaforo_con_limite_por_producto(limpio, admin):
    a = producto("MORINGA EJ 90 CAPSULAS", barras="7500000000031", lista="200.00", mem="180.00")
    vigilar(a)
    limpio.resultados["7500000000031"] = [item("Naturej Moringa EJ 90 caps", "G-M")]
    limpio.vendedores["G-M"] = [vendedor("Amazon", 150, "amazon.com.mx")]
    # 200 contra 150 = +33 %: con su propio límite de 50 % queda en amarillo y no avisa
    assert admin.patch(f"/api/compras/precios/vigilados/{a}", json={"limite_pct": 50}).status_code == 200
    assert correr().alertas == 0
    fila = next(f for f in admin.get("/api/compras/precios/lista").json()["filas"] if f["producto_id"] == a)
    assert fila["color"] == "amarillo" and Decimal(fila["limite_pct"]) == 50
    v = next(x for x in admin.get("/api/compras/precios/catalogo?solo_vigilados=true").json()["productos"] if x["producto_id"] == a)
    assert v["color"] == "amarillo" and Decimal(v["limite_propio_pct"]) == 50 and Decimal(v["dif_pct"]) > 30
    # La búsqueda no se tocó, así que la coincidencia sigue
    with Session(motor()) as bd:
        assert bd.scalar(select(PrecioCoincidencia.estado).where(PrecioCoincidencia.producto_id == a)) == "automatica"
    # Sin límite propio vuelve al general (10 %): rojo
    assert admin.patch(f"/api/compras/precios/vigilados/{a}", json={"limite_pct": None}).status_code == 200
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert d["limite_propio_pct"] is None and Decimal(d["limite_pct"]) == 10 and d["ultima"]["color"] == "rojo"
    assert admin.patch(f"/api/compras/precios/vigilados/{a}", json={"limite_pct": 150}).status_code == 422


def test_sin_precios_dos_veces_invalida_y_busca_de_nuevo(limpio):
    a = producto("ESPIRULINA EJ 100 TABLETAS", barras="7500000000031")
    vigilar(a)
    limpio.resultados["7500000000031"] = [item("Naturej Espirulina EJ 100 tabletas", "G-E")]
    for _ in range(2):
        with Session(motor()) as bd:
            bd.execute(delete(PrecioCorridaProducto))
            bd.commit()
        c = correr()
        assert fila(c.corrida_id, a).estado == "sin_precios"
    with Session(motor()) as bd:
        assert precios.vigente(bd, a) is None
        assert bd.scalar(select(PrecioCoincidencia.estado)) == "invalidada"


def test_topes_de_gasto_y_envio_incierto(limpio, monkeypatch):
    a = producto("JALEA EJ 30 ML", barras="7500000000048")
    vigilar(a)
    monkeypatch.setattr(configuracion(), "precios_tope_mensual_usd", 0.0001)
    c = correr()
    assert c.estado == "fallida" and limpio.envios == []  # no se envió nada
    assert fila(c.corrida_id, a).estado == "sin_presupuesto"

    monkeypatch.setattr(configuracion(), "precios_tope_mensual_usd", 5.0)
    limpio.falla_post = True
    c = correr()
    assert c.estado == "fallida" and c.error
    assert len(limpio.envios) == 1  # un solo intento: nunca se repite un POST
    with Session(motor()) as bd:
        e = bd.scalar(select(PrecioEnvio))
        assert e.estado == "incierto"
        assert dfs.gasto_mes(bd) == e.estimado_usd  # cuenta en el gasto aunque no se sepa si se cobró


def test_sin_precio_lista_compara_la_tienda_en_linea(limpio, admin):
    a = producto("DEMOGRASS EJ 30 CAPSULAS", barras="7500000000062", lista=None, mem=None, tienda="83.00")
    vigilar(a)
    limpio.resultados["7500000000062"] = [item("Naturej Demograss EJ 30 caps", "G-D")]
    limpio.vendedores["G-D"] = [vendedor("Súper Naturista", 83, "supernaturista.com"), vendedor("Farmacia EJ", 118, "farmacia.ej"),
                                vendedor("Otra EJ", 135.04, "otra.ej"), vendedor("Agotada EJ", 50, "agotada.ej", product_availability="out_of_stock")]
    c = correr()
    f = fila(c.corrida_id, a)
    assert f.vendedores == 2 and f.mediana == Decimal("126.52")  # sin nuestra tienda ni la agotada
    assert f.dif_lista_mediana_pct == Decimal("-34.40")
    r = next(x for x in admin.get("/api/compras/precios/lista").json()["filas"] if x["producto_id"] == a)
    assert r["base"] == "tienda" and r["color"] == "verde"


def test_detener_a_media_corrida(limpio, admin, monkeypatch):
    a = producto("SPIRULINA EJ 100 TABLETAS", barras="7500000000055")
    vigilar(a)
    limpio.resultados["7500000000055"] = [item("Naturej Spirulina EJ 100 tabletas", "G-S")]
    limpio.vendedores["G-S"] = [vendedor("Amazon", 100, "amazon.com.mx")]
    enviar = dfs.enviar

    def enviar_y_detener(bd, corrida, tipo, tareas):  # alguien da «Detener» mientras se espera a DataForSEO
        ids = enviar(bd, corrida, tipo, tareas)
        r = admin.post(f"/api/compras/precios/corridas/{corrida.corrida_id}/detener")
        assert r.status_code == 200 and r.json()["estado"] == "fallida"
        return ids

    monkeypatch.setattr(dfs, "enviar", enviar_y_detener)
    c = correr()
    assert c.estado == "fallida" and c.error.startswith("Detenida por")
    assert [t for t, _ in limpio.envios] == ["products"]  # ya no se pagaron los vendedores
    assert fila(c.corrida_id, a).estado == "fallido"
    assert admin.post(f"/api/compras/precios/corridas/{c.corrida_id}/detener").status_code == 409
    assert admin.get("/api/compras/precios/resumen").json()["en_curso"] is None
    # El programador no la vuelve a lanzar sola
    with Session(motor()) as bd:
        bd.execute(update(PrecioCorrida).where(PrecioCorrida.corrida_id == c.corrida_id)
                   .values(terminado_en=ahora() - timedelta(hours=1)))
        bd.commit()
        monkeypatch.setattr(configuracion(), "precios_hora", 0)
        assert precios.revisar_programa(bd) is None


def test_corrida_a_medias_se_cierra_al_reiniciar(limpio):
    a = producto("CHIA EJ 500 G")
    vigilar(a)
    with Session(motor(), expire_on_commit=False) as bd:
        c = precios.tomar_corrida(bd, precios.hoy_local(), "manual", forzar=True)
        assert precios.cerrar_huerfanas(bd) == 1
        bd.refresh(c)
        assert c.estado == "fallida" and "reinició" in c.error and not precios.en_curso(bd)


def test_rutas_y_permisos(admin, limpio):
    a = producto("PROPOLEO EJ 30 ML", marca="MARCA PRUEBA EJP")
    b = producto("PROPOLEO EJ 60 ML", marca="MARCA PRUEBA EJP")
    r = admin.post("/api/compras/precios/vigilados", json={"marca": "MARCA PRUEBA EJP"})
    assert r.status_code == 200 and r.json()["agregados"] == 2
    lista = admin.get("/api/compras/precios/catalogo", params={"solo_vigilados": True}).json()
    assert {p["producto_id"] for p in lista["productos"]} == {a, b}
    assert admin.patch(f"/api/compras/precios/vigilados/{a}", json={"consulta": "propoleo ej 30ml"}).status_code == 200
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert d["vigilado"] and d["consultas"] == ["propoleo ej 30ml"]
    res = admin.get("/api/compras/precios/resumen").json()
    assert res["vigilados"] == 2 and res["falta_configurar"] == [] and Decimal(res["estimado_usd"]) > 0

    # Otras pruebas cambian los permisos de este rol; aquí se dejan como vienen en el catálogo
    assert admin.put("/api/nucleo/roles/compras_consulta/permisos",
                     json={"permisos": ["compras.solicitud.ver", "compras.radar.ver", "compras.precios.ver"]}).status_code == 200
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.get("/api/compras/precios/resumen").status_code == 200
    assert consulta.post("/api/compras/precios/vigilados", json={"producto_ids": [a]}).status_code == 403
    assert consulta.post("/api/compras/precios/corridas").status_code == 403
    assert admin.delete(f"/api/compras/precios/vigilados/{b}").status_code == 200


def test_sin_configurar_no_corre(admin, limpio, monkeypatch):
    monkeypatch.setattr(configuracion(), "dataforseo_contrasena", "")
    vigilar(producto("AJO EJ 100 CAPSULAS"))
    r = admin.post("/api/compras/precios/corridas")
    assert r.status_code == 400 and "contraseña de DataForSEO" in r.json()["detail"]
    with Session(motor()) as bd:
        assert precios.revisar_programa(bd) is None


def test_ia_no_segura_queda_fuera():
    dudosos = [co.Candidato("X", "Naturej Chia 500 g", {}), co.Candidato("Y", "Naturej Chia 500 g bolsa", {})]
    for c in dudosos:
        c.evaluacion = co.evaluar("CHIA 500 G", MARCA, c.titulo, 85, set())
    assert co.leer_respuesta_ia('{"decision":"match","clave":"X","confianza":60,"motivo":"parecido"}', dudosos)[0] is None
    assert co.leer_respuesta_ia('{"decision":"match","clave":"Z","confianza":99,"motivo":"x"}', dudosos)[0] is None
    assert co.leer_respuesta_ia('```json\n{"decision":"match","clave":"Y","confianza":90,"motivo":"x"}\n```', dudosos)[0].clave == "Y"


def test_post_sin_respuesta_no_se_repite(monkeypatch):
    """El cliente real: un POST sin respuesta no se reintenta (pudo haberse cobrado); un GET sí."""
    import urllib.error

    llamadas = []

    def urlopen(peticion, timeout=None):
        llamadas.append(peticion.get_method())
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(dfs.EnvioIncierto, match="no se repitió"):
        dfs._peticion("POST", "/v3/merchant/google/products/task_post", [{}])
    assert llamadas == ["POST"]
    with pytest.raises(dfs.ErrorDataForSEO):
        dfs._peticion("GET", "/v3/merchant/google/products/tasks_ready")
    assert llamadas == ["POST", "GET", "GET", "GET"]


@pytest.mark.parametrize("descripcion, titulo, aceptada", [
    ("MORINGA 500 MG 100 CAPSULAS", "Naturej Moringa Oleifera Suplemento 500mg 100 cápsulas envío gratis", True),
    ("MORINGA 500 MG 100 CAPSULAS", "Naturej Moringa 500mg 60 cápsulas", False),  # otra presentación
    ("CURCUMA 100 CAPSULAS", "Naturej Moringa 100 cápsulas", False),  # otro producto, misma presentación
    ("OMEGA 3 1000 MG 60 CAPS", "Naturej Omega 6 1000mg 60 caps", False),
    ("VITAMINA C 1000 MG", "Naturej Vitamina D 1000 UI", False),
    ("COMPLEJO B 100 TABLETAS", "Naturej Complejo B12 100 tabletas", False),
    ("VITAMINA C 1000 MG", "Naturej Vitamina C 1000 mg 100 tabletas", True),
    ("MORINGA 500 MG 100 CAPSULAS", "Otra Marca Moringa 500mg 100 cápsulas", False),  # marca distinta
    ("MORINGA CLASICA 100 CAP", "Naturej Moringa Clásica, 100 cápsulas, 1 frasco", True),  # coma pegada a la palabra
    ("PROTEINA VEGETAL VAINILLA 510 G", "Proteína Vegetal Naturej Sabor Vainilla 510gr", True),  # unidad pegada
    ("PROTEINA VEGETAL VAINILLA 510 G", "Proteína Vegetal Naturej Vainilla 1.02kg", False),
    # Paquetes y kits (caso Birdman de Diego)
    ("PROTEINA VEGETAL VAINILLA 510 G", "Naturej Kit Proteína Vegetal Vainilla 510g + Creatina 300g", False),
    ("PROTEINA VEGETAL VAINILLA 510 G", "Naturej Proteína Vegetal Vainilla 510g Shaker", False),
    ("PROTEINA VEGETAL VAINILLA 510 G", "Naturej Creatina 450g Proteína Vegetal Vainilla 510g", False),
    ("PROTEINA VEGETAL VAINILLA 510 G", "Naturej Proteína Vegetal Vainilla 510 g 2 piezas", False),
])
def test_reglas_de_coincidencia(descripcion, titulo, aceptada):
    assert co.evaluar(descripcion, MARCA, titulo, 85, {"naturej", "otra marca"}, 1).aceptada is aceptada


def test_misma_marca_y_presentacion_con_otro_nombre_la_revisa_la_ia():
    ev = co.evaluar("MORINGA CLASICA 100 CAP", MARCA, "Naturej 100 cápsulas", 85, {"naturej"}, 1)
    assert not ev.aceptada and ev.dudosa
    # Con otra presentación no llega ni a la IA
    assert not co.evaluar("MORINGA CLASICA 100 CAP", MARCA, "Naturej 60 cápsulas", 85, {"naturej"}, 1).dudosa


def test_vendedores_con_product_id_y_data_docid():
    # Como el flujo de n8n de Diego: se mandan los dos identificadores de Google
    m = PrecioCoincidencia(google_id="123", candidato=json.dumps({"product_id": "123", "data_docid": "987"}))
    assert precios.ids_google(m) == {"product_id": "123", "data_docid": "987"}
    # Sin product_id no se manda el data_docid disfrazado de product_id
    m = PrecioCoincidencia(google_id="987", candidato=json.dumps({"data_docid": "987"}))
    assert precios.ids_google(m) == {"data_docid": "987"}
    assert precios.ids_google(PrecioCoincidencia(google_id="55", candidato=None)) == {"product_id": "55"}


def test_codigo_de_barras_no_acepta_otro_producto_de_la_marca():
    # Caso de Diego: por el código de barras Google regresó otro producto de la misma marca
    otro = co.Candidato("G-X", "Naturej Proteína Whey Chocolate", {"rank_absolute": 1})
    otro.estrategias.add("codigo_barras")
    dec = co.decidir("PROTEINA VEGETAL VAINILLA 510 G", MARCA, [otro], 85, {"naturej"}, set())
    assert dec.elegido is None
    bueno = co.Candidato("G-Y", "Naturej Proteína Vegetal Vainilla", {"rank_absolute": 1})
    bueno.estrategias.add("codigo_barras")
    assert co.decidir("PROTEINA VEGETAL VAINILLA 510 G", MARCA, [otro, bueno], 85, {"naturej"}, set()).elegido is bueno
    assert [e for e, _ in co.consultas("PROTEINA VEGETAL VAINILLA 510 G", MARCA, "7500000000017")] == ["descripcion", "codigo_barras"]


def test_ofertas_de_otra_presentacion_no_cuentan():
    # Caso de Diego: Birdman 510 g, pero Google trajo vendedores de la presentación de 34 g
    def obs(precio, titulo=None):
        return PrecioObservacion(precio_comparable=Decimal(precio), moneda="MXN", es_propia=False, disponibilidad="in_stock",
                                 datos=json.dumps({"title": titulo} if titulo else {}))
    fila = PrecioCorridaProducto(precio_lista=Decimal("650.00"))
    desc = "PROTEINA VEGETAL VAINILLA 510 G"
    todas = [obs("42"), obs("43.5"), obs("47", "Naturej Proteína Vegetal Vainilla 34 g")]
    precios.Corrida.calcular(fila, todas, desc)
    assert fila.estado == "sin_precios" and "otra presentación" in fila.mensaje
    assert precios.fuera_de_rango(todas[2], desc, Decimal("650")) == "Otra presentación (34 g)"
    fila = PrecioCorridaProducto(precio_lista=Decimal("650.00"))
    precios.Corrida.calcular(fila, todas + [obs("620", "Naturej Proteína Vegetal Vainilla 510 g"), obs("700")], desc)
    assert fila.estado == "con_precios" and fila.vendedores == 2 and fila.mediana == Decimal("660.00")


def test_ver_resultados_de_google_y_elegir_a_mano(limpio, admin):
    a = producto("PROTEINA VEGETAL EJ VAINILLA 510 G", lista="650.00", mem="600.00")
    vigilar(a)
    limpio.resultados["NATUREJ PROTEINA VEGETAL EJ VAINILLA 510 G"] = [
        item("Naturej Proteína Vegetal EJ Vainilla 510 g", "G-34", 1),  # Google la agrupa con la de 34 g
        item("Naturej Proteína Vegetal EJ Vainilla 34 g", "G-S", 2),
        item("Naturej Proteína Vegetal EJ Vainilla Polvo", "G-510", 3)]
    limpio.vendedores["G-510"] = [vendedor("Amazon", 640, "amazon.com.mx")]
    correr()
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert d["coincidencia"]["google_id"] == "G-34" and d["candidatos_fecha"]
    cands = {c["clave"]: c for c in d["candidatos"]}
    assert set(cands) == {"G-34", "G-S", "G-510"} and cands["G-34"]["elegida"]
    assert "presentación distinta" in cands["G-S"]["motivo"] and not cands["G-S"]["aceptada"]

    assert admin.post(f"/api/compras/precios/productos/{a}/elegir", json={"clave": "no-existe"}).status_code == 404
    r = admin.post(f"/api/compras/precios/productos/{a}/elegir", json={"clave": "G-510"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["coincidencia"]["google_id"] == "G-510" and d["coincidencia"]["estado"] == "persona"
    assert [x["google_id"] for x in d["anteriores"] if x["estado"] == "rechazada"] == ["G-34"]
    # Sin esperar a la siguiente corrida: los vendedores del elegido se piden al momento (Diego, 2026-10-20)
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert d["ultima"]["estado"] == "con_precios" and Decimal(d["ultima"]["mediana"]) == Decimal("640.00")
    assert [o["vendedor"] for o in d["observaciones"]] == ["Amazon"]
    assert admin.get("/api/compras/precios/resumen").json()["ultima"]["con_precios"] == 1
    # También se puede pedir a mano, sin cambiar la coincidencia
    limpio.vendedores["G-510"] = [vendedor("Amazon", 640, "amazon.com.mx"), vendedor("Walmart", 660, "walmart.com.mx")]
    r = admin.post(f"/api/compras/precios/productos/{a}/actualizar")
    assert r.status_code == 200 and Decimal(admin.get(f"/api/compras/precios/productos/{a}").json()["ultima"]["mediana"]) == Decimal("650.00")
    limpio.vendedores["G-510"] = [vendedor("Amazon", 640, "amazon.com.mx")]
    # Si otra corrida está corriendo, se deja para la siguiente
    with Session(motor()) as bd:
        corriendo = PrecioCorrida(fecha=precios.hoy_local(), origen="manual", estado="en_curso")
        bd.add(corriendo)
        bd.commit()
        assert precios.preparar_actualizacion(bd, a) is None
        bd.delete(corriendo)
        bd.commit()

    # La siguiente corrida pide los vendedores del elegido
    with Session(motor()) as bd:
        bd.execute(delete(PrecioCorridaProducto))
        bd.commit()
    c = correr()
    assert fila(c.corrida_id, a).mediana == Decimal("640.00")



def test_correr_ahora_abre_una_corrida_nueva_con_su_hora(limpio, admin):
    """Pedido de Diego (2026-10-20): repetir el mismo día reescribía la corrida y no se sabía si ya se había corrido."""
    a = producto("ASHWAGANDHA EJ 60 CAPSULAS", lista="200.00", mem="180.00")
    vigilar(a)
    limpio.resultados["NATUREJ ASHWAGANDHA EJ 60 CAPSULAS"] = [item("Naturej Ashwagandha EJ 60 cápsulas", "G-1")]
    limpio.vendedores["G-1"] = [vendedor("Amazon", 150, "amazon.com.mx")]
    c1 = correr()
    envios = len(limpio.envios)
    c2 = correr()
    assert c2.corrida_id != c1.corrida_id and c2.fecha == c1.fecha
    assert len(limpio.envios) > envios  # la nueva corre completa
    assert fila(c1.corrida_id, a).mediana == fila(c2.corrida_id, a).mediana == Decimal("150.00")  # la primera no se toca
    lista = admin.get("/api/compras/precios/corridas").json()
    assert [x["id"] for x in lista[:2]] == [c2.corrida_id, c1.corrida_id] and all(x["iniciado_en"] for x in lista)
    assert admin.get("/api/compras/precios/resumen").json()["ultima"]["id"] == c2.corrida_id
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert d["ultima_iniciada"] and len(d["serie"]) == 1  # una por día en la gráfica

    # El programador reintenta la última del día si falló, sin abrir otra
    with Session(motor(), expire_on_commit=False) as bd:
        bd.get(PrecioCorrida, c2.corrida_id).estado = "fallida"
        bd.commit()
        assert precios.tomar_corrida(bd, precios.hoy_local(), "programado").corrida_id == c2.corrida_id


def test_repetir_el_mismo_dia_rehace_lo_que_una_persona_cambio(limpio, admin):
    a = producto("ASHWAGANDHA EJ 60 CAPSULAS", lista="200.00", mem="180.00")
    vigilar(a)
    limpio.resultados["NATUREJ ASHWAGANDHA EJ 60 CAPSULAS"] = [
        item("Naturej Ashwagandha EJ 60 cápsulas", "G-1"), item("Naturej Ashwagandha EJ Polvo", "G-2", 2)]
    limpio.vendedores["G-1"] = [vendedor("Amazon", 150, "amazon.com.mx")]
    limpio.vendedores["G-2"] = [vendedor("Walmart", 190, "walmart.com.mx")]
    c = correr()
    assert fila(c.corrida_id, a).mediana == Decimal("150.00")

    # Una persona elige otro resultado: la repetición del mismo día sí lo rehace
    assert admin.post(f"/api/compras/precios/productos/{a}/elegir", json={"clave": "G-2"}).status_code == 200
    c = correr()
    assert fila(c.corrida_id, a).mediana == Decimal("190.00")
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert [o["vendedor"] for o in d["observaciones"]] == ["Walmart"]  # sin los vendedores de la coincidencia anterior



def test_oferta_de_un_paquete_no_cuenta():
    o = PrecioObservacion(precio_comparable=Decimal("1100"), moneda="MXN", es_propia=False,
                          datos=json.dumps({"title": "Naturej Kit Proteína Vegetal 510g + Creatina"}))
    assert precios.fuera_de_rango(o, "PROTEINA VEGETAL VAINILLA 510 G", Decimal("650")) == "Parece paquete o kit («kit»)"



def test_ia_elige_siempre_entre_los_resultados(limpio, monkeypatch):
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    a = producto("PROTEINA VEGETAL EJ VAINILLA 510 G", lista="650.00", mem="600.00")
    vigilar(a)
    # La tienda en línea lo publica con su nombre comercial: también se busca así
    with Session(motor()) as bd:
        bd.add(ProductoFuente(producto_id=a, fuente="TIENDA", clave_externa="EJ", huella="x" * 64,
                              datos=json.dumps({"titulo": "Naturej Fitmingo EJ Proteína Vegetal", "variante": "Vainilla 510 g"})))
        bd.commit()
    limpio.resultados["NATUREJ PROTEINA VEGETAL EJ VAINILLA 510 G"] = []
    limpio.resultados["NATUREJ Fitmingo EJ Proteína Vegetal - Vainilla 510 g"] = [
        item("Naturej Fitmingo EJ Vainilla 510g", "G-OK"), item("Naturej Kit Fitmingo EJ 510g + Shaker", "G-KIT", 2),
        item("Naturej Fitmingo EJ Vainilla 34 g", "G-34", 3), item("Otra Marca Fitmingo 510 g", "G-OTRA", 4)]
    limpio.vendedores["G-OK"] = [vendedor("Amazon", 640, "amazon.com.mx")]
    preguntas = []

    def ia(bd, tarea, **k):
        preguntas.append(json.loads(k["mensaje"]))
        assert "NO es motivo para rechazarlo" in k["instrucciones"]
        return type("R", (), {"texto": '{"decision":"match","clave":"G-OK","confianza":90,"motivo":"Misma línea Fitmingo y 510 g"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    c = correr()
    assert fila(c.corrida_id, a).mediana == Decimal("640.00")
    # La IA ve el nombre de la tienda y nuestro precio, pero no el kit ni otro tamaño;
    # una marca que no está en el catálogo sí le llega y ella la descarta
    assert preguntas[0]["producto"]["nombre_en_nuestra_tienda"].startswith("Naturej Fitmingo")
    assert preguntas[0]["producto"]["nuestro_precio_mxn"] == "650.00"
    assert [x["clave"] for x in preguntas[0]["candidatos"]] == ["G-OK", "G-OTRA"]
    with Session(motor()) as bd:
        m = precios.vigente(bd, a)
        assert m.google_id == "G-OK" and m.estado == "ia" and m.motivo.startswith("Elegido por la IA")


def test_junta_los_precios_de_todas_las_publicaciones_del_mismo_producto(limpio, monkeypatch, admin):
    monkeypatch.setattr(configuracion(), "precios_max_publicaciones", 5)  # ajuste encendido en Configuración
    # Pedido de Diego: ver todos los precios del producto en el mercado, no solo los de una publicación de Google
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    a = producto("PROTEINA VEGETAL EJ VAINILLA 510 G", lista="650.00", mem="600.00")
    vigilar(a)
    limpio.resultados["NATUREJ PROTEINA VEGETAL EJ VAINILLA 510 G"] = [
        item("Naturej Fitmingo EJ Vainilla 510g", "G-A"), item("Naturej Proteína Vegetal Fitmingo EJ 510 g Vainilla", "G-B", 2),
        item("Naturej Fitmingo EJ Chocolate 510g", "G-CHOCO", 3)]
    limpio.vendedores["G-A"] = [vendedor("Amazon", 640, "amazon.com.mx"), vendedor("Liverpool", 600, "liverpool.com.mx")]
    limpio.vendedores["G-B"] = [vendedor("Amazon", 630, "amazon.com.mx"), vendedor("Walmart", 610, "walmart.com.mx")]

    def ia(bd, tarea, **k):
        return type("R", (), {"texto": '{"decision":"match","clave":"G-A","claves":["G-A","G-B"],"confianza":90,'
                                       '"motivo":"Misma proteína, sabor y tamaño"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    c = correr()
    f = fila(c.corrida_id, a)
    # Amazon sale en las dos publicaciones: cuenta una vez, con su precio más bajo
    assert f.estado == "con_precios" and f.vendedores == 3
    assert (f.minimo, f.mediana, f.maximo) == (Decimal("600.00"), Decimal("610.00"), Decimal("630.00"))
    assert ("sellers", 2) in limpio.envios
    with Session(motor()) as bd:
        m = precios.vigente(bd, a)
        assert [d["clave"] for d in precios.iguales(m)] == ["G-B"]
    # La tabla de precios (como la del proyecto Radar Precios): vendedor, publicación de Google y precio
    tabla = admin.get("/api/compras/precios/tabla").json()
    renglones = [(r["vendedor"], r["publicacion"], r["precio"], r["cuenta"]) for r in tabla["renglones"] if r["producto_id"] == a]
    assert renglones == [("Liverpool", "Naturej Fitmingo EJ Vainilla 510g", "600.00", True),
                         ("Walmart", "Naturej Proteína Vegetal Fitmingo EJ 510 g Vainilla", "610.00", True),
                         ("Amazon", "Naturej Proteína Vegetal Fitmingo EJ 510 g Vainilla", "630.00", True)]
    assert next(r for r in tabla["renglones"] if r["vendedor"] == "Liverpool")["dif_pct"] == "8.33"
    # Diagnóstico de la corrida: lo que regresó Google, la coincidencia y cada precio, sin claves de DataForSEO
    r = admin.get(f"/api/compras/precios/corridas/{c.corrida_id}/diagnostico")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert not any("dataforseo" in k or "contrasena" in k for k in d["ajustes"])
    p = next(x for x in d["productos"] if x["producto"]["descripcion"] == "PROTEINA VEGETAL EJ VAINILLA 510 G")
    assert {g["clave"] for g in p["lo_que_regreso_google"]} == {"G-A", "G-B", "G-CHOCO"}
    assert p["coincidencia"]["estado"] == "ia" and [x["vendedor"] for x in p["precios"]] == ["Liverpool", "Walmart", "Amazon"]
    assert d["envios"] and admin.get("/api/compras/precios/corridas/999999/diagnostico").status_code == 404


def test_cada_resultado_de_la_busqueda_es_un_precio(limpio, monkeypatch, admin):
    monkeypatch.setattr(configuracion(), "precios_max_publicaciones", 5)  # ajuste encendido en Configuración
    # Pedido de Diego: la lista de «Lo que regresó Google» (tienda, producto y precio) es la tabla de precios
    cfg = configuracion()
    monkeypatch.setattr(cfg, "precios_ia_siempre", True)
    monkeypatch.setattr(cfg, "precios_buscar_siempre", True)
    a = producto("DEMOGRASS EJ 30 CAP", lista="150.00", mem="140.00")
    vigilar(a)

    def resultado(titulo, pid, tienda, precio, rank=1):
        return {**item(titulo, pid, rank), "seller": tienda, "price": precio, "currency": "MXN",
                "url": f"https://www.google.com/shopping/product/{pid}", "shopping_url": f"https://www.google.com/shopping/product/{pid}"}

    limpio.resultados["NATUREJ DEMOGRASS EJ 30 CAP"] = [
        resultado("Naturej Demograss EJ clásico 30 cápsulas", "G-A", "Tiendaestrella", 130),
        resultado("Naturej Demograss EJ 30 caps", "G-B", "Mercado Libre", 160, 2),
        resultado("Naturej Demograss EJ 90 cápsulas", "G-90", "Farmacia EJ", 380, 3)]
    limpio.vendedores["G-A"] = [vendedor("Tiendaestrella", 135, "tiendaestrella.mx"), vendedor("Mercado Libre", 150, "mercadolibre.com.mx")]
    monkeypatch.setattr("ia.puerta.ejecutar", lambda bd, tarea, **k: type("R", (), {
        "texto": '{"decision":"match","clave":"G-A","claves":["G-A","G-B"],"confianza":90,"motivo":"Mismo producto"}'})())
    c = correr()
    f = fila(c.corrida_id, a)
    # Tiendaestrella y Mercado Libre salen en la búsqueda y en vendedores: cuentan una vez, con su precio más bajo.
    # La de 90 cápsulas no es el mismo producto y no cuenta.
    assert f.estado == "con_precios" and f.vendedores == 2
    assert (f.minimo, f.maximo) == (Decimal("130.00"), Decimal("150.00"))
    renglones = [(r["vendedor"], r["publicacion"], r["precio"]) for r in admin.get("/api/compras/precios/tabla").json()["renglones"]
                 if r["producto_id"] == a]
    assert renglones == [("Tiendaestrella", "Naturej Demograss EJ clásico 30 cápsulas", "130.00"),
                         ("Mercado Libre", "Naturej Demograss EJ clásico 30 cápsulas", "150.00")]

    # La corrida siguiente vuelve a buscar: lo nuevo de Google cuenta, y la coincidencia se conserva
    with Session(motor()) as bd:
        bd.get(PrecioCorrida, c.corrida_id).fecha = precios.hoy_local() - timedelta(days=7)
        m1 = precios.vigente(bd, a).coincidencia_id
        bd.commit()
    limpio.resultados["NATUREJ DEMOGRASS EJ 30 CAP"].append(resultado("Naturej Demograss EJ 30 cáps", "G-C", "Farmacia Nueva EJ", 125, 4))
    limpio.envios.clear()

    def ia2(bd, tarea, **k):
        return type("R", (), {"texto": '{"decision":"match","clave":"G-A","claves":["G-A","G-B","G-C"],"confianza":90,"motivo":"Mismo"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia2)
    c2 = correr()
    f2 = fila(c2.corrida_id, a)
    assert ("products", 1) in limpio.envios and f2.vendedores == 3 and f2.minimo == Decimal("125.00")
    with Session(motor()) as bd:
        assert precios.vigente(bd, a).coincidencia_id == m1


def test_las_reglas_tambien_juntan_las_publicaciones_aceptadas(limpio, monkeypatch):
    monkeypatch.setattr(configuracion(), "precios_max_publicaciones", 5)  # ajuste encendido en Configuración
    a = producto("MORINGA EJ 500 MG 100 CAPSULAS")
    vigilar(a)
    limpio.resultados["NATUREJ MORINGA EJ 500 MG 100 CAPSULAS"] = [
        item("Naturej Moringa EJ 500 mg 100 cápsulas", "G-1"), item("Naturej Moringa EJ 500mg 100 caps", "G-2", 2)]
    limpio.vendedores["G-1"] = [vendedor("Amazon", 110, "amazon.com.mx")]
    limpio.vendedores["G-2"] = [vendedor("Walmart", 120, "walmart.com.mx")]
    # Dos publicaciones igual de buenas: la IA desempata y la otra también cuenta
    monkeypatch.setattr("ia.puerta.ejecutar", lambda bd, tarea, **k: type("R", (), {
        "texto": '{"decision":"match","clave":"G-1","confianza":90,"motivo":"Mismo producto"}'})())
    c = correr()
    with Session(motor()) as bd:
        m = precios.vigente(bd, a)
        assert m.google_id == "G-1" and [d["clave"] for d in precios.iguales(m)] == ["G-2"]
    assert fila(c.corrida_id, a).vendedores == 2


def test_si_la_ia_no_contesta_deciden_las_reglas(limpio, monkeypatch):
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    a = producto("CHIA EJ 500 G")
    vigilar(a)
    limpio.resultados["NATUREJ CHIA EJ 500 G"] = [item("Naturej Chia EJ 500 g", "G-1")]
    limpio.vendedores["G-1"] = [vendedor("Amazon", 100, "amazon.com.mx")]

    def sin_ia(bd, tarea, **k):
        raise puerta.ErrorIA("Ollama no responde")

    monkeypatch.setattr("ia.puerta.ejecutar", sin_ia)
    c = correr()
    assert c.estado == "completa" and fila(c.corrida_id, a).estado == "con_precios"
    with Session(motor()) as bd:
        assert precios.vigente(bd, a).estado == "automatica"


def test_casos_del_diagnostico_2026_10_20():
    """Casos reales del diagnóstico de Diego (títulos de Google tal cual; marcas y productos del catálogo)."""
    ev = lambda d, m, t: co.evaluar(d, m, t, 85, set(), 1)  # noqa: E731
    # Otro tipo de aceite de la misma marca y tamaño ya no se acepta solo (antes 90 puntos)
    a = ev("ACEITE DE AJONJOLI EXTRA VIRGEN 250 ML", "SAN LUCAS", "SAN LUCAS Aceite de Aguacate Extra Virgen 250 ml")
    assert not a.aceptada and "AJONJOLI" in a.motivo
    # La marca por siglas: NB FOODS = NBF
    assert ev("ACEITE DE AGUACATE EXTRA VIRGEN 510 ML", "NB FOODS", "Nbf Aceite de Aguacate Extra Virgen 510 ml").aceptada
    # «90 piezas» de nuestras 90 gomitas no es un paquete; 2 piezas sí
    assert ev("3 MAGNESIOS MANGO 90 GOMITAS", "BELABEAR", "Gomitas Belabear Mango 3 Magnesios con 90 Piezas").aceptada
    assert co.paquete("3 MAGNESIOS MANGO 90 GOMITAS", "3 Magnesios Mango 90 Gomitas Belabear 2 piezas")
    # Abreviado de nuestro lado sigue contando
    assert ev("MULTIVIT MUJER 30 CAP", "VIDANAT", "Vidanat Multivitaminas Mujer 30 Cápsulas").aceptada
    # «+» entre las formas del magnesio no es kit; «510g + Creatina» sí
    assert co.paquete("3 MAGNESIOS 60 TAB", "Vidanat 3 Magnesios Citrato + Cloruro + Glicinato de Magnesi") is None
    assert co.paquete("PROTEINA VEGETAL VAINILLA 510 G", "Proteína Vegetal Vainilla 510g + Creatina")


def test_casos_del_diagnostico_2026_10_21():
    """Corrida 2004: Walmart y Soriana aceptaban otro aceite de la misma marca porque «ajo» es corta."""
    ev = lambda d, m, t: co.evaluar(d, m, t, 85, set(), 1)  # noqa: E731
    for titulo in ("Aceite de oliva San Lucas gourmet 500 ml", "Aceite De Pepita De Uva San Lucas 500 ml"):
        a = ev("ACEITE DE AJO 500 ML", "SAN LUCAS", titulo)
        assert not a.aceptada and "«AJO»" in a.motivo
    assert ev("ACEITE DE AJO 500 ML", "SAN LUCAS", "San Lucas Aceite de Ajo 500 ml").aceptada
    # «ajo» tampoco se da por bueno dentro de «ajonjolí»
    assert not ev("ACEITE DE AJO 500 ML", "SAN LUCAS", "San Lucas Aceite de Ajonjolí 500 ml").aceptada
    assert co.sin_presentacion("SAN LUCAS ACEITE DE AJO 500 ML") == "SAN LUCAS ACEITE DE AJO"
    assert co.sin_presentacion("VIDANAT 3 MAGNESIOS 60 TAB") == "VIDANAT 3 MAGNESIOS"


def test_la_ia_sabe_que_variante_es_la_nuestra(limpio, monkeypatch, admin):
    """Caso Demograss clásico (2026-10-20): la IA juntó Premier y clásico. Le llegan la búsqueda escrita por Compras
    y la publicación que eligió una persona, y la instrucción de no juntar variantes."""
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    monkeypatch.setattr(configuracion(), "precios_buscar_siempre", True)
    a = producto("ADELGAZEJ 30 CAP", lista="83.00", mem="74.00")
    vigilar(a)
    limpio.resultados["NATUREJ ADELGAZEJ 30 CAP"] = [
        item("Naturej Adelgazej Premier 30 Cápsulas", "G-P"), item("Naturej Adelgazej clásico 30 cápsulas", "G-C", 2)]
    limpio.vendedores["G-P"] = [vendedor("Amazon", 199, "amazon.com.mx")]
    limpio.vendedores["G-C"] = [vendedor("Walmart", 90, "walmart.com.mx")]
    preguntas = []

    def ia(bd, tarea, **k):
        preguntas.append(json.loads(k["mensaje"]))
        assert "nunca pongas en \"claves\" dos variantes diferentes" in k["instrucciones"]
        return type("R", (), {"texto": '{"decision":"match","clave":"G-C","claves":["G-C"],"confianza":90,"motivo":"Clásico"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    # Nuestra descripción no dice la variante y Google trae dos: no se adivina, aunque la IA elija una
    f = fila(correr().corrida_id, a)
    assert f.estado == "sin_coincidencia" and "varias variantes" in f.mensaje
    # Una persona eligió el clásico: la IA lo sabe en la siguiente corrida
    assert admin.post(f"/api/compras/precios/productos/{a}/elegir", json={"clave": "G-C"}).status_code == 200
    correr()
    assert preguntas[-1]["producto"]["publicacion_confirmada_por_una_persona"] == "Naturej Adelgazej clásico 30 cápsulas"
    # Compras escribe la búsqueda con la variante: también le llega
    assert admin.patch(f"/api/compras/precios/vigilados/{a}", json={"consulta": "Adelgazej clásico 30 cápsulas"}).status_code == 200
    limpio.resultados["Adelgazej clásico 30 cápsulas"] = [item("Naturej Adelgazej clásico 30 cápsulas", "G-C")]
    f = fila(correr().corrida_id, a)
    assert preguntas[-1]["producto"]["busqueda_escrita_por_compras"] == "Adelgazej clásico 30 cápsulas"
    assert f.mediana == Decimal("90.00")


def test_con_varias_variantes_la_ia_compara_las_fotos(limpio, monkeypatch):
    """Idea de Diego (2026-10-20): cuando el texto no dice la variante, comparar la foto de nuestro producto con las de Google."""
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    monkeypatch.setattr(configuracion(), "precios_comparar_imagenes", True)
    monkeypatch.setattr(configuracion(), "precios_max_publicaciones", 5)
    a = producto("ADELGAZEJ 30 CAP", lista="83.00", mem="74.00")
    vigilar(a)
    with Session(motor()) as bd:
        bd.get(Producto, a).imagen_cdn = "https://cdn.shopify.com/s/files/EJ/adelgazej.jpg"
        bd.commit()

    def resultado(titulo, clave, rank):
        return {**item(titulo, clave, rank), "product_images": [f"https://encrypted-tbn0.gstatic.com/shopping?q={clave}"]}
    limpio.resultados["NATUREJ ADELGAZEJ 30 CAP"] = [
        resultado("Naturej Adelgazej Premier 30 Cápsulas", "G-P", 1), resultado("Naturej Adelgazej clásico 30 cápsulas", "G-C", 2)]
    limpio.vendedores["G-P"] = [vendedor("Amazon", 199, "amazon.com.mx")]
    limpio.vendedores["G-C"] = [vendedor("Walmart", 90, "walmart.com.mx")]
    monkeypatch.setattr(img, "bajar", lambda url: f"foto:{url}" if url else None)
    llamadas = []

    def ia(bd, tarea, **k):
        llamadas.append((tarea, k))
        if tarea == precios.TAREA_IMAGENES:
            return type("R", (), {"texto": '{"variante":"Clásico","claves":["G-C"],"motivo":"El empaque dice Clásico"}'})()
        # La IA de texto se equivoca y junta las dos
        return type("R", (), {"texto": '{"decision":"match","clave":"G-P","claves":["G-P","G-C"],"confianza":90,"motivo":"x"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    f = fila(correr().corrida_id, a)
    assert f.estado == "con_precios" and f.mediana == Decimal("90.00")
    tarea, k = llamadas[-1]
    assert tarea == precios.TAREA_IMAGENES
    assert k["imagenes"] == ["foto:https://cdn.shopify.com/s/files/EJ/adelgazej.jpg", "foto:https://encrypted-tbn0.gstatic.com/shopping?q=G-P",
                             "foto:https://encrypted-tbn0.gstatic.com/shopping?q=G-C"]
    with Session(motor()) as bd:
        m = precios.vigente(bd, a)
        assert m.google_id == "G-C" and m.motivo.startswith("Elegido por la IA comparando fotos")


def test_si_la_ia_no_elige_por_las_variantes_tambien_compara_fotos(limpio, monkeypatch):
    """Corrida 1004 de Diego: la IA de texto contestó «no_match» por las variantes y se seguía usando el Premier de antes."""
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    monkeypatch.setattr(configuracion(), "precios_buscar_siempre", True)
    monkeypatch.setattr(configuracion(), "precios_comparar_imagenes", True)
    a = producto("ADELGAZEJ 30 CAP", lista="83.00", mem="74.00")
    vigilar(a)
    with Session(motor()) as bd:
        bd.get(Producto, a).imagen_cdn = "https://cdn.shopify.com/s/files/EJ/adelgazej.jpg"
        # Coincidencia vieja con la variante equivocada, elegida por la IA en otra corrida
        bd.add(PrecioCoincidencia(producto_id=a, google_id="G-P", titulo="Naturej Adelgazej Premier 30 Cápsulas", estado="ia",
                                  motivo="vieja", estrategia="descripcion", candidato=json.dumps({"product_id": "G-P"})))
        bd.commit()

    def resultado(titulo, clave, rank):
        return {**item(titulo, clave, rank), "product_images": [f"https://encrypted-tbn0.gstatic.com/shopping?q={clave}"]}
    limpio.resultados["NATUREJ ADELGAZEJ 30 CAP"] = [
        resultado("Naturej Adelgazej Premier 30 Cápsulas", "G-P", 1), resultado("Naturej Adelgazej clásico 30 cápsulas", "G-C", 2)]
    limpio.vendedores["G-P"] = [vendedor("Amazon", 199, "amazon.com.mx")]
    limpio.vendedores["G-C"] = [vendedor("Walmart", 90, "walmart.com.mx")]
    monkeypatch.setattr(img, "bajar", lambda url: f"foto:{url}" if url else None)
    fotos = {"texto": '{"variante":"Clásico","claves":["G-C"],"motivo":"El empaque dice Clásico"}'}

    def ia(bd, tarea, **k):
        if tarea == precios.TAREA_IMAGENES:
            return type("R", (), fotos)()
        return type("R", (), {"texto": '{"decision":"no_match","clave":null,"confianza":40,"motivo":"Hay Premier y clásico"}'})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    f = fila(correr().corrida_id, a)
    assert f.estado == "con_precios" and f.mediana == Decimal("90.00")
    with Session(motor()) as bd:
        assert precios.vigente(bd, a).google_id == "G-C"

    # La coincidencia vieja del Premier quedó invalidada: no se vuelve a elegir
    with Session(motor()) as bd:
        assert bd.scalar(select(PrecioCoincidencia.estado).where(PrecioCoincidencia.producto_id == a,
                                                                 PrecioCoincidencia.google_id == "G-P")) == "invalidada"

    # Si las fotos tampoco lo resuelven, el producto queda sin coincidencia y no se sigue usando la vieja
    b = producto("ADELGAZEJ 30 CAP", lista="83.00", mem="74.00")
    vigilar(b)
    with Session(motor()) as bd:
        bd.get(Producto, b).imagen_cdn = "https://cdn.shopify.com/s/files/EJ/adelgazej.jpg"
        bd.add(PrecioCoincidencia(producto_id=b, google_id="G-P", titulo="Naturej Adelgazej Premier 30 Cápsulas", estado="ia",
                                  motivo="vieja", estrategia="descripcion", candidato=json.dumps({"product_id": "G-P"})))
        bd.commit()
    fotos["texto"] = '{"variante":null,"claves":[],"motivo":"No se distingue"}'
    f = fila(correr().corrida_id, b)
    assert f.estado == "sin_coincidencia" and "fotos:" in f.mensaje
    with Session(motor()) as bd:
        assert precios.vigente(bd, b) is None


def test_fotos_solo_de_sitios_permitidos_y_solo_con_ollama(limpio):
    assert img.permitida("https://encrypted-tbn0.gstatic.com/shopping?q=x")
    assert img.permitida("https://cdn.shopify.com/s/files/a.jpg")
    assert not img.permitida("http://encrypted-tbn0.gstatic.com/x")  # sin https
    assert not img.permitida("https://169.254.169.254/latest") and not img.permitida("https://gstatic.com.ejemplo.mx/x")
    with Session(motor()) as bd, pytest.raises(puerta.ErrorIA, match="solo funciona con Ollama"):
        puerta.ejecutar(bd, "compras.radar_buscar", usuario_id=None, instrucciones="x", mensaje="x", imagenes=["abc"])


def test_reglas_de_variante_sobre_lo_que_elige_la_ia():
    def cand(clave, titulo):
        return co.Candidato(clave=clave, titulo=titulo, datos={})
    premier, clasico, sin = cand("P", "Demograss Premier 30 Cápsulas"), cand("C", "Demograss clásico Con 30 cápsulas"), cand("S", "Demograss 30 caps")
    todos = [premier, clasico, sin]
    # Sabemos que es el clásico: la IA eligió el Premier, no cuenta
    e, i, problema = co.cuidar_variante(premier, [clasico], ["Demograss clásico 30 cápsulas"], todos)
    assert e is None and "otra variante" in problema
    # Eligió el clásico y juntó el Premier: el Premier se quita; el que no dice variante se queda
    e, i, problema = co.cuidar_variante(clasico, [premier, sin], [None, "Demograss Clásico, 30 cap"], todos)
    assert e is clasico and i == [sin] and problema is None
    # No sabemos cuál es: con una sola variante en Google no hay duda
    assert co.cuidar_variante(premier, [sin], ["DEMOGRASS 30 CAP"], [premier, sin])[2] is None


def test_lo_que_aceptan_las_reglas_cuenta_aunque_la_ia_no_lo_marque(limpio, monkeypatch):
    monkeypatch.setattr(configuracion(), "precios_max_publicaciones", 5)
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    a = producto("PROTEINA VEGETAL EJ VAINILLA 510 G", lista="650.00", mem="600.00")
    vigilar(a)
    limpio.resultados["NATUREJ PROTEINA VEGETAL EJ VAINILLA 510 G"] = [
        item("Naturej Proteína Vegetal EJ Vainilla 510g", "G-A"), item("Proteína Vegetal EJ Vainilla 510 g Naturej", "G-B", 2)]
    limpio.vendedores["G-A"] = [vendedor("Amazon", 640, "amazon.com.mx")]
    limpio.vendedores["G-B"] = [vendedor("Walmart", 610, "walmart.com.mx")]
    monkeypatch.setattr("ia.puerta.ejecutar", lambda bd, tarea, **k: type("R", (), {
        "texto": '{"decision":"match","clave":"G-A","claves":["G-A"],"confianza":90,"motivo":"Mismo producto"}'})())
    f = fila(correr().corrida_id, a)
    assert f.estado == "con_precios" and f.vendedores == 2  # G-B la aceptan las reglas: también cuenta


def test_error_de_ollama_dice_la_causa(monkeypatch):
    import io, urllib.error, urllib.request
    from ia import puerta

    def falla(*a, **k):
        raise urllib.error.HTTPError("http://x/api/chat", 400, "Bad Request", {},
                                     io.BytesIO(b'{"error":"qwen3:4b does not support images"}'))
    monkeypatch.setattr(urllib.request, "urlopen", falla)
    with pytest.raises(puerta.ErrorIA, match="does not support images"):
        puerta._llamar_ollama("qwen3:4b", "i", "m", 10, imagenes=["eA=="])


def test_solo_se_mandan_fotos_jpeg_o_png(monkeypatch):
    import io

    class Resp(io.BytesIO):
        headers = {"Content-Type": "image/webp"}
        def __enter__(self): return self
        def __exit__(self, *a): pass

    url = "https://encrypted-tbn0.gstatic.com/shopping?q=x"
    monkeypatch.setattr(img._abridor, "open", lambda *a, **k: Resp(b"RIFF....WEBPVP8 "))
    assert img.bajar(url) is None
    monkeypatch.setattr(img._abridor, "open", lambda *a, **k: Resp(b"\xff\xd8\xff\xe0jpeg"))
    assert img.bajar(url)


def test_ollama_sin_razonamiento_se_reintenta_sin_think(monkeypatch):
    import io, urllib.error, urllib.request
    from ia import puerta
    cuerpos = []

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def responde(peticion, timeout=None):
        cuerpos.append(json.loads(peticion.data))
        if "think" in cuerpos[-1]:
            raise urllib.error.HTTPError("http://x", 400, "Bad Request", {},
                                         io.BytesIO(b'{"error":"\\"qwen3-vl:4b-instruct\\" does not support thinking"}'))
        return Resp(json.dumps({"message": {"content": "ok"}, "done_reason": "stop"}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", responde)
    assert puerta._llamar_ollama("qwen3-vl:4b-instruct", "i", "m", 10, imagenes=["eA=="])["texto"] == "ok"
    assert "think" in cuerpos[0] and "think" not in cuerpos[1]


def test_lista_paginada_con_grupos_y_busqueda(limpio, admin):
    a = producto("CURCUMA EJ 60 CAPSULAS", barras="7500000000079", lista="100.00")
    b = producto("CURCUMA EJ 120 CAPSULAS", barras="7500000000086", lista="100.00")
    c = producto("JENGIBRE EJ 60 CAPSULAS", barras="7500000000093", lista="100.00", marca="MARCA LISTA EJ")
    for x in (a, b, c):
        vigilar(x)
    limpio.resultados["7500000000079"] = [item("Naturej Curcuma EJ 60 caps", "G-C1")]
    limpio.vendedores["G-C1"] = [vendedor("Amazon", 50, "amazon.com.mx")]  # estamos +100 %: rojo
    limpio.resultados["7500000000086"] = [item("Naturej Curcuma EJ 120 caps", "G-C2")]
    limpio.vendedores["G-C2"] = [vendedor("Amazon", 200, "amazon.com.mx")]  # -50 %: verde
    correr()  # el jengibre no trae nada: sin coincidencia
    r = admin.get("/api/compras/precios/lista", params={"por_pagina": 1}).json()
    assert r["total"] == 3 and len(r["filas"]) == 1 and r["filas"][0]["producto_id"] == a  # primero el más caro
    assert r["conteos"]["rojo"] == 1 and r["conteos"]["verde"] == 1 and r["conteos"]["revisar"] == 1
    assert {"MARCA LISTA EJ", MARCA} <= set(r["marcas"])
    assert admin.get("/api/compras/precios/lista", params={"por_pagina": 1, "pagina": 2}).json()["filas"][0]["producto_id"] == b
    assert [f["producto_id"] for f in admin.get("/api/compras/precios/lista", params={"grupo": "revisar"}).json()["filas"]] == [c]
    r = admin.get("/api/compras/precios/lista", params={"q": "curcuma", "marca": MARCA}).json()
    assert r["total"] == 2 and r["conteos"]["revisar"] == 0
    assert admin.get("/api/compras/precios/lista", params={"marca": "MARCA LISTA EJ"}).json()["total"] == 1
    assert admin.get("/api/compras/precios/lista", params={"grupo": "otro"}).status_code == 422


def test_tiendas_clave(limpio, admin, monkeypatch):
    """Pedido de Diego (2026-10-20): ver aparte Walmart, Chedraui, San Pablo y Soriana."""
    monkeypatch.setattr(configuracion(), "precios_tiendas_clave", "Walmart, Chedraui, San Pablo, Soriana")
    assert precios.tienda_clave("San Pablo Farmacia", None) == "San Pablo"
    assert precios.tienda_clave("Farmacia EJ", "farmaciasanpablo.com.mx") == "San Pablo"
    assert precios.tienda_clave("Walmart Express", None) == "Walmart" and precios.tienda_clave("Amazon", "amazon.com.mx") is None
    a = producto("ROMERO EJ 60 CAPSULAS", barras="7500000000109", lista="100.00")
    vigilar(a)
    limpio.resultados["7500000000109"] = [item("Naturej Romero EJ 60 caps", "G-R")]
    limpio.vendedores["G-R"] = [vendedor("Chedraui", 95, "chedraui.com.mx"), vendedor("Chedraui", 99, "chedraui.com.mx"),
                                vendedor("San Pablo Farmacia", 110, "farmaciasanpablo.com.mx"), vendedor("Amazon", 90, "amazon.com.mx")]
    correr()
    r = admin.get("/api/compras/precios/lista").json()
    f = next(x for x in r["filas"] if x["producto_id"] == a)
    assert {k: Decimal(v) for k, v in f["tiendas"].items()} == {"Chedraui": Decimal("95.00"), "San Pablo": Decimal("110.00")}
    assert r["tiendas"] == ["Walmart", "Chedraui", "San Pablo", "Soriana"]
    assert r["cobertura"]["Chedraui"] == 1 and r["cobertura"]["Walmart"] == 0
    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    assert {o["vendedor"]: o["tienda_clave"] for o in d["observaciones"]}["Amazon"] is None
    assert "San Pablo" in [o["tienda_clave"] for o in d["observaciones"]] and d["tiendas"][0] == "Walmart"


class TiendaSimulada(td.Tienda):
    """Un sitio de tienda en memoria: resultados[texto] = [Resultado]; falla = error en cada consulta."""

    def __init__(self, nombre, dominio, resultados=None, falla=None):
        self.nombre, self.dominio, self.base = nombre, dominio, f"https://{dominio}"
        self.resultados, self.falla, self.consultas = resultados or {}, falla, []

    def buscar(self, texto):
        self.consultas.append(texto)
        if self.falla:
            raise td.ErrorTienda(self.falla)
        return self.resultados.get(texto, [])


def con_tiendas(monkeypatch, *tiendas):
    monkeypatch.setattr(configuracion(), "precios_tiendas_directas", ", ".join(t.nombre for t in tiendas))
    monkeypatch.setattr(td, "ESPERA", 0)
    monkeypatch.setattr(td, "conectores", lambda nombres: [t for t in tiendas if t.nombre in nombres])
    monkeypatch.setattr(td, "TIENDAS", {t.nombre: type(t) for t in tiendas})


def test_tiendas_directas_cuentan_como_vendedores(limpio, admin, monkeypatch):
    """Diego (2026-10-20): buscar cada producto en Walmart, Chedraui, San Pablo y Soriana, en su propio sitio."""
    a = producto("MORINGA EJ 500 MG 100 CAPSULAS", barras="7500000000017", lista="116.00")
    vigilar(a)
    q = "NATUREJ MORINGA EJ 500 MG 100 CAPSULAS"
    limpio.resultados[q] = [item("Naturej Moringa EJ 500mg 100 cápsulas", "G-A")]
    limpio.vendedores["G-A"] = [vendedor("Amazon MX", 100, "amazon.com.mx"), vendedor("Walmart", 120, "walmart.com.mx")]
    walmart = TiendaSimulada("Walmart", "walmart.com.mx", {q: [
        td.Resultado("W-30", "Naturej Moringa EJ 500mg 30 cápsulas", Decimal("60.00"), "https://www.walmart.com.mx/ip/w30"),
        td.Resultado("W-100", "Naturej Moringa EJ 500mg 100 cápsulas", Decimal("110.00"), "https://www.walmart.com.mx/ip/w100")]})
    # Chedraui no lo encuentra por nombre; por código de barras sí, y su EAN es el nuestro
    chedraui = TiendaSimulada("Chedraui", "chedraui.com.mx", {"7500000000017": [
        td.Resultado("C-1", "Moringa Naturej 100 caps", Decimal("130.00"), "https://www.chedraui.com.mx/c-1", ean="07500000000017")]})
    san_pablo = TiendaSimulada("San Pablo", "farmaciasanpablo.com.mx")
    soriana = TiendaSimulada("Soriana", "soriana.com", falla="bloqueó la consulta automática")
    con_tiendas(monkeypatch, walmart, chedraui, san_pablo, soriana)
    c = correr()
    f = fila(c.corrida_id, a)
    assert f.estado == "con_precios", f.mensaje
    # Walmart cuenta con el precio de su sitio (110), no con el que trajo Google (120)
    assert f.vendedores == 3 and f.mediana == Decimal("110.00")
    estados = json.loads(f.tiendas)
    assert estados["Walmart"]["estado"] == "encontrado" and estados["Chedraui"]["mensaje"] == "Mismo código de barras"
    assert estados["San Pablo"]["estado"] == "no_lo_tiene" and estados["Soriana"]["estado"] == "error"
    # Sin resultados con el texto completo, prueba sin la presentación y al final con el código de barras
    assert chedraui.consultas == [q, co.sin_presentacion(q), "MORINGA EJ", "7500000000017"] and walmart.consultas == [q]
    # Soriana falló: después de 3 fallas seguidas ya no se le pregunta (aquí solo hubo un producto)
    assert len(soriana.consultas) == 1

    d = admin.get(f"/api/compras/precios/productos/{a}").json()
    obs = {o["vendedor"]: o for o in d["observaciones"]}
    assert obs["Walmart"]["directa"] and Decimal(obs["Walmart"]["precio_comparable"]) == Decimal("110.00")
    assert obs["Chedraui"]["tienda_clave"] == "Chedraui" and not obs["Amazon"]["directa"]
    directas = {x["tienda"]: x for x in d["directas"]}
    assert set(directas) == {"Walmart", "Chedraui", "San Pablo", "Soriana"} and directas["Walmart"]["titulo"].endswith("100 cápsulas")
    lista = admin.get("/api/compras/precios/lista").json()
    assert {k: Decimal(v) for k, v in lista["filas"][0]["tiendas"].items()} == {"Walmart": Decimal("110.00"), "Chedraui": Decimal("130.00")}
    tabla = admin.get("/api/compras/precios/tabla").json()["renglones"]
    assert sorted(r["vendedor"] for r in tabla) == ["Amazon", "Chedraui", "Walmart"]

    # «No es este producto» en Chedraui: deja de contar al momento y no se vuelve a elegir
    r = admin.post(f"/api/compras/precios/productos/{a}/tiendas/{directas['Chedraui']['id']}/rechazar")
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["ultima"]["mediana"]) == Decimal("105.00") and "Chedraui" not in {o["vendedor"] for o in r.json()["observaciones"]}
    c2 = correr()
    assert json.loads(fila(c2.corrida_id, a).tiendas)["Chedraui"]["estado"] != "encontrado"
    with Session(motor()) as bd:  # Walmart reusa lo que eligió antes
        assert bd.scalar(select(func.count()).select_from(PrecioTiendaCoincidencia).where(PrecioTiendaCoincidencia.tienda == "Walmart")) == 1


def test_sin_google_cuentan_las_tiendas_y_una_tienda_caida_se_deja(limpio, monkeypatch):
    a = producto("ESPIRULINA EJ 500 MG 100 TABLETAS", lista="200.00")
    b = producto("ALOE EJ 1 L", lista="90.00")
    c_ = producto("AJO EJ 60 CAPSULAS", lista="80.00")
    d = producto("ZINC EJ 50 MG 60 TABLETAS", lista="70.00")
    vigilar(a, b, c_, d)
    walmart = TiendaSimulada("Walmart", "walmart.com.mx", {"NATUREJ ESPIRULINA EJ 500 MG 100 TABLETAS": [
        td.Resultado("W-E", "Naturej Espirulina EJ 500 mg 100 tabletas", Decimal("190.00"), "https://www.walmart.com.mx/ip/e")]})
    caida = TiendaSimulada("Soriana", "soriana.com", falla="no contestó")
    con_tiendas(monkeypatch, walmart, caida)
    c = correr()
    f = fila(c.corrida_id, a)
    assert f.estado == "con_precios" and f.mediana == Decimal("190.00") and "solo cuentan" in f.mensaje
    assert fila(c.corrida_id, b).estado == "sin_coincidencia"
    # Tres fallas seguidas: a la cuarta ya no se le pregunta
    assert len(caida.consultas) == 3
    mensajes = [json.loads(fila(c.corrida_id, x).tiendas)["Soriana"]["mensaje"] for x in (a, b, c_, d)]
    assert all("Soriana" in m for m in mensajes) and sum("No se buscó" in m for m in mensajes) == 1


def test_coincidencia_automatica_que_ya_no_pasa_las_reglas_se_invalida(limpio, monkeypatch):
    """Corrida 2004: lo que se aceptó mal antes no se reusa; con las reglas de hoy se deja y no cuenta."""
    a = producto("ACEITE DE AJO 500 ML", marca="SAN LUCAS", lista="150.00")
    vigilar(a)
    with Session(motor()) as bd:
        bd.add(PrecioTiendaCoincidencia(producto_id=a, tienda="Walmart", clave="W-O", titulo="Aceite de oliva San Lucas gourmet 500 ml",
                                        estado="automatica", motivo="Misma marca y presentación", verificado_en=ahora()))
        bd.commit()
    walmart = TiendaSimulada("Walmart", "walmart.com.mx", {"SAN LUCAS ACEITE DE AJO 500 ML": [
        td.Resultado("W-O", "Aceite de oliva San Lucas gourmet 500 ml", Decimal("160.00"), "https://www.walmart.com.mx/ip/o")]})
    con_tiendas(monkeypatch, walmart)
    c = correr()
    assert walmart.consultas[0] == "SAN LUCAS ACEITE DE AJO 500 ML"
    assert json.loads(fila(c.corrida_id, a).tiendas)["Walmart"]["estado"] != "encontrado"
    with Session(motor()) as bd:
        m = bd.scalar(select(PrecioTiendaCoincidencia).where(PrecioTiendaCoincidencia.clave == "W-O"))
        assert m.estado == "invalidada" and m.motivo.startswith("Las reglas actuales ya no lo aceptan")


def test_casos_del_diagnostico_2026_10_21_corrida_2005():
    """Salir en las dos búsquedas no suple la palabra que falta; un nombre que es solo la marca sí se compara."""
    oliva = co.Candidato("W-O", "Aceite de oliva San Lucas extra virgen gourmet 250 ml", {"rank_absolute": 1})
    oliva.estrategias.update({"descripcion", "sin_presentacion"})
    for desc in ("ACEITE DE AGUACATE EXTRA VIRGEN 250 ML", "ACEITE DE AJONJOLI EXTRA VIRGEN 250 ML"):
        d = co.decidir(desc, "SAN LUCAS", [oliva], 85, set(), set())
        assert not d.elegido and not oliva.evaluacion.aceptada
    demo = co.evaluar("DEMOGRASS 30 CAP", "DEMOGRASS", "Demograss 30 Cápsulas", 85, set(), 1)
    assert demo.nombre == 100 and demo.aceptada


def test_ajonjoli_250_contra_publicacion_sin_tamano_corrida_2006():
    """Google juntaba el de 500 ml en «San Lucas · Aceite de Ajonjolí Extra Virgen» y la IA lo dio por 250 ml."""
    desc = "ACEITE DE AJONJOLI EXTRA VIRGEN 250 ML"

    def cand(clave, titulo):
        c = co.Candidato(clave, titulo, {"rank_absolute": 1})
        c.evaluacion = co.evaluar(desc, "SAN LUCAS", titulo, 85, set(), 1)
        return c
    sin_tamano = cand("G-S", "San Lucas · Aceite de Ajonjolí Extra Virgen")
    con_250 = cand("G-250", "Aceite ajonjoli 250ml, san lucas, pieza")
    oliva = cand("G-O", "Aceite de Oliva San Lucas Extra Virgen 250ml")
    # La IA solo ve los que traen 250 ml (el de oliva lo rechaza ella, como en la corrida)
    assert {c.clave for c in co.para_ia([sin_tamano, con_250, oliva], set(), descripcion=desc)} == {"G-250", "G-O"}
    # Si ninguno de nuestra marca trae el tamaño, ve todos
    assert len(co.para_ia([sin_tamano, cand("G-I", "Inés Aceite de Ajonjolí 250 ml")], set(), descripcion=desc)) == 2

    def obs(datos):
        return PrecioObservacion(precio_comparable=Decimal("90"), moneda="MXN", es_propia=False, disponibilidad="in_stock",
                                 datos=json.dumps(datos))
    ml = obs({"title": "Mercado Libre", "url": "https://www.mercadolibre.com.mx/aceite-de-ajonjoli-o-sesamo-extra-virgen-500-ml-comestible/p/MLM1"})
    agro = obs({"title": "agrotitlan", "details": "Aceite De Ajonjoli 500ml, San Lucas, pieza", "url": "https://www.agrotitlan.com/shop/x-19060"})
    buena = obs({"title": "agrotitlan", "url": "https://www.agrotitlan.com/shop/aceite-ajonjoli-250ml-san-lucas-pieza-19061"})
    assert precios.fuera_de_rango(ml, desc, Decimal("80")) == "Otra presentación (500 ml)"
    assert precios.fuera_de_rango(agro, desc, Decimal("80")) == "Otra presentación (500 ml)"
    assert precios.fuera_de_rango(buena, desc, Decimal("80")) is None


def test_publicacion_sin_tamano_se_deja_si_hay_otras_con_el_nuestro(limpio, monkeypatch):
    """Corrida 2008: la IA ya no ve la publicación sin tamaño, pero la vigente se seguía usando con vendedores de 500 ml."""
    monkeypatch.setattr(configuracion(), "precios_ia_siempre", True)
    monkeypatch.setattr(configuracion(), "precios_buscar_siempre", True)
    a = producto("ACEITE DE AJONJOLI EJ 250 ML", lista="47.00")
    vigilar(a)
    q = "NATUREJ ACEITE DE AJONJOLI EJ 250 ML"
    limpio.resultados[q] = [item("Naturej Aceite de Ajonjolí EJ", "G-S")]
    limpio.vendedores["G-S"] = [vendedor("Tienda EJ", 74, "tienda.ej", url="https://tienda.ej/aceite-de-ajonjoli-ej-500-ml")]
    respuestas = {"elige": "G-S"}
    vistos = []

    def ia(bd, tarea, **k):
        vistos.append({x["clave"] for x in json.loads(k["mensaje"])["candidatos"]})
        clave = respuestas["elige"]
        decision = "match" if clave else "no_match"
        return type("R", (), {"texto": json.dumps({"decision": decision, "clave": clave, "confianza": 90, "motivo": "prueba"})})()

    monkeypatch.setattr("ia.puerta.ejecutar", ia)
    c1 = correr()
    f1 = fila(c1.corrida_id, a)
    assert f1.estado == "sin_precios"  # el único vendedor es de 500 ml
    # Ahora Google también trae una de 250 ml (que no es; la IA la rechaza): la sin tamaño ya no se ve ni se usa
    limpio.resultados[q] = [item("Naturej Aceite de Ajonjolí EJ", "G-S"), item("Naturej Aceite de Ajo EJ 250 ml", "G-250", 2)]
    respuestas["elige"] = None
    c2 = correr()
    assert vistos[-1] == {"G-250"}
    assert fila(c2.corrida_id, a).estado == "sin_coincidencia"
    with Session(motor()) as bd:
        assert precios.vigente(bd, a) is None
        m = bd.scalar(select(PrecioCoincidencia).where(PrecioCoincidencia.google_id == "G-S"))
        assert m.estado == "invalidada" and m.motivo.startswith("Su título no dice la presentación")


def test_tienda_con_variante_que_la_persona_no_eligio(limpio, monkeypatch):
    """Corrida 2008: Walmart aceptaba Demograss Plus aunque la publicación elegida a mano es Demograss 30 cápsulas."""
    a = producto("DEMOGRASS EJ 30 CAP", marca="DEMOGRASS EJ", lista="83.00")
    vigilar(a)
    with Session(motor()) as bd:
        bd.add(PrecioCoincidencia(producto_id=a, google_id="G-D", titulo="Demograss EJ 30 Cápsulas", estado="persona",
                                  estrategia="descripcion", verificado_en=ahora()))
        bd.commit()
    limpio.vendedores["G-D"] = [vendedor("Tienda EJ", 99, "tienda.ej")]
    walmart = TiendaSimulada("Walmart", "walmart.com.mx", {"DEMOGRASS EJ DEMOGRASS EJ 30 CAP": [
        td.Resultado("W-P", "Suplemento alimenticio Demograss EJ Plus 30 cápsulas", Decimal("124.00"), "https://www.walmart.com.mx/ip/p")],
        "DEMOGRASS EJ 30 CAP": [
        td.Resultado("W-P", "Suplemento alimenticio Demograss EJ Plus 30 cápsulas", Decimal("124.00"), "https://www.walmart.com.mx/ip/p")]})
    con_tiendas(monkeypatch, walmart)
    c = correr()
    estado = json.loads(fila(c.corrida_id, a).tiendas)["Walmart"]
    assert walmart.consultas, "no se buscó en Walmart"
    assert estado["estado"] == "dudoso" and "variante plus" in estado["mensaje"], estado


def _excel(*renglones) -> bytes:
    import io

    from openpyxl import Workbook

    libro = Workbook()
    for r in renglones:
        libro.active.append(list(r))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_prueba_con_excel_corre_solo_esos_skus_y_regresa_excel(limpio, admin, monkeypatch):
    import io

    from openpyxl import load_workbook

    from modulos.compras import excel_precios as xl

    def correr_ya(corrida_id):  # en la API corre aparte; aquí al momento
        with Session(motor()) as bd:
            precios.correr(bd, bd.get(PrecioCorrida, corrida_id))
    monkeypatch.setattr(precios, "correr_aparte", correr_ya)
    a = producto("DEMOGRASS EJ 30 CAPSULAS", barras="7500000000079")
    b = producto("AJO EJ 100 CAPSULAS", barras="7500000000086")
    vigilar(a)
    limpio.resultados["7500000000079"] = [item("Naturej Demograss EJ 30 caps", "G-A")]
    limpio.resultados["7500000000086"] = [item("Naturej Ajo EJ 100 capsulas", "G-B")]
    limpio.vendedores["G-A"] = [vendedor("Farmacia EJ", 120, "farmacia.ej")]
    limpio.vendedores["G-B"] = [vendedor("Farmacia EJ", 99.5, "farmacia.ej"), vendedor("Otra EJ", 110, "otra.ej")]
    regular = correr()
    with Session(motor()) as bd:
        sku_a, sku_b = bd.get(Producto, a).sku, bd.get(Producto, b).sku

    # Encabezado «SKU» en el segundo renglón; uno por código de barras, uno que no existe y uno repetido
    archivo = _excel(["Lista de prueba (ficticia)"], ["SKU"], [sku_b], ["7500000000079"], ["NO-EXISTE-EJ"], [sku_b])
    subir = lambda **q: admin.post("/api/compras/precios/prueba", params=q,  # noqa: E731
                                   files={"archivo": ("lista.xlsx", archivo)})
    r = subir(revisar=True).json()
    assert r["skus"] == 3 and [p["producto_id"] for p in r["encontrados"]] == [b, a]
    assert r["no_encontrados"] == ["NO-EXISTE-EJ"] and r["corrida"] is None and Decimal(r["estimado_usd"]) > 0
    _, consulta, _ = alta_usuario(admin, rol="compras_consulta")
    assert consulta.post("/api/compras/precios/prueba", files={"archivo": ("lista.xlsx", archivo)}).status_code == 403

    r = subir().json()
    pid = r["corrida"]["id"]
    with Session(motor()) as bd:
        c = bd.get(PrecioCorrida, pid)
        assert c.origen == "prueba" and c.estado == "completa" and c.productos == 2
        assert not bd.scalar(select(PrecioVigilado).where(PrecioVigilado.producto_id == b))  # no se agrega a vigilados
    # No cambia lo que muestra el radar: la última corrida sigue siendo la regular
    res = admin.get("/api/compras/precios/resumen").json()
    assert res["ultima"]["id"] == regular.corrida_id and res["ultima_prueba"]["id"] == pid
    assert res["ultima_prueba"]["archivo"] == "lista.xlsx" and res["ultima_prueba"]["no_encontrados"] == ["NO-EXISTE-EJ"]
    assert [f["producto_id"] for f in admin.get("/api/compras/precios/lista").json()["filas"]] == [a]
    assert not admin.get("/api/compras/precios/tabla").json()["corrida"]["origen"] == "prueba"

    x = admin.get(f"/api/compras/precios/corridas/{pid}/excel")
    assert x.status_code == 200 and "prueba" in x.headers["content-disposition"]
    libro = load_workbook(io.BytesIO(x.content))
    assert libro.sheetnames == ["Precios por tienda", "Resumen", "Precios", "No encontrados", "Corrida"]
    tiendas = list(libro["Precios por tienda"].iter_rows(values_only=True))
    assert tiendas[0][:8] == ("SKU", "Descripción", "Precio lista", "Precio membresía", "Precio Walmart",
                              "Dif. vs lista Walmart", "Dif. vs membresía Walmart", "URL Walmart")
    assert tiendas[0][8] == "Precio San Pablo" and tiendas[0][16] == "Precio Soriana"
    otras = {tiendas[0][i]: tiendas[1][i] for i in range(20, len(tiendas[0]))}
    assert [r[0] for r in tiendas[1:]] == [sku_b, sku_a] and otras  # las demás tiendas de Google
    assert set(v for k, v in otras.items() if k.startswith("URL ") and v) == {"Ver"}
    hoja = libro["Precios por tienda"]
    assert any(c.hyperlink for c in hoja[2] if c.value == "Ver")  # la URL completa va en el vínculo
    resumen = list(libro["Resumen"].iter_rows(min_row=2, values_only=True))
    assert [r[0] for r in resumen] == [sku_b, sku_a]  # en el orden del archivo
    assert resumen[0][3] == "Con precios" and resumen[0][9] == pytest.approx(104.75)
    assert {r[2] for r in libro["Precios"].iter_rows(min_row=2, values_only=True)} == {"Farmacia EJ", "Otra EJ"}
    assert libro["No encontrados"]["A2"].value == "NO-EXISTE-EJ"
    assert consulta.get(f"/api/compras/precios/corridas/{regular.corrida_id}/excel").status_code == 200  # también la regular

    # CSV con punto y coma y sin encabezado; archivos vacíos o de más
    assert xl.leer_skus("l.csv", f"{sku_a};x\n{sku_b};y\n".encode()) == [sku_a, sku_b]
    with pytest.raises(xl.ErrorArchivo):
        xl.leer_skus("l.xlsx", _excel([None]))
    with pytest.raises(xl.ErrorArchivo):
        xl.leer_skus("l.xlsx", _excel(["SKU"], *[[f"S{i}"] for i in range(xl.MAX_SKUS + 1)]))
    assert admin.post("/api/compras/precios/prueba", files={"archivo": ("l.pdf", b"%PDF")}).status_code == 400
    assert admin.get("/api/compras/precios/prueba/plantilla").status_code == 200


def test_excel_precios_por_tienda_en_el_orden_de_diego():
    from types import SimpleNamespace as N

    from modulos.compras import excel_precios as xl

    filas = [N(producto_id=1, sku="EJ-1", descripcion="Producto EJ", precio_lista=Decimal("100"),
               precio_membresia=Decimal("90"))]

    def r(vendedor, precio, clave=None, cuenta=True):
        return N(producto_id=1, vendedor=vendedor, precio=Decimal(precio), liga=f"https://{vendedor}.ejemplo.mx/p",
                 tienda_clave=clave, cuenta=cuenta)

    encabezados, renglones = xl._por_tienda(filas, [
        r("Walmart Super", "95", "Walmart"), r("Walmart MX", "93", "Walmart"), r("Soriana", "99", "Soriana"),
        r("Otra EJ", "80"), r("Lejana EJ", "10", cuenta=False)])
    fila = dict(zip(encabezados, renglones[0]))
    assert [encabezados[i] for i in (4, 8, 12, 16)] == ["Precio Walmart", "Precio San Pablo", "Precio Chedraui",
                                                        "Precio Soriana"]
    assert fila["Precio Walmart"] == Decimal("93") and fila["URL Walmart"] == "https://Walmart MX.ejemplo.mx/p"
    assert fila["Dif. vs lista Walmart"] == pytest.approx(100 / 93 - 1, abs=1e-4)  # positivo: más caros, va en rojo
    assert fila["Dif. vs membresía Walmart"] == pytest.approx(90 / 93 - 1, abs=1e-4)
    assert fila["Precio San Pablo"] is None and fila["Dif. vs lista San Pablo"] is None
    assert fila["Precio Soriana"] == Decimal("99")
    assert encabezados[20:] == ["Precio Otra EJ", "Dif. vs lista Otra EJ", "Dif. vs membresía Otra EJ",
                                "URL Otra EJ"]  # la que no cuenta no sale
    assert fila["Precio lista"] == Decimal("100") and fila["Precio membresía"] == Decimal("90")
