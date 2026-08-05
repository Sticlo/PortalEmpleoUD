"""
Cliente DeepSeek — adaptar HV a una oferta usando solo skills reales.

Usa deepseek-v4-flash (más barato) con thinking desactivado para no gastar
tokens en chain-of-thought en una tarea de reescritura ATS.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import requests

from app.core.config import get_settings

log = logging.getLogger("bolsa-empleo.deepseek")


class DeepSeekError(Exception):
    pass


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

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        # V4 Flash tiene thinking ON por defecto → más output = más $
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    log.info(
        "DeepSeek request model=%s thinking=%s max_tokens=%s",
        settings.deepseek_model,
        thinking,
        max_tokens,
    )

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

    message = data["choices"][0]["message"]
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
