import json,base64,time
from pathlib import Path
from urllib.request import urlopen,Request
p=Path('tests/nutricional')
for sku,v in [('55527','1776424549'),('55541','1777597443')]:
 p.joinpath(sku+'.jpg').write_bytes(urlopen(f'https://supernaturista.com/cdn/shop/files/{sku}B.jpg?v={v}&width=2000').read())
def chat(model,images=[],ctx=4096,fmt=None):
 req=dict(model=model,stream=False,think=False,messages=[dict(role='user',content='Devuelve JSON con las cantidades de la tabla nutrimental visibles y sus unidades. Si no hay imagen devuelve {"ok":true}.',images=images)],options=dict(num_ctx=ctx,num_predict=2048,temperature=0))
 if fmt: req['format']=fmt
 r=json.load(urlopen(Request('http://127.0.0.1:11434/api/chat',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=600))
 out={k:r.get(k) for k in ['model','done_reason','prompt_eval_count','eval_count']};out.update(ctx=ctx,format=fmt,content=r.get('message',{}).get('content',''),thinking_present=bool(r.get('message',{}).get('thinking')))
 print(json.dumps(out,ensure_ascii=True),flush=True);p.joinpath(f'directo-{model.replace(":","-")}-{ctx}-{bool(images)}-{fmt}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
chat('qwen3-vl:8b')
chat('qwen3-vl:8b',[base64.b64encode(p.joinpath('55527.jpg').read_bytes()).decode()])
