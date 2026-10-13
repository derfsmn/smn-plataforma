"""API de SMN - Transformación digital.

Núcleo (cascarón) + puerta de IA + módulos. Ver AGENTS.md, sección 4.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import configuracion
from nucleo import salud

app = FastAPI(title="SMN - Transformación digital", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion().origenes,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(salud.router)
# Los módulos (api/modulos/<nombre>) se registran aquí cuando existan.
