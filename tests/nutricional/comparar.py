"""Comparación reproducible; solo modelos instalados, solicitudes secuenciales."""
import subprocess
import sys
from pathlib import Path
p=Path(__file__).parent
for nombre,extras in [
 ('texto',['--modelo','qwen3-vl:8b']),
 ('original',['--modelo','qwen3-vl:8b','--imagen',str(p/'55527.jpg')]),
 ('reducida-4096',['--modelo','qwen3-vl:8b','--imagen',str(p/'55527.jpg'),'--max-lado','1280']),
 ('reducida-16384',['--modelo','qwen3-vl:8b','--imagen',str(p/'55527.jpg'),'--max-lado','1280','--contexto','16384']),
 ('reducida-16384-json',['--modelo','qwen3-vl:8b','--imagen',str(p/'55527.jpg'),'--max-lado','1280','--contexto','16384','--formato','json']),
 ('instruct',['--modelo','qwen3-vl:4b-instruct','--imagen',str(p/'55527.jpg'),'--max-lado','1280','--contexto','16384','--formato','json']),
]:
 subprocess.run([sys.executable,str(p/'sonda_ollama.py'),*extras,'--salida',str(p/f'sonda-{nombre}.json')],check=True)
