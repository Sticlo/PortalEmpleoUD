"""
Settings de la Bolsa de Empleo UD.
Todo lo configurable por entorno vive aquí — no hardcodear ciudad/programa en servicios.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]  # bolsa-empleo-ud/


def _load_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    api_prefix: str
    default_tenant_slug: str
    default_city: str
    default_program_slug: str
    max_offer_age_hours: int
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    cv_generations_per_student_month: int
    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=_env("APP_NAME", "Bolsa de Empleo UD"),
        app_env=_env("APP_ENV", "development"),
        api_prefix=_env("API_PREFIX", "/api/v1"),
        default_tenant_slug=_env("DEFAULT_TENANT_SLUG", "universidad-distrital"),
        default_city=_env("DEFAULT_CITY", "Bogotá"),
        default_program_slug=_env(
            "DEFAULT_PROGRAM_SLUG", "ingenieria-de-sistemas"
        ),
        max_offer_age_hours=_env_int("MAX_OFFER_AGE_HOURS", 24),
        deepseek_api_key=_env("DEEPSEEK_API_KEY", ""),
        # Modelo caro NO se configura por env. El cliente fuerza deepseek-v4-flash.
        deepseek_model="deepseek-v4-flash",
        deepseek_base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        cv_generations_per_student_month=_env_int(
            "CV_GENERATIONS_PER_STUDENT_MONTH", 10
        ),
        database_url=_env("DATABASE_URL", "sqlite:///./data/bolsa_empleo.db"),
    )
