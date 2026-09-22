"""Первичное наполнение базы: стартовые категории, фразы похвалы и голос модели.

Дальше материал ведёт автор в редакторе (#author), поэтому сидинг ничего не
перезаписывает и не удаляет: он только добавляет то, чего в базе ещё нет.
- категории и слова из words.js — только для категорий, которых ещё нет;
- фразы похвалы — если фразы с таким ключом нет;
- голос модели из seed_data/audio-pack.js — словам и фразам, у которых его ещё нет.

Запуск: ``python -m app.seed [путь/к/words.js]``. Повторный запуск безопасен.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.media import store
from app.models import Phrase, Topic, Word

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


PHRASES: list[tuple[str, str, str]] = [
    ("p:your_turn", "Енді сен айт!", "Теперь скажи ты!"),
    ("p:great", "Керемет!", "Отлично!"),
    ("p:good", "Жарайсың!", "Молодец!"),
    ("p:almost", "Жақсы! Тағы байқап көр.", "Хорошо! Попробуй ещё."),
    ("p:again", "Тағы бір рет айтшы.", "Скажи ещё разок."),
    ("p:silent", "Естімедім. Қаттырақ айтшы.", "Не расслышал. Скажи погромче."),
    ("p:mic_intro", "Микрофонды басып, сөзді айт.", "Нажми микрофон и скажи слово."),
    ("p:done", "Сабақ бітті! Жарайсың!", "Урок окончен! Молодец!"),
]


def seed_topics(db: Session, topics: list[dict[str, Any]]) -> tuple[int, int]:
    """Добавляет категории, которых ещё нет. Возвращает (новых категорий, новых слов)."""
    new_topics = new_words = 0
    for raw_topic in topics:
        slug = str(raw_topic["id"])
        exists = db.execute(
            select(Topic.id).where(Topic.slug == slug, Topic.family_id.is_(None))
        ).first()
        if exists is not None:
            continue                      # категорию уже ведёт автор — не трогаем
        title_kk = str(raw_topic.get("title") or slug)
        topic = Topic(
            slug=slug, kind="builtin", family_id=None, is_published=True,
            title_kk=title_kk, title_ru=TOPIC_TITLES_RU.get(slug, title_kk),
            pic=str(raw_topic.get("pic") or ""),
            order_index=TOPIC_ORDER.index(slug) if slug in TOPIC_ORDER else len(TOPIC_ORDER),
        )
        db.add(topic)
        db.flush()
        new_topics += 1
        for index, entry in enumerate(raw_topic.get("words") or []):
            # Слово во фронтенде — массив [текст, картинка/цвет/цифра, слоги].
            text_kk = str(entry[0])
            db.add(Word(
                topic_id=topic.id, text_kk=text_kk, text_ru=WORDS_RU.get(text_kk, ""),
                syllables=str(entry[2]) if len(entry) > 2 else text_kk,
                pic=str(entry[1]) if len(entry) > 1 else "",
                audio_key=f"w:{text_kk}", order_index=index,
            ))
            new_words += 1
    db.commit()
    return new_topics, new_words


def seed_phrases(db: Session) -> int:
    added = 0
    for index, (key, kk, ru) in enumerate(PHRASES):
        if db.get(Phrase, key) is None:
            db.add(Phrase(key=key, text_kk=kk, text_ru=ru, order_index=index))
            added += 1
    db.commit()
    return added


def audio_pack_path() -> Path | None:
    here = Path(__file__).resolve()
    for path in (here.parents[1] / "seed_data" / "audio-pack.js",
                 here.parents[2] / "public" / "src" / "audio-pack.js"):
        if path.is_file():
            return path
    return None


def parse_audio_pack(raw: str) -> dict[str, bytes]:
    """{"w:алма": mp3-байты, …} из ``export const AUDIO={...}``."""
    text = raw.strip()
    start = text.index("{")
    data = json.loads(text[start:].rstrip(";").strip())
    out: dict[str, bytes] = {}
    for key, uri in data.items():
        if isinstance(uri, str) and "," in uri:
            out[key] = base64.b64decode(uri.split(",", 1)[1])
    return out


def seed_model_audio(db: Session, pack: dict[str, bytes]) -> int:
    """Голос модели — словам и фразам, у которых его ещё нет. Возвращает число привязок."""
    linked = 0
    for word in db.execute(select(Word).join(Topic).where(Topic.family_id.is_(None))).unique().scalars():
        data = pack.get(f"w:{word.text_kk}")
        if data and word.model_audio_id is None:
            word.model_audio_id = store(db, data, "audio").id
            linked += 1
    for phrase in db.execute(select(Phrase)).unique().scalars():
        data = pack.get(phrase.key)
        if data and phrase.model_audio_id is None:
            phrase.model_audio_id = store(db, data, "audio").id
            linked += 1
    db.commit()
    return linked


def main(argv: list[str] | None = None) -> int:
    """CLI-обёртка: разбирает аргументы, читает файлы, наполняет БД."""
    argv = argv if argv is not None else sys.argv[1:]
    path = resolve_words_js(argv[0] if argv else None)
    topics = parse_words_js(path.read_text(encoding="utf-8"))
    pack_path = audio_pack_path()
    pack = parse_audio_pack(pack_path.read_text(encoding="utf-8")) if pack_path else {}
    with SessionLocal() as db:
        topic_count, word_count = seed_topics(db, topics)
        phrase_count = seed_phrases(db)
        audio_count = seed_model_audio(db, pack)
    print(f"Новых категорий: {topic_count}, слов: {word_count}, фраз: {phrase_count}, "
          f"звуков модели: {audio_count} (из {path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
