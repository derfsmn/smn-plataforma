"""Reporte de proveedores para Compras en Excel (Diego, 2026-11-04; plan https://claude.ai/artifact/5RKK4iMitXSEBhuLJM1xNG).

Entran los proveedores de tblProveedores en estatus ALTA y con agente, con la última calificación ya calculada en
Datos → Proveedores (no se recalcula). Sin RFC y en una sola hoja con filtro por agente (respuestas de Diego en el plan).
Los que no tienen calificación salen al final de su agente como «Sin datos», con el motivo.
"""
import io
import json
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datos import proveedores as pv
from datos.modelos import Carga, Proveedor, ProveedorCalificacion, ProveedorEvaluacion

FUENTES = ("SMNBI_PROVEEDORES", "SMNBI_COMPRAS", "SMNBI_ARTICULOS", "SMNBI_COSTOS", "SMNBI_INVENTARIO", "ETL_VENTAS")
NOMBRE_FUENTE = {"SMNBI_PROVEEDORES": "proveedores", "SMNBI_COMPRAS": "compras", "SMNBI_ARTICULOS": "artículos",
                 "SMNBI_COSTOS": "costos", "SMNBI_INVENTARIO": "inventario", "ETL_VENTAS": "venta"}
COLOR = {"verde": "Verde", "amarillo": "Amarillo", "rojo": "Rojo"}
RELLENO = {"verde": "C6EFCE", "amarillo": "FFEB9C", "rojo": "FFC7CE"}
CONFIANZA = {"alta": "Alta", "media": "Media", "baja": "Baja", "sin_datos": "Sin datos"}

# (encabezado, ancho, formato)
COLUMNAS = [
    ("Agente", 10, None), ("Clave", 10, None), ("Proveedor", 38, None), ("Puntaje (0-100)", 10, "0"),
    ("Semáforo", 11, None), ("Confianza", 11, None), ("Motivo sin calificación", 40, None),
    ("Cumplimiento (0-100)", 13, "0"), ("Comercial (0-100)", 12, "0"), ("Costo y condiciones (0-100)", 13, "0"),
    ("Inventario (0-100)", 12, "0"),
    ("Órdenes 12 meses", 10, "0"), ("Surtido %", 10, "0.0"), ("Días hábiles a la primera entrada", 13, "0.0"),
    ("Días de entrega prometidos", 12, "0"), ("Retraso (días hábiles)", 11, "0.0"), ("Perdido o rechazado %", 11, "0.0"),
    ("SKU activos", 9, "0"), ("Venta 26 semanas sin IVA ($)", 15, "#,##0"), ("Margen real %", 10, "0.0"),
    ("SKU con buena rotación %", 11, "0.0"), ("SKU debajo de la permanencia", 12, "0"),
    ("Alza de costo vs. promedio 12 meses %", 13, "0.0"), ("Condición de pago", 16, None), ("Días de crédito", 9, "0"),
    ("Existencia (piezas)", 12, "#,##0"), ("Días de inventario", 11, "0"), ("SKU con más de 180 días", 11, "0"),
    ("Compra 12 meses ($)", 15, "#,##0"),
]


def en_alta_con_agente(bd: Session, agente: str = "") -> list[Proveedor]:
    """Estatus ALTA (sin importar mayúsculas ni espacios) y agente con valor; si se pide, solo los de ese agente."""
    q = select(Proveedor).where(func.upper(func.ltrim(func.rtrim(Proveedor.estatus))) == "ALTA",
                                Proveedor.agente.is_not(None), func.ltrim(func.rtrim(Proveedor.agente)) != "")
    filas = [p for p in bd.scalars(q)]
    if agente:
        filas = [p for p in filas if p.agente.strip() == agente.strip()]
    return filas


def desactualizada(bd: Session, ev: ProveedorEvaluacion | None) -> str | None:
    """Qué datos se cargaron después de la evaluación (entonces conviene pulsar «Calcular» antes de bajar)."""
    if not ev:
        return None
    desde = ev.terminada_en or ev.iniciada_en
    nuevas = sorted({NOMBRE_FUENTE[f] for (f,) in bd.execute(
        select(Carga.fuente).where(Carga.fuente.in_(FUENTES), Carga.estado == "completa", Carga.fin_en > desde))})
    return ", ".join(nuevas) or None


