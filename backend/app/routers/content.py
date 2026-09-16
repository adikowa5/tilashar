"""Темы и слова: встроенный контент плюс темы, созданные семьёй."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.deps import current_family, get_db
from app.models import Family, Topic, Word
from app.schemas import TopicCreate, TopicDetail, TopicOut, WordOut

router = APIRouter(prefix="/content", tags=["content"])

# Транслитерация казахской кириллицы в латиницу для slug'ов пользовательских тем.
TRANSLIT = {
    "а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "қ": "q", "л": "l",
    "м": "m", "н": "n", "ң": "n", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s",
    "т": "t", "у": "u", "ұ": "u", "ү": "u", "ф": "f", "х": "h", "һ": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "і": "i", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


def slugify(text: str) -> str:
    """Делает безопасный slug из казахского или русского заголовка."""
    lowered = (text or "").strip().lower()
    latin = "".join(TRANSLIT.get(char, char) for char in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", latin).strip("-")
    return slug[:56] or "topic"


def audio_key_for(text_kk: str) -> str:
    """Ключ записи в паке озвучки для слова."""
    return f"w:{text_kk}"


def _to_topic_out(topic: Topic) -> TopicOut:
    return TopicOut(
        id=topic.id,
        slug=topic.slug,
        title_kk=topic.title_kk,
        title_ru=topic.title_ru,
        pic=topic.pic,
        kind="family" if topic.kind == "family" else "builtin",
        word_count=len(topic.words),
    )


def _to_word_out(word: Word) -> WordOut:
    return WordOut(
        id=word.id,
        text_kk=word.text_kk,
        text_ru=word.text_ru,
        syllables=word.syllables,
        pic=word.pic,
        audio_key=word.audio_key or audio_key_for(word.text_kk),
    )


def visible_topics(db: Session, family_id: str) -> list[Topic]:
    """Встроенные темы плюс темы этой семьи, в порядке order_index."""
    return list(
        db.execute(
            select(Topic)
            .where(or_(Topic.family_id.is_(None), Topic.family_id == family_id))
            .order_by(Topic.kind, Topic.order_index, Topic.created_at)
        ).scalars()
    )


@router.get("/topics", response_model=list[TopicOut])
def list_topics(
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> list[TopicOut]:
    """Список тем, доступных семье."""
    return [_to_topic_out(topic) for topic in visible_topics(db, family.id)]


@router.get("/topics/{slug}", response_model=TopicDetail)
def read_topic(
    slug: str,
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> TopicDetail:
    """Тема со словами. Своя тема семьи имеет приоритет над встроенной с тем же slug."""
    topics = db.execute(
        select(Topic)
        .where(
            Topic.slug == slug,
            or_(Topic.family_id.is_(None), Topic.family_id == family.id),
        )
        .order_by(Topic.family_id.is_(None))
    ).scalars().all()
    if not topics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic_not_found")
    topic = topics[0]
    base = _to_topic_out(topic)
    return TopicDetail(**base.model_dump(), words=[_to_word_out(w) for w in topic.words])


@router.post("/topics", response_model=TopicDetail, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> TopicDetail:
    """Создаёт тему семьи (обычно — результат AI-генерации на клиенте).

    Slug выводится из казахского заголовка; при коллизии внутри семьи
    к нему дописывается порядковый суффикс.
    """
    base_slug = slugify(payload.title_kk)
    slug = base_slug
    suffix = 2
    taken = {
        row
        for row in db.execute(
            select(Topic.slug).where(Topic.family_id == family.id)
        ).scalars()
    }
    while slug in taken:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    max_order = db.execute(
        select(Topic.order_index)
        .where(Topic.family_id == family.id)
        .order_by(Topic.order_index.desc())
        .limit(1)
    ).scalar_one_or_none()

    topic = Topic(
        slug=slug,
        title_kk=payload.title_kk,
        title_ru=payload.title_ru,
        pic=payload.pic,
        kind="family",
        family_id=family.id,
        order_index=(max_order or 0) + 1,
    )
    db.add(topic)
    db.flush()

    for index, word in enumerate(payload.words):
        db.add(
            Word(
                topic_id=topic.id,
                text_kk=word.text_kk,
                text_ru=word.text_ru,
                syllables=word.syllables or word.text_kk,
                pic=word.pic,
                audio_key=audio_key_for(word.text_kk),
                order_index=index,
            )
        )
    db.commit()
    db.refresh(topic)

    base = _to_topic_out(topic)
    return TopicDetail(**base.model_dump(), words=[_to_word_out(w) for w in topic.words])
