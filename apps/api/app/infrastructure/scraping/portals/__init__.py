"""Registro de portals de empleo."""

from app.infrastructure.scraping.portals.computrabajo import ComputrabajoScraper
from app.infrastructure.scraping.portals.elempleo import ElempleoScraper
from app.infrastructure.scraping.portals.linkedin import LinkedInScraper

__all__ = ["ComputrabajoScraper", "ElempleoScraper", "LinkedInScraper"]
