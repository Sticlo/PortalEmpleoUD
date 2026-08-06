"""Controller (MVC) — Ofertas."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.application.services.indexed_search_service import IndexedSearchService
from app.application.services.offer_service import OfferService
from app.application.services.today_jobs_service import TodayJobsService, sync_today_into_store
from app.domain.models.offer import Offer
from app.domain.schemas.api import (
    CompanyOfferPublishRequest,
    IndexedSearchResponse,
    OfferCreateResponse,
    OfferListResponse,
    TodayJobsResponse,
)

router = APIRouter()
_service = OfferService()
_today = TodayJobsService()
_indexed = IndexedSearchService()


@router.get(
    "/offers",
    response_model=OfferListResponse,
    summary="Listar ofertas frescas",
    description=(
        "Lista ofertas en memoria filtradas por ciudad y frescura. "
        "Antes de responder **elimina** las que superen `max_age_hours`."
    ),
)
def list_offers(
    city: Optional[str] = Query(None, examples=["Bogotá"]),
    program_slug: Optional[str] = Query(None, examples=["ingenieria-de-sistemas"]),
    max_age_hours: Optional[int] = Query(None, ge=1, le=72, examples=[24]),
):
    return _service.list_offers(city=city, program_slug=program_slug, max_age_hours=max_age_hours)


@router.get(
    "/offers/search",
    response_model=IndexedSearchResponse,
    summary="Búsqueda rápida en índice (sin scrapers)",
    description=(
        "Busca en el histórico archivado + memoria. **No llama a portales.** "
        "Pensado para picos de concurrencia: respuesta en milisegundos. "
        "El refresco en vivo queda en POST /scraping/run (cola)."
    ),
)
def search_indexed(
    q: str = Query(..., min_length=2, examples=["desarrollador python"]),
    city: Optional[str] = Query("Bogotá"),
    days: int = Query(30, ge=7, le=180),
    limit: int = Query(40, ge=5, le=100),
):
    return _indexed.search(query=q, city=city, days=days, limit=limit)


@router.get(
    "/offers/today",
    response_model=TodayJobsResponse,
    summary="Empleos de hoy",
    description=(
        "Hasta 10 ofertas **reales** ≤24 h de Computrabajo, Elempleo y LinkedIn "
        "para varias carreras UD. Cada oferta trae portal + link original. "
        "Se cachea el día (Colombia); `refresh=true` fuerza nuevo scrape."
    ),
)
def empleos_de_hoy(refresh: bool = Query(False, description="Forzar scrape (ignora cache del día)")):
    return _today.list_today(force_refresh=refresh)


@router.post(
    "/offers/publish",
    response_model=OfferCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar oferta (empresa)",
    description=(
        "Formulario para empresas aliadas. Sin autenticación en el MVP; "
        "luego SSO / guard / multi-tenant. source=empresa, vigencia 24 h."
    ),
)
def publish_offer(body: CompanyOfferPublishRequest):
    try:
        created = _service.publish_from_company(body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OfferCreateResponse(
        ok=True,
        id=created.id,
        message="Oferta publicada. Aparecerá en el radar mientras tenga menos de 24 h.",
    )


@router.get(
    "/offers/{offer_id}",
    response_model=Offer,
    summary="Obtener oferta por id",
    responses={404: {"description": "No existe o expirada (>24 h)"}},
)
def get_offer(offer_id: str):
    offer = _service.get_offer(offer_id)
    if not offer:
        # Intentar materializar el carrusel cacheado del día
        sync_today_into_store(force_refresh=False)
        offer = _service.get_offer(offer_id)
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Oferta no encontrada o expirada (>24h)",
        )
    return offer


@router.post(
    "/offers",
    response_model=OfferCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear oferta manual (dev)",
)
def create_offer(offer: Offer):
    try:
        created = _service.create_offer(offer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OfferCreateResponse(ok=True, id=created.id)
