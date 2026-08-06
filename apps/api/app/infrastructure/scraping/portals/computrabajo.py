"""
Adapter Computrabajo Colombia.

URL ejemplo:
  https://co.computrabajo.com/trabajo-de-desarrollador-en-bogota?pubdate=1

`pubdate=1` = filtro "Hoy" del portal (ofertas del día / ~24h).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from app.domain.models.offer import Offer
from app.infrastructure.scraping.base import BasePortalScraper
from app.infrastructure.scraping.browser import human_delay, now_colombia

log = logging.getLogger("bolsa-empleo.scraping.computrabajo")

BASE_URL = "https://co.computrabajo.com"
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


def slugify_keyword(query: str) -> str:
    """desarrollador python -> desarrollador-python"""
    text = unicodedata.normalize("NFD", query.strip().lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text or "desarrollador"


def build_search_url(
    query: str,
    city: str = "Bogotá",
    max_age_hours: int = 24,
) -> str:
    """pubdate: 1=hoy, 3≈3 días, 7≈semana (más data para métricas de mercado)."""
    keyword = slugify_keyword(query)
    city_slug = slugify_keyword(city.replace("á", "a").replace("Á", "a"))
    if city_slug in ("bogota", "bogota-dc", "bogota-d-c"):
        city_slug = "bogota"
    path = f"/trabajo-de-{keyword}-en-{city_slug}"
    url = urljoin(BASE_URL, path)
    if max_age_hours <= 24:
        pubdate = 1
    elif max_age_hours <= 72:
        pubdate = 3
    else:
        pubdate = 7
    return f"{url}?pubdate={pubdate}"


def parse_relative_age(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Convierte 'Hace 11 horas' / 'Ayer' / 'Hace 2 días' a datetime Colombia."""
    now = now or now_colombia()
    raw = unicodedata.normalize("NFKC", (text or "")).strip().lower()
    raw = re.sub(r"\s+", " ", raw)

    if not raw:
        return None
    if "minuto" in raw:
        m = re.search(r"(\d+)", raw)
        mins = int(m.group(1)) if m else 1
        return now - timedelta(minutes=mins)
    if "hora" in raw:
        m = re.search(r"(\d+)", raw)
        hours = int(m.group(1)) if m else 1
        return now - timedelta(hours=hours)
    if raw == "ayer" or raw.startswith("ayer"):
        # "Ayer" del portal ≈ últimas 24–36 h; lo anclamos dentro de la ventana de 24 h
        return now - timedelta(hours=18)
    if "día" in raw or "dia" in raw:
        m = re.search(r"(\d+)", raw)
        days = int(m.group(1)) if m else 1
        return now - timedelta(days=days)
    if "hoy" in raw:
        return now - timedelta(hours=1)
    return None


def detect_modality(card_text: str) -> str:
    t = (card_text or "").lower()
    if "presencial y remoto" in t or "híbrido" in t or "hibrido" in t:
        return "hibrido"
    if "remoto" in t and "presencial" not in t:
        return "remoto"
    if "presencial" in t:
        return "presencial"
    return "presencial"


