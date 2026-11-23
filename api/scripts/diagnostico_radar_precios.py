"""Diagnóstico del Radar de precios en producción (2026-11-23). SOLO LEE: no cambia nada ni llama a DataForSEO.

Diego: «es muy lenta la carga de los datos y aparte de forma masiva veo ya muchos errores».
1) Mide cuánto tarda cada paso de la pantalla Resumen (lo que hace la API en cada clic).
2) Cuenta y lista los precios y productos sospechosos para revisarlos con datos reales.

    docker exec -it <api> python -m scripts.diagnostico_radar_precios
Deja /tmp/diagnostico_radar_precios.json dentro del contenedor.
"""
import json
import time
from collections import Counter
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.bd import _fabrica
from core.config import configuracion
from modulos.compras import evaluacion_precios as ev
from modulos.compras import nocturno_precios as noche
from modulos.compras import precios
from modulos.compras import tablero_precios as tb
from modulos.compras.modelos_precios import (PrecioCorrida, PrecioCorridaProducto, PrecioMarcaMal, PrecioObservacion,
                                             PrecioValidacion, PrecioVigilado)

SALIDA = "/tmp/diagnostico_radar_precios.json"


def reloj():
    t = time.perf_counter()
    return lambda: round(time.perf_counter() - t, 2)


def num(v):
    return float(v) if isinstance(v, Decimal) else v


def main() -> None:
    d: dict = {"tiempos_seg": {}, "conteos": {}}
    t = d["tiempos_seg"]
    cfg = configuracion()
    d["ajustes"] = {k: getattr(cfg, k, None) for k in (
        "precios_validar", "precios_nocturno_activo", "precios_nocturno_catalogo", "precios_nocturno_lote",
        "precios_alerta_pct", "precios_comparar_imagenes", "precios_max_publicaciones", "precios_buscar_siempre")}
    with _fabrica()() as bd:
        bd: Session
        # ---------------------------------------------------------------- tiempos (lo que hace /tablero)
        r = reloj(); a = noche.avance(bd); t["avance_de_la_noche"] = r()
        r = reloj(); productos = tb.universo(bd); t["universo"] = r()
        r = reloj(); filas = tb.ultimas_filas(bd); t["ultimas_filas"] = r()
        con = [p for p in productos if p.producto_id in filas]
        por_id = {p.producto_id: p for p in con}
        r = reloj(); obs = tb.precios_que_cuentan(bd, {k: v for k, v in filas.items() if k in por_id}, por_id)
        t["precios_con_validacion"] = r()
        skus = [p.sku for p in con]
        r = reloj(); ev.ventas(bd, skus); t["evaluador_ventas"] = r()
        r = reloj(); ev.costos(bd, skus); t["evaluador_costos"] = r()
        r = reloj(); ev.tendencias(bd, list(por_id)); t["evaluador_tendencias"] = r()
        r = reloj(); rs = tb.renglones(bd, con); t["renglones_completos"] = r()
        r = reloj(); tb.contra_tiendas(rs); t["contra_tiendas"] = r()
        try:
            from modulos.compras.rutas_tablero_precios import tablero
            r = reloj(); tablero(grupo="accion", clase="", q="", marca="", pagina=1, por_pagina=25, precio="lista", _=None, bd=bd)
            t["pantalla_resumen_completa"] = r()
        except Exception as e:  # noqa: BLE001
            t["pantalla_resumen_completa"] = f"error: {e.__class__.__name__}: {e}"
        c = d["conteos"]
        c.update(universo=len(productos), con_resultado=len(con), observaciones_leidas=sum(len(v) for v in obs.values()),
                 avance={"total": a.total, "validados": a.validados, "dudosos": a.dudosos,
                         "sin_referencia": a.sin_referencia, "sin_revisar": a.sin_revisar, "ritmo_noche": a.ritmo_noche})
        c["tamano_tablas"] = {n: bd.scalar(select(func.count()).select_from(m)) for n, m in (
            ("precio_observacion", PrecioObservacion), ("precio_validacion", PrecioValidacion),
            ("precio_corrida_producto", PrecioCorridaProducto), ("precio_corrida", PrecioCorrida),
            ("precio_vigilado", PrecioVigilado), ("precio_marca_mal", PrecioMarcaMal))}

        # ---------------------------------------------------------------- calidad
        estados = Counter((f.estado, (f.mensaje or "")[:90]) for f, _ in filas.values())
        c["renglon_estado_mensaje_top"] = [{"estado": e, "mensaje": m, "n": n} for (e, m), n in estados.most_common(25)]
        c["validacion_resultado"] = dict(Counter((v.resultado if v else "sin_validacion") for x in obs.values() for _, v in x))
        motivos = Counter(((v.resultado, (v.motivo or "")[:90]) for x in obs.values() for _, v in x if v and v.resultado != "validado"))
        c["motivos_no_cuenta_top"] = [{"resultado": r_, "motivo": m, "n": n} for (r_, m), n in motivos.most_common(25)]
        c["marcas_esta_mal"] = dict(Counter(m.motivo for m in bd.scalars(select(PrecioMarcaMal))))
        cuentan = Counter()
        sospechosos = []
        for x in rs:
            n_cuentan = len(x.tiendas) + len(x.otras)
            cuentan[min(n_cuentan, 5)] += 1
            if x.dif is not None and abs(x.dif) >= 35:
                sospechosos.append({
                    "sku": x.producto.sku, "producto": x.producto.descripcion, "marca": x.producto.marca,
                    "clase": x.evaluacion.clase, "nuestro": num(x.base), "membresia": num(x.membresia),
                    "mediana": num(x.fila.mediana), "dif_pct": num(x.dif), "precios_que_cuentan": n_cuentan,
                    "tiendas": {k: num(v[0]) for k, v in x.tiendas.items()},
                    "otras": [(o[0], num(o[1])) for o in x.otras[:6]], "corrida": x.fila.corrida_id,
                    "accion": x.evaluacion.accion_texto})
        c["productos_por_precios_que_cuentan"] = {("5 o más" if k == 5 else str(k)): v for k, v in sorted(cuentan.items())}
        c["color"] = dict(Counter(x.cuadro for x in rs))
        c["accion"] = dict(Counter(x.evaluacion.accion for x in rs))
        sospechosos.sort(key=lambda s: -abs(s["dif_pct"]))
        d["sospechosos_mas_de_35pct"] = {"total": len(sospechosos), "primeros_80": sospechosos[:80]}
        # Corridas de los últimos 7 días: duración y errores
        q = select(PrecioCorrida).order_by(PrecioCorrida.corrida_id.desc()).limit(120)
        d["corridas_recientes"] = [{
            "id": k.corrida_id, "origen": k.origen, "estado": k.estado, "productos": k.productos,
            "inicio": k.iniciado_en.isoformat() if k.iniciado_en else None,
            "min": round((k.terminado_en - k.iniciado_en).total_seconds() / 60, 1) if k.terminado_en and k.iniciado_en else None,
            "usd": num(k.costo_usd), "error": (k.error or "")[:200] or None} for k in bd.scalars(q)]
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({"tiempos_seg": d["tiempos_seg"], "conteos": {k: d["conteos"][k] for k in (
        "universo", "con_resultado", "observaciones_leidas", "color", "productos_por_precios_que_cuentan")},
        "sospechosos": d["sospechosos_mas_de_35pct"]["total"]}, ensure_ascii=False, indent=1, default=str))
    print(f"\nListo: {SALIDA}")


if __name__ == "__main__":
    main()
