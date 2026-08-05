from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Offer(BaseModel):
    """Modelo de dominio — oferta de empleo."""

    id: str
    title: str
    company: str
    city: str = "Bogotá"
    modality: str = "hibrido"  # presencial | hibrido | remoto
    source: str = "manual"
    url: Optional[str] = None
    published_at: datetime
    description: str = ""
    salary: Optional[str] = None
    program_tags: List[str] = Field(default_factory=list)
    # Conteo público de postulantes cuando el portal lo muestra (LinkedIn a veces).
    # Computrabajo/Elempleo casi nunca lo publican sin cuenta empresa → None.
    applicants: Optional[int] = Field(
        default=None,
        description="Postulantes reportados por el portal, si es público",
    )
