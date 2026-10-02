"""Cola / single-flight de scrapes — evita stampede a portales.

Casos:
A) 100 estudiantes, MISMA búsqueda → 1 scrape (caché + single-flight).
B) 100 búsquedas DIFERENTES → no se puede scrapear 100 portales a la vez.
   Se encolan con semáforo global; si la cola crece demasiado, se responde 503
   amable (reintenta / usa Empleos de hoy) en vez de tumbar Computrabajo.

MVP in-memory; luego Celery/RQ + Redis sin cambiar el contrato HTTP.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

log = logging.getLogger("bolsa-empleo.scrape-queue")

DEFAULT_TTL_SECONDS = 10 * 60  # misma query → reusar 10 min
# Búsquedas distintas en curso a la vez. El freno anti-bot real es PORTAL_SLOTS.
MAX_CONCURRENT_PORTAL_JOBS = 4
# Búsquedas distintas esperando hueco. Más allá → rechazo controlado.
MAX_QUEUED_DISTINCT = 12
PORTAL_WAIT_TIMEOUT = 90  # segundos máximos en cola de búsquedas

# Búsquedas simultáneas por portal. En LinkedIn el freno real es el ritmo global
# de peticiones de portals/linkedin.py.
PORTAL_SLOTS = {"computrabajo": 2, "elempleo": 2, "linkedin": 2}
DEFAULT_PORTAL_SLOTS = 2
# Si un portal sigue ocupado tras esto, la búsqueda sigue sin él en vez de esperar.
PORTAL_SLOT_TIMEOUT = 25

_slot_guard = threading.Lock()
_slots: Dict[str, threading.Semaphore] = {}


class PortalBusyError(TimeoutError):
    pass


@contextmanager
def portal_slot(name: str, timeout: float = PORTAL_SLOT_TIMEOUT) -> Iterator[None]:
    with _slot_guard:
        sem = _slots.get(name)
        if sem is None:
            sem = threading.Semaphore(PORTAL_SLOTS.get(name, DEFAULT_PORTAL_SLOTS))
            _slots[name] = sem
    if not sem.acquire(timeout=timeout):
        raise PortalBusyError(f"{name} ocupado por otras búsquedas; se omitió esta vez")
    try:
        yield
    finally:
        sem.release()


def cache_key(query: str, city: str, max_age_hours: int) -> str:
    q = (query or "").strip().lower()
    c = (city or "").strip().lower()
    return f"{q}|{c}|{max_age_hours}"


class ScrapeJobQueue:
    """Cache + single-flight + semáforo + tope de cola para queries distintas."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_PORTAL_JOBS,
        max_queued: int = MAX_QUEUED_DISTINCT,
    ):
        self.ttl_seconds = ttl_seconds
        self.max_concurrent = max_concurrent
        self.max_queued = max_queued
        self._portal_sem = threading.Semaphore(max_concurrent)
        self._guard = threading.Lock()
        self._cache: Dict[str, Tuple[float, dict]] = {}
        self._inflight: Dict[str, Tuple[threading.Event, Dict[str, Any]]] = {}
        self._portal_waiting = 0  # líderes esperando semáforo
        self._portal_running = 0

    def stats(self) -> dict:
        with self._guard:
            return {
                "cache_entries": len(self._cache),
                "inflight_keys": len(self._inflight),
                "portal_waiting": self._portal_waiting,
                "portal_running": self._portal_running,
                "ttl_seconds": self.ttl_seconds,
                "max_concurrent_portal_jobs": self.max_concurrent,
                "max_queued_distinct": self.max_queued,
                "portal_slots": PORTAL_SLOTS,
                "note": (
                    "Misma query → cache/single-flight. "
                    "Queries distintas → cola limitada; el resto usa Empleos de hoy o reintenta."
                ),
            }

    def get_cached(self, key: str) -> Optional[dict]:
        with self._guard:
            hit = self._cache.get(key)
            if not hit:
                return None
            expires_at, payload = hit
            if time.time() > expires_at:
                del self._cache[key]
                return None
            return payload

    def run(
        self,
        key: str,
        worker: Callable[[], dict],
        *,
        force: bool = False,
    ) -> dict:
        if not force:
            cached = self.get_cached(key)
            if cached is not None:
                out = dict(cached)
                out["from_cache"] = True
                out["shared_waiters"] = 0
                out["queue_position"] = 0
                out["queue_note"] = (
                    "Resultado compartido (caché ~10 min). No se re-consultaron los portales."
                )
                log.info("scrape cache HIT key=%s", key)
                return out

        leader = False
        event: threading.Event
        box: Dict[str, Any]
        with self._guard:
            if not force and key in self._inflight:
                event, box = self._inflight[key]
            else:
                event = threading.Event()
                box = {"result": None, "error": None, "waiters": 0}
                self._inflight[key] = (event, box)
                leader = True

        if not leader:
            with self._guard:
                box["waiters"] = int(box.get("waiters") or 0) + 1
            log.info("scrape WAIT key=%s (single-flight)", key)
            ok = event.wait(timeout=PORTAL_WAIT_TIMEOUT + 60)
            if not ok:
                raise TimeoutError(
                    "La búsqueda tardó demasiado. Reintenta o mira Empleos de hoy."
                )
            if box.get("error") is not None:
                raise box["error"]
            result = dict(box["result"] or {})
            result["from_cache"] = False
            result["shared_waiters"] = int(box.get("waiters") or 0)
            result["queue_position"] = 0
            result["queue_note"] = (
                "Había un scrape idéntico en curso: compartiste ese resultado "
                "(sin saturar portales)."
            )
            return result

        # Líder de una query distinta: ¿hay cupo en la cola de portales?
        with self._guard:
            queued_ahead = self._portal_waiting + self._portal_running
            if queued_ahead >= self.max_queued:
                self._inflight.pop(key, None)
                event.set()
                raise TimeoutError(
                    "Hay muchas búsquedas distintas en cola. "
                    "Para no saturar los portales, reintenta en un minuto "
                    "o usa «Empleos de hoy» (ya cacheado para todos)."
                )
            self._portal_waiting += 1
            position = queued_ahead + 1

        log.info("scrape QUEUE key=%s position≈%s", key, position)
        acquired = self._portal_sem.acquire(timeout=PORTAL_WAIT_TIMEOUT)
        with self._guard:
            self._portal_waiting = max(0, self._portal_waiting - 1)

        if not acquired:
            with self._guard:
                self._inflight.pop(key, None)
            event.set()
            raise TimeoutError(
                "Cola de scraping llena (muchas consultas distintas). "
                "Reintenta en unos segundos o abre Empleos de hoy."
            )

        with self._guard:
            self._portal_running += 1

        try:
            log.info("scrape RUN key=%s", key)
            raw = worker()
            result = dict(raw)
            result["from_cache"] = False
            result["shared_waiters"] = int(box.get("waiters") or 0)
            result["queue_position"] = position
            result["queue_note"] = (
                f"Scrape ejecutado (posición ~{position} en cola de portales). "
                "Otras personas con la misma búsqueda lo reutilizarán unos minutos. "
                "Búsquedas distintas se atienden de a pocas para no bloquear LinkedIn/Computrabajo."
            )
            n_offers = len(result.get("offers") or [])
            imported = int(result.get("imported") or 0)
            # Nunca cachear vacío: un domingo/bloqueo no debe congelar 0 ofertas 10 min.
            if imported > 0 and n_offers > 0:
                with self._guard:
                    self._cache[key] = (time.time() + self.ttl_seconds, dict(result))
                    box["result"] = result
            else:
                log.info("scrape SKIP cache (vacío) key=%s", key)
                with self._guard:
                    box["result"] = result
            return result
        except Exception as exc:
            box["error"] = exc
            raise
        finally:
            self._portal_sem.release()
            with self._guard:
                self._portal_running = max(0, self._portal_running - 1)
                self._inflight.pop(key, None)
            event.set()

    def run_exclusive_portal(self, worker: Callable[[], Any], timeout: float = 300) -> Any:
        """Harvest/admin: semáforo global, sin cache de query."""
        with self._guard:
            self._portal_waiting += 1
        ok = self._portal_sem.acquire(timeout=timeout)
        with self._guard:
            self._portal_waiting = max(0, self._portal_waiting - 1)
        if not ok:
            raise TimeoutError("Hay scrapes de estudiantes en curso; reintenta el harvest.")
        with self._guard:
            self._portal_running += 1
        try:
            return worker()
        finally:
            self._portal_sem.release()
            with self._guard:
                self._portal_running = max(0, self._portal_running - 1)


scrape_queue = ScrapeJobQueue()
