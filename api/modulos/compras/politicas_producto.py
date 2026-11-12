"""Revisión de un producto nuevo contra la Base de conocimiento de Compras (pedido de Diego, 2026-10-26: «que se cruce
con las políticas de compras»).

La IA lee las políticas vigentes y las reglas activas de rechazo y de umbral que aplican al departamento, y dice cuáles
cumple el producto, cuáles no y para cuáles faltan datos, citando el dato. Si el producto cae en una regla de rechazo,
el semáforo queda en rojo con ese motivo. También junta los casos que Compras ya decidió y se parecen al producto.

La IA solo puede citar reglas y políticas que existen: un id que no viene en la lista se descarta. Sin IA no se decide
nada: se listan las que aplican como «sin revisar».

Desde el 11 nov 2026 (aprobado por Diego) un rechazo directo pide pruebas: la IA debe copiar el dato del producto que
lo hace caer, ese dato debe estar de verdad en los datos del producto, y si la regla habla de un tipo de producto
(suplemento, cosmético, alimento…) el producto debe ser de ese tipo. Si falta algo, queda como aviso para Compras y
no cambia el color (antes un shaker caía en una regla de suplementos).
"""
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from ia import puerta
from modulos.compras.modelos_conocimiento import ConocimientoCaso, ConocimientoPolitica, ConocimientoRegla

log = logging.getLogger("smn.compras.politicas_producto")

TAREA_IA = "compras.productos_politicas"
MAX_CASOS = 5
MIN_SIMILITUD_CASO = 0.2
MAX_TEXTO_POLITICA = 3000
RESULTADOS = ("cumple", "no_cumple", "sin_datos")
# Con todo el consolidado vigente (40+ políticas) la respuesta es larga, y en OpenAI el razonamiento cuenta dentro de
# este tope: con 1,500 se cortaba y todo quedaba «sin revisar».
MAX_TOKENS = 8000

INSTRUCCIONES = """Eres analista de Compras de una cadena de tiendas naturistas en México.
Te doy un producto nuevo con los datos que tenemos y las reglas y políticas de Compras que aplican a su departamento.
Revisa el producto SOLO con esos datos. No inventes datos ni supongas lo que no viene.
Para cada regla y cada política que tenga que ver con el producto, di:
- "cumple": los datos muestran que la cumple;
- "no_cumple": los datos muestran que no la cumple. En una regla de tipo "rechazo", "no_cumple" quiere decir que el
  producto CAE en ese rechazo;
- "sin_datos": la regla aplica pero falta el dato para saberlo (di cuál falta).
Omite las políticas que no tengan nada que ver con este producto. El motivo es una línea corta en español (máximo 25
palabras) que cita el dato.
Cuidado con el tipo de producto: una regla de suplementos no aplica a un accesorio (un shaker, una cinta, un vaso), ni
una de alimentos a un cosmético. Si la regla habla de otro tipo de producto, omítela.
Para una regla de tipo "rechazo" con "no_cumple" es obligatorio "dato": copia TAL CUAL, letra por letra, el valor del
producto que lo hace caer (por ejemplo el nombre, el precio o el ingrediente). Sin ese dato no es rechazo.
Contesta solo JSON: {"hallazgos": [{"id": "R3", "resultado": "no_cumple", "motivo": "...", "dato": "..."}]}"""


# Tipos de producto que una regla puede nombrar: si la regla nombra uno, el producto debe ser de ese tipo
TIPOS = {
    "suplemento": ("suplement", "capsul", "tableta", "vitamin", "proteina", "colageno", "creatina", "probiotic",
                   "omega", "magnesio", "electrolit", "enzima"),
    "cosmetico": ("cosmet", "shampoo", "crema", "jabon", "locion", "gel", "desodorante", "body", "facial", "corporal"),
    "alimento": ("aliment", "harina", "chips", "botana", "bebida", "galleta", "pan", "especia", "cereal", "proteina"),
    "medicamento": ("medicament", "farmac"),
    "herbolaria": ("herbolari", "hierba", "planta", "te ", "infusion"),
    "bebida": ("bebida", "agua", "refresco", "jugo", "kombucha"),
}
_RAIZ_TIPO = {"suplemento": "suplement", "cosmetico": "cosmet", "alimento": "aliment", "medicamento": "medicament",
              "herbolaria": "herbolari", "bebida": "bebida"}


