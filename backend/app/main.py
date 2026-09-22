"""Точка входа FastAPI: сборка приложения, CORS, роутеры, статика и служебные ручки."""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.config import settings
from app.db import SessionLocal
from app.routers import admin, auth, children, content, internal, lesson, me, voice
from app.schemas import ConfigOut, HealthOut

logging.basicConfig(level=logging.INFO)

API_PREFIX = "/api/v1"

SECRET_RE = re.compile(r"://[^/\s]*:[^/@\s]*@")


def dsn_shape() -> str:
    """Драйвер, база и замаскированный хост — чтобы понять, какую строку подключения увидел сервер."""
    try:
        from sqlalchemy.engine import make_url

        url = make_url(settings.database_url)
        host = url.host or "-"
        if len(host) > 10:
            host = f"{host[:3]}***{host[-12:]}"
        return f"{url.drivername} host={host} db={url.database or '-'}"
    except Exception:  # noqa: BLE001
        return "unparsable"


DB_ENV_NAMES = ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "DATABASE_URL_UNPOOLED")


def env_shape() -> str:
    """Какие переменные БД видит сервер (только имена, без значений), окружение и коммит."""
    import os

    seen = [name for name in DB_ENV_NAMES if (os.environ.get(name) or "").strip()]
    env = os.environ.get("VERCEL_ENV", "-")
    sha = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "-")[:7]
    # Похожие имена (с опечаткой, пробелом, другим регистром или пустым значением) — тоже только имена.
    similar = sorted(
        f"{name!r}{'' if (value or '').strip() else ':empty'}"
        for name, value in os.environ.items()
        if re.search(r"DATABASE|POSTGRES|NEON|^PG", name, re.IGNORECASE) and name not in seen
    )
    return (
        f"env={env} commit={sha} db_vars={','.join(seen) or 'none'}"
        f" similar={','.join(similar) or 'none'}"
    )


def safe_reason(exc: BaseException) -> str:
    """Короткое описание ошибки БД без логина и пароля — чтобы /health можно было открыть в браузере."""
    text_ = f"{type(exc).__name__}: {exc}".replace("\n", " ")
    text_ = SECRET_RE.sub("://***:***@", text_)
    return text_[:300]


def create_app() -> FastAPI:
    """Собирает приложение. Отдельная функция удобна для тестов и для uvicorn --factory."""
    app = FastAPI(title="Tilashar API", version=__version__, docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (auth, me, children, content, lesson, voice, admin, internal):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(content.files_router, prefix=API_PREFIX)

    @app.exception_handler(RequestValidationError)
    def _validation_handler(_request, _exc: RequestValidationError) -> JSONResponse:
        """Приводит 422 к формату контракта: {"detail": "<code>"}."""
        return JSONResponse(status_code=422, content={"detail": "validation_error"})

    @app.get("/health", response_model=HealthOut, tags=["service"])
    def health() -> HealthOut:
        """Проверка живости процесса и доступности БД."""
        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — health не должен падать, только сообщать
            logging.exception("health: база недоступна")
            return HealthOut(status="ok", db="error", reason=f"{env_shape()} | {dsn_shape()} | {safe_reason(exc)}")
        return HealthOut(status="ok", db="ok")

    @app.get(f"{API_PREFIX}/config", response_model=ConfigOut, tags=["service"])
    def read_config() -> ConfigOut:
        """Публичные настройки, которые нужны клиенту до логина."""
        return ConfigOut(
            max_children=settings.max_children,
            version=__version__,
        )

    return app


app = create_app()
