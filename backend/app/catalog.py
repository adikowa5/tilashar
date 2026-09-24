"""Каталог учебного материала: категории, слова, фразы — в одном ответе.

Используется и публичным /content/catalog, и редактором автора (с неопубликованным).
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.media import url_of
from app.models import Phrase, Topic, Word
from app.schemas import CatalogOut, CatalogPhrase, CatalogTopic, CatalogWord


def word_out(word: Word) -> CatalogWord:
    return CatalogWord(
        id=word.id,
        text_kk=word.text_kk,
        text_ru=word.text_ru,
        syllables=word.syllables or word.text_kk,
        pic=word.pic,
        image_url=url_of(word.image),
        image_credit=word.image.credit if word.image is not None else None,
        audio_url=url_of(word.audio),
        model_audio_url=url_of(word.model_audio),
    )


def topic_out(topic: Topic) -> CatalogTopic:
    return CatalogTopic(
        id=topic.id,
        slug=topic.slug,
        title_kk=topic.title_kk,
        title_ru=topic.title_ru,
        pic=topic.pic,
        image_url=url_of(topic.image),
        image_credit=topic.image.credit if topic.image is not None else None,
        is_published=topic.is_published,
        order_index=topic.order_index,
        words=[word_out(w) for w in topic.words],
    )


def phrase_out(phrase: Phrase) -> CatalogPhrase:
    return CatalogPhrase(
        key=phrase.key,
        text_kk=phrase.text_kk,
        text_ru=phrase.text_ru,
        audio_url=url_of(phrase.audio),
        model_audio_url=url_of(phrase.model_audio),
    )


def build_catalog(db: Session, include_unpublished: bool = False) -> CatalogOut:
    query = (
        select(Topic)
        .where(Topic.family_id.is_(None))
        .options(selectinload(Topic.words))
        .order_by(Topic.order_index, Topic.created_at)
    )
    if not include_unpublished:
        query = query.where(Topic.is_published.is_(True))
    topics = [topic_out(t) for t in db.execute(query).unique().scalars()]
    phrases = [
        phrase_out(p)
        for p in db.execute(select(Phrase).order_by(Phrase.order_index, Phrase.key)).unique().scalars()
    ]
    out = CatalogOut(version="", topics=topics, phrases=phrases)
    # Версия — хеш содержимого: клиент по ней понимает, что каталог поменялся.
    out.version = hashlib.sha256(out.model_dump_json().encode("utf-8")).hexdigest()[:16]
    return out
