"""Controller (MVC) — Estudiantes / perfil."""

from fastapi import APIRouter

from app.application.services.student_service import StudentService
from app.domain.models.student import StudentProfile

router = APIRouter()
_service = StudentService()


@router.put(
    "/students/{student_id}/profile",
    summary="Guardar / actualizar HV",
)
def upsert_profile(student_id: str, profile: StudentProfile):
    saved = _service.upsert_profile(student_id, profile)
    return {"student_id": student_id, "profile": saved}


@router.get(
    "/students/{student_id}/profile",
    summary="Obtener HV del estudiante",
)
def get_profile(student_id: str):
    profile = _service.get_profile(student_id)
    return {"student_id": student_id, "profile": profile}


@router.delete(
    "/students/{student_id}/profile",
    summary="Borrar HV del estudiante",
    description="Derecho de supresión (Ley 1581 de 2012): elimina el perfil guardado en el servidor.",
)
def delete_profile(student_id: str):
    deleted = _service.delete_profile(student_id)
    return {"student_id": student_id, "deleted": deleted}
