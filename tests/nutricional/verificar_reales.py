"""Cotejo de artefactos de inferencia REAL contra lecturas manuales de fotos públicas.
No invoca modelos, no rellena sus resultados y no se usa desde el extractor.
"""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prueba_nutricional import validar_ficha
p=Path(__file__).parent

def cargar(nombre):
 f=json.loads((p/nombre).read_text(encoding='utf8'))
 validar_ficha(f,f['fuentes'])
 for fuente in f['fuentes'].values():
  assert hashlib.sha256(Path(fuente['ruta']).read_bytes()).hexdigest()==fuente['sha256']
 assert f['inferencia']['contenido_final'] and f['inferencia']['done_reason']=='stop'
 assert f['lecturas']
 assert all(x['inferencia']['contenido_final'] and x['inferencia']['done_reason']=='stop' for x in f['lecturas'])
 assert len(f['ingredientes'])==1, 'No debe mezclarse toda la foto con los ingredientes'
 return f

def revisar_magnesio(nombre,masas,elemental):
 f=cargar(nombre)
 assert any(d['tipo']=='porcion' and d['valor']==2 and d['unidad']=='tabletas' for d in f['datos'])
 comp=[d for d in f['datos'] if d['tipo']=='compuesto' and d['base']=='por porción' and d['estado']=='declarado']
 assert [d['valor'] for d in comp]==masas, comp
 assert all(d['unidad']=='mg' for d in comp)
 elems=[d for d in f['datos'] if d['tipo']=='nutrimento' and 'magnesio' in d['nombre'].lower() and d['base']=='por porción' and d['estado']=='declarado']
 assert [d['valor'] for d in elems]==([] if elemental is None else [elemental]), elems
 assert all(d['unidad']=='mg' for d in elems)
 assert any('No exceder' in x['texto'] for x in f['advertencias'])
 if elemental is not None:assert len(f['equivalencias'])==2
 if elemental is None:assert any('Magnesio elemental' in x for x in f['pendientes'])
 assert sum(d['valor'] for d in comp)==sum(masas)
 print(nombre, 'cotejo real correcto')

if __name__=='__main__':
 revisar_magnesio('55527.json',[500],70)
 revisar_magnesio('55541.json',[50]*8,None)
 f=cargar('77755.json')
 esperados=[('Proteínas',8.4,'g'),('Grasas totales',9.6,'g'),('Grasas saturadas',1.2,'g'),('Grasas trans',0,'mg'),('Grasas poliinsaturadas',1.6,'g'),('Grasas monoinsaturadas',6.3,'g'),('Colesterol',1.3,'mg'),('Hidratos de carbono disponibles',75.1,'g'),('Azúcares',2.5,'g'),('Azúcares añadidos',0,'g'),('Fibra dietética',2.3,'g'),('Sodio',460,'mg')]
 for nombre,valor,unidad in esperados:
  assert any(d['nombre'].casefold()==nombre.casefold() and d['valor']==valor and d['unidad']==unidad and d['base']=='por 100 g' for d in f['datos']),nombre
 for base in ['por 100 g','por envase']:
  for valor,unidad in [(420.4,'kcal'),(1774.7,'kJ')]:
   assert any(d['valor']==valor and d['unidad']==unidad and d['base']==base for d in f['datos']),(base,valor,unidad)
 print('77755.json: cotejo real correcto')
