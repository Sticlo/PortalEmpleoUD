"""
Adapter Elempleo Colombia (https://www.elempleo.com/co/).

Listado:
  https://www.elempleo.com/co/ofertas-empleo?trabajo={query}&ciudad=bogota

Filtro de frescura: parsea la etiqueta del portal (Hoy / Ayer / Hace N…)
y descarta lo que exceda max_age_hours (MVP: 24 h).
"""

from __future__ import annotations

import json
import logging
import unicodedata
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from app.domain.models.offer import Offer
from app.infrastructure.scraping.base import BasePortalScraper
from app.infrastructure.scraping.browser import human_delay, now_colombia
from app.infrastructure.scraping.portals.computrabajo import (
    detect_modality,
    parse_relative_age,
)
from app.infrastructure.scraping.relevance import filter_query_relevance

log = logging.getLogger("bolsa-empleo.scraping.elempleo")

BASE_URL = "https://www.elempleo.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-CO,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


def _decode(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def build_search_url(query: str, city: str = "Bogotá") -> str:
    q = (query or "desarrollador").strip()
    city_slug = "bogota"
    city_l = unicodedata.normalize("NFD", city.lower())
    city_l = "".join(c for c in city_l if unicodedata.category(c) != "Mn")
    if "medellin" in city_l:
        city_slug = "medellin"
    elif "cali" in city_l:
        city_slug = "cali"
    elif "barranquilla" in city_l:
        city_slug = "barranquilla"
    return (
        f"{BASE_URL}/co/ofertas-empleo"
        f"?trabajo={quote_plus(q)}&ciudad={quote_plus(city_slug)}"
    )


def _modality_from_card(item, fallback_text: str) -> str:
    for box in item.select(".small"):
        label = box.select_one(".small-text") or box.select_one(".text-medium-gray")
        val = box.select_one(".text-blue-petrol-dark")
        if not label or not val:
            continue
        if "odalidad" in _decode(label.get_text()).lower():
            return detect_modality(_decode(val.get_text()))
    return detect_modality(fallback_text)


class ElempleoScraper(BasePortalScraper):
    name = "elempleo"

    def __init__(self, timeout: int = 45, limit: int = 30):
        self.timeout = timeout
        self.limit = limit

    def fetch_offers(
        self,
        city: str = "Bogotá",
        max_age_hours: int = 24,
        query: str = "",
    ) -> List[Offer]:
        query = (query or "desarrollador").strip()
        url = build_search_url(query, city=city)
        log.info("Elempleo GET %s", url)

        human_delay(0.8, 1.8)
        resp = requests.get(url, headers=HEADERS, timeout=self.timeout)
        resp.raise_for_status()

        offers = self._parse_listing(
            resp.text,
            max_age_hours=max_age_hours,
            query=query,
            city=city,
        )
        log.info("Elempleo: %s ofertas <= %sh", len(offers), max_age_hours)
        return offers[: self.limit]

    def _parse_listing(
        self,
        html: str,
        max_age_hours: int,
        query: str,
        city: str,
    ) -> List[Offer]:
        soup = BeautifulSoup(html, "html.parser")
        now = now_colombia()
        cutoff = now - timedelta(hours=max_age_hours)
        results: List[Offer] = []
        seen = set()

        for item in soup.select(".result-item"):
            bind = item.select_one(".js-area-bind[data-ga4-offerdata]")
            if not bind:
                continue

            try:
                data = json.loads(bind.get("data-ga4-offerdata") or "{}")
            except json.JSONDecodeError:
                continue

            title = (data.get("title") or "").strip()
            company = (data.get("company") or "Empresa confidencial").strip()
            salary = (data.get("salary") or "").strip() or None
            location = (data.get("location") or city).strip()
            offer_id = str(data.get("id") or "")

            href = bind.get("data-url") or ""
            title_a = item.select_one("a.js-offer-title")
            if title_a and title_a.get("href"):
                href = title_a.get("href") or href
            url = urljoin(BASE_URL, href.split("?")[0]) if href else None

            date_el = item.select_one(".js-offer-date")
            age_text = _decode(date_el.get_text()) if date_el else ""
            published_at = parse_relative_age(age_text, now=now)
            if published_at is None:
                continue
            if published_at < cutoff:
                continue

            card_text = item.get_text(" ", strip=True)
            modality = _modality_from_card(item, card_text)

            desc_el = item.select_one(
                ".result-info-hover-li-description-size, .result-info-hover-li-description"
            )
            description = _decode(desc_el.get_text()) if desc_el else ""
            if len(description) > 420:
                description = description[:417].rsplit(" ", 1)[0] + "…"
            if salary and salary.lower() not in description.lower():
                description = f"Salario: {salary}. {description}".strip()
            if not description:
                bits = [p for p in [salary, location, age_text] if p]
                description = " · ".join(bits)

            dedupe = offer_id or url or title
            if dedupe in seen:
                continue
            seen.add(dedupe)

            results.append(
                Offer(
                    id=f"elempleo-{offer_id or quote_plus(title)[:40]}",
                    title=title,
                    company=company,
                    city="Bogotá" if "bogot" in location.lower() else location,
                    modality=modality,
                    source="elempleo",
                    url=url,
                    published_at=published_at,
                    description=description,
                    salary=salary,
                    program_tags=[query],
                )
            )

        results.sort(key=lambda o: o.published_at, reverse=True)
        return filter_query_relevance(results, query)
