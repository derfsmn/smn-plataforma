"""Casos reales públicos; expectativas de cotejo, nunca se pasan al modelo."""
import json
from pathlib import Path
from urllib.request import urlopen
CASOS = [
 {'sku':'55527','url':'https://supernaturista.com/cdn/shop/files/55527B.jpg?v=1776424549&width=2000','archivo':'55527.jpg','esperado':{'tabletas':2,'compuestos_mg':[500],'elemental_mg':70}},
 {'sku':'55541','url':'https://supernaturista.com/cdn/shop/files/55541B.jpg?v=1777597443&width=2000','archivo':'55541.jpg','esperado':{'tabletas':2,'compuestos_mg':[50]*8,'elemental_mg':None}},
 {'sku':'77755','url':'https://supernaturista.com/cdn/shop/files/77755A.jpg?width=2000','archivo':'77755A.jpg','esperado':{'proteinas_g_100g':8.4,'sodio_mg_100g':460,'grasas_trans_mg_100g':0,'energia_kcal_100g':420.4}},
]
if __name__=='__main__':
 p=Path(__file__).parent
 for caso in CASOS:
  destino=p/caso['archivo']
  if not destino.exists():destino.write_bytes(urlopen(caso['url'],timeout=30).read())
 p.joinpath('casos_reales.json').write_text(json.dumps(CASOS,ensure_ascii=False,indent=2),encoding='utf8')
