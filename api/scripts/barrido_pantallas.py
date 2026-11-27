"""Barrido de las pantallas de los dos radares, solo lectura (revisión del 26 nov 2026).

Llama, desde dentro de la API, cada ruta que usan las pantallas del radar de productos y del radar de precios, para todas
las evaluaciones y corridas de la base, y avisa cualquier respuesta que no sea 200 o que la web no sabría pintar. No
escribe nada, no llama a DataForSEO, tiendas ni a la IA.

Uso (en el servidor, después de publicar):
    docker compose exec api python -m scripts.barrido_pantallas --usuario <id de un administrador>
Opciones: --max N (evaluaciones a revisar, de las más nuevas; 0 = todas), --sin-pdf (no arma los PDF).
"""
import argparse
import sys
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from core import ajustes
from core.bd import _fabrica
from core.seguridad import Contexto, permisos_de, usuario_actual
from main import app
from modulos.compras.modelos_precios import PrecioCorrida
from modulos.compras.modelos_productos import ProductoEvaluacion
from nucleo.modelos import Usuario

R_PROD = "/api/compras/productos"
R_PRECIOS = "/api/compras/precios"
FUENTES_CONOCIDAS = {"google", "sitio", "web", "google_sitio", "mercadolibre", "amazon"}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--usuario", type=int, required=True)
    a.add_argument("--max", type=int, default=0)
    a.add_argument("--sin-pdf", action="store_true")
    args = a.parse_args()

    with _fabrica()() as bd:
        ajustes.aplicar(bd)
        u = bd.get(Usuario, args.usuario)
        if u is None:
            print(f"No existe el usuario {args.usuario}.")
            return 2
        bd.expunge(u)
        ctx = Contexto(usuario=u, permisos=permisos_de(bd, args.usuario))
        q = select(ProductoEvaluacion.evaluacion_id).where(ProductoEvaluacion.estado == "lista") \
            .order_by(ProductoEvaluacion.evaluacion_id.desc())
        evaluaciones = list(bd.scalars(q.limit(args.max) if args.max else q))
        corridas = list(bd.scalars(select(PrecioCorrida.corrida_id).where(PrecioCorrida.origen == "pedido")
                                   .order_by(PrecioCorrida.corrida_id.desc()).limit(30)))
    app.dependency_overrides[usuario_actual] = lambda: ctx
    c = TestClient(app, raise_server_exceptions=False)
    fallas: list[str] = []
    revisadas = 0

    def pedir(ruta: str, tipo: str = "json", **kw):
        nonlocal revisadas
        revisadas += 1
        r = c.get(ruta, **kw)
        if r.status_code != 200:
            fallas.append(f"{r.status_code} {ruta}: {r.text[:200]}")
            return None
        if tipo == "pdf" and not r.content.startswith(b"%PDF"):
            fallas.append(f"no es PDF: {ruta}")
        if tipo == "xlsx" and not r.content.startswith(b"PK"):
            fallas.append(f"no es Excel: {ruta}")
        return r.json() if tipo == "json" else r.content

    inicio = time.monotonic()
    # Radar de productos
    lista = pedir(f"{R_PROD}/evaluaciones") or []
    for f in lista:
        if not f.get("sujeto", {}).get("nombre"):
            fallas.append(f"lista: evaluación {f.get('id')} sin nombre")
    for i in evaluaciones:
        d = pedir(f"{R_PROD}/evaluaciones/{i}")
        if d:
            for p in (d.get("mercado") or {}).get("precios", []):
                if p.get("fuente") not in FUENTES_CONOCIDAS:
                    fallas.append(f"evaluación {i}: fuente de precio desconocida «{p.get('fuente')}»")
                if p.get("precio") in (None, ""):
                    fallas.append(f"evaluación {i}: precio vacío de {p.get('vendedor')}")
        p = pedir(f"{R_PROD}/evaluaciones/{i}/pantalla")
        if p:
            for clave in ("producto", "puntaje", "color", "factores", "cifras", "precio"):
                if clave not in p:
                    fallas.append(f"pantalla {i}: falta «{clave}»")
            if p.get("color") not in ("verde", "amarillo", "rojo", None):
                fallas.append(f"pantalla {i}: color «{p.get('color')}»")
        if not args.sin_pdf:
            pedir(f"{R_PROD}/evaluaciones/{i}/reporte", "pdf")
    # Radar de precios
    pedir(f"{R_PRECIOS}/tablero/dia")
    t = pedir(f"{R_PRECIOS}/tablero", params={"grupo": "todos", "por_pagina": 200}) or {}
    for f in t.get("filas", []):
        pedir(f"{R_PRECIOS}/tablero/producto/{f['producto_id']}")
        pedir(f"{R_PRECIOS}/productos/{f['producto_id']}/validacion")
        if f.get("color") not in ("verde", "amarillo", "rojo", None):
            fallas.append(f"tablero {f['sku']}: color «{f.get('color')}»")
    pedir(f"{R_PRECIOS}/tablero/excel", "xlsx")
    pedir(f"{R_PRECIOS}/pedidos", params={"todas": "true"})
    for cid in corridas:
        pedir(f"{R_PRECIOS}/pedidos/{cid}")
        pedir(f"{R_PRECIOS}/pedidos/{cid}/excel", "xlsx")

    print(f"Rutas revisadas: {revisadas} · evaluaciones: {len(evaluaciones)} · productos del tablero: "
          f"{len(t.get('filas', []))} · corridas: {len(corridas)} · {time.monotonic() - inicio:.0f} s")
    if fallas:
        print(f"FALLAS ({len(fallas)}):")
        for x in fallas[:100]:
            print("  -", x)
        return 1
    print("Sin fallas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
