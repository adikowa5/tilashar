"""Урок дня, приём попыток и сводный прогресс ребёнка.

Состав дня фиксируется при первом обращении к `/today` и хранится в
`lesson_days.plan`, чтобы список не менялся по мере роста прогресса внутри
дня. Выбор слов детерминирован: генератор случайных чисел засевается
идентификатором ребёнка и датой.

Все даты считаются по UTC — и `day` попытки, и «сегодня» урока.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, owned_child, streak_for_child
from app.models import Attempt, Child, LessonDay, Progress, Topic, Word, utcnow
from app.routers.content import visible_topics
from app.schemas import AttemptIn, AttemptsResult, ProgressEntry, TodayItem, TodayOut

router = APIRouter(prefix="/children", tags=["lesson"])

# Слово считается выученным (и уходит из повторов) начиная с этого числа звёзд.
LEARNED_STARS = 2


def _seeded_random(child_id: str, day: date) -> random.Random:
    """Детерминированный ГПСЧ: один и тот же ребёнок в один и тот же день — один порядок."""
    digest = hashlib.sha256(f"{child_id}:{day.isoformat()}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _to_utc_naive(value: datetime) -> datetime:
    """Приводит момент попытки к naive UTC — в таком виде времена лежат в БД."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _progress_map(db: Session, child_id: str) -> dict[str, Progress]:
    rows = db.execute(select(Progress).where(Progress.child_id == child_id)).scalars()
    return {row.word_id: row for row in rows}


def build_plan(db: Session, child: Child, day: date) -> list[dict[str, str]]:
    """Собирает план дня: до LESSON_SIZE слов.

    Сначала новые слова первой незакрытой темы (тема закрыта, когда все её
    слова набрали не меньше LEARNED_STARS), затем — повторение слов с 0-1
    звездой из уже пройденного материала.
    """
    topics: list[Topic] = visible_topics(db, child.family_id)
    progress = _progress_map(db, child.id)
    rnd = _seeded_random(child.id, day)

    def stars(word_id: str) -> int:
        row = progress.get(word_id)
        return row.best_stars if row is not None else 0

    def seen(word_id: str) -> bool:
        return word_id in progress

    plan: list[dict[str, str]] = []
    chosen: set[str] = set()

    # 1. Новые слова первой незакрытой темы.
    for topic in topics:
        words = sorted(topic.words, key=lambda w: w.order_index)
        if not words:
            continue
        if all(stars(w.id) >= LEARNED_STARS for w in words):
            continue  # тема закрыта, идём дальше
        for word in words:
            if len(plan) >= settings.lesson_size:
                break
            if seen(word.id):
                continue
            plan.append({"word_id": word.id, "topic_slug": topic.slug, "status": "new"})
            chosen.add(word.id)
        break

    # 2. Добор повторами: слова, которые уже пробовали, но звёзд мало.
    if len(plan) < settings.lesson_size:
        review_pool: list[tuple[str, str]] = []
        for topic in topics:
            for word in topic.words:
                if word.id in chosen:
                    continue
                if seen(word.id) and stars(word.id) < LEARNED_STARS:
                    review_pool.append((word.id, topic.slug))
        review_pool.sort()  # стабильный базовый порядок до перемешивания
        rnd.shuffle(review_pool)
        for word_id, topic_slug in review_pool[: settings.lesson_size - len(plan)]:
            plan.append({"word_id": word_id, "topic_slug": topic_slug, "status": "review"})
            chosen.add(word_id)

    # 3. Если и повторять нечего (весь контент закрыт) — освежаем случайные выученные слова.
    if not plan:
        fallback: list[tuple[str, str]] = [
            (word.id, topic.slug) for topic in topics for word in topic.words
        ]
        fallback.sort()
        rnd.shuffle(fallback)
        for word_id, topic_slug in fallback[: settings.lesson_size]:
            plan.append({"word_id": word_id, "topic_slug": topic_slug, "status": "review"})

    return plan


def get_or_create_day(db: Session, child: Child, day: date, today: date) -> LessonDay:
    """Возвращает запись дня, создавая её при первом обращении.

    План составляется только для сегодняшнего дня. Записи за прошлые даты
    появляются при синхронизации офлайн-попыток и живут без плана.
    """
    row = db.execute(
        select(LessonDay).where(LessonDay.child_id == child.id, LessonDay.day == day)
    ).scalar_one_or_none()
    need_plan = day == today
    if row is None:
        plan = build_plan(db, child, day) if need_plan else []
        row = LessonDay(
            child_id=child.id, day=day, plan=json.dumps(plan, ensure_ascii=False)
        )
        db.add(row)
        db.flush()
    elif need_plan and not _plan_items(row):
        row.plan = json.dumps(build_plan(db, child, day), ensure_ascii=False)
        db.flush()
    return row


def _plan_items(row: LessonDay) -> list[dict[str, str]]:
    """Разбирает сохранённый план дня; повреждённый JSON трактуется как пустой план."""
    try:
        data = json.loads(row.plan or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("word_id")]


