"""Filtros de calidad de ofertas (spam / empresas bloqueadas)."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Sequence

from app.domain.models.offer import Offer

# Empresas bloqueadas en todos los portales (spam / no útiles para el MVP).
# Matching por substring normalizado sobre company, title y url.
BLOCKED_COMPANIES: Sequence[str] = (
    "bairesdev",
    "baires dev",
)


def _norm(text: str) -> str:
    raw = unicodedata.normalize("NFD", (text or "").lower())
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", raw).strip()


def is_blocked_company(offer: Offer) -> bool:
    haystack = _norm(f"{offer.company} {offer.title} {offer.url or ''}")
    return any(block in haystack for block in BLOCKED_COMPANIES)


def reject_blocked(offers: Iterable[Offer]) -> List[Offer]:
    return [o for o in offers if not is_blocked_company(o)]
