"""Ficha técnica estándar (migración 0047): reglas + IA local con cita obligatoria, «Está mal» y uso en el radar.
La IA es FALSA en estas pruebas; los productos son ficticios."""
import json
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.bd import motor
from datos import fichas as fi
from datos.modelos import IdeaFicha, Producto, ProductoFicha
from ia import puerta
from tests.test_productos import sincrono  # noqa: F401


def _resp(datos: dict) -> puerta.Respuesta:
    return puerta.Respuesta(json.dumps(datos, ensure_ascii=False), "ollama", "falso", 1, 1, Decimal(0), 1, True, 0)


def test_reglas_leen_contenido_forma_porciones_y_registro():
    f = fi.reglas("Proteína vegetal sabor vainilla 510 g, 17 porciones. Reg. 123M2019 SSA")
    assert (f.contenido_cantidad, f.contenido_unidad) == (Decimal("510"), "g")
    assert f.porciones == 17 and f.forma == "polvo" and f.registro_sanitario.startswith("123M2019")
    g = fi.reglas("Magnesio 3 en 1, 60 tabletas de 500 mg")
    assert g.piezas == 60 and g.contenido_unidad == "pz" and g.forma == "tabletas"
    assert fi.precio_por_unidad(Decimal("300"), g) == (Decimal("5"), "pz")


def test_la_ia_solo_cuenta_lo_que_puede_citar(base_de_pruebas, monkeypatch):
    texto = "Creatina monohidratada Creapure 300 g. Cada porción de 5 g aporta 5 g de creatina. Sin sabor."
    propuesta = {
        "tipo": {"valor": "creatina en polvo", "cita": "Creatina monohidratada Creapure"},
        "ingrediente_principal": {"valor": "creatina monohidratada", "cita": "creatina monohidratada"},
        "activo_g_porcion": {"valor": 5, "cita": "aporta 5 g de creatina"},
        "sabor": {"valor": "natural", "cita": "Sin sabor"},
        "uso": {"valor": "aumenta la fuerza muscular", "cita": "aumenta tu fuerza"},  # no está en el texto
        "porciones": {"valor": 60, "cita": "60 porciones"},  # inventado
        "contenido_cantidad": {"valor": 1000, "cita": "300 g"},  # el número no está en la cita
    }
    monkeypatch.setattr(puerta, "ejecutar", lambda *a, **k: _resp(propuesta))
    with Session(motor()) as bd:
        f, nota = fi.extraer(bd, texto)
    assert nota is None
    assert f.tipo == "creatina en polvo" and f.origenes["tipo"] == "texto"
    assert f.activo_g_porcion == Decimal("5") and f.sabor == "natural"
    assert f.uso is None and f.porciones is None  # sin cita en el texto no entra
    assert f.contenido_cantidad == Decimal("300") and f.origenes["contenido"] == "reglas"  # las reglas ganan


def test_ficha_del_catalogo_esta_mal_y_lote(admin: TestClient, monkeypatch):
    llamadas = []

    def ia(bd, tarea, **k):
        llamadas.append(k["mensaje"])
        return _resp({"tipo": {"valor": "té de hierbas", "cita": "Té de manzanilla"}})

    monkeypatch.setattr(puerta, "ejecutar", ia)
    h = uuid.uuid4().hex[:6]
    with Session(motor()) as bd:
        p = Producto(sku=f"FI-{h}", descripcion=f"Té de manzanilla FI{h} 25 sobres", marca=f"FI{h}", origen="API",
                     activo=True, iva_pct=Decimal("0"))
        bd.add(p)
        bd.commit()
        assert p.producto_id in fi.pendientes(bd, 100000)
        f = fi.de_producto(bd, p)
        bd.commit()
        assert f.tipo == "té de hierbas" and f.piezas == 25 and f.iva_pct == 0 and f.origenes["iva_pct"] == "catalogo"
        n = len(llamadas)
        fi.de_producto(bd, p)  # mismo texto: no se vuelve a leer
        assert len(llamadas) == n and p.producto_id not in fi.pendientes(bd, 100000)
        pid = p.producto_id

    r = admin.get(f"/api/datos/fichas/producto/{pid}")
    assert r.status_code == 200 and r.json()["estado"] == "lista"
    assert next(c for c in r.json()["campos"] if c["campo"] == "tipo")["cita"] == "Té de manzanilla"
    r = admin.post(f"/api/datos/fichas/producto/{pid}/esta-mal", json={"motivo": "Son 20 sobres, no 25"})
    assert r.status_code == 200 and r.json()["estado"] == "mal"

    with Session(motor()) as bd:
        assert fi.a_ficha(bd.get(ProductoFicha, pid)) is None  # deja de usarse al momento
        assert pid in fi.pendientes(bd, 100000)
        fi.lote(bd, limite=10000)
        fila = bd.get(ProductoFicha, pid)
        assert fila.estado == "lista" and fila.mal_motivo is None
    assert "Son 20 sobres" in llamadas[-1]  # la siguiente lectura recibe el motivo


