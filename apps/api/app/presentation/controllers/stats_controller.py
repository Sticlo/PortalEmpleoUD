"""Controller (MVC) — Métricas de mercado (sección administrativa)."""

from fastapi import APIRouter, Query

from app.application.services.market_harvest_service import MarketHarvestService
from app.application.services.market_stats_service import MarketStatsService
from app.domain.schemas.api import MarketHarvestResponse, MarketStatsResponse

router = APIRouter()
_stats = MarketStatsService()
_harvest = MarketHarvestService()


@router.get(
    "/stats/market",
    response_model=MarketStatsResponse,
    summary="Métricas de mercado laboral (admin)",
    description=(
        "Demanda de skills, títulos, empresas, salarios, seniority y (si el portal "
        "lo publica) postulantes. Alimentado por el histórico de scrapes. "
        "Usa POST /stats/market/refresh para traer más data real de 7 días."
    ),
)
def market_stats(days: int = Query(30, ge=7, le=180, description="Ventana de análisis en días")):
    return _stats.market(days=days)


@router.post(
    "/stats/market/refresh",
    response_model=MarketHarvestResponse,
    summary="Actualizar datos del mercado (scrape amplio)",
    description=(
        "Ejecuta scrapes multi-query (~7 días) en Computrabajo, Elempleo y LinkedIn "
        "para varias carreras UD y archiva todo. Puede tardar 1–3 minutos."
    ),
)
def market_refresh(
    max_age_hours: int = Query(168, ge=24, le=336, description="Ventana a scrapear (horas)"),
):
    return MarketHarvestResponse(**_harvest.harvest(max_age_hours=max_age_hours))
