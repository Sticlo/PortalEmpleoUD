"""
Servicio de scraping — orquesta adapters + cola (cache / single-flight / rate limit).
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from app.core.config import get_settings
from app.domain.filters.blocked_companies import is_blocked_company, reject_blocked
from app.domain.models.offer import Offer
from app.infrastructure.persistence import memory as store
from app.infrastructure.scraping.base import BasePortalScraper
from app.infrastructure.scraping.job_queue import (
    MAX_CONCURRENT_PORTAL_JOBS,
    cache_key,
    portal_slot,
    scrape_queue,
)
from app.infrastructure.scraping.portals.computrabajo import ComputrabajoScraper
from app.infrastructure.scraping.portals.elempleo import ElempleoScraper
from app.infrastructure.scraping.portals.linkedin import LinkedInScraper

log = logging.getLogger("bolsa-empleo.scrape")

# Ventana más amplia que usa una búsqueda (reintento a 72 h). Purgar con una ventana
# menor borraría ofertas que otra búsqueda en curso acaba de traer.
STORE_MAX_AGE_HOURS = 72
PORTAL_LABELS = {"computrabajo": "Computrabajo", "elempleo": "Elempleo", "linkedin": "LinkedIn"}
# 3 portales por búsqueda × búsquedas simultáneas.
_portal_pool = ThreadPoolExecutor(
    max_workers=3 * MAX_CONCURRENT_PORTAL_JOBS, thread_name_prefix="portal"
)


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
        force: bool = False,
    ) -> dict:
        s = get_settings()
        city = city or s.default_city
        max_age = max_age_hours or s.max_offer_age_hours
        query = (query or "desarrollador").strip()
        extras = related_queries(query)
        key = cache_key(query, city, max_age)

        def _merge(queries: List[str], max_age_hours: int) -> dict:
            merged_offers: List[Offer] = []
            merged_ids: set[str] = set()
            errors: List[dict] = []
            per_source: dict = {}
            purged = 0
            blocked = 0
            last: dict = {}
            for q in queries:
                chunk = self._run_portals(query=q, city=city, max_age=max_age_hours)
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
            result = _merge([query], max_age)
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
                result = _merge(qs, wider)
                note_bits.append(
                    "Pocas vacantes de las últimas 24 h (típico en fin de semana o perfil nicho). "
                    "Se amplió a 72 h."
                )
                if extras:
                    note_bits.append(
                        "También se buscó catastro, geodesia y topografía "
                        "(afines a Ingeniería Catastral y Geodesia)."
                    )
            failed = sorted({PORTAL_LABELS.get(e["source"], e["source"]) for e in result.get("errors") or []})
            if failed:
                verb = "no respondió" if len(failed) == 1 else "no respondieron"
                note_bits.append(f"{' y '.join(failed)} {verb} esta vez; se muestran los demás portales.")
            if not result.get("offers"):
                note_bits.append(
                    "En los portales casi no hay vacantes frescas de este perfil. "
                    "No se rellenó con empleos ajenos."
                )
            result["freshness_note"] = " ".join(note_bits)
            return result

        return scrape_queue.run(key, _do_scrape, force=force)

    def _run_portals(self, query: str, city: str, max_age: int) -> dict:
        """Consulta los portales en paralelo (cada uno con su cupo en PORTAL_SLOTS).

        La respuesta sale de lo que trajo ESTA búsqueda, no del store compartido:
        otras búsquedas en curso pueden estar escribiendo en él al mismo tiempo.
        """

        def fetch(scraper: BasePortalScraper) -> List[Offer]:
            with portal_slot(scraper.name):
                return scraper.fetch_offers(city=city, max_age_hours=max_age, query=query)

        futures = {scraper.name: _portal_pool.submit(fetch, scraper) for scraper in self.scrapers}

        blocked = 0
        collected: List[Offer] = []
        errors = []
        per_source = {}
        for name, future in futures.items():
            try:
                offers = future.result()
            except Exception as e:
                errors.append({"source": name, "error": str(e)})
                per_source[name] = 0
                continue
            kept = 0
            for offer in offers:
                if is_blocked_company(offer):
                    blocked += 1
                    continue
                collected.append(offer)
                kept += 1
            per_source[name] = kept

        collected = reject_blocked(collected)
        for offer in collected:
            store.add_offer(offer)
        purged = store.purge_stale(STORE_MAX_AGE_HOURS)

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
