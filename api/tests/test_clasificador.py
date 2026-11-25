"""Clasificador por votación: arreglos del examen v0.5.4 (Diego, 25 nov 2026)."""
from decimal import Decimal

from datos import fichas as fi
from datos.modelos import Producto
from modulos.compras import clasificador as cl
from modulos.compras import examen_clasificacion as ex
from modulos.compras import radar_productos as rp


def _p(i, desc, sub, rama="R"):
    return Producto(producto_id=i, sku=str(i), descripcion=desc, marca=f"M{i}", subcategoria=sub, rama=rama,
                    departamento="D", precio_lista_con_impuestos=Decimal("100"), activo=True)


def _preparar(monkeypatch, catalogo):
    cl._CACHE.clear()
    monkeypatch.setattr(cl, "catalogo_completo", lambda bd: catalogo)

    def sin_huellas(*a, **k):
        raise RuntimeError("sin huellas")

    monkeypatch.setattr(fi, "cercanos_por_funcion", sin_huellas)
    llamadas = []

    def ia(bd, s, finalistas, ejemplos):
        llamadas.append(list(finalistas))
        return finalistas[-1]  # la IA elige la de abajo

    monkeypatch.setattr(cl, "desempatar", ia)
    return llamadas


def test_la_ia_no_cambia_una_ganadora_clara(monkeypatch):
    catalogo = ([_p(i, f"MENOPAUSIA FENOGRECO {i} 60 CAP", "MENOPAUSIA") for i in range(1, 6)]
                + [_p(i, f"FENOGRECO ULCERA {i} 60 CAP", "ULCERAS") for i in range(6, 9)]
                + [_p(i, f"FENOGRECO OTRO {i} 60 CAP", "OTRA") for i in range(9, 12)])
    llamadas = _preparar(monkeypatch, catalogo)
    s = rp.Sujeto(tipo="idea", nombre="FENOGRECO AGUAJE 60 CAP", marca="X")
    c = cl.clasificar(None, s)
    assert c.subcategoria == "MENOPAUSIA" and c.origen == "votos" and not llamadas


def test_la_ia_solo_desempata_entre_parejas(monkeypatch):
    catalogo = ([_p(i, "FENOGRECO MUJER 60 CAP", "MENOPAUSIA") for i in range(1, 5)]
                + [_p(i, "FENOGRECO CICLO 60 CAP", "SINTOMAS MENSTRUALES") for i in range(5, 9)]
                + [_p(i, "FENOGRECO OTRO 60 CAP", "OTRA") for i in range(9, 11)])
    llamadas = _preparar(monkeypatch, catalogo)
    c = cl.clasificar(None, rp.Sujeto(tipo="idea", nombre="FENOGRECO 60 CAP", marca="X"))
    assert llamadas and "OTRA" not in llamadas[0] and len(llamadas[0]) == 2 and c.origen == "votos_ia"


def test_un_gotero_no_cae_en_bebidas(monkeypatch):
    catalogo = ([_p(i, "HOJA GUAYABA AGUA 600 ML", "SABORIZADA") for i in range(1, 7)]
                + [_p(i, "HOJA GUAYABA EXTRACTO 30 ML", "MALESTAR ESTOMACAL") for i in range(7, 9)])
    _preparar(monkeypatch, catalogo)
    c = cl.clasificar(None, rp.Sujeto(tipo="idea", nombre="HOJA DE GUAYABA 30 ML", marca="X"))
    assert c.subcategoria == "MALESTAR ESTOMACAL"
    assert any("sin productos de su forma" in r for r in c.razones)


def test_subcategorias_repetidas_cuentan_como_una():
    assert ex.canon("ACEITE") == ex.canon("ACEITES")
    assert ex.canon("MINERAL") == ex.canon("MINERALES")
    assert ex.canon("GOMITA") == ex.canon("GOMITAS")
    assert ex.canon("MULTIUSO") == ex.canon("MULTIUSOS")
    assert ex.canon("TE") == ex.canon("TE EN SOBRE")
    assert ex.canon("HUESOS") != ex.canon("ARTICULACIONES") and ex.canon("FACIAL") != ex.canon("CORPORAL")
    grupos = ex.repetidas([_p(1, "a", "ACEITE"), _p(2, "b", "ACEITES"), _p(3, "c", "ACEITES"), _p(4, "d", "FACIAL")])
    assert grupos == [("aceit", [("ACEITES", 2), ("ACEITE", 1)])]
