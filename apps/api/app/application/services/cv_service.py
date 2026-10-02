"""Servicio de HV — adapta con DeepSeek Flash + Ojo (afinidad / gaps)."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional, Tuple

from fastapi import HTTPException

from app.application.services.ai_quota_service import ai_quota
from app.core.config import get_settings
from app.domain.models.student import StudentProfile
from app.domain.schemas.api import AdaptCvRequest, AdaptCvResponse
from app.infrastructure.ai.deepseek import CHEAPEST_MODEL, DeepSeekError, chat, parse_json
from app.infrastructure.persistence import memory as store

log = logging.getLogger("bolsa-empleo.cv")

SYSTEM_PROMPT = """Eres un asistente de empleabilidad de la Universidad Distrital (Bogotá).
Tu trabajo tiene DOS partes:
1) Reescribir una hoja de vida ATS con el PERFIL REAL del estudiante y UNA oferta.
2) Analizar afinidad y gaps (el "Ojo") con detalle útil para el estudiante.

Reglas estrictas del CV:
- NO inventes empresas, cargos, fechas, skills, proyectos ni logros que no estén en el perfil.
- Sí puedes reordenar, enfatizar y usar el vocabulario de la oferta cuando haya match real.
- Si un requisito no está en el perfil, NO lo agregues al CV; va en missing_skills / notes.
- Formato ATS: texto limpio, una columna, secciones (Perfil, Skills, Experiencia, Proyectos, Educación, Idiomas).
- Idioma: español. cv_text máx ~450 palabras.

Reglas del Ojo (análisis):
- affinity_score: entero 0–100 según overlap real (skills + experiencia + carrera vs oferta). Sé honesto.
- Si la carrera del estudiante NO encaja con el área de la oferta (ej. Sistemas vs Ingeniería Civil),
  affinity_score DEBE ser bajo (máx 22). Explica el choque en notes; NO inventes fit.
- matched_skills: solo skills del perfil que aparecen (o equivalen) en la oferta.
- missing_skills: requisitos claros de la oferta que NO están en el perfil (máx 8).
- strengths: 2–4 frases cortas de por qué SÍ encaja (solo con evidencia del perfil).
  Si hay choque de carrera, di que igual puede preparar el CV y el Ojo avisa.
- notes: párrafo claro: afinidad + choque de carrera si aplica + qué falta + tip (sin inventar).