def _norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)))


def _texto_producto(datos: dict) -> str:
    return " " + _norm(" ".join(str(datos.get(k) or "") for k in (
        "nombre", "descripcion", "ingrediente", "forma", "departamento", "subcategoria", "tipo"))) + " "


def tipo_que_no_es(regla: dict, datos: dict) -> str | None:
    """Si la regla habla de un tipo de producto (suplemento, cosmético…) y nada del producto dice que sea de ese tipo,
    regresa el tipo. «Rechazar suplementos sin registro» no aplica a un shaker."""
    texto_regla = _norm(f"{regla.get('titulo')} {regla.get('descripcion') or ''}")
    producto = _texto_producto(datos)
    for tipo, raiz in _RAIZ_TIPO.items():
        if raiz in texto_regla and not any(x in producto for x in TIPOS[tipo]):
            return tipo
    return None


def dato_comprobado(dato, datos: dict) -> bool:
    """El dato que citó la IA está de verdad en los datos del producto (sin acentos ni mayúsculas)."""
    d = _norm(dato).strip(" .\"'«»")
    if len(d) < 2:
        return False
    plano = _norm(json.dumps(datos, ensure_ascii=False, default=str))
    if d in plano:
        return True
    numeros = re.findall(r"\d+(?:[.,]\d+)?", d)  # «$1,500» contra 1500.00
    return bool(numeros) and all(n.replace(",", "") in plano.replace(",", "") for n in numeros)


@dataclass
class Revision:
    hallazgos: list[dict] = field(default_factory=list)  # {id, tipo, titulo, resultado, motivo}
    rechazo: dict | None = None  # el hallazgo de la regla de rechazo en la que cae
    avisos: list[dict] = field(default_factory=list)  # rechazos que la IA dijo sin probarlos: no cambian el color
    casos: list[dict] = field(default_factory=list)  # {caso_id, producto, decision, motivo, resultado, fecha, similitud}
    notas: list[str] = field(default_factory=list)
    revisada_ia: bool = False

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def de_json(cls, texto: str | None) -> "Revision | None":
        return cls(**json.loads(texto)) if texto else None


def _del_departamento(columna, departamento: str | None):
    return or_(columna.is_(None), columna == "", columna == departamento) if departamento else or_(columna.is_(None), columna == "")


def aplicables(bd: Session, departamento: str | None) -> tuple[list[ConocimientoRegla], list[ConocimientoPolitica]]:
    reglas = bd.scalars(select(ConocimientoRegla).where(
        ConocimientoRegla.activa == true(), ConocimientoRegla.tipo.in_(("rechazo", "umbral")),
        _del_departamento(ConocimientoRegla.departamento, departamento)).order_by(ConocimientoRegla.regla_id)).all()
    politicas = bd.scalars(select(ConocimientoPolitica).where(
        ConocimientoPolitica.estado == "vigente", _del_departamento(ConocimientoPolitica.departamento, departamento))
        .order_by(ConocimientoPolitica.politica_id)).all()
    return list(reglas), list(politicas)


def casos_parecidos(bd: Session, texto: set[str], departamento: str | None) -> list[dict]:
    """Productos que Compras ya decidió, por palabras en común con el producto nuevo."""
    from modulos.compras.radar_productos import palabras

    salida = []
    for c in bd.scalars(select(ConocimientoCaso)).all():
        suyas = palabras(c.producto)
        if not suyas or not texto:
            continue
        sim = len(suyas & texto) / len(suyas | texto) + (0.1 if departamento and c.departamento == departamento else 0)
        if sim >= MIN_SIMILITUD_CASO:
            salida.append({"caso_id": c.caso_id, "producto": c.producto, "decision": c.decision, "motivo": c.motivo,
                           "resultado": c.resultado, "fecha": c.fecha_decision.isoformat() if c.fecha_decision else None,
                           "similitud": round(min(sim, 1.0), 2)})
    return sorted(salida, key=lambda x: -x["similitud"])[:MAX_CASOS]


