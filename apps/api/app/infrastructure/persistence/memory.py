"""Persistencia en memoria (esqueleto MVP). Luego Postgres/SQLAlchemy."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.domain.models.offer import Offer
from app.domain.models.student import StudentProfile

_PROFILES: Dict[str, StudentProfile] = {}
_OFFERS: Dict[str, Offer] = {}

TZ_CO = timezone(timedelta(hours=-5))


def get_profile(student_id: str) -> Optional[StudentProfile]:
    return _PROFILES.get(student_id)


def save_profile(student_id: str, profile: StudentProfile) -> StudentProfile:
    _PROFILES[student_id] = profile
    return profile


def delete_profile(student_id: str) -> bool:
    return _PROFILES.pop(student_id, None) is not None


def list_offers() -> List[Offer]:
    return sorted(_OFFERS.values(), key=lambda o: o.published_at, reverse=True)


def get_offer(offer_id: str) -> Optional[Offer]:
    return _OFFERS.get(offer_id)


def add_offer(offer: Offer) -> Offer:
    _OFFERS[offer.id] = offer
    # Historial para métricas de mercado (no se purga a las 24 h)
    try:
        from app.infrastructure.persistence.offer_archive import archive_offer

        archive_offer(offer)
    except Exception:  # el archivo nunca debe romper el flujo principal
        pass
    return offer


def remove_offer(offer_id: str) -> bool:
    if offer_id in _OFFERS:
        del _OFFERS[offer_id]
        return True
    return False


def clear_offers(source: Optional[str] = None) -> int:
    if source is None:
        n = len(_OFFERS)
        _OFFERS.clear()
        return n
    to_del = [k for k, v in _OFFERS.items() if v.source == source]
    for k in to_del:
        del _OFFERS[k]
    return len(to_del)


def purge_stale(max_age_hours: int = 24) -> int:
    """Borra ofertas con más de max_age_hours. No se archivan."""
    now = datetime.now(TZ_CO)
    cutoff = now - timedelta(hours=max_age_hours)
    stale = []
    for key, offer in _OFFERS.items():
        published = offer.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=TZ_CO)
        if published < cutoff:
            stale.append(key)
    for key in stale:
        del _OFFERS[key]
    return len(stale)
