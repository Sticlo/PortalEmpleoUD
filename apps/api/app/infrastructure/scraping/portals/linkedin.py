"""
Adapter LinkedIn Jobs (guest / público).

Búsqueda base (últimas 24 h en Colombia):
  https://www.linkedin.com/jobs/search?keywords=Dev&location=Colombia&geoId=100876405&f_TPR=r86400

Usa el endpoint guest (sin login):
  /jobs-guest/jobs/api/seeMoreJobPostings/search
  /jobs-guest/jobs/api/jobPosting/{id}

Prioriza Bogotá / remoto Colombia. BairesDev se filtra en capa de dominio.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.domain.models.offer import Offer
from app.infrastructure.scraping import http_client
from app.infrastructure.scraping.base import BasePortalScraper
from app.infrastructure.scraping.browser import human_delay, now_colombia
from app.infrastructure.scraping.portals.computrabajo import (
    detect_modality,
    parse_relative_age,
)
from app.infrastructure.scraping.relevance import filter_query_relevance

log = logging.getLogger("bolsa-empleo.scraping.linkedin")

BASE = "https://www.linkedin.com"
GUEST_SEARCH = f"{BASE}/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_DETAIL = f"{BASE}/jobs-guest/jobs/api/jobPosting"
COLOMBIA_GEO_ID = "100876405"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}


def _decode(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def _clean_job_url(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    # Quitar tracking; dejar path limpio
    path = parsed.path.rstrip("/")
    # Preferir co.linkedin.com o www
    netloc = parsed.netloc or "www.linkedin.com"
    return urlunparse(("https", netloc, path, "", "", ""))


def _job_id_from_card(card) -> str:
    urn = card.get("data-entity-urn") or ""
    m = re.search(r"jobPosting:(\d+)", urn)
    if m:
        return m.group(1)
    a = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
    href = a.get("href") if a else ""
    m = re.search(r"/jobs/view/[^/]*?(\d{8,})", href or "")
    if m:
        return m.group(1)
    m = re.search(r"(\d{8,})", href or "")
    return m.group(1) if m else ""


def _is_bogota_relevant(location: str, title: str = "") -> bool:
    """MVP: Bogotá / Distrito Capital, o remoto genérico en Colombia."""
    loc = (location or "").lower()
    title_l = (title or "").lower()
    hay = f"{loc} {title_l}"

    if "bogot" in loc or "distrito capital" in loc or "bogot" in title_l:
        return True

    other_places = (
        "medell",
        "cali",
        "barranquilla",
        "bucaramanga",
        "pereira",
        "cartagena",
        "manizales",
        "cúcuta",
        "cucuta",
        "atlántico",
        "atlantico",
        "antioquia",
        "valle del cauca",
        "magdalena",
        "santander",
        "meta,",
        "meta ",
        "villavicencio",
        "ibagué",
        "ibague",
        "neiva",
        "armenia",
        "pasto",
        "montería",
        "monteria",
        "fundación",
        "el banco",
    )
    if any(c in loc for c in other_places):
        return False

    # Solo "Colombia" (típico de remoto / nacional)
    if re.fullmatch(r"colombia\s*", loc.strip()):
        return True
    if "colombia" in loc and ("remoto" in hay or "remote" in hay):
        return True
    return False


def _published_from_card(card, now: datetime) -> Optional[datetime]:
    time_el = card.select_one("time")
    relative_text = _decode(time_el.get_text()) if time_el else ""
    relative = parse_relative_age(relative_text, now=now) if relative_text else None
    hours_or_minutes = bool(
        re.search(r"hora|hour|minuto|minute", (relative_text or "").lower())
    )

    if time_el and time_el.get("datetime"):
        raw = time_el.get("datetime")
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                # Fecha calendario: anclar a mediodía. LinkedIn dice "1 day ago"
                # para todo lo de ayer; si usamos 24 h exactas, la UI pinta “1 día”.
                if hours_or_minutes and relative:
                    return relative
                day = datetime.fromisoformat(raw).replace(tzinfo=now.tzinfo)
                posted = day.replace(hour=12, minute=0, second=0, microsecond=0)
                if posted > now:
                    posted = now - timedelta(hours=1)
                return posted
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(now.tzinfo)
        except ValueError:
            pass
    if relative:
        return relative
    return None


class LinkedInScraper(BasePortalScraper):
    name = "linkedin"

    def __init__(self, timeout: int = 45, limit: int = 40, page_size: int = 10):
        self.timeout = timeout
        self.limit = limit
        self.page_size = page_size

    def fetch_offers(
        self,
        city: str = "Bogotá",
        max_age_hours: int = 24,
        query: str = "",
    ) -> List[Offer]:
        query = (query or "desarrollador").strip()
        # LinkedIn responde mejor con keywords cortas tipo Dev / desarrollador
        keywords = query
        if query.lower().startswith("desarrollador "):
            # "desarrollador python" ok; si es solo ruido, dejar
            keywords = query

        seconds = max(3600, int(max_age_hours) * 3600)
        log.info(
            "LinkedIn guest search keywords=%s location=Colombia f_TPR=r%s",
            keywords,
            seconds,
        )

        human_delay(0.6, 1.4)
        cards_html_chunks: List[str] = []
        # Paginar guest API (10 por página)
        for start in range(0, self.limit, self.page_size):
            params = {
                "keywords": keywords,
                "location": "Colombia",
                "geoId": COLOMBIA_GEO_ID,
                "f_TPR": f"r{seconds}",
                "start": start,
            }
            try:
                resp = http_client.get(
                    GUEST_SEARCH,
                    params=params,
                    headers=HEADERS,
                    timeout=self.timeout,
                )
                if resp.status_code != 200 or len(resp.text) < 200:
                    log.warning("LinkedIn page start=%s status=%s", start, resp.status_code)
                    break
                if "base-card" not in resp.text and "base-search-card" not in resp.text:
                    break
                cards_html_chunks.append(resp.text)
                human_delay(0.4, 0.9)
            except Exception as e:
                log.warning("LinkedIn page error start=%s: %s", start, e)
                break

        offers = self._parse_listings(
            cards_html_chunks,
            max_age_hours=max_age_hours,
            query=query,
            city=city,
        )
        self._enrich_descriptions(offers)
        offers = filter_query_relevance(offers, query)
        log.info("LinkedIn: %s ofertas <= %sh (Bogotá/remoto)", len(offers), max_age_hours)
        return offers[: self.limit]

    def _parse_listings(
        self,
        html_chunks: List[str],
        max_age_hours: int,
        query: str,
        city: str,
    ) -> List[Offer]:
        now = now_colombia()
        cutoff = now - timedelta(hours=max_age_hours)
        results: List[Offer] = []
        seen = set()

        for html in html_chunks:
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.select("div.base-card, div.base-search-card"):
                title_el = card.select_one("h3.base-search-card__title, h3")
                company_el = card.select_one("h4.base-search-card__subtitle, h4")
                loc_el = card.select_one("span.job-search-card__location")
                a = card.select_one("a.base-card__full-link") or card.select_one(
                    "a[href*='/jobs/view/']"
                )

                title = _decode(title_el.get_text()) if title_el else ""
                company = _decode(company_el.get_text()) if company_el else "Empresa confidencial"
                location = _decode(loc_el.get_text()) if loc_el else "Colombia"
                if not title:
                    continue
                if not _is_bogota_relevant(location, title):
                    continue

                published_at = _published_from_card(card, now)
                if published_at is None:
                    published_at = now - timedelta(hours=12)
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=now.tzinfo)
                if published_at < cutoff:
                    continue

                job_id = _job_id_from_card(card)
                href = _clean_job_url(a.get("href") if a else "")
                if not href and job_id:
                    href = f"https://www.linkedin.com/jobs/view/{job_id}"

                dedupe = job_id or href or title
                if dedupe in seen:
                    continue
                seen.add(dedupe)

                card_text = card.get_text(" ", strip=True)
                modality = detect_modality(f"{title} {location} {card_text}")
                city_label = (
                    "Bogotá"
                    if ("bogot" in location.lower() or "distrito capital" in location.lower())
                    else location
                )

                results.append(
                    Offer(
                        id=f"linkedin-{job_id or re.sub(r'[^a-zA-Z0-9]+', '-', title)[:40]}",
                        title=title,
                        company=company,
                        city=city_label,
                        modality=modality,
                        source="linkedin",
                        url=href or None,
                        published_at=published_at,
                        description=f"{location} · {modality}",
                        salary=None,
                        program_tags=[query],
                    )
                )

        results.sort(key=lambda o: o.published_at, reverse=True)
        return results

    def _enrich_descriptions(self, offers: List[Offer]) -> None:
        pairs: List[Tuple[Offer, str]] = []
        for o in offers[:18]:
            m = re.search(r"(\d{8,})", o.id) or re.search(r"(\d{8,})", o.url or "")
            if m:
                pairs.append((o, m.group(1)))
        if not pairs:
            return

        by_jid = {jid: offer for offer, jid in pairs}

        def fetch_one(job_id: str) -> Tuple[str, str, Optional[int]]:
            try:
                r = http_client.get(
                    f"{GUEST_DETAIL}/{job_id}",
                    headers=HEADERS,
                    timeout=14,
                )
                if r.status_code != 200:
                    return job_id, "", None
                soup = BeautifulSoup(r.text, "html.parser")
                desc_el = soup.select_one(
                    ".show-more-less-html__markup, .description__text, .description"
                )
                snippet = _decode(desc_el.get_text()) if desc_el else ""
                if len(snippet) > 900:
                    snippet = snippet[:897].rsplit(" ", 1)[0] + "…"
                criteria = " · ".join(
                    _decode(li.get_text())
                    for li in soup.select("li.description__job-criteria-item")[:3]
                )
                if criteria and snippet:
                    snippet = f"{snippet} ({criteria})"

                # Postulantes públicos (cuando LinkedIn guest los muestra)
                applicants: Optional[int] = None
                page_text = soup.get_text(" ", strip=True)
                m = re.search(
                    r"(?:Be among the first|Sé de los primeros)\s+(\d+)\s+applicant",
                    page_text,
                    re.I,
                )
                if m:
                    applicants = int(m.group(1))
                else:
                    m = re.search(r"Over\s+(\d[\d,]*)\s+applicant", page_text, re.I)
                    if m:
                        applicants = int(m.group(1).replace(",", ""))
                    else:
                        m = re.search(r"(\d[\d,]*)\s+applicant", page_text, re.I)
                        if m:
                            applicants = int(m.group(1).replace(",", ""))
                        else:
                            m = re.search(
                                r"(\d[\d.]*)\s+candidat",
                                page_text,
                                re.I,
                            )
                            if m:
                                applicants = int(m.group(1).replace(".", ""))

                return job_id, snippet, applicants
            except Exception as e:
                log.debug("LinkedIn detail %s: %s", job_id, e)
                return job_id, "", None

        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = [pool.submit(fetch_one, jid) for jid in by_jid]
            for fut in as_completed(futs):
                jid, snippet, applicants = fut.result()
                offer = by_jid.get(jid)
                if not offer:
                    continue
                if snippet:
                    offer.description = snippet
                if applicants is not None:
                    offer.applicants = applicants
