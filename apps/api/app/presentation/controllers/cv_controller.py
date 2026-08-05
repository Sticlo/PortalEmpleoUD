"""Controller (MVC) — Adaptación de HV."""

from fastapi import APIRouter

from app.application.services.cv_service import CvService
from app.domain.schemas.api import AdaptCvRequest, AdaptCvResponse

router = APIRouter()
_service = CvService()


@router.post(
    "/cv/adapt",
    response_model=AdaptCvResponse,
    summary="Adaptar HV a una oferta",
    description=(
        "Genera texto de CV ATS a partir del perfil del estudiante y la oferta. "
        "No inventa experiencia: solo reordena/enfatiza lo declarado en la HV."
    ),
)
def adapt_cv(body: AdaptCvRequest):
    return _service.adapt(body)
