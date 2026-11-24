"""Reaplica solo Python a inferencias REALES guardadas; no simula ni llama a Ollama."""
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prueba_nutricional import crear_ficha, preparar, validar_extraccion, mostrar_resumen
sys.stdout.reconfigure(encoding='utf8')
p=Path(__file__).parent
for sku,archivo,categoria in [('55527','55527.jpg',None),('55541','55541.jpg','suplemento'),('77755','77755A.jpg','alimento')]:
 r=json.loads(p.joinpath(sku+'.respuesta.json').read_text(encoding='utf8'))
 l=json.loads(p.joinpath(sku+'.lecturas.json').read_text(encoding='utf8'))
 _,fuente=preparar(p/archivo,1600)
 respuesta={**r['inferencia'],'message':{'content':r['contenido']}}
 f=crear_ficha(validar_extraccion(respuesta),{'foto_1':fuente},l,r['inferencia'],sku,categoria)
 f['revision_python']='Revisión de las mismas inferencias reales guardadas; sin nueva llamada al modelo.'
 p.joinpath(sku+'.json').write_text(json.dumps(f,ensure_ascii=False,indent=2),encoding='utf8')
 out=StringIO()
 with redirect_stdout(out):
  print(f['revision_python'])
  for lectura in l:print('Lectura visual real:',json.dumps(lectura['inferencia'],ensure_ascii=False))
  print('Estructuración real:',json.dumps(r['inferencia'],ensure_ascii=False))
  mostrar_resumen(f)
 p.joinpath(sku+'.salida.txt').write_text(out.getvalue(),encoding='utf8')
 print(sku,'ficha revisada desde inferencia real:',len(f['datos']),'cantidades')
