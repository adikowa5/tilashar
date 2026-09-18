"""Pydantic-схемы запросов и ответов. Имена полей строго по контракту docs/api.md."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- auth


class PhoneIn(BaseModel):
    phone: str


class CodeIn(BaseModel):
    phone: str
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


class CodeSent(BaseModel):
    sent: bool
    dev_code: str | None = None
    retry_after: int


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


# --------------------------------------------------------------------------- me / family


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    phone: str | None
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


class ConfigOut(BaseModel):
    sms_provider: str
    dev_mode: bool
    max_children: int
    version: str
