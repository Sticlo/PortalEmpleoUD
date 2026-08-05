"""Controller (MVC) — Tenants."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get(
    "/tenants/current",
    summary="Tenant activo",
    description="Universidad / institución configurada y reglas del MVP.",
)
def current_tenant():
    s = get_settings()
    return {
        "slug": s.default_tenant_slug,
        "name": "Universidad Distrital Francisco José de Caldas",
        "product_name": "RutaUD",
        "rules": {
            "default_city": s.default_city,
            "max_offer_age_hours": s.max_offer_age_hours,
            "prefer_modality": "hibrido",
            "active_program_slugs": [s.default_program_slug],
        },
    }
