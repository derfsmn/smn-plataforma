import sys,json
from pathlib import Path
sys.path.insert(0,'.')
from prueba_nutricional import preparar,consultar_ollama,diagnostico
p=Path('tests/nutricional');img,_=preparar(p/'55527.jpg',1600)
opt=dict(num_ctx=16384,num_predict=4096,temperature=0)
r=consultar_ollama(dict(model='qwen3-vl:4b-instruct',stream=False,think=False,options=opt,messages=[dict(role='user',content='Transcribe literalmente todo el texto legible de esta etiqueta. Reproduce la tabla nutrimental como tabla Markdown con sus encabezados y columnas separadas. No expliques ni calcules. Incluye nombre, tamaño de porción, porciones por envase, ingredientes y advertencias.',images=[img])]))
p.joinpath('55527-ocr.json').write_text(json.dumps({'inferencia':diagnostico(r,opt),'contenido':r['message']['content']},ensure_ascii=False,indent=2),encoding='utf8');print(r['message']['content'])
