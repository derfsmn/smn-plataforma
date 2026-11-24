"""Revisa fichas de inferencias reales guardadas; Ollama solo prioriza hallazgos."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf8')
p = Path(__file__).parent
for sku in ('55527','55541','77755'):
    origen = p / (sku+'.json')
    huella = hashlib.sha256(origen.read_bytes()).hexdigest()
    destino = p / ('revision_'+sku+'.json')
    cmd = [sys.executable,'prueba_nutricional.py','--ficha',str(origen),'--salida',str(destino),'--modelo-revision','qwen3:8b']
    # Categoría confirmada por el usuario; no se proporcionan población ni finalidad.
    if sku=='55527':cmd.extend(['--categoria','suplemento'])
    print(subprocess.list2cmdline(cmd),flush=True)
    r = subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8')
    destino.with_suffix('.salida.txt').write_text(r.stdout,encoding='utf8')
    if r.returncode:
        print(r.stdout);raise SystemExit(r.returncode)
    assert huella == hashlib.sha256(origen.read_bytes()).hexdigest(), 'La ficha original cambió'
    revision = json.loads(destino.read_text(encoding='utf8'))['revision_nutrimental']
    print(sku,revision['estado_general'],json.dumps(revision['ia'],ensure_ascii=False),flush=True)