def _motivo(met: dict, c: ProveedorCalificacion | None) -> str | None:
    if c is None:
        return "No está en la última evaluación: se cargó después de calcular."
    if c.puntaje is not None:
        return None
    return " ".join(met.get("notas") or []) or "Sin órdenes, venta ni inventario en las ventanas de la evaluación."


def _renglon(p: Proveedor, c: ProveedorCalificacion | None) -> list:
    met = json.loads(c.metricas) if c and c.metricas else {}
    cu, co, cs, inv = (met.get(k) or {} for k in ("cumplimiento", "comercial", "costo", "inventario"))
    return [
        p.agente.strip(), p.proveedor.strip(), (c.nombre if c else None) or p.nombre or f"Proveedor {p.proveedor.strip()}",
        c.puntaje if c else None, COLOR.get(c.color, "Sin datos") if c else "Sin datos",
        CONFIANZA.get(c.confianza, c.confianza) if c else "Sin datos", _motivo(met, c),
        c.cumplimiento if c else None, c.comercial if c else None, c.costo if c else None, c.inventario if c else None,
        cu.get("ordenes"), cu.get("surtido_pct"), cu.get("dias_reales"), p.dias_entrega or None, cu.get("retraso_dias"),
        cu.get("perdidas_rechazadas_pct"),
        c.skus_activos if c else None, float(c.venta) if c and c.venta is not None else None, co.get("margen_pct"),
        co.get("buena_rotacion_pct"), co.get("debajo_permanencia"),
        cs.get("alza_costo_pct"), p.condicion, cs.get("dias_credito", pv.dias_credito(p.condicion)),
        inv.get("existencia"), inv.get("dias"), inv.get("skus_exceso"),
        float(c.compra) if c and c.compra is not None else None,
    ]


def _encabezado(ws, encabezados: list[tuple[str, int, str | None]]) -> None:
    for k, (texto, ancho, _) in enumerate(encabezados, start=1):
        celda = ws.cell(row=1, column=k, value=texto)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="222221")
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(k)].width = ancho
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "D2"