def test_el_radar_usa_la_ficha_de_la_idea(admin: TestClient, sincrono, monkeypatch):  # noqa: F811
    """La idea no dice su contenido; la ficha lo saca de la descripción y el radar lo usa."""
    def ia(bd, tarea, **k):
        if tarea == fi.TAREA:
            return _resp({"tipo": {"valor": "shampoo", "cita": "Shampoo de romero"},
                          "uso": {"valor": "fortalece el cabello", "cita": "fortalece el cabello"}})
        raise puerta.ErrorIA("sin IA en esta prueba")

    monkeypatch.setattr(puerta, "ejecutar", ia)
    r = admin.post("/api/compras/productos/ideas", json={
        "nombre": f"Shampoo de romero FI{uuid.uuid4().hex[:5]}", "departamento": "CUIDADO PERSONAL (ejemplo)",
        "descripcion": "Shampoo de romero que fortalece el cabello. Botella de 500 ml.", "precio_visto": "120"})
    assert r.status_code == 201, r.text
    e = r.json()["id"]
    ficha = admin.get(f"/api/compras/productos/evaluaciones/{e}/ficha").json()
    campos = {c["campo"]: c for c in ficha["campos"]}
    assert campos["tipo"]["valor"] == "shampoo" and campos["contenido"]["valor"] == "500 ml"
    assert campos["contenido"]["origen"] == "reglas" and campos["uso"]["cita"] == "fortalece el cabello"
    r = admin.post(f"/api/compras/productos/evaluaciones/{e}/ficha/esta-mal", json={"motivo": "Es de 1 litro"})
    assert r.status_code == 200 and r.json()["mal_motivo"] == "Es de 1 litro"
    with Session(motor()) as bd:
        fila = bd.scalar(select(IdeaFicha).where(IdeaFicha.origen == "idea"))
        assert fila is not None


def test_sustitutos_por_funcion(base_de_pruebas, monkeypatch):
    """La piedra de alumbre no comparte palabras con «desodorante natural», pero hace lo mismo."""
    h = uuid.uuid4().hex[:6]

    def vec(texto: str) -> list[float]:
        t = texto.lower()
        return [1.0 if ("desodorante" in t or "axilas" in t) else 0.0, 1.0 if "té" in t else 0.0, 0.1]

    monkeypatch.setattr(puerta, "vectores", lambda bd, tarea, textos, **k: ("bge-m3", [vec(t) for t in textos]))
    with Session(motor()) as bd:
        ids = {}
        for nombre, tipo, uso in (("piedra", "piedra de alumbre", "evita el mal olor de axilas"),
                                  ("te", "té de hierbas", "relaja")):
            p = Producto(sku=f"SF-{nombre}-{h}", descripcion=f"{nombre.upper()} SF{h}", origen="API", activo=True,
                         precio_lista_con_impuestos=Decimal("80"))
            bd.add(p)
            bd.flush()
            bd.add(ProductoFicha(producto_id=p.producto_id, tipo=tipo, uso=uso, estado="lista", intentos=1,
                                 extraida_en=p.creado_en or fi.ahora()))
            ids[nombre] = p.producto_id
        bd.commit()
        assert fi.calcular_huellas(bd, limite=100000) >= 2
        assert not [x for x in fi.huellas_pendientes(bd) if x[0] in ids.values()]
        cerca = fi.cercanos_por_funcion(bd, fi.Ficha(tipo="desodorante natural", uso="para axilas"), k=500)
        pids = [pid for pid, _ in cerca]
        assert ids["piedra"] in pids and ids["te"] not in pids
