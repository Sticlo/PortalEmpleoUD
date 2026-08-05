"""Controller (MVC) — Programas curriculares."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()

PROGRAMS = [
    {
        "slug": "ingenieria-de-sistemas",
        "name": "Ingeniería de Sistemas",
        "faculty": "Facultad de Ingeniería",
        "active_in_mvp": True,
    },
]


@router.get(
    "/programs",
    summary="Listar programas académicos",
    description="En el MVP solo está activo Ingeniería de Sistemas.",
)
def list_programs(only_mvp: bool = True):
    s = get_settings()
    items = PROGRAMS
    if only_mvp:
        items = [p for p in items if p["slug"] == s.default_program_slug]
    return {"tenant": s.default_tenant_slug, "programs": items}
