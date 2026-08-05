"""Empleos de hoy — ofertas reales ≤24 h desde portales, multi-carrera, cache diario."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import ROOT_DIR, get_settings
from app.domain.filters.blocked_companies import is_blocked_company
from app.domain.models.offer import Offer
from app.domain.schemas.api import TodayJobsResponse
from app.infrastructure.persistence import memory as store
from app.infrastructure.scraping.portals.computrabajo import ComputrabajoScraper
from app.infrastructure.scraping.portals.elempleo import ElempleoScraper
from app.infrastructure.scraping.portals.linkedin import LinkedInScraper

log = logging.getLogger("bolsa-empleo.today")

TZ_CO = timezone(timedelta(hours=-5))
TODAY_COUNT = 10
CACHE_PATH = ROOT_DIR / "data" / "cache" / "empleos_de_hoy.json"

# query por carrera — lo que se busca en los portales
CAREER_QUERIES: List[Tuple[str, str, str]] = [
    ("ingenieria-civil", "Ingeniería Civil", "ingeniero civil"),
    ("ingenieria-de-sistemas", "Ingeniería de Sistemas", "desarrollador"),
    ("ingenieria-electronica", "Ingeniería Electrónica", "ingeniero electronico"),
    ("ingenieria-forestal", "Ingeniería Forestal", "ingeniero forestal"),
    ("ingenieria-quimica", "Ingeniería Química", "ingeniero quimico"),
    ("licenciatura-en-artes", "Licenciatura en Artes", "docente artes"),
]


def _day_iso(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(TZ_CO)
    return now.astimezone(TZ_CO).date().isoformat()


def _today_scrapers():
    # Límites bajos: varias carreras × 3 portales
    return [
        ComputrabajoScraper(limit=12),
        ElempleoScraper(limit=10),
        LinkedInScraper(limit=12),
    ]


def _tag_offer(offer: Offer, program_slug: str, program_label: str) -> Offer:
    tags = [program_slug, program_label]
    for t in offer.program_tags:
        if t not in tags:
            tags.append(t)
    return offer.model_copy(update={"program_tags": tags})


def _offer_key(offer: Offer) -> str:
    if offer.url:
        return offer.url.strip().lower()
    return f"{offer.source}:{offer.title}:{offer.company}".lower()


def _score_freshness(offer: Offer) -> float:
    published = offer.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=TZ_CO)
    return published.timestamp()


def _stable_rank(day: str, offer: Offer) -> str:
    raw = f"{day}|{_offer_key(offer)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _pick_diverse(candidates: List[Offer], day: str, n: int = TODAY_COUNT) -> List[Offer]:
    """Hasta n ofertas con URL, priorizando una por carrera y variedad de portal."""
    with_url = [o for o in candidates if (o.url or "").startswith("http")]
    with_url.sort(key=lambda o: (-_score_freshness(o), _stable_rank(day, o)))

    by_program: Dict[str, List[Offer]] = {}
    for o in with_url:
        slug = o.program_tags[0] if o.program_tags else "otra"
        by_program.setdefault(slug, []).append(o)

    chosen: List[Offer] = []
    seen: set[str] = set()
    used_sources: Dict[str, int] = {}

    # 1) Una por carrera prioritaria
    for slug, _label, _q in CAREER_QUERIES:
        for o in by_program.get(slug, []):
            key = _offer_key(o)
            if key in seen:
                continue
            src_count = used_sources.get(o.source, 0)
            if src_count >= 4:
                continue
            chosen.append(o)
            seen.add(key)
            used_sources[o.source] = src_count + 1
            break
        if len(chosen) >= n:
            return chosen[:n]

    # 2) Completar con lo más fresco restante (máx 2 por carrera)
    per_prog: Dict[str, int] = {}
    for o in chosen:
        slug = o.program_tags[0] if o.program_tags else "otra"
        per_prog[slug] = per_prog.get(slug, 0) + 1

    for o in with_url:
        if len(chosen) >= n:
            break
        key = _offer_key(o)
        if key in seen:
            continue
        slug = o.program_tags[0] if o.program_tags else "otra"
        if per_prog.get(slug, 0) >= 2:
            continue
        chosen.append(o)
        seen.add(key)
        per_prog[slug] = per_prog.get(slug, 0) + 1

    # 3) Si aún faltan, sin tope de carrera
    for o in with_url:
        if len(chosen) >= n:
            break
        key = _offer_key(o)
        if key in seen:
            continue
        chosen.append(o)
        seen.add(key)
    return chosen[:n]


def _load_cache(day: str) -> Optional[List[Offer]]:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("day") != day:
        return None
    offers: List[Offer] = []
    for raw in data.get("offers") or []:
        try:
            offers.append(Offer.model_validate(raw))
        except Exception:
            continue
    if not offers:
        return None
    return offers


def _save_cache(day: str, offers: List[Offer]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "day": day,
        "updated_at": datetime.now(TZ_CO).isoformat(),
        "offers": [o.model_dump(mode="json") for o in offers],
    }
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fetch_career(
    program_slug: str,
    program_label: str,
    query: str,
    city: str,
    max_age: int,
) -> List[Offer]:
    found: List[Offer] = []
    for scraper in _today_scrapers():
        try:
            batch = scraper.fetch_offers(
                city=city,
                max_age_hours=max_age,
                query=query,
            )
            for offer in batch:
                if is_blocked_company(offer):
                    continue
                if not (offer.url or "").startswith("http"):
                    continue
                found.append(_tag_offer(offer, program_slug, program_label))
            log.info(
                "today %s/%s query=%r -> %s",
                scraper.name,
                program_slug,
                query,
                len(batch),
            )
        except Exception as exc:
            log.warning(
                "today scrape fail %s/%s: %s",
                scraper.name,
                program_slug,
                exc,
            )
    return found


def _scrape_all_careers() -> List[Offer]:
    s = get_settings()
    city = s.default_city
    max_age = s.max_offer_age_hours
    collected: List[Offer] = []

    # Carreras en paralelo (cada una lanza sus 3 portales en serie)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(
                _fetch_career,
                slug,
                label,
                query,
                city,
                max_age,
            ): slug
            for slug, label, query in CAREER_QUERIES
        }
        for fut in as_completed(futures):
            slug = futures[fut]
            try:
                collected.extend(fut.result())
            except Exception as exc:
                log.warning("career %s failed: %s", slug, exc)

    # Dedup
    uniq: Dict[str, Offer] = {}
    for o in collected:
        key = _offer_key(o)
        prev = uniq.get(key)
        if not prev or _score_freshness(o) > _score_freshness(prev):
            uniq[key] = o
    return list(uniq.values())


def _materialize(offers: List[Offer]) -> List[Offer]:
    """Guarda en memoria para /offers/{id} y Preparar CV."""
    for offer in offers:
        store.add_offer(offer)
    return offers


def sync_today_into_store(force_refresh: bool = False) -> List[Offer]:
    day = _day_iso()
    if not force_refresh:
        cached = _load_cache(day)
        if cached:
            return _materialize(cached)

    candidates = _scrape_all_careers()
    picked = _pick_diverse(candidates, day, TODAY_COUNT)
    if picked:
        _save_cache(day, picked)
        return _materialize(picked)

    # Si el scrape falló pero hay cache viejo del mismo día parcialmente… nada
    return []


class TodayJobsService:
    def list_today(self, force_refresh: bool = False) -> TodayJobsResponse:
        day = _day_iso()
        offers = sync_today_into_store(force_refresh=force_refresh)
        programs = sorted(
            {
                (o.program_tags[1] if len(o.program_tags) > 1 else o.program_tags[0])
                for o in offers
                if o.program_tags
            }
        )
        portals = sorted({o.source for o in offers})
        portal_labels = {
            "computrabajo": "Computrabajo",
            "elempleo": "Elempleo",
            "linkedin": "LinkedIn",
            "empresa": "Empresa",
        }
        nice = [portal_labels.get(p, p) for p in portals]
        note = (
            f"Ofertas reales ≤24 h desde {', '.join(nice) or 'portales'}. "
            "Cada tarjeta muestra el portal y el link original. "
            "El set se refresca una vez al día (hora Colombia)."
        )
        return TodayJobsResponse(
            day=day,
            title="Empleos de hoy",
            count=len(offers),
            offers=offers,
            programs_covered=programs,
            note=note,
        )
