"""Точка входа FastAPI: сборка приложения, CORS, роутеры, статика и служебные ручки."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.config import settings
from app.db import SessionLocal
from app.routers import auth, children, content, lesson, me, voice
from app.schemas import ConfigOut, HealthOut

logging.basicConfig(level=logging.INFO)

API_PREFIX = "/api/v1"


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

    for module in (auth, me, children, content, lesson, voice):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.exception_handler(RequestValidationError)
    def _validation_handler(_request, _exc: RequestValidationError) -> JSONResponse:
        """Приводит 422 к формату контракта: {"detail": "<code>"}."""
        return JSONResponse(status_code=422, content={"detail": "validation_error"})

    @app.get("/health", response_model=HealthOut, tags=["service"])
    def health() -> HealthOut:
        """Проверка живости процесса и доступности БД."""
        db_status = "ok"
        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — health не должен падать, только сообщать
            db_status = "error"
        return HealthOut(status="ok", db=db_status)

    @app.get(f"{API_PREFIX}/config", response_model=ConfigOut, tags=["service"])
    def read_config() -> ConfigOut:
        """Публичные настройки, которые нужны клиенту до логина."""
        return ConfigOut(
            sms_provider=settings.sms_provider,
            dev_mode=settings.dev_mode,
            max_children=settings.max_children,
            version=__version__,
        )

    return app


app = create_app()
