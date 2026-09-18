"""Сидинг встроенного контента из words.js фронтенда.

Файл words.js имеет вид ``window.TILASHAR_TOPICS=[...];`` — обрезаем префикс и
точку с запятой и разбираем остаток как JSON. Русские переводы и русские
названия тем лежат здесь же, явными словарями.

Запуск: ``python -m app.seed [путь/к/words.js]``
Операция идемпотентна: повторный запуск обновляет существующие темы и слова.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Topic, Word

PREFIX = "window.TILASHAR_TOPICS="

# Порядок тем в приложении: от простого к сложному.
TOPIC_ORDER = ["animals", "fruits", "colors", "numbers", "home", "nature"]

TOPIC_TITLES_RU: dict[str, str] = {
    "animals": "Животные",
    "fruits": "Фрукты и ягоды",
    "colors": "Цвета",
    "numbers": "Числа",
    "home": "Дома",
    "nature": "Природа",
}

# Переводы слов на русский — простые бытовые значения для детей 6-9 лет.
WORDS_RU: dict[str, str] = {
    # жануарлар
    "мысық": "кошка",
    "ит": "собака",
    "ат": "лошадь",
    "сиыр": "корова",
    "қой": "овца",
    "түйе": "верблюд",
    "қоян": "заяц",
    "аю": "медведь",
    # жеміс-жидек
    "алма": "яблоко",
    "алмұрт": "груша",
    "жүзім": "виноград",
    "қарбыз": "арбуз",
    "лимон": "лимон",
    "шие": "вишня",
    "құлпынай": "клубника",
    "банан": "банан",
    # түстер
    "қызыл": "красный",
    "көк": "синий",
    "сары": "жёлтый",
    "жасыл": "зелёный",
    "ақ": "белый",
    "қара": "чёрный",
    "қызғылт": "розовый",
    "күлгін": "фиолетовый",
    # сандар
    "бір": "один",
    "екі": "два",
    "үш": "три",
    "төрт": "четыре",
    "бес": "пять",
    "алты": "шесть",
    "жеті": "семь",
    "сегіз": "восемь",
    "тоғыз": "девять",
    "он": "десять",
    # үйде
    "үй": "дом",
    "есік": "дверь",
    "терезе": "окно",
    "орындық": "стул",
    "кітап": "книга",
    "қасық": "ложка",
    "кесе": "чашка",
    "төсек": "кровать",
    # табиғат
    "күн": "солнце",
    "ай": "луна",
    "жұлдыз": "звезда",
    "бұлт": "облако",
    "тау": "гора",
    "су": "вода",
    "гүл": "цветок",
    "ағаш": "дерево",
}


def candidate_paths() -> list[Path]:
    """Где искать words.js, если путь не передан явно."""
    here = Path(__file__).resolve()
    paths: list[Path] = []
    from_env = os.environ.get("SEED_WORDS_JS")
    if from_env:
        paths.append(Path(from_env))
    paths.extend(
        [
            here.parents[1] / "seed_data" / "words.js",
            here.parents[2] / "public" / "src" / "words.js",
            here.parents[2] / "web" / "words.js",
            here.parents[3] / "tilashar" / "words.js",
        ]
    )
    return paths


def resolve_words_js(explicit: str | None = None) -> Path:
    """Возвращает путь к words.js или бросает FileNotFoundError со списком проверенных мест."""
    candidates = [Path(explicit)] if explicit else candidate_paths()
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("words.js не найден. Проверены: " + ", ".join(map(str, candidates)))


def parse_words_js(raw: str) -> list[dict[str, Any]]:
    """Достаёт JSON-массив тем из текста words.js."""
    text = raw.strip()
    # Файл живёт и как модуль клиента (export const TOPICS = [...]),
    # и как старый скрипт (window.TILASHAR_TOPICS = [...]).
    for prefix in (PREFIX, "export const TOPICS", "export const TILASHAR_TOPICS", "window.TILASHAR_TOPICS"):
        start = text.find(prefix)
        if start != -1:
            break
    else:
        raise ValueError("в файле нет объявления со списком тем")
    payload = text[start + len(prefix) :].strip()
    payload = payload.lstrip("=").strip().rstrip(";").strip()
    topics = json.loads(payload)
    if not isinstance(topics, list):
        raise ValueError("ожидался массив тем")
    return topics


def seed_topics(db: Session, topics: list[dict[str, Any]]) -> tuple[int, int]:
    """Создаёт или обновляет встроенные темы и их слова. Возвращает (тем, слов)."""
    word_total = 0
    for raw_topic in topics:
        slug = str(raw_topic["id"])
        title_kk = str(raw_topic.get("title") or slug)
        order_index = TOPIC_ORDER.index(slug) if slug in TOPIC_ORDER else len(TOPIC_ORDER)

        topic = db.execute(
            select(Topic).where(Topic.slug == slug, Topic.family_id.is_(None))
        ).scalar_one_or_none()
        if topic is None:
            topic = Topic(slug=slug, kind="builtin", family_id=None)
            db.add(topic)
        topic.title_kk = title_kk
        topic.title_ru = TOPIC_TITLES_RU.get(slug, title_kk)
        topic.pic = str(raw_topic.get("pic") or "")
        topic.kind = "builtin"
        topic.order_index = order_index
        db.flush()

        existing = {word.text_kk: word for word in topic.words}
        seen: set[str] = set()
        for index, entry in enumerate(raw_topic.get("words") or []):
            # Каждое слово во фронтенде — массив [текст, картинка/цвет/цифра, слоги].
            text_kk = str(entry[0])
            pic = str(entry[1]) if len(entry) > 1 else ""
            syllables = str(entry[2]) if len(entry) > 2 else text_kk
            seen.add(text_kk)

            word = existing.get(text_kk)
            if word is None:
                word = Word(topic_id=topic.id, text_kk=text_kk)
                db.add(word)
            word.text_ru = WORDS_RU.get(text_kk, "")
            word.syllables = syllables
            word.pic = pic
            word.audio_key = f"w:{text_kk}"
            word.order_index = index
            word_total += 1

        # Слова, пропавшие из words.js, удаляем — иначе они всплывут в уроке дня.
        for text_kk, word in existing.items():
            if text_kk not in seen:
                db.delete(word)
        db.flush()

    db.commit()
    return len(topics), word_total


def main(argv: list[str] | None = None) -> int:
    """CLI-обёртка: разбирает аргументы, читает файл, наполняет БД."""
    argv = argv if argv is not None else sys.argv[1:]
    path = resolve_words_js(argv[0] if argv else None)
    topics = parse_words_js(path.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        topic_count, word_count = seed_topics(db, topics)
    missing = [
        entry[0]
        for topic in topics
        for entry in topic.get("words") or []
        if entry[0] not in WORDS_RU
    ]
    print(f"Загружено тем: {topic_count}, слов: {word_count} (из {path})")
    if missing:
        print("Без русского перевода: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
