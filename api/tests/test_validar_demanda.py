"""Validación de la Demanda con lanzamientos reales (Diego, 20 nov 2026: «esa conclusión es muy general»). Datos
ficticios, sin base de datos."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from modulos.compras import pronostico as pn
from modulos.compras import radar_productos as rp
from modulos.compras import realidad_producto as rr
from modulos.compras import validacion_demanda as vd
from scripts import validar_demanda as script


def _lz(sku: str, real: float, razon: float = 1.0, ini: date = date(2026, 4, 6)) -> pn.Lanzamiento:
    return pn.Lanzamiento(sku, "CREATINA" if sku.startswith("C") else "OTRA", ini, {12: razon}, {12: real}, None)


def _prod(sku: str, depto: str = "DEPORTES", precio: str = "400", sub: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(sku=sku, descripcion=f"Producto {sku}", departamento=depto, marca=None, activo=True,
                           subcategoria=sub or ("CREATINA" if sku.startswith("C") else "OTRA"),
                           precio_lista_con_impuestos=Decimal(precio))


def test_clase_y_zona():
    assert [vd.clase(x) for x in (6, 3, 2, 1.2, 0.9, 0.5)] == ["AA", "A", "B", "C", "D", "E"]
    assert vd.calificacion(26) == 19 and vd.zona(19) == "rojo" and vd.zona(85) == "verde"


def test_la_frase_dice_con_que_productos_se_compara():
    lista = [_lz("C1", 2.0), _lz("C2", 0.5), _lz("X1", 1.5)]
    misma = [script.Fila("C1", "YAOCA Creatina", "DEPORTES", "CREATINA", Decimal(462), None, 2.0),
             script.Fila("C2", "BASMAC Creatina", "DEPORTES", "CREATINA", Decimal(403), None, 0.5)]
    lineas = script.frase("Wonu", 0.9, lista, True, "DEPORTES", misma, misma[:1], "CREATINA")
    assert "De los 3 productos del departamento DEPORTES" in lineas[0] and "2 vendieron más" in lineas[0]
    assert "De los 2 lanzamientos de CREATINA, 1 vendieron más: YAOCA Creatina 2.0; BASMAC Creatina 0.5" in lineas[1]
    assert "YAOCA Creatina ($462) 2.0" in lineas[2]
    assert "no hay un caso igual" in script.frase("Wonu", 0.9, lista, True, "DEPORTES", [], [], "CREATINA")[1]


def test_elige_del_departamento_y_de_toda_la_cadena_de_arriba_a_abajo():
    m = pn.Modelo(lanzamientos=[_lz(f"D{i}", 10 - i) for i in range(6)] + [_lz(f"X{i}", 10 - i) for i in range(10)])
    productos = {x.sku: _prod(x.sku, "DEPORTES" if x.sku.startswith("D") else "OTRO") for x in m.lanzamientos}
    elegidos = vd.elegir(m, productos, "DEPORTES", 6)
    assert [x.sku for x in elegidos][:3] == ["D0", "D2", "D5"]  # el que más vendió, uno en medio y el que menos
    assert len(elegidos) == 6 and {"X0", "X9"} <= {x.sku for x in elegidos}


def test_se_pronostica_con_lo_que_habia_antes_del_lanzamiento(monkeypatch):
    ini = date(2026, 4, 6)
    x = _lz("C9", 1.0, ini=ini)
    otros = [_lz(f"X{i}", r, razon=0.5 + i * 0.1) for i, r in enumerate((0.5, 0.8, 1.2, 2.0, 3.0))]
    m = pn.Modelo(lanzamientos=[x, *otros])
    productos = {"C9": _prod("C9"), "P1": _prod("P1", precio="380"), "P2": _prod("P2", precio="390"),
                 **{y.sku: _prod(y.sku) for y in otros}}
    primera = {"P1": date(2025, 1, 6), "P2": ini + timedelta(weeks=2)}  # P2 salió después: no existía
    monkeypatch.setattr(rp, "buscar_parecidos", lambda bd, s, sub: [(productos["P1"], Decimal("0.8")),
                                                                      (productos["P2"], Decimal("0.7"))])
    vistas = {}

    def venta(bd, v, skus=None, departamento=None):
        vistas["fin"], vistas["skus"] = v.fin, skus
        return {s: rr.VentaSku(piezas=26 * 10, tiendas=10, semanas=26, recientes=0, anteriores=0) for s in skus}

    monkeypatch.setattr(rr, "venta_por_sku", venta)
    fila, detalle = vd.probar(None, x, m, productos, primera, date(2025, 1, 6), set())
    assert vistas["fin"] == ini - timedelta(weeks=1) and vistas["skus"] == ["P1"]
    base = 26 * 10 / 10 / 26 * rr.SEMANAS_MES
    assert fila["base"] == round(base, 2) and fila["pron_medio"] == round(base * 0.7, 2)  # mediana de los otros
    assert fila["real"] == 1.0 and fila["clase_real"] == "C"
    assert [d["parecido"] for d in detalle] == ["P1"]


def test_banda_mas_ancha_que_los_cuartiles():
    xs = [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2]
    bajo, medio, alto = pn._banda(xs)
    q1, _, q3 = pn._cuartiles(xs)
    assert bajo < q1 and alto > q3 and medio == 1.2


def test_demanda_dice_contra_su_subcategoria_y_que_tan_seguido_atina(monkeypatch):
    monkeypatch.setattr(rr, "venta_por_sku", lambda *a, **k: {})
    monkeypatch.setattr(pn, "lugar_entre_lanzamientos", lambda bd, x, depto=None: (26.0, 39, True))
    pron = pn.Pronostico(base=1.1, base_de="2 parecido(s) que ya vendemos", tramos={"12": [0.6, 0.88, 1.4]},
                         examen={"prueba": {"probados": 24, "color": 17, "clase": 9, "en_rango": 18}},
                         misma_sub=[{"sku": "1", "descripcion": "CREATINE CREAPURE 500 G", "por_tienda": 1.99},
                                    {"sku": "2", "descripcion": "CREAATOR JELLY RIVER 540 G", "por_tienda": 0.91}])
    s = rp.Sujeto(tipo="idea", nombre="Creatina + Inositol", departamento="DEPORTES", precio=Decimal("599"))
    f = rp.f_demanda(None, s, [], rr.Ventana(date(2026, 4, 6), date(2026, 9, 28), set()), None, pron)
    assert f.valor.endswith("los 2 lanzamientos de su subcategoría en 2026 vendieron entre 0.9 y 2.0")
    assert "CREATINE CREAPURE 500 G 2.0; CREAATOR JELLY RIVER 540 G 0.9" in f.detalle
    assert "quedaría como el más bajo" in f.detalle
    assert "atinó el color de la Demanda en 17 y la clase AA–E en 9" in f.detalle


def test_el_rango_se_ajusta_con_los_errores_reales():
    filas = [{"real": r, "pron_medio": 1.0, "error_pct": round((1 - r) * 100), "misma_zona": True,
              "clase_pron": "C", "clase_real": "C", "dentro_rango": True}
             for r in [0.3 + 0.1 * i for i in range(20)]]
    r = vd.resumen(filas)
    assert r["probados"] == 20 and r["ajuste"][0] < 0.6 and r["ajuste"][1] > 1.8
    assert "ajuste" not in vd.resumen(filas[:5])
