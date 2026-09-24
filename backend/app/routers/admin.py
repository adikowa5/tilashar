"""Редактор автора: категории, слова, фразы, запись голоса и картинки, статистика.

Вход — пароль из переменной ADMIN_PASSWORD. Токен автора передаётся в заголовке
X-Admin-Token, чтобы не смешиваться с токеном семьи на том же устройстве.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ratelimit
from app.catalog import build_catalog, phrase_out, topic_out, word_out
from app.config import settings
from app.deps import get_db
from app.media import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, read_upload, store
from app.photos import fetch as fetch_photo
from app.photos import search as search_photos
from app.models import Attempt, Child, Family, Media, Phrase, Topic, Word, utcnow
from app.routers.content import audio_key_for, slugify
from app.schemas import (
    AdminLoginIn,
    AdminOrderIn,
    AdminPhrasePatch,
    AdminStatsOut,
    AdminTokenOut,
    AdminTopicIn,
    AdminTopicPatch,
    AdminWordIn,
    AdminWordPatch,
    AdminWordsBulkIn,
    CatalogOut,
    CatalogPhrase,
    CatalogTopic,
    CatalogWord,
    PhotoOut,
    PhotoPick,
)
from app.security import check_admin_password, create_admin_token, verify_admin_token

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="admin_disabled")
    if not x_admin_token or not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_token_invalid")


# --------------------------------------------------------------------------- вход


@router.post("/login", response_model=AdminTokenOut)
def admin_login(payload: AdminLoginIn, request: Request, db: Session = Depends(get_db)) -> AdminTokenOut:
    if not settings.admin_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="admin_disabled")
    key = "admin:" + ratelimit.client_ip(request)
    ratelimit.check(db, key, settings.admin_attempts_per_hour)
    if not check_admin_password(payload.password):
        ratelimit.hit(db, key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="password_invalid")
    token, ttl = create_admin_token()
    return AdminTokenOut(token=token, expires_in=ttl)


# --------------------------------------------------------------------------- чтение


@router.get("/catalog", response_model=CatalogOut, dependencies=[Depends(require_admin)])
def admin_catalog(db: Session = Depends(get_db)) -> CatalogOut:
    return build_catalog(db, include_unpublished=True)


@router.get("/stats", response_model=AdminStatsOut, dependencies=[Depends(require_admin)])
def admin_stats(db: Session = Depends(get_db)) -> AdminStatsOut:
    now = utcnow()
    today = now.date()
    week = now - timedelta(days=7)

    def count(q):  # noqa: ANN001, ANN202
        return int(db.execute(q).scalar_one() or 0)

    media_bytes = count(select(func.coalesce(func.sum(Media.size_bytes), 0)))
    return AdminStatsOut(
        families=count(select(func.count(Family.id))),
        families_active_7d=count(select(func.count(Family.id)).where(Family.last_seen_at >= week)),
        children=count(select(func.count(Child.id)).where(Child.deleted_at.is_(None))),
        attempts_today=count(select(func.count(Attempt.id)).where(Attempt.day == today)),
        attempts_7d=count(select(func.count(Attempt.id)).where(Attempt.at >= week)),
        topics=count(select(func.count(Topic.id)).where(Topic.family_id.is_(None))),
        words=count(select(func.count(Word.id)).join(Topic).where(Topic.family_id.is_(None))),
        words_with_voice=count(
            select(func.count(Word.id)).join(Topic).where(Topic.family_id.is_(None), Word.audio_id.is_not(None))
        ),
        media_mb=round(media_bytes / 1024 / 1024, 1),
    )


# --------------------------------------------------------------------------- категории


def _topic(db: Session, topic_id: str) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.family_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="topic_not_found")
    return topic


def _fresh_topic(db: Session, topic: Topic) -> CatalogTopic:
    db.commit()
    db.expire_all()
    return topic_out(_topic(db, topic.id))


@router.post("/topics", response_model=CatalogTopic, status_code=201, dependencies=[Depends(require_admin)])
def create_topic(payload: AdminTopicIn, db: Session = Depends(get_db)) -> CatalogTopic:
    taken = set(db.execute(select(Topic.slug).where(Topic.family_id.is_(None))).scalars())
    base = slugify(payload.title_ru or payload.title_kk)
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    last = db.execute(
        select(func.max(Topic.order_index)).where(Topic.family_id.is_(None))
    ).scalar_one()
    topic = Topic(
        slug=slug, title_kk=payload.title_kk.strip(), title_ru=payload.title_ru.strip(),
        pic=payload.pic.strip(), kind="builtin", family_id=None,
        order_index=(last if last is not None else -1) + 1, is_published=payload.is_published,
    )
    db.add(topic)
    db.flush()
    return _fresh_topic(db, topic)


@router.patch("/topics/{topic_id}", response_model=CatalogTopic, dependencies=[Depends(require_admin)])
def patch_topic(topic_id: str, payload: AdminTopicPatch, db: Session = Depends(get_db)) -> CatalogTopic:
    topic = _topic(db, topic_id)
    for field in ("title_kk", "title_ru", "pic"):
        value = getattr(payload, field)
        if value is not None:
            setattr(topic, field, value.strip())
    if payload.is_published is not None:
        topic.is_published = payload.is_published
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


@router.delete("/topics/{topic_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_topic(topic_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_topic(db, topic_id))
    db.commit()
    return Response(status_code=204)


@router.post("/topics/order", response_model=CatalogOut, dependencies=[Depends(require_admin)])
def order_topics(payload: AdminOrderIn, db: Session = Depends(get_db)) -> CatalogOut:
    for index, topic_id in enumerate(payload.ids):
        _topic(db, topic_id).order_index = index
    db.commit()
    return build_catalog(db, include_unpublished=True)


@router.put("/topics/{topic_id}/image", response_model=CatalogTopic, dependencies=[Depends(require_admin)])
def put_topic_image(topic_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> CatalogTopic:
    topic = _topic(db, topic_id)
    topic.image_id = store(db, read_upload(file, MAX_IMAGE_BYTES), "image").id
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


@router.delete("/topics/{topic_id}/image", response_model=CatalogTopic, dependencies=[Depends(require_admin)])
def delete_topic_image(topic_id: str, db: Session = Depends(get_db)) -> CatalogTopic:
    topic = _topic(db, topic_id)
    topic.image_id = None
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


# --------------------------------------------------------------------------- слова


def _word(db: Session, word_id: str) -> Word:
    word = db.get(Word, word_id)
    if word is None or word.topic.family_id is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="word_not_found")
    return word


def _fresh_word(db: Session, word: Word) -> CatalogWord:
    db.commit()
    db.expire_all()
    return word_out(_word(db, word.id))


def _next_word_index(db: Session, topic_id: str) -> int:
    last = db.execute(select(func.max(Word.order_index)).where(Word.topic_id == topic_id)).scalar_one()
    return (last if last is not None else -1) + 1


def _add_word(db: Session, topic: Topic, payload: AdminWordIn, index: int) -> Word:
    text = payload.text_kk.strip()
    word = Word(
        topic_id=topic.id,
        text_kk=text,
        text_ru=payload.text_ru.strip(),
        syllables=(payload.syllables.strip() or text),
        pic=payload.pic.strip(),
        audio_key=audio_key_for(text),
        order_index=index,
    )
    db.add(word)
    return word


@router.post("/topics/{topic_id}/words", response_model=CatalogWord, status_code=201,
             dependencies=[Depends(require_admin)])
def create_word(topic_id: str, payload: AdminWordIn, db: Session = Depends(get_db)) -> CatalogWord:
    topic = _topic(db, topic_id)
    word = _add_word(db, topic, payload, _next_word_index(db, topic.id))
    db.flush()
    return _fresh_word(db, word)


@router.post("/topics/{topic_id}/words/bulk", response_model=CatalogTopic, status_code=201,
             dependencies=[Depends(require_admin)])
def create_words_bulk(topic_id: str, payload: AdminWordsBulkIn, db: Session = Depends(get_db)) -> CatalogTopic:
    """Несколько слов сразу (вставка списком). Слова, которые уже есть в категории, пропускаем."""
    topic = _topic(db, topic_id)
    existing = {w.text_kk.lower() for w in topic.words}
    index = _next_word_index(db, topic.id)
    for item in payload.words:
        if item.text_kk.strip().lower() in existing:
            continue
        existing.add(item.text_kk.strip().lower())
        _add_word(db, topic, item, index)
        index += 1
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


@router.patch("/words/{word_id}", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def patch_word(word_id: str, payload: AdminWordPatch, db: Session = Depends(get_db)) -> CatalogWord:
    word = _word(db, word_id)
    if payload.text_kk is not None:
        word.text_kk = payload.text_kk.strip()
        word.audio_key = audio_key_for(word.text_kk)
    for field in ("text_ru", "syllables", "pic"):
        value = getattr(payload, field)
        if value is not None:
            setattr(word, field, value.strip())
    if not word.syllables:
        word.syllables = word.text_kk
    if payload.topic_id is not None and payload.topic_id != word.topic_id:
        target = _topic(db, payload.topic_id)
        word.topic_id = target.id
        word.order_index = _next_word_index(db, target.id)
    word.updated_at = utcnow()
    return _fresh_word(db, word)


@router.delete("/words/{word_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_word(word_id: str, db: Session = Depends(get_db)) -> Response:
    db.delete(_word(db, word_id))
    db.commit()
    return Response(status_code=204)


@router.post("/topics/{topic_id}/words/order", response_model=CatalogTopic, dependencies=[Depends(require_admin)])
def order_words(topic_id: str, payload: AdminOrderIn, db: Session = Depends(get_db)) -> CatalogTopic:
    topic = _topic(db, topic_id)
    ids = {w.id: w for w in topic.words}
    for index, word_id in enumerate(payload.ids):
        if word_id in ids:
            ids[word_id].order_index = index
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


@router.put("/words/{word_id}/audio", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def put_word_audio(word_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> CatalogWord:
    word = _word(db, word_id)
    word.audio_id = store(db, read_upload(file, MAX_AUDIO_BYTES), "audio").id
    word.updated_at = utcnow()
    return _fresh_word(db, word)


@router.delete("/words/{word_id}/audio", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def delete_word_audio(word_id: str, db: Session = Depends(get_db)) -> CatalogWord:
    word = _word(db, word_id)
    word.audio_id = None
    word.updated_at = utcnow()
    return _fresh_word(db, word)


@router.get("/photos", response_model=list[PhotoOut], dependencies=[Depends(require_admin)])
def find_photos(q: str, per_page: int = 24) -> list[PhotoOut]:
    """Поиск фотографий на Pexels. Ключ PEXELS_API_KEY не покидает сервер."""
    return search_photos(q, max(1, min(per_page, 40)))


@router.post("/words/{word_id}/image/pexels", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def put_word_photo(word_id: str, payload: PhotoPick, db: Session = Depends(get_db)) -> CatalogWord:
    """Ставит слову выбранную фотографию вместе с подписью автора."""
    word = _word(db, word_id)
    data, credit, source = fetch_photo(payload.photo_id)
    word.image_id = store(db, data, "image", credit=credit, source_url=source).id
    word.updated_at = utcnow()
    return _fresh_word(db, word)


@router.post("/topics/{topic_id}/image/pexels", response_model=CatalogTopic, dependencies=[Depends(require_admin)])
def put_topic_photo(topic_id: str, payload: PhotoPick, db: Session = Depends(get_db)) -> CatalogTopic:
    topic = _topic(db, topic_id)
    data, credit, source = fetch_photo(payload.photo_id)
    topic.image_id = store(db, data, "image", credit=credit, source_url=source).id
    topic.updated_at = utcnow()
    return _fresh_topic(db, topic)


@router.put("/words/{word_id}/image", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def put_word_image(word_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> CatalogWord:
    word = _word(db, word_id)
    word.image_id = store(db, read_upload(file, MAX_IMAGE_BYTES), "image").id
    word.updated_at = utcnow()
    return _fresh_word(db, word)


@router.delete("/words/{word_id}/image", response_model=CatalogWord, dependencies=[Depends(require_admin)])
def delete_word_image(word_id: str, db: Session = Depends(get_db)) -> CatalogWord:
    word = _word(db, word_id)
    word.image_id = None
    word.updated_at = utcnow()
    return _fresh_word(db, word)


# --------------------------------------------------------------------------- фразы


def _phrase(db: Session, key: str) -> Phrase:
    phrase = db.get(Phrase, key)
    if phrase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="phrase_not_found")
    return phrase


def _fresh_phrase(db: Session, phrase: Phrase) -> CatalogPhrase:
    db.commit()
    db.expire_all()
    return phrase_out(_phrase(db, phrase.key))


@router.patch("/phrases/{key}", response_model=CatalogPhrase, dependencies=[Depends(require_admin)])
def patch_phrase(key: str, payload: AdminPhrasePatch, db: Session = Depends(get_db)) -> CatalogPhrase:
    phrase = _phrase(db, key)
    if payload.text_kk is not None:
        phrase.text_kk = payload.text_kk.strip()
    if payload.text_ru is not None:
        phrase.text_ru = payload.text_ru.strip()
    phrase.updated_at = utcnow()
    return _fresh_phrase(db, phrase)


@router.put("/phrases/{key}/audio", response_model=CatalogPhrase, dependencies=[Depends(require_admin)])
def put_phrase_audio(key: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> CatalogPhrase:
    phrase = _phrase(db, key)
    phrase.audio_id = store(db, read_upload(file, MAX_AUDIO_BYTES), "audio").id
    phrase.updated_at = utcnow()
    return _fresh_phrase(db, phrase)


@router.delete("/phrases/{key}/audio", response_model=CatalogPhrase, dependencies=[Depends(require_admin)])
def delete_phrase_audio(key: str, db: Session = Depends(get_db)) -> CatalogPhrase:
    phrase = _phrase(db, key)
    phrase.audio_id = None
    phrase.updated_at = utcnow()
    return _fresh_phrase(db, phrase)
