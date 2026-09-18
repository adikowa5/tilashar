"""Движок SQLAlchemy, фабрика сессий и базовый класс моделей."""

from collections.abc import Iterator
from typing import Any

import os

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Базовый декларативный класс для всех моделей."""


def build_engine(url: str) -> Any:
    """Создаёт движок. Для SQLite добавляет check_same_thread=False (нужно TestClient'у)."""
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    # На Vercel каждый вызов функции живёт отдельно: пул соединений там вреден,
    # соединения держит пулер Neon на стороне базы.
    if os.environ.get("VERCEL"):
        return create_engine(
            url, poolclass=NullPool, pool_pre_ping=True, future=True, connect_args=connect_args
        )
    return create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def session_scope() -> Iterator[Session]:
    """Отдаёт сессию и гарантированно закрывает её. Используется зависимостью get_db."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