Responde SOLO JSON:
{
  "cv_text": "...",
  "notes": "...",
  "affinity_score": 0,
  "matched_skills": ["..."],
  "missing_skills": ["..."],
  "strengths": ["..."]
}
"""

COMMON_REQS = [
    "docker",
    "kubernetes",
    "react",
    "angular",
    "java",
    "spring",
    "spring boot",
    "aws",
    "azure",
    "linux",
    "node",
    "nodejs",
    "typescript",
    "javascript",
    "python",
    "c#",
    ".net",
    "sql",
    "sql server",
    "postgresql",
    "mongodb",
    "power bi",
    "kafka",
    "git",
    "api",
    "microservicios",
    "express",
]

_CONTACT_PREFIXES = ("direccion", "tel:", "link:")


def _is_contact_line(text: str) -> bool:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().strip().lower()
    return plain.startswith(_CONTACT_PREFIXES)

CAREER_PATTERNS = {
    "civil": [r"civil", r"estructur", r"cimentac", r"obra\b", r"residente", r"topograf", r"vial"],
    "electronica": [r"electr[oó]n", r"\biot\b", r"embebido", r"hardware", r"circuito"],
    "forestal": [r"forestal", r"ecol[oó]g", r"silvicult", r"ambiental"],
    "quimica": [r"qu[ií]mic", r"laboratorio", r"procesos qu[ií]m"],
    "industrial": [r"industrial", r"log[ií]stica", r"producci[oó]n", r"calidad"],
    "artes": [r"artes", r"docente", r"expresi[oó]n", r"taller art"],
    "sistemas": [
        r"sistema",
        r"software",
        r"desarroll",
        r"programad",
        r"backend",
        r"frontend",
        r"full\s*stack",
        r"\bqa\b",
        r"datos",
        r"data",
        r"devops",
        r"inform[aá]tica",
        r"computaci",
    ],
}

CAREER_LABELS = {
    "civil": "Ingeniería Civil",
    "electronica": "Electrónica",
    "forestal": "Forestal / ambiental",
    "quimica": "Química",
    "industrial": "Industrial",
    "artes": "Artes",
    "sistemas": "Sistemas / software",
    "otra": "otra área",
}


def _norm(text: str) -> str:
    return (text or "").lower()


def _detect_career(blob: str) -> str:
    text = _norm(blob)
    # civil / otras ingenierías primero para no confundir con "sistemas"
    for family in ("civil", "electronica", "forestal", "quimica", "artes", "industrial", "sistemas"):
        for pat in CAREER_PATTERNS[family]:
            if re.search(pat, text):
                return family
    return "otra"


def _profile_career(profile: StudentProfile) -> str:
    prog = _norm(profile.program_slug.replace("-", " "))
    edu = _norm(" ".join(profile.education))
    skills = _norm(" ".join(profile.skills))
    blob = f"{prog} {edu} {skills}"

    if re.search(r"civil", prog):
        return "civil"
    if re.search(r"electr", prog):
        return "electronica"
    if re.search(r"forestal|ambiental", prog):
        return "forestal"
    if re.search(r"qu[ií]mic", prog):
        return "quimica"
    if re.search(r"industrial", prog):
        return "industrial"
    if re.search(r"artes|licenciatura", prog):
        return "artes"
    if re.search(r"sistema|software|datos|telem[aá]tica|inform[aá]tica", prog):
        return "sistemas"
    if re.search(r"python|angular|java|react|\.net|sql|node", skills):
        return "sistemas"
    return _detect_career(blob)


def _analyze(profile: StudentProfile, body: AdaptCvRequest) -> Tuple[int, List[str], List[str], List[str], str]:
    skills = [s for s in profile.skills if s.strip()]
    hay = _norm(
        f"{body.offer_title} {body.offer_description} {body.offer_requirements or ''}"
    )
    exp_blob = _norm(" ".join(profile.experience + profile.projects + profile.education))
    offer_career = _detect_career(hay)
    profile_career = _profile_career(profile)
    career_mismatch = (
        offer_career != "otra"
        and profile_career != "otra"
        and offer_career != profile_career
    )

    matched: List[str] = []
    for s in skills:
        sn = _norm(s)
        tokens = [t for t in re.split(r"[\s/,\-+#.]+", sn) if len(t) >= 2]
        if sn in hay or any(tok in hay for tok in tokens if len(tok) >= 3):
            matched.append(s)

    missing: List[str] = []
    for req in COMMON_REQS:
        if req not in hay:
            continue
        if any(req in _norm(s) or _norm(s) in req for s in skills):
            continue
        if req in exp_blob:
            continue
        label = req.upper() if req in ("sql", "api", "aws", "c#", ".net") else req.title()
        if req == "sql server":
            label = "SQL Server"
        if req == "spring boot":
            label = "Spring Boot"
        if req == "nodejs":
            label = "Node.js"
        if label not in missing:
            missing.append(label)

    ratio = len(matched) / max(len(skills), 1) if skills else 0.0

    if career_mismatch:
        # Civil vs sistemas → % bajo y honesto (no ~45%)
        score = min(22, max(8, int(8 + ratio * 14)))
    elif skills:
        score = int(40 + ratio * 55)
        if profile.experience:
            score = min(95, score + 5)
        if missing:
            score = max(25, score - min(20, len(missing) * 3))
        else:
            score = min(95, score + 5)
    else:
        score = 40

    strengths: List[str] = []
    if career_mismatch:
        strengths.append(
            "Puedes preparar el CV igual; el Ojo te avisa que el área de la oferta no es la tuya."
        )
    if matched and not career_mismatch:
        strengths.append(f"Encajas en: {', '.join(matched[:6])}.")
    elif matched and career_mismatch:
        strengths.append(
            f"Hay overlap superficial en: {', '.join(matched[:4])} — no alcanza para un buen encaje de carrera."
        )
    if profile.experience and not career_mismatch:
        strengths.append("Ya tienes experiencia declarada que puedes enfatizar en la postulación.")
    if profile.projects and not career_mismatch:
        strengths.append("Tus proyectos académicos refuerzan el perfil técnico.")
    if not strengths:
        strengths.append("Completa más skills y logros en tu HV para subir la afinidad.")

    career_note = ""
    if career_mismatch:
        career_note = (
            f"Esta vacante apunta a {CAREER_LABELS[offer_career]}, y tu HV es de "
            f"{CAREER_LABELS[profile_career]}. El encaje bajo es intencional: puedes preparar el CV, "
            f"pero el perfil no es el natural para esta oferta. "
        )

    if career_mismatch:
        notes = (
            f"{career_note}Afinidad estimada {score}%. "
            f"No inventamos experiencia de {CAREER_LABELS[offer_career]} que no está en tu HV. "
            f"Tip: prioriza ofertas alineadas a {CAREER_LABELS[profile_career]}."
        )
    elif missing:
        notes = (
            f"Afinidad estimada {score}%. Te alineas bien en {', '.join(matched[:4]) or 'lo básico'}. "
            f"Te falta declarar (y no inventamos): {', '.join(missing)}. "
            f"Tip: si sí los conoces, agrégalos a tu HV antes de postular; si no, sé transparente en la entrevista."
        )
    else:
        notes = (
            f"Afinidad estimada {score}%. No vimos gaps críticos entre tu HV y esta oferta. "
            f"Enfatiza {', '.join(matched[:5]) or 'tu experiencia'} al postular."
        )

    return score, matched, missing, strengths, notes


def _local_adapt(profile: StudentProfile, body: AdaptCvRequest) -> AdaptCvResponse:
    skills = [s for s in profile.skills if s.strip()]
    score, matched, missing, strengths, notes = _analyze(profile, body)

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

    return AdaptCvResponse(
        cv_text="\n".join(lines).strip(),
        notes=notes,
        affinity_score=score,
        matched_skills=matched,
        missing_skills=missing,
        strengths=strengths,
        provider="local",
        model=None,
    )


def _clamp_score(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, n))


class CvService:
    def adapt(self, body: AdaptCvRequest, client_ip: Optional[str] = None) -> AdaptCvResponse:
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
        # Análisis local siempre (base honesta); DeepSeek puede enriquecer notes
        local = _local_adapt(profile, body)

        if not settings.deepseek_api_key:
            log.warning("Sin DEEPSEEK_API_KEY — usando adaptador local")
            return local

        if not body.ai_consent:
            return local

        allowed, reason = ai_quota.try_acquire(client_ip)
        if not allowed:
            log.warning("Cuota DeepSeek agotada (ip=%s) — adaptador local", client_ip)
            local.notes = f"{reason} {local.notes}".strip()
            return local

        desc = (body.offer_description or "").strip()
        if len(desc) > 2500:
            desc = desc[:2500] + "…"

        # Minimización (Ley 1581): a DeepSeek no van nombre, correo, teléfono, dirección ni enlaces.
        education = [e for e in (profile.education or []) if not _is_contact_line(e)]
        user_payload = {
            "perfil": {
                "carrera": profile.program_slug,
                "semestre": profile.semester,
                "ciudad": profile.city,
                "skills": (profile.skills or [])[:20],
                "proyectos": (profile.projects or [])[:6],
                "experiencia": (profile.experience or [])[:6],
                "educacion": education[:4],
                "idiomas": (profile.languages or [])[:6],
            },
            "oferta": {
                "titulo": body.offer_title,
                "empresa": body.offer_company,
                "descripcion": desc,
            },
            "analisis_previo": {
                "affinity_score_sugerido": local.affinity_score,
                "matched_skills": local.matched_skills,
                "missing_skills": local.missing_skills,
            },
        }

        try:
            raw = chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Adapta la HV y completa el Ojo (afinidad + gaps). "
                            "No inventes nada fuera del perfil. "
                            f"Datos:\n{user_payload}"
                        ),
                    },
                ],
                temperature=0.2,
                json_mode=True,
                max_tokens=900,
                thinking=False,
            )
        except DeepSeekError as exc:
            log.exception("DeepSeek falló, fallback local: %s", exc)
            local.notes = f"{local.notes}"
            return local

        try:
            data = parse_json(raw)
        except Exception:
            log.exception("JSON inválido de DeepSeek, fallback local")
            return local

        matched = data.get("matched_skills") or local.matched_skills
        missing = data.get("missing_skills") or local.missing_skills
        strengths = data.get("strengths") or local.strengths
        if not isinstance(matched, list):
            matched = local.matched_skills
        if not isinstance(missing, list):
            missing = local.missing_skills
        if not isinstance(strengths, list):
            strengths = local.strengths

        score = _clamp_score(data.get("affinity_score", local.affinity_score))
        notes = (data.get("notes") or local.notes or "").strip()
        # Choque de carrera: score bajo + notes del Ojo locales si el modelo no lo menciona
        if local.affinity_score <= 22:
            score = min(score, local.affinity_score)
            low = notes.lower()
            if "apunta" not in low and "carrera" not in low and "área" not in low:
                notes = f"{local.notes} {notes}".strip()
            if strengths and not any("preparar el cv" in str(s).lower() for s in strengths):
                strengths = list(local.strengths)[:1] + list(strengths)

        return AdaptCvResponse(
            cv_text=data.get("cv_text") or local.cv_text,
            notes=notes,
            affinity_score=score,
            matched_skills=[str(x).strip() for x in matched if str(x).strip()][:12],
            missing_skills=[str(x).strip() for x in missing if str(x).strip()][:10],
            strengths=[str(x).strip() for x in strengths if str(x).strip()][:5],
            provider="deepseek",
            model=CHEAPEST_MODEL,
        )
