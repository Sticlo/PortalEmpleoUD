"""
Cliente DeepSeek — adaptar HV a una oferta usando solo skills reales.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.core.config import get_settings

log = logging.getLogger("bolsa-empleo.deepseek")


class DeepSeekError(Exception):
    pass


def chat(
    messages: list[dict],
    temperature: float = 0.3,
    json_mode: bool = False,
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
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise DeepSeekError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:400]}")

    return resp.json()["choices"][0]["message"]["content"].strip()


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
