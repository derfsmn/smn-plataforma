"""Consultar a la base de Vidanat: respuesta con citas verificadas solo entre lo que la persona puede ver.

- Solo se contesta con fuentes REVISADAS; las pendientes que hablan del tema se mencionan como «no usadas».
- Si no hay respaldo, o la IA no cita, la respuesta es «evidencia insuficiente».
- Sin Ollama, se muestran las secciones encontradas sin redactar.
- La consulta guardada hereda la clasificación más alta de sus citas.
"""
import json
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from ia import puerta
from modulos.innovacion import ia_local, indice
from modulos.innovacion.acceso import Acceso
from modulos.innovacion.modelos import Consulta

ORDEN_CLASE = {"general": 0, "restringido": 1, "formula": 2}


@dataclass
class Cita:
    numero: int
    fragmento_id: int
    recurso_id: int
    version_id: int
    version: int
    titulo: str
    tipo: str
    seccion: str | None
    pagina: int | None
    extracto: str
    clasificacion: str


@dataclass
class Respuesta:
    consulta_id: int
    texto: str
    insuficiente: bool
    modo: str  # ia / palabras
    citas: list[Cita] = field(default_factory=list)
    no_usadas: list[dict] = field(default_factory=list)  # fuentes pendientes de revisión que hablan del tema
    aviso: str | None = None
    duracion_ms: int = 0


def _cita(n: int, h) -> Cita:
    e = h.entrada
    return Cita(n, e.fragmento_id, e.recurso_id, e.version_id, e.numero, e.titulo, e.tipo, e.seccion, e.pagina,
                e.texto[:700], e.clasificacion)


def responder(bd: Session, acc: Acceso, pregunta: str, *, expediente_id: int | None = None, usar_ia: bool = True) -> Respuesta:
    inicio = time.monotonic()
    base = indice.Filtros(expediente_id=expediente_id)
    revisadas, _ = indice.buscar(bd, acc, pregunta, indice.Filtros(expediente_id=expediente_id, solo_revisadas=True), limite=6)
    todas, _ = indice.buscar(bd, acc, pregunta, base, limite=12, con_significado=False)
    ids_rev = {h.entrada.version_id for h in revisadas}
    no_usadas = []
    for h in todas:
        e = h.entrada
        if e.estado == "pendiente" and e.version_id not in ids_rev and e.recurso_id not in {x["recurso_id"] for x in no_usadas} \
                and h.cubre >= indice.CUBRE_MINIMO:
            no_usadas.append({"recurso_id": e.recurso_id, "titulo": e.titulo, "version": e.numero})
    respaldo = indice.hay_respaldo(revisadas)
    texto, citas, modo, aviso, insuficiente = "", [], "ia", None, True
    if respaldo and usar_ia and puerta.estado_ollama()["disponible"]:
        try:
            secciones = [f"({h.entrada.titulo} · v{h.entrada.numero}"
                         + (f" · pág. {h.entrada.pagina}" if h.entrada.pagina else "")
                         + (f" · {h.entrada.seccion}" if h.entrada.seccion else "") + f")\n{h.entrada.texto[:1800]}"
                         for h in revisadas]
            bruto = ia_local.responder(bd, pregunta, secciones, acc.usuario_id)
            limpio, usados = ia_local.citas_validas(bruto, len(revisadas))
            if ia_local.NO_ALCANZA not in limpio and usados:
                texto, insuficiente = limpio, False
                citas = [_cita(n, revisadas[n - 1]) for n in usados]
        except puerta.ErrorIA:
            modo, aviso = "palabras", "La IA local no respondió; te muestro las secciones que hablan de eso."
    elif respaldo:
        modo = "palabras"
    if respaldo and modo == "palabras":
        insuficiente = False
        citas = [_cita(n, h) for n, h in enumerate(revisadas[:3], start=1)]
        texto = "Estas secciones de fuentes revisadas hablan de eso:"
    if insuficiente:
        texto = ("Evidencia insuficiente: las fuentes revisadas que puedes ver no alcanzan para contestar."
                 + (" Hay fuentes pendientes de revisión que hablan del tema; no se usaron." if no_usadas else "")
                 + " Puedes lanzar una investigación en internet o cargar una fuente.")
        citas = []
    clasificacion = max((c.clasificacion for c in citas), key=lambda x: ORDEN_CLASE.get(x, 0), default="general")
    duracion = int((time.monotonic() - inicio) * 1000)
    c = Consulta(usuario_id=acc.usuario_id, expediente_id=expediente_id, pregunta=pregunta[:1000], respuesta=texto,
                 citas=json.dumps([asdict(x) for x in citas], ensure_ascii=False) if citas else None,
                 insuficiente=insuficiente, clasificacion=clasificacion, duracion_ms=duracion)
    bd.add(c)
    bd.commit()
    return Respuesta(c.consulta_id, texto, insuficiente, modo, citas, no_usadas[:5], aviso, duracion)
