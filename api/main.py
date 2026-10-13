"""API de SMN - Transformación digital.

Núcleo (cascarón) + puerta de IA + módulos. Ver AGENTS.md, sección 4.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import configuracion
from nucleo import administracion, autenticacion, salud

app = FastAPI(title="SMN - Transformación digital", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion().origenes,
    # En desarrollo se acepta la web en el puerto 3000 desde cualquier dirección
    # (localhost, 127.0.0.1 o la IP del equipo para probar desde el celular)
    allow_origin_regex=r"https?://[^/]+:3000" if configuracion().es_desarrollo else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salud.router)
app.include_router(autenticacion.router)
app.include_router(administracion.router)
# Los módulos (api/modulos/<nombre>) se registran aquí cuando existan.
