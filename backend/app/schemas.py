"""Pydantic-схемы запросов и ответов. Имена полей строго по контракту docs/api.md."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- auth


class RefreshIn(BaseModel):
    refresh_token: str


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class FamilyCodeOut(BaseModel):
    code: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


# --------------------------------------------------------------------------- me / family


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    locale: str
    created_at: datetime


class FamilyOut(BaseModel):
    # protected_namespaces=(): поле model_voice из контракта начинается с model_,
    # pydantic иначе считает это конфликтом со своими служебными именами.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    is_guest: bool
    model_voice: bool
    created_at: datetime


class UserPatch(BaseModel):
    locale: str | None = None


class FamilyPatch(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_voice: bool | None = None


# --------------------------------------------------------------------------- children


class ChildOut(BaseModel):
    id: str
    name: str
    age: int
    avatar: str
    locale: str
    stars_total: int
    streak: int
    created_at: datetime


class ChildCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    age: int
    avatar: str = "fox"
    locale: str = "kk"


class ChildPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    age: int | None = None
    avatar: str | None = None
    locale: str | None = None


class MeOut(BaseModel):
    user: UserOut
    family: FamilyOut
    children: list[ChildOut]


# --------------------------------------------------------------------------- content


class WordOut(BaseModel):
    id: str
    text_kk: str
    text_ru: str
    syllables: str
    pic: str
    audio_key: str


class TopicOut(BaseModel):
    id: str
    slug: str
    title_kk: str
    title_ru: str
    pic: str
    kind: Literal["builtin", "family"]
    word_count: int


class TopicDetail(TopicOut):
    words: list[WordOut]


class WordIn(BaseModel):
    text_kk: str = Field(min_length=1, max_length=64)
    text_ru: str = Field(default="", max_length=64)
    syllables: str = Field(default="", max_length=96)
    pic: str = Field(default="", max_length=64)


class TopicCreate(BaseModel):
    title_kk: str = Field(min_length=1, max_length=128)
    title_ru: str = Field(default="", max_length=128)
    pic: str = Field(default="", max_length=64)
    words: list[WordIn] = Field(default_factory=list, max_length=40)


class CatalogWord(BaseModel):
    id: str
    text_kk: str
    text_ru: str
    syllables: str
    pic: str
    image_url: str | None = None
    audio_url: str | None = None
    model_audio_url: str | None = None


class CatalogTopic(BaseModel):
    id: str
    slug: str
    title_kk: str
    title_ru: str
    pic: str
    image_url: str | None = None
    is_published: bool = True
    order_index: int = 0
    words: list[CatalogWord]


class CatalogPhrase(BaseModel):
    key: str
    text_kk: str
    text_ru: str
    audio_url: str | None = None
    model_audio_url: str | None = None


class CatalogOut(BaseModel):
    version: str
    topics: list[CatalogTopic]
    phrases: list[CatalogPhrase]


# --------------------------------------------------------------------------- автор


class AdminLoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdminTokenOut(BaseModel):
    token: str
    expires_in: int


class AdminTopicIn(BaseModel):
    title_kk: str = Field(min_length=1, max_length=128)
    title_ru: str = Field(default="", max_length=128)
    pic: str = Field(default="", max_length=64)
    is_published: bool = False


class AdminTopicPatch(BaseModel):
    title_kk: str | None = Field(default=None, min_length=1, max_length=128)
    title_ru: str | None = Field(default=None, max_length=128)
    pic: str | None = Field(default=None, max_length=64)
    is_published: bool | None = None


class AdminWordIn(BaseModel):
    text_kk: str = Field(min_length=1, max_length=64)
    text_ru: str = Field(default="", max_length=64)
    syllables: str = Field(default="", max_length=96)
    pic: str = Field(default="", max_length=64)


class AdminWordPatch(BaseModel):
    text_kk: str | None = Field(default=None, min_length=1, max_length=64)
    text_ru: str | None = Field(default=None, max_length=64)
    syllables: str | None = Field(default=None, max_length=96)
    pic: str | None = Field(default=None, max_length=64)
    topic_id: str | None = None


class AdminWordsBulkIn(BaseModel):
    words: list[AdminWordIn] = Field(min_length=1, max_length=200)


class AdminOrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class AdminPhrasePatch(BaseModel):
    text_kk: str | None = Field(default=None, min_length=1, max_length=128)
    text_ru: str | None = Field(default=None, max_length=128)


class AdminStatsOut(BaseModel):
    families: int
    families_active_7d: int
    children: int
    attempts_today: int
    attempts_7d: int
    topics: int
    words: int
    words_with_voice: int
    media_mb: float


# --------------------------------------------------------------------------- урок дня


class TodayItem(BaseModel):
    kind: Literal["word"] = "word"
    word_id: str
    topic_slug: str
    status: Literal["new", "review", "done"]


class TodayOut(BaseModel):
    date: date_type
    streak: int
    done: int
    total: int
    items: list[TodayItem]


class AttemptIn(BaseModel):
    word_id: str
    stars: int = Field(ge=0, le=3)
    heard: str | None = None
    mode: Literal["asr", "manual"] = "asr"
    at: datetime


class AttemptsResult(BaseModel):
    stars_total: int
    streak: int
    day_done: bool


class ProgressEntry(BaseModel):
    stars: int
    attempts: int


# --------------------------------------------------------------------------- голос


class VoiceOut(BaseModel):
    key: str
    url: str
    duration_ms: int
    updated_at: datetime


# --------------------------------------------------------------------------- прочее


class HealthOut(BaseModel):
    status: str
    db: str
    reason: str | None = None


class ConfigOut(BaseModel):
    max_children: int
    version: str