def _decode(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def _clean_offer_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("/"):
        href = urljoin(BASE_URL, href)
    return href.split("#")[0].split("?")[0]


class ComputrabajoScraper(BasePortalScraper):
    name = "computrabajo"

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
        url = build_search_url(query, city=city, max_age_hours=max_age_hours)
        log.info("Computrabajo GET %s", url)

        human_delay(0.8, 1.8)
        resp = requests.get(url, headers=HEADERS, timeout=self.timeout)
        resp.raise_for_status()

        offers = self._parse_listing(
            resp.text,
            max_age_hours=max_age_hours,
            query=query,
        )
        offers = offers[: self.limit]
        self._enrich_descriptions(offers)
        log.info("Computrabajo: %s ofertas <= %sh", len(offers), max_age_hours)
        return offers

    def _parse_listing(
        self,
        html: str,
        max_age_hours: int,
        query: str,
    ) -> List[Offer]:
        soup = BeautifulSoup(html, "html.parser")
        now = now_colombia()
        cutoff = now - timedelta(hours=max_age_hours)
        results: List[Offer] = []
        seen = set()

        for article in soup.select("article.box_offer"):
            offer_id = article.get("data-id") or article.get("id") or ""
            link = article.select_one("a.js-o-link")
            if not link:
                continue

            title = _decode(link.get_text())
            href = _clean_offer_url(link.get("href") or "")

            company_el = article.select_one("a[offer-grid-article-company-url]")
            company = _decode(company_el.get_text()) if company_el else "Empresa confidencial"

            loc_el = article.select_one("p.fs16.fc_base.mt5 span.mr10")
            city_text = _decode(loc_el.get_text()) if loc_el else "Bogotá"

            age_el = article.select_one("p.fs13.fc_aux.mt15")
            age_text = _decode(age_el.get_text()) if age_el else ""
            published_at = parse_relative_age(age_text, now=now)
            if published_at is None:
                published_at = now - timedelta(hours=12)

            if published_at < cutoff:
                continue

            card_text = article.get_text(" ", strip=True)
            modality = detect_modality(card_text)

            salary = ""
            salary_icon = article.select_one(".i_salary")
            if salary_icon and salary_icon.parent:
                salary = _decode(salary_icon.parent.get_text())
                salary = re.sub(r"\s+", " ", salary).strip()

            # Tags de modalidad / contrato en .fs13.mt15
            tag_bits = []
            for span in article.select("div.fs13.mt15 span.dIB"):
                t = _decode(span.get_text())
                if t and t != salary:
                    tag_bits.append(t)

            desc_parts = []
            if salary:
                desc_parts.append(f"Salario: {salary}")
            if tag_bits:
                desc_parts.append(" · ".join(tag_bits))
            if city_text:
                desc_parts.append(city_text)
            description = " · ".join(desc_parts) if desc_parts else age_text

            dedupe_key = offer_id or href
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            results.append(
                Offer(
                    id=f"computrabajo-{offer_id or quote(title)[:40]}",
                    title=title,
                    company=company,
                    city="Bogotá" if "bogot" in city_text.lower() else city_text,
                    modality=modality,
                    source="computrabajo",
                    url=href or None,
                    published_at=published_at,
                    description=description,
                    salary=salary or None,
                    program_tags=[query],
                )
            )

        results.sort(key=lambda o: o.published_at, reverse=True)
        return self._filter_relevance(results, query)

    def _enrich_descriptions(self, offers: List[Offer]) -> None:
        """Trae un extracto de la página de detalle (en paralelo)."""
        to_fetch = [o for o in offers if o.url][:12]
        if not to_fetch:
            return

        def fetch_one(offer: Offer) -> tuple[str, str]:
            try:
                r = requests.get(offer.url, headers=HEADERS, timeout=12)
                r.raise_for_status()
                soup = BeautifulSoup(r.text, "html.parser")
                paras = [
                    _decode(p.get_text())
                    for p in soup.select("p.mbB")
                    if _decode(p.get_text())
                ]
                # Filtra ruido típico
                paras = [
                    p
                    for p in paras
                    if len(p) > 40
                    and not p.lower().startswith("palabras clave")
                    and "competencias añadidas" not in p.lower()
                ]
                snippet = " ".join(paras[:4]).strip()
                if len(snippet) > 900:
                    snippet = snippet[:897].rsplit(" ", 1)[0] + "…"
                return offer.id, snippet
            except Exception as e:
                log.debug("Detalle %s falló: %s", offer.id, e)
                return offer.id, ""

        by_id = {o.id: o for o in offers}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(fetch_one, o) for o in to_fetch]
            for fut in as_completed(futures):
                oid, snippet = fut.result()
                offer = by_id.get(oid)
                if offer and snippet:
                    # Conserva salario/modalidad al inicio si ya estaban
                    prefix = ""
                    if offer.salary:
                        prefix = f"Salario: {offer.salary}. "
                    offer.description = f"{prefix}{snippet}".strip()

    def _filter_relevance(self, offers: List[Offer], query: str) -> List[Offer]:
        """Exige términos específicos (ej. químico); 'ingeniero' solo no basta."""
        raw_tokens = [
            t
            for t in slugify_keyword(query).split("-")
            if len(t) >= 3 and t not in {"para", "como", "desde", "bogota", "con", "del"}
        ]
        generic = {
            "ingeniero",
            "ingeniera",
            "ingenieria",
            "desarrollador",
            "desarrolladora",
            "programador",
            "analista",
            "auxiliar",
            "junior",
            "senior",
            "empleo",
            "trabajo",
        }
        required = [t for t in raw_tokens if t not in generic] or raw_tokens
        if not required:
            return offers

        def ok(offer: Offer) -> bool:
            hay = slugify_keyword(f"{offer.title} {offer.description}")
            return all(t in hay for t in required)

        matched = [o for o in offers if ok(o)]
        if matched:
            return matched
        # Si el portal no trajo nada estricto, no inventar con genéricos
        return []
