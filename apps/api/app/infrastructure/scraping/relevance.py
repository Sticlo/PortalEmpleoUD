"""Relevancia de ofertas vs la query del estudiante.

No devolver vacío por un recorte de tarjeta, pero tampoco vendedor/cartera
cuando se busca «desarrollador python».
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable, List, Optional

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
    "practicante",
    "intern",
}

# Nivel de experiencia: no es profesión; no debe casar “junior” con un abogado junior.
JUNIOR_WORDS = {
    "junior",
    "practicante",
    "intern",
    "trainee",
    "egresado",
    "entry",
}
SENIOR_WORDS = {
    "senior",
    "lead",
    "principal",
    "experto",
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
    # “civil” suelto casa “responsabilidad civil”. El sentido de ingeniería va aparte.
    "civil": ("ingeniero-civil", "civil-engineer", "ingenieria-civil", "estructur", "obras-civiles"),
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
    "abogado",
    "lawyer",
    "indemniz",
    "casualty",
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


def _query_seniority(query: str) -> Optional[str]:
    toks = set(_tokens(query))
    if toks & JUNIOR_WORDS:
        return "junior"
    if toks & SENIOR_WORDS:
        return "senior"
    return None


def _title_is_junior(title: str) -> bool:
    return any(w in title for w in ("junior", "practicante", "intern", "trainee", "egresado", "entry"))


def _title_is_senior(title: str) -> bool:
    # Evitar “sr” de 2 letras; LinkedIn usa senior / lead / principal
    return any(
        w in title
        for w in ("senior", "lead", "principal", "jefe-", "experto")
    )


def _is_legal_civil(title: str, hay: str) -> bool:
    blob = f"{title} {hay}"
    return any(
        n in blob
        for n in (
            "abogado",
            "lawyer",
            "indemniz",
            "casualty",
            "responsabilidad-civil",
            "juridic",
            "litigio",
            "legal",
        )
    )


def _is_civil_engineering(offer: Offer) -> bool:
    """ingeniero civil ≠ responsabilidad civil / abogado junior."""
    title = _title(offer)
    hay = _hay(offer)
    if _is_legal_civil(title, hay) and not (
        "ingeniero-civil" in title or "civil-engineer" in title
    ):
        return False
    if any(
        n in title
        for n in (
            "ingeniero-civil",
            "civil-engineer",
            "ingenieria-civil",
            "obras-civiles",
            "estructural",
        )
    ):
        return True
    if "civil" in title and any(n in title for n in ("ingenier", "engineer", "estructur")):
        return True
    return False


def _profession_ok(offer: Offer, query: str) -> bool:
    q = slugify_keyword(query)
    title = _title(offer)
    tokens = set(_tokens(query))

    if "civil" in tokens and "catastr" not in q:
        if "catastr" in title or "geodes" in title:
            return "civil" in title
        return _is_civil_engineering(offer)

    return True


def _seniority_ok(offer: Offer, query: str) -> bool:
    """Si pide junior, no devolver Senior Civil Engineer. No exige la palabra junior en el título."""
    level = _query_seniority(query)
    if level != "junior":
        return True
    title = _title(offer)
    if _title_is_senior(title) and not _title_is_junior(title):
        return False
    return True


def _score(offer: Offer, tokens: List[str], needles: List[str], query: str) -> int:
    hay = _hay(offer)
    title = _title(offer)
    s = sum(4 for n in needles if n in hay) + sum(1 for t in tokens if t in hay)
    if _query_seniority(query) == "junior":
        if _title_is_junior(title):
            s += 15
        if _title_is_senior(title):
            s -= 20
    return s


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
    specific = [o for o in specific if _profession_ok(o, query) and _seniority_ok(o, query)]
    if specific:
        return sorted(
            specific,
            key=lambda o: _score(o, tokens, needles, query),
            reverse=True,
        )

    # Solo software genérico puede ampliar a roles dev; un perfil nicho no se rellena.
    if not _is_specific_query(query) and _query_is_software(query):
        soft = [o for o in clean if _is_software_title(o)]
        if soft:
            log.info("Relevancia: query genérica; %s roles software", len(soft))
            return sorted(soft, key=lambda o: _score(o, tokens, needles, query), reverse=True)

    log.info("Relevancia: 0 ofertas afines a %r (no se rellena con ajenas)", query)
    return []
