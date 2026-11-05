"""Lista inicial del Radar de tendencias: fuentes y temas de la búsqueda abierta.

Solo se carga si las tablas están vacías; después todo se administra desde la plataforma.
Las fuentes salen del prompt del radar en n8n y de los sitios que revisa Compras. Las ligas RSS se
revisaron el 2026-10-14; las demás se leen con la búsqueda de la IA dentro de su sitio.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modulos.compras.modelos import RadarFuente, RadarTema
from modulos.compras.modelos_precios import PrecioVendedor

# (nombre, liga, tipo, país, idioma, método, lectura, notas)
FUENTES = [
    ("COFEPRIS", "https://www.gob.mx/cofepris", "oficial", "MX", "es", "busqueda", "gob.mx",
     "Sin RSS: se busca dentro de gob.mx"),
    ("Secretaría de Salud", "https://www.gob.mx/salud", "oficial", "MX", "es", "busqueda", "gob.mx",
     "Sin RSS: se busca dentro de gob.mx"),
    ("Diario Oficial de la Federación", "https://www.dof.gob.mx", "oficial", "MX", "es", "busqueda", "dof.gob.mx",
     "Sin RSS: se busca dentro de dof.gob.mx"),
    ("FDA (comunicados)", "https://www.fda.gov", "oficial", "EUA", "en", "rss",
     "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml", None),
    ("FTC (comunicados)", "https://www.ftc.gov", "oficial", "EUA", "en", "rss",
     "https://www.ftc.gov/feeds/press-release.xml", None),
    ("EFSA", "https://www.efsa.europa.eu", "oficial", "UE", "en", "rss", "https://www.efsa.europa.eu/en/all/rss", None),
    ("NutraIngredients", "https://www.nutraingredients.com", "especializada", "global", "en", "rss",
     "https://www.nutraingredients.com/arc/outboundfeeds/rss/", "Incluye las ediciones USA y LATAM"),
    ("FoodNavigator", "https://www.foodnavigator.com", "especializada", "global", "en", "rss",
     "https://www.foodnavigator.com/arc/outboundfeeds/rss/", "Incluye la edición LATAM"),
    ("Natural Products Insider / SupplySide", "https://www.supplysidesj.com", "especializada", "EUA", "en", "rss",
     "https://www.supplysidesj.com/rss.xml", None),
    ("Nutraceuticals World", "https://www.nutraceuticalsworld.com", "especializada", "EUA", "en", "rss",
     "https://www.nutraceuticalsworld.com/feed/", None),
    ("Nutrition Business Journal", "https://www.nutritionbusinessjournal.com", "especializada", "EUA", "en",
     "busqueda", "nutritionbusinessjournal.com", None),
    ("WholeFoods Magazine", "https://wholefoodsmagazine.com", "especializada", "EUA", "en", "busqueda",
     "wholefoodsmagazine.com", None),
    ("Reuters", "https://www.reuters.com", "negocios", "global", "en", "busqueda", "reuters.com", None),
    ("Bloomberg", "https://www.bloomberg.com", "negocios", "global", "en", "busqueda", "bloomberg.com", None),
    ("Forbes", "https://www.forbes.com", "negocios", "global", "en", "busqueda", "forbes.com", None),
    ("CNBC", "https://www.cnbc.com", "negocios", "EUA", "en", "busqueda", "cnbc.com", None),
    ("Innova Market Insights", "https://www.innovamarketinsights.com", "estudios", "global", "en", "busqueda",
     "innovamarketinsights.com", "Solo lo que publican abierto"),
    ("Mintel", "https://www.mintel.com", "estudios", "global", "en", "busqueda", "mintel.com",
     "Solo lo que publican abierto"),
    ("Euromonitor", "https://www.euromonitor.com", "estudios", "global", "en", "busqueda", "euromonitor.com",
     "Solo lo que publican abierto"),
    ("SPINS", "https://www.spins.com", "estudios", "EUA", "en", "busqueda", "spins.com", "Solo lo que publican abierto"),
    ("NIQ", "https://nielseniq.com", "estudios", "global", "en", "busqueda", "nielseniq.com",
     "Solo lo que publican abierto, como NIQ Health and Wellness Consumer Trends 2026"),
]

# (nombre, descripción). Salen de la cobertura del prompt del radar en n8n.
TEMAS = [
    ("Suplementos y naturistas en México",
     "Suplementos, productos naturistas, nuevos lanzamientos, industria nutracéutica, fabricantes y retail naturista en México"),
    ("Regulación en México",
     "COFEPRIS, Secretaría de Salud y DOF sobre suplementos alimenticios, etiquetado, ingredientes restringidos o prohibidos y alertas sanitarias"),
    ("Tendencias de suplementos en EUA",
     "Dietary supplement trends, supplement launches, natural products innovation and nutraceutical market in the United States"),
    ("Ingredientes emergentes",
     "Emerging supplement ingredients: probióticos, postbióticos, adaptógenos, hongos funcionales, creatina, botánicos y superfoods"),
    ("Formatos y presentaciones",
     "Innovación en formatos: gomitas, polvos, sticks, shots, bebidas funcionales, sprays y snacks funcionales"),
    ("Proveedores y fabricantes",
     "Fabricantes, maquila, private label, materias primas, nuevas plantas, adquisiciones y expansión hacia México o Latinoamérica"),
    ("Consumidor y bienestar",
     "Hábitos y preferencias de consumo: healthy aging, sueño, estrés, salud digestiva, salud femenina, belleza desde dentro, energía y control de peso"),
]


def sembrar_radar(bd: Session) -> None:
    if not bd.scalar(select(func.count()).select_from(RadarFuente)):
        for nombre, liga, tipo, pais, idioma, metodo, lectura, notas in FUENTES:
            bd.add(RadarFuente(nombre=nombre, liga=liga, tipo=tipo, pais=pais, idioma=idioma, metodo=metodo,
                               lectura=lectura, notas=notas))
    if not bd.scalar(select(func.count()).select_from(RadarTema)):
        for i, (nombre, descripcion) in enumerate(TEMAS, start=1):
            bd.add(RadarTema(nombre=nombre, descripcion=descripcion, orden=i * 10))
    bd.commit()


# Radar de precios: vendedores y los nombres con que aparecen en Google Shopping (del proyecto Radar Precios).
# (nombre, alias, es propio)
VENDEDORES = [
    ("Amazon", "amazon mx, amazon.com.mx, amazon.com", False),
    ("Mercado Libre", "mercadolibre, mercadolibre.com.mx", False),
    ("Walmart", "walmart mexico, walmart.com.mx", False),
    ("HEB", "heb.com.mx, h-e-b", False),
    ("Farmacias del Ahorro", "farmaciasdelahorro.com", False),
    ("Chedraui", "chedraui.com.mx", False),
    ("Bodega Aurrera", "bodega aurrera mexico, bodegaaurrera.com.mx", False),
    ("Liverpool", "liverpool.com.mx", False),
    ("Sanborns", "sanborns.com.mx", False),
    ("Suburbia", "suburbia.com.mx", False),
    ("Súper Naturista", "super naturista, supernaturista, supernaturista.com", True),
]


def sembrar_precios(bd: Session) -> None:
    if not bd.scalar(select(func.count()).select_from(PrecioVendedor)):
        for nombre, alias, propio in VENDEDORES:
            bd.add(PrecioVendedor(nombre=nombre, alias=alias, es_propio=propio))
    bd.commit()
