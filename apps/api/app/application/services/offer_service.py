"""Servicio de ofertas — Bogotá / frescura / purga >24h / bloqueos."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from app.core.config import get_settings
from app.domain.filters.blocked_companies import is_blocked_company
from app.domain.models.offer import Offer
from app.domain.schemas.api import (
    CompanyOfferPublishRequest,
    OfferListFilters,
    OfferListResponse,
)
from app.infrastructure.persistence import memory as store

TZ_CO = timezone(timedelta(hours=-5))


def _is_fresh(offer: Offer, max_age_hours: int) -> bool:
    now = datetime.now(TZ_CO)
    published = offer.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=TZ_CO)
    return published >= now - timedelta(hours=max_age_hours)


def _modality_rank(modality: str) -> int:
    m = modality.lower()
    if "hibr" in m or "híbr" in m:
        return 0
    if "presencial" in m:
        return 1
    return 2


class OfferService:
    def list_offers(
        self,
        city: Optional[str] = None,
        program_slug: Optional[str] = None,
        max_age_hours: Optional[int] = None,
    ) -> OfferListResponse:
        s = get_settings()
        city = city or s.default_city
        max_age = max_age_hours or s.max_offer_age_hours
        program_slug = program_slug or s.default_program_slug

        purged = store.purge_stale(max_age)

        for offer in list(store.list_offers()):
            if is_blocked_company(offer):
                store.remove_offer(offer.id)
                purged += 1

        filtered: List[Offer] = [
            o
            for o in store.list_offers()
            if (city.lower() in o.city.lower() or o.city.lower() in city.lower())
            and not is_blocked_company(o)
        ]
        filtered = [o for o in filtered if _is_fresh(o, max_age)]
        filtered.sort(
            key=lambda o: (_modality_rank(o.modality), -o.published_at.timestamp())
        )
        return OfferListResponse(
            filters=OfferListFilters(
                city=city,
                max_age_hours=max_age,
                program_slug=program_slug,
                prefer_modality="hibrido",
            ),
            count=len(filtered),
            offers=filtered,
            purged=purged,
        )

    def get_offer(self, offer_id: str) -> Optional[Offer]:
        s = get_settings()
        store.purge_stale(s.max_offer_age_hours)
        offer = store.get_offer(offer_id)
        if not offer:
            return None
        if is_blocked_company(offer):
            store.remove_offer(offer.id)
            return None
        if not _is_fresh(offer, s.max_offer_age_hours):
            store.purge_stale(s.max_offer_age_hours)
            return None
        return offer

    def create_offer(self, offer: Offer) -> Offer:
        if is_blocked_company(offer):
            raise ValueError("Empresa bloqueada (spam): no se importa la oferta")
        return store.add_offer(offer)

    def publish_from_company(self, body: CompanyOfferPublishRequest) -> Offer:
        """Publicación directa de empresa aliada (sin auth en MVP)."""
        modality = (body.modality or "hibrido").strip().lower()
        if modality in ("híbrido", "hibrida", "híbrida"):
            modality = "hibrido"
        if modality not in ("presencial", "hibrido", "remoto"):
            modality = "hibrido"

        desc = body.description.strip()
        if body.contact_email:
            desc = f"{desc}\n\nContacto: {body.contact_email}"

        offer = Offer(
            id=f"empresa-{uuid4().hex[:12]}",
            title=body.title.strip(),
            company=body.company.strip(),
            city=(body.city or "Bogotá").strip(),
            modality=modality,
            source="empresa",
            url=(body.apply_url or None),
            published_at=datetime.now(TZ_CO),
            description=desc,
            salary=(body.salary.strip() if body.salary else None),
            program_tags=[body.program_slug] if body.program_slug else [],
        )
        return self.create_offer(offer)
