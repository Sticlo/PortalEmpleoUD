"""
Servicio de scraping — orquesta adapters + cola (cache / single-flight / rate limit).
"""

from typing import List, Optional

from app.core.config import get_settings
from app.domain.filters.blocked_companies import is_blocked_company, reject_blocked
from app.domain.models.offer import Offer
from app.infrastructure.persistence import memory as store
from app.infrastructure.scraping.base import BasePortalScraper
from app.infrastructure.scraping.job_queue import cache_key, scrape_queue
from app.infrastructure.scraping.portals.computrabajo import ComputrabajoScraper
from app.infrastructure.scraping.portals.elempleo import ElempleoScraper
from app.infrastructure.scraping.portals.linkedin import LinkedInScraper


def default_scrapers() -> List[BasePortalScraper]:
    return [
        ComputrabajoScraper(limit=40),
        ElempleoScraper(limit=30),
        LinkedInScraper(limit=40),
    ]


class ScrapeService:
    def __init__(self, scrapers: Optional[List[BasePortalScraper]] = None):
        self.scrapers = scrapers if scrapers is not None else default_scrapers()

    def run(
        self,
        query: str = "desarrollador",
        city: Optional[str] = None,
        max_age_hours: Optional[int] = None,
        replace_source: bool = True,
        force: bool = False,
    ) -> dict:
        s = get_settings()
        city = city or s.default_city
        max_age = max_age_hours or s.max_offer_age_hours
        query = (query or "desarrollador").strip()
        key = cache_key(query, city, max_age)

        def _do_scrape() -> dict:
            return self._run_portals(
                query=query,
                city=city,
                max_age=max_age,
                replace_source=replace_source,
            )

        return scrape_queue.run(key, _do_scrape, force=force)

    def _run_portals(
        self,
        query: str,
        city: str,
        max_age: int,
        replace_source: bool,
    ) -> dict:
        purged = store.purge_stale(max_age)
        blocked = 0

        collected: List[Offer] = []
        errors = []
        per_source = {}

        for scraper in self.scrapers:
            try:
                if replace_source:
                    store.clear_offers(source=scraper.name)
                offers = scraper.fetch_offers(
                    city=city,
                    max_age_hours=max_age,
                    query=query,
                )
                kept = 0
                for offer in offers:
                    if is_blocked_company(offer):
                        blocked += 1
                        continue
                    store.add_offer(offer)
                    collected.append(offer)
                    kept += 1
                per_source[scraper.name] = kept
            except Exception as e:
                errors.append({"source": scraper.name, "error": str(e)})
                per_source[scraper.name] = 0

        purged += store.purge_stale(max_age)
        for offer in list(store.list_offers()):
            if is_blocked_company(offer):
                store.remove_offer(offer.id)
                blocked += 1

        collected = reject_blocked(collected)
        kept_ids = {o.id for o in store.list_offers()}
        collected = [o for o in collected if o.id in kept_ids]

        return {
            "query": query,
            "city": city,
            "max_age_hours": max_age,
            "scrapers": [sc.name for sc in self.scrapers],
            "imported": len(collected),
            "blocked": blocked,
            "purged": purged,
            "per_source": per_source,
            "errors": errors,
            "offers": [o.model_dump(mode="json") for o in collected],
        }
