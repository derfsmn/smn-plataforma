"""Prueba por lote de los precios de afuera y aviso de búsquedas que DataForSEO no acepta (25 nov 2026)."""
import json

from openpyxl import load_workbook

from modulos.compras import dataforseo as dfs
from modulos.compras import mercado_producto as mp
from modulos.compras import prueba_afuera as pa


class _BD:
    def rollback(self):
        pass


def test_motivos_y_resumen(tmp_path, monkeypatch):
    def buscar(bd, nombre, marca, codigo, referencia):
        if nombre == "A":
            return mp.Mercado(precios=[{"precio": 10.0, "vendedor": "x", "fuente": "google"}])
        if nombre == "B":
            return mp.Mercado(notas=["Google Shopping no aceptó la búsqueda «B +» (40501 Invalid Field)."])
        if nombre == "C":
            return mp.Mercado(notas=["Google Shopping no regresó resultados."])
        if nombre == "D":
            raise RuntimeError("se cayó")
        return mp.Mercado(notas=["Google Shopping: ningún resultado es claramente el mismo producto."])

    monkeypatch.setattr(mp, "buscar", buscar)
    lista = [pa.Caso("idea", f"idea {n}", n, None, None) for n in "ABCDE"]
    pa.probar(_BD(), lista)
    assert [c.motivo for c in lista] == [pa.ENCONTRADO, pa.RECHAZADA, pa.SIN_RESULTADOS, pa.ERROR, pa.PARECIDOS]
    res = pa.resumen(lista)
    assert res["encontrados"] == 1 and res["pct"] == 20.0 and res["por_origen"]["idea"] == {"total": 5, "encontrados": 1}
    archivo = tmp_path / "p.xlsx"
    pa.a_excel(archivo, lista, res, 5)
    wb = load_workbook(archivo)
    assert wb.sheetnames == ["Resumen", "Detalle"] and wb["Detalle"].max_row == 6
    assert any(r[0] == pa.RECHAZADA for r in wb["Resumen"].iter_rows(values_only=True))


def test_google_dice_que_busqueda_no_acepto(admin, monkeypatch):
    from core.bd import _fabrica
    from modulos.compras.modelos_precios import PrecioEnvio

    monkeypatch.setattr(dfs, "configurado", lambda: [])

    def enviar(bd, corrida, tipo, tareas):
        bd.add(PrecioEnvio(corrida_id=corrida.corrida_id, tipo=tipo, tareas=len(tareas), estado="confirmado", estimado_usd=0,
                           respuesta=json.dumps([{"id": "1", "tag": "0", "estado": 20100, "mensaje": "Task Created."},
                                                 {"id": None, "tag": "1", "estado": 40501, "mensaje": "Invalid Field: 'keyword'."}])))
        bd.commit()
        return {"0": "1"}

    monkeypatch.setattr(dfs, "enviar", enviar)
    monkeypatch.setattr(dfs, "recoger", lambda tipo, ids: {"0": []})
    m = mp.Mercado()
    with _fabrica()() as bd:
        mp._google(bd, m, "BDM Life", None, [("codigo_barras", "7503005911294"), ("descripcion", "BDM Life Berberina")],
                   set(), "idea 1")
    assert any("no aceptó la búsqueda «BDM Life Berberina» (40501 Invalid Field: 'keyword'.)" in n for n in m.notas)
    assert pa.motivo(m) == pa.RECHAZADA
