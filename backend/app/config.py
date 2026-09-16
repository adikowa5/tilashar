"""Настройки приложения, читаются из переменных окружения."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация сервиса. Все поля берутся из env (регистр не важен)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Подключение к БД: postgresql+psycopg://... в проде, sqlite:///... в тестах.
    database_url: str = "postgresql+psycopg://tilashar:tilashar@localhost:5432/tilashar"

    # Секрет для подписи JWT и для HMAC-хеша SMS-кодов.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 30
    refresh_ttl_days: int = 30

    # Отправка SMS: console пишет код в лог, mobizon ходит во внешний API.
    sms_provider: Literal["console", "mobizon"] = "console"
    mobizon_api_key: str = ""
    mobizon_base_url: str = "https://api.mobizon.kz"

    # Каталог, куда складываются родительские записи голоса.
    media_root: str = "/data/media"

    max_children: int = 4

    # Лимиты на выдачу и ввод SMS-кода.
    code_ttl_sec: int = 300
    code_retry_after_sec: int = 60
    code_requests_per_hour: int = 5
    code_max_attempts: int = 5

    # Урок дня.
    lesson_size: int = 8

    # Голосовые записи.
    max_voice_bytes: int = 2 * 1024 * 1024

    # CORS: список через запятую либо "*".
    cors_origins: str = "*"

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return value.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        """Разбирает CORS_ORIGINS в список источников для middleware."""
        if self.cors_origins in ("", "*"):
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def dev_mode(self) -> bool:
        """В dev-режиме код подтверждения фиксированный и возвращается клиенту."""
        return self.sms_provider == "console"


@lru_cache
def get_settings() -> Settings:
    """Синглтон настроек (кешируется, чтобы не перечитывать env на каждый запрос)."""
    return Settings()


settings = get_settings()
