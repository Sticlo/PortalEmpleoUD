from typing import List, Optional

from pydantic import BaseModel, Field


class StudentProfile(BaseModel):
    """Modelo de dominio — perfil maestro del estudiante (fuente de verdad para HV)."""

    full_name: str
    program_slug: str = "ingenieria-de-sistemas"
    semester: Optional[int] = None
    email: Optional[str] = None
    city: str = "Bogotá"
    skills: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    experience: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
