"""ORM-модели. Типы намеренно портируемые: работают и в Postgres, и в SQLite.

UUID хранится строкой (36 символов), времена — naive UTC DateTime.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    LargeBinary,
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
    """Семья — владелец детей и родительских записей похвалы.

    Регистрации нет: семья создаётся на первом устройстве, остальные устройства
    подключаются по коду семьи (join_code). Личных данных родителя не храним.
    """

    __tablename__ = "families"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    is_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    model_voice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Код для подключения второго устройства, вида ABCD2345. Выдаётся по запросу.
    join_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    # Когда семья последний раз открывала приложение — по нему чистим брошенные семьи.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    users: Mapped[list[User]] = relationship(back_populates="family")
    children: Mapped[list[Child]] = relationship(back_populates="family")


class User(Base):
    """Устройство семьи. Один пользователь = одно подключённое устройство, без личных данных."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=False, index=True
    )
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


class RateHit(Base):
    """Отметка о действии для ограничения частоты (гости, вход по коду, вход автора).

    Процессы на Vercel живут недолго, поэтому счётчики храним в базе.
    Старые отметки удаляет ежедневная уборка.
    """

    __tablename__ = "rate_hits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)


class Media(Base):
    """Файл в базе: запись голоса автора, звук модели или картинка.

    Отдаётся по /api/v1/media/<sha256>.<ext> без авторизации и кешируется навсегда:
    содержимое по одному адресу никогда не меняется.
    """

    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)          # audio | image
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    ext: Mapped[str] = mapped_column(String(8), nullable=False)
    # deferred: байты грузятся только при отдаче файла, а не при каждом чтении каталога.
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    # Неопубликованную категорию видит только автор — удобно готовить её заранее.
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    image: Mapped[Media | None] = relationship(foreign_keys=[image_id], lazy="joined")
    words: Mapped[list[Word]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", order_by="Word.order_index"
    )

    __table_args__ = (UniqueConstraint("slug", "family_id", name="uq_topics_slug_family"),)


class Word(Base):
    """Слово темы. pic — эмодзи, hex-цвет или цифра (запасная картинка).

    audio_id — запись автора, model_audio_id — синтезированный голос (запасной),
    image_id — загруженная автором картинка.
    """

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
    audio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    model_audio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    image_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    topic: Mapped[Topic] = relationship(back_populates="words")
    audio: Mapped[Media | None] = relationship(foreign_keys=[audio_id], lazy="joined")
    model_audio: Mapped[Media | None] = relationship(foreign_keys=[model_audio_id], lazy="joined")
    image: Mapped[Media | None] = relationship(foreign_keys=[image_id], lazy="joined")


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
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Содержимое лежит в БД: serverless-окружение не имеет постоянного диска.
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("family_id", "key", name="uq_voice_family_key"),)


class Phrase(Base):
    """Фраза похвалы или подсказки (p:great, p:good …).

    Голос автора звучит у всех; семья может перезаписать фразу своим голосом (VoiceRecord).
    """

    __tablename__ = "phrases"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    text_kk: Mapped[str] = mapped_column(String(128), nullable=False)
    text_ru: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    model_audio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    audio: Mapped[Media | None] = relationship(foreign_keys=[audio_id], lazy="joined")
    model_audio: Mapped[Media | None] = relationship(foreign_keys=[model_audio_id], lazy="joined")
