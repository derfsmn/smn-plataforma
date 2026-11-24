import sys,json
from pathlib import Path
sys.path.insert(0,'.')
from prueba_nutricional import consultar_ollama,diagnostico,PROMPT,ESQUEMA,validar_extraccion,validar_ficha
p=Path('tests/nutricional');ocr=json.loads(p.joinpath('55527-ocr.json').read_text(encoding='utf8'))['contenido']
opt=dict(num_ctx=16384,num_predict=8192,temperature=0,seed=42)
r=consultar_ollama(dict(model='qwen3:8b',stream=False,think=False,format=ESQUEMA,options=opt,messages=[dict(role='user',content=PROMPT+'\nEstructura SOLO esta transcripción visual generada localmente. Respeta los encabezados y las dos columnas de la tabla. Fuente foto_1:\n'+ocr)]))
p.joinpath('55527-dos-pasos-qwen3.respuesta.json').write_text(json.dumps({'inferencia':diagnostico(r,opt),'contenido':r['message']['content']},ensure_ascii=False,indent=2),encoding='utf8')
f=validar_ficha(validar_extraccion(r),{'foto_1'});print(json.dumps(f,ensure_ascii=True))
