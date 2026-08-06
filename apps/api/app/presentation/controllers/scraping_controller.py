"""Controller (MVC) — Scraping de ofertas (con cola / caché anti-stampede)."""

from fastapi import APIRouter, HTTPException, Query, status

from app.application.services.scrape_service import ScrapeService
from app.domain.schemas.api import ScrapeRequest, ScrapeResponse
from app.infrastructure.scraping.job_queue import scrape_queue

router = APIRouter()
_service = ScrapeService()


@router.post(
    "/scraping/run",
    response_model=ScrapeResponse,
    status_code=status.HTTP_200_OK,
    summary="Buscar ofertas en portales (con cola compartida)",
    description=(
        "Ejecuta scrapers (Computrabajo + Elempleo + LinkedIn) con **protección anti-stampede**:\n\n"
        "1. **Caché ~10 min** por query+ciudad: muchos con la misma búsqueda "
        "comparten un solo scrape.\n"
        "2. **Single-flight**: scrape idéntico en curso → los demás esperan ese resultado.\n"
        "3. **Semáforo global (2)** + **tope de cola (~8 queries distintas)**: "
        "si 100 buscan cosas diferentes, no se abren 100 scrapes; se encolan y, "
        "si hay saturación, se pide reintentar o usar Empleos de hoy "
        "(así no bloquean los portales).\n\n"
        "Así se evitan bloqueos anti-bot y datos obsoletos por saturación. "
        "En producción se puede migrar a Celery/RQ + Redis sin cambiar este contrato."
    ),
)
def run_scraping(
    body: ScrapeRequest,
    force: bool = Query(False, description="Ignorar caché y forzar scrape nuevo"),
) -> ScrapeResponse:
    try:
        raw = _service.run(
            query=body.query,
            city=body.city,
            max_age_hours=body.max_age_hours,
            force=force,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ScrapeResponse.model_validate(raw)


@router.get(
    "/scraping/queue",
    summary="Estado de la cola de scraping",
    description="Métricas de caché e inflight (útil para demo / monitoreo MVP).",
)
def scraping_queue_stats():
    return {"ok": True, **scrape_queue.stats()}
