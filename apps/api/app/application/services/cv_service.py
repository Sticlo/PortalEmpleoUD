"""Servicio de HV — adapta con DeepSeek (o fallback local) sin inventar experiencia."""

from __future__ import annotations

import re
from typing import List

from fastapi import HTTPException

from app.core.config import get_settings
from app.domain.models.student import StudentProfile
from app.domain.schemas.api import AdaptCvRequest, AdaptCvResponse
from app.infrastructure.ai.deepseek import DeepSeekError, chat, parse_json
from app.infrastructure.persistence import memory as store

SYSTEM_PROMPT = """Eres un asistente de empleabilidad de la Universidad Distrital (Bogotá).
Tu trabajo: reescribir una hoja de vida ATS a partir del PERFIL REAL del estudiante
y el texto de UNA oferta de empleo.

Reglas estrictas:
- NO inventes empresas, cargos, fechas, skills ni logros que no estén en el perfil.
- Sí puedes reordenar, enfatizar y usar el vocabulario de la oferta cuando haya match real.
- Si un requisito no está en el perfil, no lo agregues; menciónalo en "notes".
- Formato ATS: texto limpio, una columna, secciones claras (Perfil, Skills, Experiencia, Proyectos, Educación).
- Idioma: español.
- Responde SOLO JSON: {"cv_text": "...", "notes": "..."}
"""

COMMON_REQS = [
    "docker",
    "kubernetes",
    "react",
    "angular",
    "java",
    "spring",
    "aws",
    "azure",
    "linux",
    "node",
    "typescript",
    "power bi",
    "kafka",
    "mongodb",
]


def _norm(text: str) -> str:
    return (text or "").lower()


def _local_adapt(profile: StudentProfile, body: AdaptCvRequest) -> AdaptCvResponse:
    """Fallback determinista cuando no hay DEEPSEEK_API_KEY — nunca inventa."""
    skills = [s for s in profile.skills if s.strip()]
    hay = _norm(
        f"{body.offer_title} {body.offer_description} {body.offer_requirements or ''}"
    )
    matched = [s for s in skills if _norm(s) in hay or any(
        tok in hay for tok in re.split(r"[\s/,\-]+", _norm(s)) if len(tok) >= 3
    )]
    missing = [
        req
        for req in COMMON_REQS
        if req in hay
        and not any(req in _norm(s) or _norm(s) in req for s in skills)
    ]

    lines: List[str] = [
        "PERFIL",
        (
            f"Estudiante de {profile.program_slug.replace('-', ' ').title()}"
            + (f" (semestre {profile.semester})" if profile.semester else "")
            + f" · {profile.city}."
        ),
        (
            f"Interés en la vacante «{body.offer_title}»"
            + (f" en {body.offer_company}." if body.offer_company else ".")
        ),
        "",
        "SKILLS",
        ", ".join(skills) if skills else "(sin skills declaradas en la HV)",
        "",
        "EXPERIENCIA / LOGROS",
    ]
    if profile.experience:
        lines.extend(f"• {e}" for e in profile.experience)
    else:
        lines.append("• (sin experiencia declarada — no se inventa)")

    if profile.projects:
        lines.extend(["", "PROYECTOS"])
        lines.extend(f"• {p}" for p in profile.projects)

    lines.extend(["", "EDUCACIÓN"])
    if profile.education:
        lines.extend(f"• {e}" for e in profile.education)
    else:
        lines.append("• Universidad Distrital Francisco José de Caldas")

    if matched:
        lines.extend(
            [
                "",
                "ENFATIZADO PARA ESTA OFERTA",
                "• Skills con match real: " + ", ".join(matched),
            ]
        )

    notes = (
        f"La oferta menciona {', '.join(missing)} y no está en tu HV — no lo inventamos."
        if missing
        else "Sin gaps críticos respecto a tu HV."
    )
    return AdaptCvResponse(cv_text="\n".join(lines).strip(), notes=notes)


class CvService:
    def adapt(self, body: AdaptCvRequest) -> AdaptCvResponse:
        profile = store.get_profile(body.student_id)
        if not profile:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Primero guarda el perfil del estudiante (skills). "
                    "Sin perfil no se genera HV."
                ),
            )

        settings = get_settings()
        if not settings.deepseek_api_key:
            return _local_adapt(profile, body)

        user_payload = {
            "perfil": profile.model_dump(),
            "oferta": {
                "titulo": body.offer_title,
                "empresa": body.offer_company,
                "descripcion": body.offer_description,
                "requisitos": body.offer_requirements,
                "ciudad_contexto": settings.default_city,
                "programa_contexto": settings.default_program_slug,
            },
        }

        try:
            raw = chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Adapta la HV con estos datos (JSON). "
                            f"No inventes nada fuera del perfil:\n{user_payload}"
                        ),
                    },
                ],
                temperature=0.2,
                json_mode=True,
            )
        except DeepSeekError:
            # Si DeepSeek falla, no rompemos el flujo del estudiante
            return _local_adapt(profile, body)

        try:
            data = parse_json(raw)
        except Exception:
            return _local_adapt(profile, body)

        return AdaptCvResponse(
            cv_text=data.get("cv_text", raw),
            notes=data.get("notes", ""),
        )