def _numero(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _lista(reglas: list[ConocimientoRegla], politicas: list[ConocimientoPolitica]) -> dict[str, dict]:
    salida = {}
    for r in reglas:
        salida[f"R{r.regla_id}"] = {"tipo": r.tipo, "titulo": r.criterio, "minimo": _numero(r.minimo),
                                    "maximo": _numero(r.maximo), "unidad": r.unidad, "descripcion": r.descripcion}
    for p in politicas:
        salida[f"P{p.politica_id}"] = {"tipo": "politica", "titulo": p.titulo, "tema": p.tema,
                                       "contenido": (p.contenido or "")[:MAX_TEXTO_POLITICA]}
    return salida


def revisar(bd: Session, departamento: str | None, texto: set[str], datos: dict) -> Revision:
    """datos: lo que sabemos del producto (nombre, marca, precio, margen, factores…). Nunca lanza."""
    rev = Revision(casos=casos_parecidos(bd, texto, departamento))
    reglas, politicas = aplicables(bd, departamento)
    if not reglas and not politicas:
        rev.notas.append("Compras todavía no tiene políticas vigentes ni reglas de rechazo o umbral para este "
                         "departamento en la Base de conocimiento.")
        return rev
    lista = _lista(reglas, politicas)
    mensaje = json.dumps({"producto": datos, "reglas_y_politicas": [{"id": k, **v} for k, v in lista.items()],
                          "casos_parecidos_que_ya_decidio_compras": rev.casos}, ensure_ascii=False, default=str)
    r = None
    try:
        r = puerta.ejecutar(bd, TAREA_IA, usuario_id=None, instrucciones=INSTRUCCIONES, mensaje=mensaje,
                            max_tokens=MAX_TOKENS, esfuerzo="medium",
                            contexto=puerta.ventana(INSTRUCCIONES, mensaje, salida=MAX_TOKENS))
        respuesta = json.loads(r.texto[r.texto.find("{"):r.texto.rfind("}") + 1])
        for h in respuesta.get("hallazgos") or []:
            ident = str(h.get("id") or "").strip().upper()
            if ident not in lista or h.get("resultado") not in RESULTADOS:
                continue  # la IA no puede citar lo que no existe
            hallazgo = {"id": ident, "tipo": lista[ident]["tipo"], "titulo": lista[ident]["titulo"],
                        "resultado": h["resultado"], "motivo": str(h.get("motivo") or "")[:500]}
            if hallazgo["tipo"] == "rechazo" and hallazgo["resultado"] == "no_cumple":
                if tipo_que_no_es(lista[ident], datos):
                    continue  # la regla es de otro tipo de producto: no tiene que ver con este
                if not dato_comprobado(h.get("dato"), datos):
                    hallazgo["sin_prueba"] = True
                    hallazgo["motivo"] = ("Posible, sin un dato del producto que lo pruebe; que Compras lo confirme. "
                                          + hallazgo["motivo"])[:500]
                    rev.avisos.append(hallazgo)
                else:
                    hallazgo["dato"] = str(h.get("dato"))[:200]
            rev.hallazgos.append(hallazgo)
        rev.revisada_ia = True
    except (puerta.ErrorIA, ValueError, TypeError, AttributeError) as e:
        log.info("Radar de productos: la IA no revisó las políticas de «%s»: %s", datos.get("nombre"), e)
        if isinstance(e, puerta.ErrorIA):
            causa = str(e)
        elif r is not None and not getattr(r, "completa", True):
            causa = "su respuesta se cortó por largo"
        else:
            causa = "su respuesta no se pudo leer"
        rev.notas.append(f"La IA no pudo revisar las políticas ({causa.rstrip('.')}); aquí están las que aplican, "
                         "sin revisar. Recalcula para intentarlo de nuevo.")
        rev.hallazgos = [{"id": k, "tipo": v["tipo"], "titulo": v["titulo"], "resultado": "sin_revisar", "motivo": ""}
                         for k, v in lista.items()]
        return rev
    citadas = {h["id"] for h in rev.hallazgos}
    if omitidas := len(lista) - len(citadas):
        rev.notas.append(f"La IA consideró que {omitidas} regla(s) o política(s) no tienen que ver con este producto.")
    rev.rechazo = next((h for h in rev.hallazgos if h["tipo"] == "rechazo" and h["resultado"] == "no_cumple"
                        and not h.get("sin_prueba")), None)
    return rev
