"""Relevancia de ofertas vs la query del estudiante.

No devolver vacío por un recorte de tarjeta, pero tampoco vendedor/cartera
cuando se busca «desarrollador python».
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable, List

from app.domain.models.offer import Offer

log = logging.getLogger("bolsa-empleo.scraping.relevance")


def slugify_keyword(query: str) -> str:
    text = unicodedata.normalize("NFD", (query or "").strip().lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text


GENERIC = {
    "ingeniero",
    "ingeniera",
    "ingenieria",
    "desarrollador",
    "desarrolladora",
    "programador",
    "programadora",
    "analista",
    "auxiliar",
    "junior",
    "senior",
    "empleo",
    "trabajo",
    "profesional",
    "dev",
}

SYNONYMS = {
    "python": ("python", "django", "flask", "fastapi", "pandas", "pytorch"),
    "javascript": (
        "javascript",
        "nodejs",
        "node",
        "react",
        "angular",
        "vue",
        "typescript",
        "frontend",
    ),
    "java": ("java", "spring", "springboot"),
    "react": ("react", "reactjs", "frontend"),
    "angular": ("angular", "frontend"),
    "datos": ("datos", "data", "python", "sql", "etl"),
    "quimico": ("quimico", "quimica", "proceso-quimico"),
    "civil": ("civil", "estructur", "obra", "construccion"),
    "forestal": ("forestal", "ambiental", "bosque"),
    "electronico": ("electronico", "electronica", "hardware", "iot", "plc"),
    "catastral": (
        "catastral",
        "catastro",
        "geodesia",
        "geodesico",
        "geodesta",
        "predial",
        "igac",
        "topograf",
        "cartograf",
        "fotogrametr",
        "ortofoto",
        "georreferenc",
        "agrimens",
        "lidar",
    ),
    "catastro": (
        "catastro",
        "catastral",
        "geodesia",
        "predial",
        "igac",
        "topograf",
        "cartograf",
    ),
    "geodesia": ("geodesia", "geodesico", "catastral", "topograf", "cartograf"),
}

SOFTWARE_TITLE = (
    "desarrollador",
    "developer",
    "programador",
    "backend",
    "frontend",
    "fullstack",
    "full-stack",
    "devops",
    "software",
    "data-engineer",
    "ingeniero-de-sistemas",
    "ingeniero-de-software",
    "ingeniero-de-datos",
    "cientifico-de-datos",
    "machine-learning",
    "qa-automat",
    "automatizador",
    "python",
    "engineer",
    "sde",
)

NOISE_TITLE = (
    "vendedor",
    "venta",
    "comercial",
    "asesor-comercial",
    "desarrollo-comercial",
    "desarrollador-de-negocio",
    "programador-de-ruta",
    "producto-industrial",
    "solidworks",
    "analista-financ",
    "cartera",
    "conciliacion",
    "cajero",
    "call-center",
    "teleoperador",
    "recepcion",
    "mesero",
    "domiciliario",
    "conductor",
    "mecanico",
    "mecanic",
)

SOFTWARE_QUERY_HINTS = (
    "desarroll",
    "program",
    "software",
    "python",
    "java",
    "javascript",
    "react",
    "angular",
    "sistemas",
    "datos",
    "devops",
    "backend",
    "frontend",
)


def _hay(offer: Offer) -> str:
    return slugify_keyword(f"{offer.title} {offer.description}")


def _title(offer: Offer) -> str:
    return slugify_keyword(offer.title)


def _tokens(query: str) -> List[str]:
    return [
        t
        for t in slugify_keyword(query).split("-")
        if len(t) >= 3 and t not in {"para", "como", "desde", "bogota", "con", "del"}
    ]


def _required(tokens: Iterable[str]) -> List[str]:
    specific = [t for t in tokens if t not in GENERIC]
    return specific or list(tokens)


def _expanded(required: List[str]) -> List[str]:
    out: List[str] = []
    for t in required:
        out.extend(SYNONYMS.get(t, (t,)))
    return list(dict.fromkeys(out))


def _is_noise(offer: Offer) -> bool:
    t = _title(offer)
    if any(n in t for n in NOISE_TITLE):
        return True
    # Título que es claramente ventas, aunque la ficha mencione “desarrollador”
    # (LinkedIn a veces pone el cargo del reclutador en la descripción).
    if re.search(r"(^|-)(vendedor|vendedora|ventas)(-|$)", t):
        return True
    return False


def _is_software_title(offer: Offer) -> bool:
    t = _title(offer)
    return any(s in t for s in SOFTWARE_TITLE)


def _query_is_software(query: str) -> bool:
    q = slugify_keyword(query)
    return any(h in q for h in SOFTWARE_QUERY_HINTS)


def _score(offer: Offer, tokens: List[str], needles: List[str]) -> int:
    hay = _hay(offer)
    return sum(4 for n in needles if n in hay) + sum(1 for t in tokens if t in hay)


def _has_needle(hay: str, needle: str) -> bool:
    if len(needle) <= 3:
        return f"-{needle}-" in f"-{hay}-"
    return needle in hay


def _is_specific_query(query: str) -> bool:
    return any(t not in GENERIC for t in _tokens(query))


def filter_query_relevance(offers: List[Offer], query: str) -> List[Offer]:
    """Match específico/sinónimos. No rellenar con ofertas ajenas (catastral ≠ mecánico)."""
    tokens = _tokens(query)
    required = _required(tokens)
    needles = _expanded(required)
    clean = [o for o in offers if not _is_noise(o)]
    specific_needles = [n for n in needles if n not in GENERIC]

    def has_specific(offer: Offer) -> bool:
        title = _title(offer)
        hay = _hay(offer)
        # El término específico debe estar en el TÍTULO o, si no, en el cuerpo
        # pero solo si el título parece del oficio buscado (no “Vendedor”).
        if specific_needles:
            if any(_has_needle(title, n) for n in specific_needles):
                return True
            if _query_is_software(query) and not _is_software_title(offer):
                return False
            return any(_has_needle(hay, n) for n in specific_needles)
        if required and all(_has_needle(hay, t) for t in required):
            return True
        return False

    specific = [o for o in clean if has_specific(o)]
    if specific:
        return sorted(specific, key=lambda o: _score(o, tokens, needles), reverse=True)

    # Solo software genérico puede ampliar a roles dev; un perfil nicho no se rellena.
    if not _is_specific_query(query) and _query_is_software(query):
        soft = [o for o in clean if _is_software_title(o)]
        if soft:
            log.info("Relevancia: query genérica; %s roles software", len(soft))
            return sorted(soft, key=lambda o: _score(o, tokens, needles), reverse=True)

    log.info("Relevancia: 0 ofertas afines a %r (no se rellena con ajenas)", query)
    return []
