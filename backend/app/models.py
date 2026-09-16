"""ORM-модели. Типы намеренно портируемые: работают и в Postgres, и в SQLite.

UUID хранится строкой (36 символов), времена — naive UTC DateTime.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_uuid() -> str:
    """Новый идентификатор в виде строки (36 символов)."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Текущее UTC-время без таймзоны — единый формат хранения во всех таблицах."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Family(Base):
    """Семья — владелец детей, своих тем и родительских записей голоса."""

    __tablename__ = "families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_voice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    users: Mapped[list[User]] = relationship(back_populates="family")
    children: Mapped[list[Child]] = relationship(back_populates="family")


class User(Base):
    """Родитель. У гостевой семьи телефон пустой до вызова /auth/claim."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    family: Mapped[Family] = relationship(back_populates="users")


class Child(Base):
    """Ребёнок. Удаление мягкое: выставляется deleted_at, строки прогресса остаются."""

    __tablename__ = "children"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    avatar: Mapped[str] = mapped_column(String(32), nullable=False, default="fox")
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="kk")
    stars_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    family: Mapped[Family] = relationship(back_populates="children")


class AuthCode(Base):
    """Одноразовый SMS-код. Хранится только HMAC-хеш, сам код в БД не попадает."""

    __tablename__ = "auth_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RefreshToken(Base):
    """Выданный refresh-токен. Ротация: старая запись помечается revoked_at."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Topic(Base):
    """Тема. kind='builtin' — общая для всех, kind='family' — созданная семьёй."""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title_kk: Mapped[str] = mapped_column(String(128), nullable=False)
    title_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    pic: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="builtin")
    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    words: Mapped[list[Word]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", order_by="Word.order_index"
    )

    __table_args__ = (UniqueConstraint("slug", "family_id", name="uq_topics_slug_family"),)


class Word(Base):
    """Слово темы. pic — эмодзи, hex-цвет или цифра; audio_key — ключ в паке озвучки."""

    __tablename__ = "words"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    topic_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text_kk: Mapped[str] = mapped_column(String(64), nullable=False)
    text_ru: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    syllables: Mapped[str] = mapped_column(String(96), nullable=False, default="")
    pic: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    audio_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    topic: Mapped[Topic] = relationship(back_populates="words")


class Progress(Base):
    """Сводный прогресс ребёнка по слову: лучший результат и число попыток."""

    __tablename__ = "progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    best_stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("child_id", "word_id", name="uq_progress_child_word"),)


class Attempt(Base):
    """Одна попытка произнесения. Идемпотентность — по тройке (child_id, word_id, at)."""

    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heard: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="asr")
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("child_id", "word_id", "at", name="uq_attempts_child_word_at"),
    )


class LessonDay(Base):
    """День занятий ребёнка. Серия считается по дням с completed=True."""

    __tablename__ = "lesson_days"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # План дня, зафиксированный при первом обращении: JSON-список
    # [{"word_id": ..., "topic_slug": ..., "status": "new"|"review"}].
    # Хранится, чтобы состав урока не «плыл» по мере роста прогресса внутри дня.
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    words_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("child_id", "day", name="uq_lesson_days_child_day"),)


class VoiceRecord(Base):
    """Родительская запись голоса для ключа вида w:алма или p:сәлеметсіз бе."""

    __tablename__ = "voice_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("family_id", "key", name="uq_voice_family_key"),)
