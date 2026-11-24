"""Inferencias reales, secuenciales. No usa las expectativas del cotejo."""
import argparse
import subprocess
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf8')
p=Path(__file__).parent
args=argparse.ArgumentParser();args.add_argument('--skus',nargs='+',default=['55527','55541','77755']);args=args.parse_args()
fallos=0
for sku,archivo,categoria in [('55527','55527.jpg',None),('55541','55541.jpg','suplemento'),('77755','77755A.jpg','alimento')]:
 if sku not in args.skus:continue
 cmd=[sys.executable,'prueba_nutricional.py','--imagen',str(p/archivo),'--sku',sku,'--modelo','qwen3-vl:4b-instruct','--modelo-texto','qwen3:8b','--contexto','16384','--contexto-texto','8192','--tokens','8192','--max-lado','1600','--salida',str(p/(sku+'.json'))]
 if categoria:cmd.extend(['--categoria',categoria])
 print(subprocess.list2cmdline(cmd),flush=True)
 r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace')
 p.joinpath(sku+'.salida.txt').write_text(r.stdout,encoding='utf8')
 print(r.stdout,flush=True);fallos+=bool(r.returncode)
sys.exit(bool(fallos))
