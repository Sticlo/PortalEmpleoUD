"""
Utilidades de browser Playwright — extraídas de la lógica del scraper (flores.py).
Base para scrapers de portales de empleo.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bolsa-empleo.scraping.browser")

TZ_COL = timezone(timedelta(hours=-5))


def now_colombia() -> datetime:
    return datetime.now(TZ_COL)


def human_delay(min_s: float = 1.0, max_s: float = 3.5) -> None:
    """Pausa aleatoria para simular comportamiento humano (lógica original del scraper)."""
    time.sleep(random.uniform(min_s, max_s))


def goto_with_retry(page, url: str, retries: int = 2, timeout: int = 20000) -> bool:
    """Navega a una URL con reintentos y backoff (lógica original del scraper)."""
    for attempt in range(retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            error_msg = str(e)[:200]
            if attempt < retries:
                wait = (attempt + 1) * 2
                log.warning(
                    "Reintento %s/%s en %ss... (%s)",
                    attempt + 1,
                    retries,
                    wait,
                    error_msg,
                )
                time.sleep(wait)
            else:
                log.error("Falló tras %s intentos: %s", retries + 1, error_msg)
                return False
    return False


def block_heavy_resources(route) -> None:
    """Bloquea imágenes/video; deja CSS/fonts (lógica original del scraper)."""
    if route.request.resource_type in ("image", "media"):
        route.abort()
    else:
        route.continue_()


def launch_browser(playwright, headless: bool = True):
    """Abre Chromium listo para scrapear."""
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        locale="es-CO",
        timezone_id="America/Bogota",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    page.route("**/*", block_heavy_resources)
    return browser, context, page
