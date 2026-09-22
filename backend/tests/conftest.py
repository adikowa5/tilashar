"""Общие фикстуры: SQLite в памяти, приложение с подменённой сессией, вспомогательный контент.

Схема создаётся через ``Base.metadata.create_all`` — alembic в тестах не участвует.
Переменные окружения выставляются до импорта приложения, чтобы настройки
подхватили тестовые значения.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-bytes-long!!"
os.environ["SMS_PROVIDER"] = "console"
os.environ["MAX_CHILDREN"] = "4"
os.environ["CORS_ORIGINS"] = "*"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Topic, Word  # noqa: E402

API = "/api/v1"


@pytest.fixture()
def db() -> Iterator[Session]:
    """Чистая база в памяти на каждый тест.

    StaticPool держит одно соединение, поэтому и тест, и обработчики запроса
    видят одни и те же таблицы.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Как в Postgres: внешние ключи с ON DELETE CASCADE должны реально срабатывать.
    event.listen(engine, "connect", lambda conn, _rec: conn.execute("PRAGMA foreign_keys=ON"))
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    """TestClient поверх тестовой сессии."""
    app = create_app()

    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def content(db: Session) -> dict[str, list[str]]:
    """Две встроенные темы: alpha (10 слов) и beta (5 слов).

    Возвращает словарь slug -> список word_id в порядке order_index.
    """
    result: dict[str, list[str]] = {}
    for order, (slug, count) in enumerate([("alpha", 10), ("beta", 5)]):
        topic = Topic(
            slug=slug,
            title_kk=f"{slug}-kk",
            title_ru=f"{slug}-ru",
            pic="*",
            kind="builtin",
            family_id=None,
            order_index=order,
        )
        db.add(topic)
        db.flush()
        ids: list[str] = []
        for index in range(count):
            word = Word(
                topic_id=topic.id,
                text_kk=f"{slug}{index}",
                text_ru=f"перевод{index}",
                syllables=f"{slug}-{index}",
                pic="*",
                audio_key=f"w:{slug}{index}",
                order_index=index,
            )
            db.add(word)
            db.flush()
            ids.append(word.id)
        result[slug] = ids
    db.commit()
    return result


def login_as_guest(client: TestClient) -> dict[str, str]:
    """Новая семья на «устройстве», возвращает пару токенов."""
    response = client.post(f"{API}/auth/guest")
    assert response.status_code == 200, response.text
    return response.json()


def auth_header(tokens: dict[str, str]) -> dict[str, str]:
    """Заголовок Authorization из пары токенов."""
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture()
def tokens(client: TestClient) -> dict[str, str]:
    """Устройство семьи с сессией."""
    return login_as_guest(client)


@pytest.fixture()
def headers(tokens: dict[str, str]) -> dict[str, str]:
    """Готовый заголовок авторизации."""
    return auth_header(tokens)


@pytest.fixture()
def child(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    """Один ребёнок в семье авторизованного родителя."""
    response = client.post(
        f"{API}/children",
        json={"name": "Айша", "age": 7, "avatar": "fox", "locale": "kk"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
