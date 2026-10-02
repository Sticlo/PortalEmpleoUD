"""Controller (MVC) — Adaptación de HV."""

from fastapi import APIRouter, Request

from app.application.services.ai_quota_service import ai_quota
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
        "No inventa experiencia: solo reordena/enfatiza lo declarado en la HV. "
        "Si se supera el tope diario de IA (global o por IP) responde en modo local."
    ),
)
def adapt_cv(body: AdaptCvRequest, request: Request):
    client_ip = request.client.host if request.client else None
    return _service.adapt(body, client_ip=client_ip)


@router.get(
    "/cv/quota",
    summary="Uso diario de la IA",
    description="Llamadas a DeepSeek usadas hoy frente a los topes configurados.",
)
def cv_quota():
    return ai_quota.snapshot()
