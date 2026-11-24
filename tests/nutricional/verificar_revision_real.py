"""Comprueba reportes guardados; no ejecuta ni simula llamadas a Ollama."""
import json
from pathlib import Path

p = Path(__file__).parent
for sku in ('55527','55541','77755'):
    f = json.loads(p.joinpath('revision_'+sku+'.json').read_text(encoding='utf8'))
    r = f['revision_nutrimental']
    assert r['estado_general']=='informacion_insuficiente'
    assert r['contexto']['poblacion'] is None and r['contexto']['finalidad'] is None
    assert r['contexto']['perfil_referencia'] is None
    assert r['ia']['estado']=='correcto' and r['ia']['contenido_final']
    assert r['ia']['done_reason']=='stop' and r['ia']['eval_count']>0
    assert set(r['prioridades']).issubset({h['id'] for h in r['hallazgos']})
    assert all(x['estado']=='coincide' for x in r['integridad_fuentes'])
    assert all(ref in {x['id'] for x in r['referencias']} for h in r['hallazgos'] for ref in h['referencias'])
    assert r['preguntas_proveedor']
    if sku=='55527':
        elem=[a for a in r['aportes'] if a['nombre']=='Equivalente a Magnesio' and a['base']=='por porción']
        assert len(elem)==1 and elem[0]['valor_diario']==70
        assert r['contexto']['consumo_diario']['origen']=='instruccion_etiqueta'
    elif sku=='55541':
        comp=[a for a in r['aportes'] if a['tipo']=='compuesto' and a['base']=='por porción']
        assert len(comp)==8 and sum(a['valor_diario'] for a in comp)==400
        assert any(h['criterio']=='Magnesio elemental declarado por porción' and h['resultado']=='informacion_insuficiente' for h in r['hallazgos'])
    else:
        assert r['contexto']['consumo_diario']['porciones'] is None
        assert all(a['valor_diario'] is None for a in r['aportes'])
        assert any(h['criterio']=='Aporte por porción identificable' for h in r['hallazgos'])
    print(sku, 'revisión de ficha real y priorización real verificadas')
