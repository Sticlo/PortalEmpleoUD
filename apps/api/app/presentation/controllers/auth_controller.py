"""Controller (MVC) — Auth (esqueleto)."""

from fastapi import APIRouter

from app.domain.schemas.api import LoginRequest, LoginResponse

router = APIRouter()


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Login (placeholder)",
    description="Esqueleto. Más adelante: correo institucional / SSO UD.",
)
def login(body: LoginRequest):
    return LoginResponse(
        ok=True,
        message="Auth placeholder — conectar correo institucional / SSO UD",
        email=body.email,
        tenant="universidad-distrital",
    )