def _done_word_ids(db: Session, child_id: str, day: date) -> set[str]:
    """Слова, закрытые в этот день на LEARNED_STARS и выше."""
    rows = db.execute(
        select(Attempt.word_id).where(
            Attempt.child_id == child_id,
            Attempt.day == day,
            Attempt.stars >= LEARNED_STARS,
        )
    ).scalars()
    return set(rows)


def refresh_day_state(
    db: Session, child: Child, day: date, today: date
) -> tuple[LessonDay, int, int]:
    """Пересчитывает прогресс дня. Возвращает запись дня, «сделано» и «всего».

    День с планом закрыт, когда закрыты все слова плана. День без плана
    (пришёл из офлайн-синхронизации) закрыт, если закрыто хотя бы одно слово.
    """
    row = get_or_create_day(db, child, day, today)
    items = _plan_items(row)
    done_ids = _done_word_ids(db, child.id, day)
    if items:
        done = sum(1 for item in items if item["word_id"] in done_ids)
        total = len(items)
        completed = total > 0 and done >= total
    else:
        done = len(done_ids)
        total = done
        completed = done > 0
    row.words_done = done
    row.completed = completed
    db.flush()
    return row, done, total


@router.get("/{child_id}/today", response_model=TodayOut)
def read_today(
    db: Session = Depends(get_db),
    child: Child = Depends(owned_child),
) -> TodayOut:
    """Урок на сегодня. Повторный вызов в тот же день возвращает тот же состав."""
    day = datetime.now(timezone.utc).date()
    row, done, total = refresh_day_state(db, child, day, day)
    done_ids = _done_word_ids(db, child.id, day)
    items = [
        TodayItem(
            kind="word",
            word_id=item["word_id"],
            topic_slug=item.get("topic_slug", ""),
            status="done" if item["word_id"] in done_ids else item.get("status", "new"),
        )
        for item in _plan_items(row)
    ]
    db.commit()
    return TodayOut(
        date=day,
        streak=streak_for_child(db, child.id, day),
        done=done,
        total=total,
        items=items,
    )


@router.post("/{child_id}/attempts", response_model=AttemptsResult)
def post_attempts(
    payload: list[AttemptIn] = Body(..., max_length=50),
    db: Session = Depends(get_db),
    child: Child = Depends(owned_child),
) -> AttemptsResult:
    """Принимает пачку попыток (до 50). Идемпотентно по (child_id, word_id, at).

    Голос ребёнка на сервер не попадает: приходят только звёзды и распознанный текст.
    """
    today = datetime.now(timezone.utc).date()

    word_ids = {item.word_id for item in payload}
    allowed = set(
        db.execute(
            select(Word.id)
            .join(Topic, Topic.id == Word.topic_id)
            .where(
                Word.id.in_(word_ids),
                or_(Topic.family_id.is_(None), Topic.family_id == child.family_id),
            )
        ).scalars()
    )
    unknown = word_ids - allowed
    if unknown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="word_not_found")

    # План на сегодня фиксируем ДО применения попыток: иначе только что закрытые
    # слова перестанут считаться новыми и выпадут из состава дня.
    get_or_create_day(db, child, today, today)

    progress = _progress_map(db, child.id)
    touched_days: set[date] = {today}
    seen_keys: set[tuple[str, datetime]] = set()

    for item in payload:
        at = _to_utc_naive(item.at)
        day = at.date()
        key = (item.word_id, at)
        if key in seen_keys:
            continue  # дубль внутри одной пачки
        exists = db.execute(
            select(Attempt.id).where(
                Attempt.child_id == child.id,
                Attempt.word_id == item.word_id,
                Attempt.at == at,
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue  # идемпотентность: такую попытку уже записали
        seen_keys.add(key)

        db.add(
            Attempt(
                child_id=child.id,
                word_id=item.word_id,
                stars=item.stars,
                heard=item.heard,
                mode=item.mode,
                at=at,
                day=day,
            )
        )
        touched_days.add(day)

        row = progress.get(item.word_id)
        if row is None:
            row = Progress(
                child_id=child.id,
                word_id=item.word_id,
                best_stars=item.stars,
                attempts_count=1,
                updated_at=utcnow(),
            )
            db.add(row)
            progress[item.word_id] = row
        else:
            row.best_stars = max(row.best_stars, item.stars)
            row.attempts_count += 1
            row.updated_at = utcnow()

    db.flush()

    # Общий счёт — сумма лучших результатов по всем словам.
    child.stars_total = sum(row.best_stars for row in progress.values())

    day_done = False
    for day in sorted(touched_days):
        row_day, _done, _total = refresh_day_state(db, child, day, today)
        if day == today:
            day_done = row_day.completed

    db.commit()
    return AttemptsResult(
        stars_total=child.stars_total,
        streak=streak_for_child(db, child.id, today),
        day_done=day_done,
    )


@router.get("/{child_id}/progress", response_model=dict[str, ProgressEntry])
def read_progress(
    db: Session = Depends(get_db),
    child: Child = Depends(owned_child),
) -> dict[str, ProgressEntry]:
    """Сводка по всем словам, которые ребёнок хоть раз пробовал."""
    return {
        word_id: ProgressEntry(stars=row.best_stars, attempts=row.attempts_count)
        for word_id, row in _progress_map(db, child.id).items()
    }
