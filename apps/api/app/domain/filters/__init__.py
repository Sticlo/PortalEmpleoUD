"""Filtros de dominio (spam, calidad)."""

from app.domain.filters.blocked_companies import (
    BLOCKED_COMPANIES,
    is_blocked_company,
    reject_blocked,
)

__all__ = ["BLOCKED_COMPANIES", "is_blocked_company", "reject_blocked"]
