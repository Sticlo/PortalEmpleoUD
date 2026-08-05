"""Archivo histórico de ofertas (JSONL append-only).

A diferencia de la memoria (que purga a las 24 h), aquí se acumulan TODAS las
ofertas vistas por los scrapers / empresas para poder sacar métricas de mercado
en el tiempo. Luego se puede migrar a Postgres sin cambiar el contrato.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import ROOT_DIR
from app.domain.models.offer import Offer

log = logging.getLogger("bolsa-empleo.archive")

TZ_CO = timezone(timedelta(hours=-5))
ARCHIVE_PATH = ROOT_DIR / "data" / "archive" / "offers_archive.jsonl"

_lock = threading.Lock()
_seen_keys: Optional[set[str]] = None


def _offer_key(offer: Offer) -> str:
    if offer.url:
        return offer.url.strip().lower()
    return f"{offer.source}:{offer.title}:{offer.company}".strip().lower()


def _load_seen() -> set[str]:
    global _seen_keys
    if _seen_keys is not None:
        return _seen_keys
    keys: set[str] = set()
    if ARCHIVE_PATH.exists():
        for line in ARCHIVE_PATH.read_text(encoding="utf-8").splitlines():
            try:
                keys.add(json.loads(line).get("_key", ""))
            except Exception:
                continue
    _seen_keys = keys
    return keys


def archive_offer(offer: Offer) -> bool:
    """Guarda la oferta si no se había archivado antes. Devuelve True si es nueva."""
    key = _offer_key(offer)
    with _lock:
        seen = _load_seen()
        if key in seen:
            return False
        ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = offer.model_dump(mode="json")
        record["_key"] = key
        record["_archived_at"] = datetime.now(TZ_CO).isoformat()
        with ARCHIVE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        seen.add(key)
    return True


def load_archived(days: int = 30) -> List[Dict]:
    """Ofertas archivadas dentro de los últimos `days` días (dicts crudos)."""
    if not ARCHIVE_PATH.exists():
        return []
    cutoff = datetime.now(TZ_CO) - timedelta(days=days)
    rows: List[Dict] = []
    for line in ARCHIVE_PATH.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except Exception:
            continue
        stamp = raw.get("_archived_at") or raw.get("published_at") or ""
        try:
            when = datetime.fromisoformat(stamp)
            if when.tzinfo is None:
                when = when.replace(tzinfo=TZ_CO)
        except Exception:
            continue
        if when >= cutoff:
            raw["_when"] = when
            rows.append(raw)
    return rows


def archive_count() -> int:
    if not ARCHIVE_PATH.exists():
        return 0
    return sum(1 for _ in ARCHIVE_PATH.open(encoding="utf-8"))
