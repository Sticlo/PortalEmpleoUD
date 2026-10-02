"""Cuota de uso de DeepSeek — tope global diario + tope diario por IP.

Protege el saldo prepagado: al superar cualquiera de los topes el CV se
genera con el adaptador local (sin IA) en vez de llamar a DeepSeek.
Contadores en memoria: se reinician a medianoche (hora Colombia) o al reiniciar la API.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from app.core.config import get_settings

# Colombia no tiene horario de verano: UTC-5 fijo.
_COLOMBIA_TZ = timezone(timedelta(hours=-5))


def _today() -> str:
    return datetime.now(_COLOMBIA_TZ).strftime("%Y-%m-%d")


class AiQuotaService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day = _today()
        self._total = 0
        self._per_ip: Dict[str, int] = {}

    def _roll_day(self) -> None:
        today = _today()
        if today != self._day:
            self._day = today
            self._total = 0
            self._per_ip.clear()

    def try_acquire(self, client_ip: Optional[str]) -> Tuple[bool, str]:
        """Reserva una llamada a DeepSeek. Devuelve (permitido, motivo_si_no)."""
        settings = get_settings()
        ip = client_ip or "desconocida"
        with self._lock:
            self._roll_day()
            if self._total >= settings.deepseek_daily_limit:
                return False, (
                    "La IA alcanzó su límite diario gratuito. "
                    "Este CV se generó en modo local; vuelve a intentarlo mañana para la versión con IA."
                )
            used_by_ip = self._per_ip.get(ip, 0)
            if used_by_ip >= settings.deepseek_daily_limit_per_ip:
                return False, (
                    f"Usaste tus {settings.deepseek_daily_limit_per_ip} adaptaciones con IA de hoy. "
                    "Este CV se generó en modo local; mañana se renueva tu cupo."
                )
            self._total += 1
            self._per_ip[ip] = used_by_ip + 1
            return True, ""

    def snapshot(self) -> dict:
        settings = get_settings()
        with self._lock:
            self._roll_day()
            return {
                "day": self._day,
                "used": self._total,
                "daily_limit": settings.deepseek_daily_limit,
                "per_ip_limit": settings.deepseek_daily_limit_per_ip,
                "unique_ips": len(self._per_ip),
            }


ai_quota = AiQuotaService()
