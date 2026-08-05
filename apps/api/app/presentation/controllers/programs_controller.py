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
    {
        "slug": "ingenieria-civil",
        "name": "Ingeniería Civil",
        "faculty": "Facultad de Ingeniería",
        "active_in_mvp": True,
    },
    {
        "slug": "ingenieria-electronica",
        "name": "Ingeniería Electrónica",
        "faculty": "Facultad de Ingeniería",
        "active_in_mvp": True,
    },
    {
        "slug": "ingenieria-forestal",
        "name": "Ingeniería Forestal",
        "faculty": "Facultad del Medio Ambiente",
        "active_in_mvp": True,
    },
    {
        "slug": "ingenieria-quimica",
        "name": "Ingeniería Química",
        "faculty": "Facultad de Ingeniería",
        "active_in_mvp": True,
    },
    {
        "slug": "ingenieria-industrial",
        "name": "Ingeniería Industrial",
        "faculty": "Facultad de Ingeniería",
        "active_in_mvp": True,
    },
    {
        "slug": "licenciatura-en-artes",
        "name": "Licenciatura en Artes",
        "faculty": "Facultad de Artes",
        "active_in_mvp": True,
    },
]


@router.get(
    "/programs",
    summary="Listar programas académicos",
    description="Programas visibles en Empleos de hoy y publicación de empresas.",
)
def list_programs(only_mvp: bool = False):
    s = get_settings()
    items = PROGRAMS
    if only_mvp:
        items = [p for p in items if p.get("active_in_mvp")]
    return {"tenant": s.default_tenant_slug, "programs": items}
