"""Controller (MVC) — Scraping de ofertas."""

from typing import Optional

from fastapi import APIRouter, status

from app.application.services.scrape_service import ScrapeService
from app.domain.schemas.api import ScrapeRequest, ScrapeResponse

router = APIRouter()
_service = ScrapeService()


@router.post(
    "/scraping/run",
    response_model=ScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Buscar ofertas en portales",
    description=(
        "Ejecuta scrapers activos (Computrabajo + Elempleo + LinkedIn). "
        "El parámetro `query` es la palabra clave (ej: `desarrollador python`). "
        "Solo conserva ofertas con antigüedad ≤ `max_age_hours` (default 24) y "
        "borra del store las que ya expiraron. Bloquea empresas spam (BairesDev). "
        "LinkedIn usa el listado público guest (Colombia · f_TPR=24h) priorizando Bogotá/remoto."
    ),
    responses={
        200: {"description": "Scraping terminado (puede traer 0 ofertas o errores parciales)."},
    },
)
def run_scraping(body: ScrapeRequest) -> ScrapeResponse:
    raw = _service.run(
        query=body.query,
        city=body.city,
        max_age_hours=body.max_age_hours,
    )
    return ScrapeResponse.model_validate(raw)
