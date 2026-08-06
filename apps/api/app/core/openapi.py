"""
Metadatos OpenAPI / Swagger UI.

Docs interactivas: http://127.0.0.1:8000/docs
Esquema JSON:     http://127.0.0.1:8000/openapi.json
"""

from typing import Any, Dict, List

API_DESCRIPTION = """
## Bolsa de Empleo UD (RutaUD)

API del MVP de empleabilidad para **Universidad Distrital** · Ingeniería de Sistemas · Bogotá.

### Flujo típico
1. `POST /api/v1/scraping/run` con `query` (palabra clave) → trae ofertas ≤24 h desde Computrabajo.
2. `GET /api/v1/offers` → lista en memoria (purga automática de ofertas viejas).
3. `POST /api/v1/cv/adapt` → adapta HV a una oferta (DeepSeek cuando hay API key).

### Reglas
- Ofertas con más de **24 horas** se **eliminan** (no se archivan).
- Ciudad por defecto: **Bogotá**.
- Scrapers legacy (`flores.py`) no se usan en este endpoint; viven en `infrastructure/scraping/legacy/`.
"""

OPENAPI_TAGS: List[Dict[str, Any]] = [
    {
        "name": "health",
        "description": "Estado del servicio y configuración activa.",
    },
    {
        "name": "scraping",
        "description": (
            "Scrapers de portales con cola anti-stampede: caché compartida, "
            "single-flight y semáforo global (evita que N estudiantes saturen "
            "Computrabajo/Elempleo/LinkedIn). LinkedIn guest · bloqueo BairesDev."
        ),
    },
    {
        "name": "offers",
        "description": "CRUD/listado de ofertas en memoria. Purga automática >24 h.",
    },
    {
        "name": "cv",
        "description": "Adaptación de hoja de vida a una oferta (ATS, sin inventar experiencia).",
    },
    {
        "name": "students",
        "description": "Perfil / HV del estudiante.",
    },
    {
        "name": "programs",
        "description": "Programas académicos del tenant (piloto: Ingeniería de Sistemas).",
    },
    {
        "name": "tenants",
        "description": "Universidad / institución multi-tenant.",
    },
    {
        "name": "auth",
        "description": "Autenticación (esqueleto SSO / correo institucional).",
    },
    {
        "name": "stats",
        "description": (
            "Métricas de mercado para administrativos: demanda de skills según "
            "vacantes archivadas, tendencias y distribución por carrera/modalidad."
        ),
    },
]
