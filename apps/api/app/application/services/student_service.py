"""Servicio de estudiantes — perfil / skills."""

from typing import Optional

from app.domain.models.student import StudentProfile
from app.infrastructure.persistence import memory as store


class StudentService:
    def get_profile(self, student_id: str) -> Optional[StudentProfile]:
        return store.get_profile(student_id)

    def upsert_profile(self, student_id: str, profile: StudentProfile) -> StudentProfile:
        return store.save_profile(student_id, profile)
