from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.domain.models.offer import Offer


class OfferListFilters(BaseModel):
    city: str = Field(..., examples=["Bogotá"])
    max_age_hours: int = Field(..., examples=[24])
    program_slug: str = Field(..., examples=["ingenieria-de-sistemas"])
    prefer_modality: str = Field(default="hibrido", examples=["hibrido"])


class OfferListResponse(BaseModel):
    filters: OfferListFilters
    count: int
    offers: List[Offer]
    purged: int = Field(
        default=0,
        description="Cantidad de ofertas borradas por superar max_age_hours",
    )


class OfferCreateResponse(BaseModel):
    ok: bool = True
    id: str
    message: str = ""


class CompanyOfferPublishRequest(BaseModel):
    """Formulario público empresa → oferta en RutaUD (sin auth todavía)."""

    title: str = Field(..., min_length=3, max_length=160, examples=["Practicante Backend Python"])
    company: str = Field(..., min_length=2, max_length=120, examples=["NexPay Fintech"])
    description: str = Field(..., min_length=20, examples=["Buscamos estudiante de Sistemas…"])
    salary: Optional[str] = Field(default=None, examples=["$1.500.000 (Mensual)"])
    city: str = Field(default="Bogotá", examples=["Bogotá"])
    modality: str = Field(
        default="hibrido",
        examples=["hibrido"],
        description="presencial | hibrido | remoto",
    )
    contact_email: Optional[str] = Field(default=None, examples=["talento@empresa.com"])
    apply_url: Optional[str] = Field(default=None, examples=["https://empresa.com/carreras"])
    program_slug: str = Field(
        default="ingenieria-de-sistemas",
        examples=["ingenieria-de-sistemas"],
        description="Carrera UD a la que apunta la vacante",
    )


class ScrapeRequest(BaseModel):
    query: str = Field(
        default="desarrollador",
        description="Palabra clave de búsqueda en el portal",
        examples=["desarrollador python", "qa automation", "datos"],
    )
    city: Optional[str] = Field(default="Bogotá", examples=["Bogotá"])
    max_age_hours: Optional[int] = Field(
        default=24,
        ge=1,
        le=72,
        description="Descarta ofertas más viejas que este umbral (horas)",
    )


class ScrapeErrorItem(BaseModel):
    source: str
    error: str


class ScrapeResponse(BaseModel):
    query: str
    city: str
    max_age_hours: int
    scrapers: List[str]
    imported: int = Field(..., description="Ofertas nuevas importadas")
    blocked: int = Field(
        default=0,
        description="Ofertas descartadas por empresa bloqueada (ej. BairesDev)",
    )
    purged: int = Field(default=0, description="Ofertas eliminadas por > max_age_hours")
    per_source: Dict[str, int] = Field(default_factory=dict)
    errors: List[ScrapeErrorItem] = Field(default_factory=list)
    offers: List[Offer] = Field(default_factory=list)


class AdaptCvRequest(BaseModel):
    student_id: str = Field(..., examples=["demo-student"])
    offer_title: str
    offer_description: str
    offer_company: Optional[str] = None
    offer_requirements: Optional[str] = None


class AdaptCvResponse(BaseModel):
    cv_text: str
    notes: str = Field(
        default="",
        description="Qué se enfatizó / qué requisitos no cubre el perfil",
    )


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["estudiante@udistrital.edu.co"])


class LoginResponse(BaseModel):
    ok: bool
    message: str
    email: str
    tenant: str


class HealthResponse(BaseModel):
    status: str
    app: str
    architecture: str
    tenant: str
    city: str
    program: str
    max_offer_age_hours: int
    scraper_legacy: str
    docs: str = "/docs"
