"""
Contrato base para scrapers de portales de empleo.
Cada portal (Computrabajo, Elempleo, Magneto…) implementa este ABC.
La lógica de browser/reintentos/delays viene de infrastructure.scraping.browser
(origen: flores.py recuperado).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.domain.models.offer import Offer


class BasePortalScraper(ABC):
    """Un adapter por portal — no un scraper genérico único."""

    name: str = "base"

    @abstractmethod
    def fetch_offers(
        self,
        city: str = "Bogotá",
        max_age_hours: int = 24,
        query: str = "",
    ) -> List[Offer]:
        """Devuelve ofertas frescas normalizadas al modelo de dominio."""
        raise NotImplementedError
