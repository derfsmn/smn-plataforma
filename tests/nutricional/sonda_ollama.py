"""Sonda directa /api/chat. No imprime ni guarda message.thinking."""
import argparse
import base64
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from prueba_nutricional import consultar_ollama, preparar, diagnostico

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--modelo',default='qwen3-vl:8b')
 p.add_argument('--imagen',type=Path)
 p.add_argument('--max-lado',type=int,default=0)
 p.add_argument('--contexto',type=int,default=4096)
 p.add_argument('--tokens',type=int,default=2048)
 p.add_argument('--formato',choices=['libre','json'],default='libre')
 p.add_argument('--salida',type=Path,required=True)
 a=p.parse_args()
 mensaje={'role':'user','content':'Devuelve JSON con las cantidades de la tabla nutrimental visibles y sus unidades. Si no hay imagen devuelve {"ok":true}.'}
 fuente=None
 if a.imagen:
  if a.max_lado:
   imagen,fuente=preparar(a.imagen,a.max_lado)
  else:
   imagen=base64.b64encode(a.imagen.read_bytes()).decode()
   fuente={'ruta':str(a.imagen),'resolucion':'original'}
  mensaje['images']=[imagen]
 opciones=dict(num_ctx=a.contexto,num_predict=a.tokens,temperature=0)
 req=dict(model=a.modelo,stream=False,think=False,messages=[mensaje],options=opciones)
 if a.formato=='json':req['format']='json'
 r=consultar_ollama(req)
 resultado={**diagnostico(r,opciones),'formato':a.formato,'fuente':fuente,'thinking_presente':bool(r.get('message',{}).get('thinking')),'contenido':r.get('message',{}).get('content','')}
 a.salida.write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(resultado,ensure_ascii=True))
if __name__=='__main__':main()
