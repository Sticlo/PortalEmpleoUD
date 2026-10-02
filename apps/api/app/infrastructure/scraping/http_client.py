"""
GET HTTP para los adapters de portales con salida alternativa por proxy.

Los portales suelen bloquear IPs de centros de datos (Oracle, AWS…). Flujo:
  1. Petición directa.
  2. Si parece bloqueada (403/429/503/999, página de captcha o error de red) y hay
     SCRAPER_PROXY_URL, se repite por el proxy.
  3. El host queda marcado BLOCK_COOLDOWN_S y las siguientes peticiones van directo
     al proxy, sin gastar un intento directo que se sabe bloqueado.
Sin SCRAPER_PROXY_URL se comporta como requests.get.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional
from urllib.parse import urlsplit

import requests

from app.core.config import get_settings

log = logging.getLogger("bolsa-empleo.scraping.http")

BLOCK_COOLDOWN_S = 30 * 60
# 999: código propio de LinkedIn para tráfico que considera bot.
_BLOCK_STATUS = {403, 429, 503, 999}
_BLOCK_MARKERS = (
    "captcha",
    "cf-chl",
    "attention required",
    "access denied",
    "unusual traffic",
    "request unsuccessful",
)
# Las páginas de bloqueo son cortas; en páginas normales "captcha" puede aparecer en scripts.
_MARKER_MAX_LEN = 15000

_lock = threading.Lock()
_blocked_until: Dict[str, float] = {}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _is_cooling(host: str) -> bool:
    with _lock:
        return _blocked_until.get(host, 0.0) > time.monotonic()


def _mark_blocked(host: str) -> None:
    with _lock:
        _blocked_until[host] = time.monotonic() + BLOCK_COOLDOWN_S


def _looks_blocked(resp: requests.Response) -> bool:
    if resp.status_code in _BLOCK_STATUS:
        return True
    if resp.status_code == 200 and len(resp.text) < _MARKER_MAX_LEN:
        body = resp.text.lower()
        return any(marker in body for marker in _BLOCK_MARKERS)
    return False


def _via_proxy(url: str, proxy: str, **kwargs) -> requests.Response:
    return requests.get(url, proxies={"http": proxy, "https": proxy}, **kwargs)


def get(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 15,
) -> requests.Response:
    proxy = get_settings().scraper_proxy_url
    kwargs = {"headers": headers, "params": params, "timeout": timeout}
    host = _host(url)

    if proxy and _is_cooling(host):
        return _via_proxy(url, proxy, **kwargs)

    try:
        resp = requests.get(url, **kwargs)
    except requests.RequestException as exc:
        if not proxy:
            raise
        log.warning("%s sin respuesta directa (%s) — reintento por proxy", host, exc)
        _mark_blocked(host)
        return _via_proxy(url, proxy, **kwargs)

    if proxy and _looks_blocked(resp):
        log.warning("%s bloqueó la IP del servidor (HTTP %s) — reintento por proxy", host, resp.status_code)
        _mark_blocked(host)
        try:
            return _via_proxy(url, proxy, **kwargs)
        except requests.RequestException as exc:
            log.warning("Proxy falló para %s: %s", host, exc)
    return resp


def status() -> dict:
    now = time.monotonic()
    with _lock:
        blocked = {h: int(t - now) for h, t in _blocked_until.items() if t > now}
    return {
        "proxy_configured": bool(get_settings().scraper_proxy_url),
        "hosts_via_proxy": blocked,
    }