def reporte(bd: Session, agente: str = "") -> tuple[bytes, int]:
    """El Excel y cuántos proveedores trae. Falla con ValueError si todavía no hay evaluación."""
    ev = pv.ultima(bd)
    if not ev:
        raise ValueError("Todavía no hay una calificación de proveedores: pulsa «Calcular» primero.")
    proveedores = en_alta_con_agente(bd, agente)
    cal = {c.proveedor.strip(): c for c in bd.scalars(
        select(ProveedorCalificacion).where(ProveedorCalificacion.evaluacion_id == ev.evaluacion_id))}
    datos = [(p, cal.get(p.proveedor.strip())) for p in proveedores]
    datos.sort(key=lambda x: (x[0].agente.strip(), x[1] is None or x[1].puntaje is None,
                              x[1].puntaje if x[1] and x[1].puntaje is not None else 0, x[0].proveedor.strip()))

    wb = Workbook()
    ws = wb.active
    ws.title = "Proveedores"
    _encabezado(ws, COLUMNAS)
    k_color = [c[0] for c in COLUMNAS].index("Semáforo") + 1
    for fila, (p, c) in enumerate(datos, start=2):
        for col, valor in enumerate(_renglon(p, c), start=1):
            celda = ws.cell(row=fila, column=col, value=valor)
            if COLUMNAS[col - 1][2] and valor is not None:
                celda.number_format = COLUMNAS[col - 1][2]
        if c and c.color in RELLENO:
            ws.cell(row=fila, column=k_color).fill = PatternFill("solid", fgColor=RELLENO[c.color])
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{max(2, len(datos) + 1)}"

    # Resumen por agente
    rs = wb.create_sheet("Resumen por agente")
    encabezados = [("Agente", 10, None), ("Proveedores", 12, "0"), ("Verde", 9, "0"), ("Amarillo", 10, "0"),
                   ("Rojo", 9, "0"), ("Sin datos", 10, "0"), ("Puntaje promedio", 11, "0"),
                   ("Venta 26 semanas sin IVA ($)", 16, "#,##0"), ("Compra 12 meses ($)", 16, "#,##0")]
    _encabezado(rs, encabezados)
    rs.freeze_panes = "B2"
    por_agente: dict[str, list] = {}
    for p, c in datos:
        por_agente.setdefault(p.agente.strip(), []).append(c)
    for fila, (ag, cs) in enumerate(sorted(por_agente.items()), start=2):
        puntajes = [c.puntaje for c in cs if c and c.puntaje is not None]
        valores = [ag, len(cs), *(sum(1 for c in cs if c and c.color == k) for k in ("verde", "amarillo", "rojo")),
                   sum(1 for c in cs if not c or not c.color), round(sum(puntajes) / len(puntajes)) if puntajes else None,
                   sum(float(c.venta) for c in cs if c and c.venta is not None),
                   sum(float(c.compra) for c in cs if c and c.compra is not None)]
        for col, valor in enumerate(valores, start=1):
            celda = rs.cell(row=fila, column=col, value=valor)
            if encabezados[col - 1][2] and valor is not None:
                celda.number_format = encabezados[col - 1][2]

    # Cómo se calcula
    cc = wb.create_sheet("Cómo se calcula")
    cc.column_dimensions["A"].width = 34
    cc.column_dimensions["B"].width = 100
    ctx = json.loads(ev.contexto) if ev.contexto else {}
    peso, de_quien = pv.pesos(bd)
    viejo = desactualizada(bd, ev)
    lineas = [
        ("Quién entra", "Proveedores de tblProveedores en estatus ALTA y con agente" + (f" (solo el agente {agente})" if agente else "") + "."),
        ("Evaluación", f"Calculada el {(ev.terminada_en or ev.iniciada_en):%d/%m/%Y %H:%M}. Proveedores en el reporte: {len(datos)}."),
        ("Aviso", f"Después de esta evaluación se volvieron a cargar: {viejo}. Pulsa «Calcular» en Datos → Proveedores para actualizarla." if viejo else "La evaluación está al día con lo cargado."),
        ("Puntaje", "De 0 a 100: suma de los 4 bloques con su peso. Solo cuentan los bloques con datos; la confianza dice qué parte del peso se pudo medir."),
        ("Pesos", f"Cumplimiento {peso['cumplimiento']} · Comercial {peso['comercial']} · Costo y condiciones {peso['costo']} · Inventario {peso['inventario']} ({'de Compras' if de_quien == 'compras' else 'provisionales; Compras los define en la Base de conocimiento'})."),
        ("Semáforo", "Verde, amarillo o rojo según el puntaje; «Sin datos» si no se pudo medir ningún bloque."),
        ("Cumplimiento", "Órdenes de los últimos 12 meses cargados: % de piezas surtidas, días hábiles (lunes a viernes, sin festivos oficiales) de la orden a la primera entrada contra los días de entrega prometidos en Intelisis, y % de piezas perdidas o rechazadas. Se califica con 3 órdenes o más."),
        ("Comercial", "Venta de sus SKU (sin mayoreo): margen real contra el de toda la empresa, % de SKU activos con buena rotación y SKU debajo de la permanencia (metas de la Base de conocimiento)."),
        ("Costo y condiciones", "Costo de la última compra contra el promedio de 12 meses y días de crédito de la condición de pago."),
        ("Inventario", "Días que alcanza su existencia al ritmo de las últimas 13 semanas y SKU con más de 180 días."),
        *((f"Datos: {k}", str(v)) for k, v in ctx.items() if k in ("venta", "compras", "inventario") and v),
        ("Fuente", "SMNBI (Intelisis), cargado en el Centro de datos. Este archivo no incluye RFC."),
        ("Generado", f"{date.today():%d/%m/%Y} desde Datos → Proveedores."),
    ]
    for fila, (a, b) in enumerate(lineas, start=1):
        cc.cell(row=fila, column=1, value=a).font = Font(bold=True)
        cc.cell(row=fila, column=2, value=b).alignment = Alignment(wrap_text=True, vertical="top")

    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue(), len(datos)
