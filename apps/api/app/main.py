"""
Bolsa de Empleo UD — API
Arquitectura por capas + MVC.

Presentation (Controllers) → Application (Services) → Domain (Models)
                                              ↓
                                     Infrastructure (AI, DB, Scrapers)

Swagger UI:  /docs
ReDoc:       /redoc
OpenAPI JSON: /openapi.json
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.openapi import API_DESCRIPTION, OPENAPI_TAGS
from app.domain.schemas.api import HealthResponse
from app.presentation.controllers.auth_controller import router as auth_router
from app.presentation.controllers.cv_controller import router as cv_router
from app.presentation.controllers.offers_controller import router as offers_router
from app.presentation.controllers.programs_controller import router as programs_router
from app.presentation.controllers.scraping_controller import router as scraping_router
from app.presentation.controllers.stats_controller import router as stats_router
from app.presentation.controllers.students_controller import router as students_router
from app.presentation.controllers.tenants_controller import router as tenants_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=API_DESCRIPTION,
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "Bolsa de Empleo UD / RutaUD",
        "url": "https://www.udistrital.edu.co",
    },
    license_info={"name": "Uso interno institucional"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# JSON más liviano en picos (ofertas/métricas)
app.add_middleware(GZipMiddleware, minimum_size=800)

prefix = settings.api_prefix
app.include_router(tenants_router, prefix=prefix, tags=["tenants"])
app.include_router(programs_router, prefix=prefix, tags=["programs"])
app.include_router(students_router, prefix=prefix, tags=["students"])
app.include_router(offers_router, prefix=prefix, tags=["offers"])
app.include_router(cv_router, prefix=prefix, tags=["cv"])
app.include_router(auth_router, prefix=prefix, tags=["auth"])
app.include_router(scraping_router, prefix=prefix, tags=["scraping"])
app.include_router(stats_router, prefix=prefix, tags=["stats"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    response_model=HealthResponse,
)
def health():
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        architecture="layered-mvc",
        tenant=settings.default_tenant_slug,
        city=settings.default_city,
        program=settings.default_program_slug,
        max_offer_age_hours=settings.max_offer_age_hours,
        scraper_legacy="app/infrastructure/scraping/legacy/flores.py",
        docs="/docs",
    )
