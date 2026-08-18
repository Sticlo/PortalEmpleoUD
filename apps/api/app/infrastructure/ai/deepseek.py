"""
Cliente DeepSeek — adaptar HV a una oferta usando solo skills reales.

CRÍTICO (costo producción): el modelo está FIJO en código.
Nunca se lee DEEPSEEK_MODEL del entorno: un .env con v4-pro
o un deploy mal copiado no puede inflar la factura de miles de estudiantes.
Thinking siempre OFF (Flash lo activa por defecto y cobra output extra).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import requests

from app.core.config import get_settings

log = logging.getLogger("bolsa-empleo.deepseek")

# Único modelo permitido en RutaUD. No cambiar sin revisión de presupuesto.
CHEAPEST_MODEL = "deepseek-v4-flash"
_BLOCKED_MODELS = ("pro", "reasoner", "r1")


class DeepSeekError(Exception):
    pass


def locked_model() -> str:
    """Siempre Flash. Ignora env para no perder plata en producción."""
    return CHEAPEST_MODEL


def chat(
    messages: list[dict],
    temperature: float = 0.3,
    json_mode: bool = False,
    max_tokens: int = 1200,
    thinking: bool = False,
) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise DeepSeekError(
            "Falta DEEPSEEK_API_KEY. Configúrala en .env en la raíz del proyecto."
        )

    wanted = (settings.deepseek_model or "").strip().lower()
    if wanted and wanted != CHEAPEST_MODEL:
        log.warning(
            "DEEPSEEK_MODEL=%s ignorado. RutaUD fuerza %s (costo).",
            settings.deepseek_model,
            CHEAPEST_MODEL,
        )
    if any(part in wanted for part in _BLOCKED_MODELS):
        log.error(
            "Intento de modelo caro (%s) bloqueado. Usando %s.",
            settings.deepseek_model,
            CHEAPEST_MODEL,
        )

    model = CHEAPEST_MODEL
    # Thinking NUNCA en producción de HV: dispara tokens de salida.
    _ = thinking

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": min(int(max_tokens), 900),
        # Docs oficiales: thinking.type default = enabled (caro).
        "thinking": {"type": "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    log.info("DeepSeek request model=%s thinking=disabled max_tokens=%s", model, max_tokens)

    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise DeepSeekError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    usage = data.get("usage") or {}
    if usage:
        log.info(
            "DeepSeek usage prompt=%s completion=%s total=%s",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        )
    used = (data.get("model") or model).lower()
    if "pro" in used or "reasoner" in used:
        raise DeepSeekError(
            f"DeepSeek respondió con modelo caro ({data.get('model')}). Abortado."
        )

    message = data["choices"][0]["message"]
    reasoning = (message.get("reasoning_content") or "").strip()
    details = (usage.get("completion_tokens_details") or {}) if usage else {}
    reasoning_tok = int(details.get("reasoning_tokens") or 0)
    if reasoning or reasoning_tok:
        log.error(
            "DeepSeek thinking SIGUE activo (reasoning_tokens=%s). Revisar payload.",
            reasoning_tok,
        )
    content: Optional[str] = message.get("content")
    if not content:
        raise DeepSeekError("DeepSeek devolvió content vacío")
    return content.strip()


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
