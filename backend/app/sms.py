"""Отправка SMS с кодом подтверждения.

В dev-режиме код фиксированный (000000) и просто пишется в лог.
Для прода заготовлен отправитель через Mobizon; в тестах он не вызывается.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from app.config import Settings, settings

logger = logging.getLogger("tilashar.sms")

# Код, который выдаётся в dev-режиме. Никогда не используется при SMS_PROVIDER=mobizon.
DEV_CODE = "000000"


class SmsSender(Protocol):
    """Интерфейс отправителя SMS."""

    def send_code(self, phone: str, code: str) -> None:
        """Отправляет код на номер. Бросает исключение, если отправка не удалась."""
        ...


class ConsoleSender:
    """Пишет код в лог вместо отправки SMS. Используется в разработке и тестах."""

    def send_code(self, phone: str, code: str) -> None:
        logger.info("SMS (console) -> %s: код %s", phone, code)


class MobizonSender:
    """Отправка через Mobizon (https://mobizon.kz). Заготовка для прода."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def send_code(self, phone: str, code: str) -> None:
        url = f"{self._base_url}/service/message/sendSmsMessage"
        params = {"apiKey": self._api_key, "output": "json", "api": "v1"}
        data = {"recipient": phone, "text": f"Tilashar: код {code}"}
        response = httpx.post(url, params=params, data=data, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        # Mobizon отвечает 200 даже на логические ошибки, поэтому проверяем code внутри тела.
        if payload.get("code") != 0:
            raise RuntimeError(f"mobizon error: {payload!r}")


def build_sender(cfg: Settings | None = None) -> SmsSender:
    """Собирает отправителя по настройкам."""
    cfg = cfg or settings
    if cfg.sms_provider == "mobizon":
        return MobizonSender(cfg.mobizon_api_key, cfg.mobizon_base_url)
    return ConsoleSender()


def generate_code(cfg: Settings | None = None) -> str:
    """Возвращает код для отправки: фиксированный в dev, случайный в проде."""
    cfg = cfg or settings
    if cfg.dev_mode:
        return DEV_CODE
    import secrets

    return f"{secrets.randbelow(1_000_000):06d}"
