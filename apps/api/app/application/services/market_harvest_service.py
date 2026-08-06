"""Harvest de mercado — scrape amplio multi-query para alimentar métricas admin.

A diferencia de "Empleos de hoy" (10 ofertas del día), aquí se busca ~7 días
en varias keywords/carreras y se ARCHIVA todo para tener masa crítica de data.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from app.core.config import get_settings
from app.domain.filters.blocked_companies import is_blocked_company
from app.domain.models.offer import Offer
from app.infrastructure.persistence import memory as store
from app.infrastructure.persistence.offer_archive import archive_count
from app.infrastructure.scraping.job_queue import scrape_queue
from app.infrastructure.scraping.portals.computrabajo import ComputrabajoScraper
from app.infrastructure.scraping.portals.elempleo import ElempleoScraper
from app.infrastructure.scraping.portals.linkedin import LinkedInScraper

log = logging.getLogger("bolsa-empleo.market-harvest")

# (program_slug, program_label, query)
MARKET_QUERIES: List[Tuple[str, str, str]] = [
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "desarrollador"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "desarrollador python"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "desarrollador java"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "analista de datos"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "qa automation"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "devops"),
    ("ingenieria-civil", "Ingeniería Civil", "ingeniero civil"),
    ("ingenieria-civil", "Ingeniería Civil", "residente de obra"),
    ("ingenieria-electronica", "Ingeniería Electrónica", "ingeniero electronico"),
    ("ingenieria-forestal", "Ingeniería Forestal", "ingeniero forestal"),
    ("ingenieria-quimica", "Ingeniería Química", "ingeniero quimico"),
    ("licenciatura-en-artes", "Licenciatura en Artes", "docente artes"),
]


def _tag(offer: Offer, slug: str, label: str) -> Offer:
    tags = [slug, label]
    for t in offer.program_tags:
        if t not in tags:
            tags.append(t)
    return offer.model_copy(update={"program_tags": tags})


def _key(offer: Offer) -> str:
    if offer.url:
        return offer.url.strip().lower()
    return f"{offer.source}:{offer.title}:{offer.company}".lower()


class MarketHarvestService:
    """Scrape amplio → archivo histórico. No reemplaza el carrusel de hoy."""

    def harvest(self, max_age_hours: int = 168) -> dict:
        """max_age_hours=168 ≈ 7 días de ventana en portales."""
        # No compite con scrapes de estudiantes: toma el semáforo global de portales
        return scrape_queue.run_exclusive_portal(
            lambda: self._harvest_body(max_age_hours=max_age_hours),
            timeout=600,
        )

    def _harvest_body(self, max_age_hours: int = 168) -> dict:
        s = get_settings()
        city = s.default_city
        scrapers = [
            ComputrabajoScraper(limit=25),
            ElempleoScraper(limit=20),
            LinkedInScraper(limit=20),
        ]

        collected: List[Offer] = []
        errors: List[dict] = []
        per_query: Dict[str, int] = {}

        def run_one(slug: str, label: str, query: str) -> Tuple[str, List[Offer], List[dict]]:
            found: List[Offer] = []
            errs: List[dict] = []
            for scraper in scrapers:
                try:
                    batch = scraper.fetch_offers(
                        city=city,
                        max_age_hours=max_age_hours,
                        query=query,
                    )
                    for o in batch:
                        if is_blocked_company(o):
                            continue
                        found.append(_tag(o, slug, label))
                except Exception as exc:
                    errs.append({"source": scraper.name, "query": query, "error": str(exc)})
                    log.warning("harvest fail %s/%s: %s", scraper.name, query, exc)
            return query, found, errs

        # Pocas queries en paralelo: ya tenemos el lock global; no saturar anti-bot
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [
                pool.submit(run_one, slug, label, query)
                for slug, label, query in MARKET_QUERIES
            ]
            for fut in as_completed(futs):
                query, found, errs = fut.result()
                per_query[query] = len(found)
                collected.extend(found)
                errors.extend(errs)

        # Dedup + archive via store.add_offer
        uniq: Dict[str, Offer] = {}
        for o in collected:
            k = _key(o)
            prev = uniq.get(k)
            if not prev or (o.published_at > prev.published_at):
                uniq[k] = o

        before = archive_count()
        for o in uniq.values():
            store.add_offer(o)
        newly_archived = max(0, archive_count() - before)

        return {
            "ok": True,
            "queries": len(MARKET_QUERIES),
            "max_age_hours": max_age_hours,
            "collected_raw": len(collected),
            "unique": len(uniq),
            "newly_archived": newly_archived,
            "archive_total": archive_count(),
            "per_query": per_query,
            "errors": errors,
            "note": (
                "Harvest bajo cola global de portales (no satura junto a búsquedas de estudiantes). "
                "Computrabajo/Elempleo no publican # de postulantes sin cuenta empresa; "
                "LinkedIn a veces sí (campo applicants)."
            ),
        }
