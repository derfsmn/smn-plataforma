"""Cotejo de artefactos reales guardados; no llama a Ollama ni repite OCR."""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analisis_nutrimental import mostrar_analisis, validar_interpretacion

raiz=Path(__file__).parent
for sku in ('55527','55541','77755'):
    archivo=raiz/f'analisis_{sku}.json'
    ficha=json.loads(archivo.read_text(encoding='utf8'))
    r=ficha['revision_nutrimental'];a=r['analisis_producto']
    assert all(x['estado']=='coincide' for x in r['integridad_fuentes'])
    assert r['contexto']['finalidad'] is None and r['contexto']['poblacion'] is None
    if a['interpretacion_ia']:
        try:
            validar_interpretacion(a['interpretacion_ia'],a,r['hallazgos'])
        except ValueError as error:
            r['ia'].update(estado='rechazado_en_cotejo',motivo=str(error))
            a['interpretacion_ia']=None
            r['prioridades']=[]
            archivo.write_text(json.dumps(ficha,ensure_ascii=False,indent=2),encoding='utf8')
    if a['interpretacion_ia']:
        assert r['ia']['contenido_final'] and r['ia']['done_reason']=='stop'
    if sku=='55527':
        assert [e['porcentaje_referencia'] for e in a['escenarios_referencia']]==[17.5,22.58,16.67,21.88]
        assert a['estudios_contrastados'][0]['proporcion_cantidad_estudiada']==28
    elif sku=='55541':
        assert not a['escenarios_referencia']
        assert a['estudios_contrastados'][0]['proporcion_cantidad_estudiada'] is None
    else:
        assert any(e['base']=='por 100 g' and e['porcentaje_referencia']==20 for e in a['escenarios_referencia'])
        assert not a['estudios_contrastados']
    resumen=io.StringIO()
    with contextlib.redirect_stdout(resumen):mostrar_analisis(r)
    archivo.with_suffix('.salida.txt').write_text(resumen.getvalue(),encoding='utf8')
    print(sku,r['ia'],'calculos cotejados')
