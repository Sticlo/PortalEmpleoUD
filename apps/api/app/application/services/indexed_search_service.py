"""Búsqueda rápida sobre índice local (memoria + archivo histórico).

Estricto: "ingeniero químico" NO debe devolver DevOps/Sistemas solo por "ingeniero".
No toca portales (picos de concurrencia). El scrape en vivo enriquece después.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Set

from app.domain.models.offer import Offer
from app.domain.schemas.api import IndexedSearchResponse
from app.infrastructure.persistence import memory as store
from app.infrastructure.persistence.offer_archive import load_archived

# Palabras demasiado genéricas: no bastan solas para un match
_GENERIC: Set[str] = {
    "ingeniero",
    "ingeniera",
    "ingenieria",
    "desarrollador",
    "desarrolladora",
    "programador",
    "programadora",
    "analista",
    "auxiliar",
    "profesional",
    "tecnologo",
    "tecnologa",
    "tecnologia",
    "junior",
    "senior",
    "empleo",
    "trabajo",
    "oferta",
    "bogota",
    "remoto",
    "presencial",
    "hibrido",
}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t


def _tokens(query: str) -> List[str]:
    parts = re.split(r"[\s,/;|]+", _norm(query))
    return [p for p in parts if len(p) >= 3]


def _required_tokens(tokens: List[str]) -> List[str]:
    """Si hay términos específicos (químico, python…), esos son obligatorios."""
    specific = [t for t in tokens if t not in _GENERIC]
    return specific if specific else tokens


def _matches(blob: str, tokens: List[str], required: List[str]) -> bool:
    if not tokens:
        return True
    # Todos los tokens específicos deben aparecer
    if required and not all(t in blob for t in required):
        return False
    # Si solo había genéricos, al menos uno
    if not required:
        return any(t in blob for t in tokens)
    return True


def _score(blob: str, tokens: List[str], required: List[str]) -> int:
    if not _matches(blob, tokens, required):
        return -1
    s = sum(3 for t in required if t in blob)
    s += sum(1 for t in tokens if t in blob)
    # Bonus frase completa
    return s


def _from_archive_row(row: Dict) -> Optional[Offer]:
    try:
        data = {k: v for k, v in row.items() if not k.startswith("_")}
        return Offer.model_validate(data)
    except Exception:
        return None


class IndexedSearchService:
    def search(
        self,
        query: str,
        city: Optional[str] = None,
        days: int = 30,
        limit: int = 40,
    ) -> IndexedSearchResponse:
        q = (query or "").strip() or "desarrollador"
        tokens = _tokens(q)
        required = _required_tokens(tokens)

        scored: List[tuple[int, Offer]] = []
        seen: Set[str] = set()

        def consider(offer: Offer) -> None:
            if offer.id in seen:
                return
            blob = _norm(f"{offer.title} {offer.description} {' '.join(offer.program_tags)}")
            sc = _score(blob, tokens, required)
            if sc < 0:
                return
            seen.add(offer.id)
            scored.append((sc, offer))

        for o in store.list_offers():
            consider(o)

        for row in load_archived(days=days):
            offer = _from_archive_row(row)
            if offer:
                consider(offer)

        scored.sort(key=lambda x: (-x[0], -x[1].published_at.timestamp()))
        ranked = [o for _, o in scored[:limit]]

        for o in ranked:
            store.add_offer(o)

        note = (
            "Resultado del índice local (solo vacantes que coinciden con tu búsqueda). "
            "No consulta portales ahora; un refresco en vivo puede ampliar después."
        )
        if required:
            note += f" Filtro estricto: {', '.join(required)}."

        return IndexedSearchResponse(
            query=q,
            city=city or "Bogotá",
            count=len(ranked),
            offers=ranked,
            source="index",
            note=note,
        )
