"""Настройки приложения, читаются из переменных окружения."""

import os
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Локальная база для разработки — используется, только если ни одна переменная окружения не задана.
DEV_DATABASE_URL = "postgresql+psycopg://tilashar:tilashar@localhost:5432/tilashar"


class Settings(BaseSettings):
    """Конфигурация сервиса. Все поля берутся из env (регистр не важен)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Подключение к БД: postgresql+psycopg://... в проде, sqlite:///... в тестах.
    # Пусто по умолчанию: тогда валидатор успевает поискать строку в других переменных
    # (POSTGRES_URL и т.п.) и только потом подставить локальную базу для разработки.
    # validate_default=True обязателен: без него pydantic не прогоняет валидатор
    # по значению по умолчанию, и подстановка из других переменных не сработает.
    database_url: str = Field(default="", validate_default=True)

    # Секрет для подписи JWT.
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_ttl_min: int = 30
    # Входа по паролю нет, поэтому сессия устройства живёт долго и продлевается
    # при каждом обновлении токена: семья, открывающая приложение хоть раз в год, не теряется.
    refresh_ttl_days: int = 400

    max_children: int = 4

    # Ключ Pexels для поиска фотографий в редакторе. Пусто — поиск выключен.
    pexels_api_key: str = ""

    # Пароль автора (страница #author). Пусто — редактор выключен.
    admin_password: str = ""
    admin_ttl_hours: int = 12

    # Секрет ежедневной уборки: Vercel Cron присылает его в заголовке Authorization.
    cron_secret: str = ""

    # Ограничения частоты (на один IP-адрес).
    guest_per_hour: int = 20
    join_attempts_per_hour: int = 12
    admin_attempts_per_hour: int = 10

    # Уборка: семьи без единой попытки удаляются через inactive_empty_days без визитов,
    # любые семьи — через inactive_days.
    inactive_empty_days: int = 60
    inactive_days: int = 400

    # Урок дня.
    lesson_size: int = 8

    # Голосовые записи.
    max_voice_bytes: int = 2 * 1024 * 1024

    # CORS: список через запятую либо "*".
    cors_origins: str = "*"

    @model_validator(mode="before")
    @classmethod
    def _ignore_empty_env(cls, data: object) -> object:
        """Пустую переменную окружения считаем незаданной.

        Хостинги позволяют завести переменную без значения; pydantic на пустой
        строке падает («не число», «не console»), и приложение не стартует.
        Безопаснее взять значение по умолчанию.
        """
        if isinstance(data, dict):
            return {
                key: value
                for key, value in data.items()
                if not (isinstance(value, str) and not value.strip())
            }
        return data

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Приводит строку подключения к виду, который понимает SQLAlchemy.

        Хостинги (Vercel, Neon, Railway) выдают её как postgres:// или postgresql://
        и кладут то в DATABASE_URL, то в POSTGRES_URL. SQLAlchemy же ждёт явный драйвер.
        """
        url = (value or "").strip()
        if not url:
            for name in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "DATABASE_URL_UNPOOLED"):
                url = (os.environ.get(name) or "").strip()
                if url:
                    break
        if not url:
            url = DEV_DATABASE_URL
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

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
    def jwt_secret_is_default(self) -> bool:
        """Секрет не задан — подписи токенов можно подделать, редактор автора не включаем."""
        return self.jwt_secret in ("", "dev-secret-change-me") or len(self.jwt_secret) < 16

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_password) and not (self.jwt_secret_is_default and os.environ.get("VERCEL"))


@lru_cache
def get_settings() -> Settings:
    """Синглтон настроек (кешируется, чтобы не перечитывать env на каждый запрос)."""
    return Settings()


settings = get_settings()
