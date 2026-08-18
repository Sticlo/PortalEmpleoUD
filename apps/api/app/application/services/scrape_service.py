"""
Servicio de scraping — orquesta adapters + cola (cache / single-flight / rate limit).
"""

import logging
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

log = logging.getLogger("bolsa-empleo.scrape")


def related_queries(query: str) -> List[str]:
    """Búsquedas extra para perfiles nicho (p. ej. Catastral y Geodesia en la UD)."""
    blob = (
        (query or "")
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if "catastr" in blob or "geodes" in blob:
        extras = ["catastro", "geodesia", "topografo"]
        seen = {(query or "").strip().lower()}
        return [e for e in extras if e.lower() not in seen]
    return []


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
        extras = related_queries(query)
        key = cache_key(query, city, max_age)

        def _merge(queries: List[str], max_age_hours: int, replace_first: bool) -> dict:
            merged_offers: List[Offer] = []
            merged_ids: set[str] = set()
            errors: List[dict] = []
            per_source: dict = {}
            purged = 0
            blocked = 0
            last: dict = {}
            for i, q in enumerate(queries):
                chunk = self._run_portals(
                    query=q,
                    city=city,
                    max_age=max_age_hours,
                    replace_source=replace_first and i == 0,
                )
                last = chunk
                purged += int(chunk.get("purged") or 0)
                blocked += int(chunk.get("blocked") or 0)
                errors.extend(chunk.get("errors") or [])
                for src, n in (chunk.get("per_source") or {}).items():
                    per_source[src] = per_source.get(src, 0) + n
                for raw in chunk.get("offers") or []:
                    oid = raw.get("id")
                    if not oid or oid in merged_ids:
                        continue
                    merged_ids.add(oid)
                    merged_offers.append(Offer.model_validate(raw))
            from app.infrastructure.scraping.relevance import filter_query_relevance

            kept = filter_query_relevance(merged_offers, query)
            last.update(
                {
                    "query": query,
                    "max_age_hours": max_age_hours,
                    "imported": len(kept),
                    "blocked": blocked,
                    "purged": purged,
                    "per_source": per_source,
                    "errors": errors,
                    "offers": [o.model_dump(mode="json") for o in kept],
                    "freshness_note": "",
                }
            )
            return last

        def _do_scrape() -> dict:
            result = _merge([query], max_age, replace_first=True)
            note_bits: List[str] = []
            if len(result.get("offers") or []) < 5 and max_age <= 24:
                wider = 72
                log.info(
                    "Scrape corto (%s ofertas) a %sh para %r; reintento a %sh",
                    len(result.get("offers") or []),
                    max_age,
                    query,
                    wider,
                )
                qs = [query, *extras] if extras else [query]
                result = _merge(qs, wider, replace_first=True)
                note_bits.append(
                    "Pocas vacantes de las últimas 24 h (típico en fin de semana o perfil nicho). "
                    "Se amplió a 72 h."
                )
                if extras:
                    note_bits.append(
                        "También se buscó catastro, geodesia y topografía "
                        "(afines a Ingeniería Catastral y Geodesia)."
                    )
            if not result.get("offers"):
                note_bits.append(
                    "En los portales casi no hay vacantes frescas de este perfil. "
                    "No se rellenó con empleos ajenos."
                )
            result["freshness_note"] = " ".join(note_bits)
            return result

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

        payload = {
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
            "freshness_note": "",
        }
        return payload
