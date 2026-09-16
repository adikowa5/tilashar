"""Урок дня, попытки, прогресс и чистая логика серии."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Child
from app.routers.lesson import build_plan
from app.seed import parse_words_js
from app.streaks import compute_streak, is_frozen
from tests.conftest import API

TODAY = date(2026, 9, 15)


# --------------------------------------------------------------------------- серия


def test_streak_empty_history() -> None:
    assert compute_streak([], TODAY) == 0


def test_streak_single_day() -> None:
    assert compute_streak([TODAY], TODAY) == 1


def test_streak_consecutive_days() -> None:
    days = [TODAY - timedelta(days=offset) for offset in range(5)]
    assert compute_streak(days, TODAY) == 5


def test_streak_survives_one_missed_day() -> None:
    """Пропуск одного дня замораживает серию, но не обнуляет её."""
    days = [TODAY, TODAY - timedelta(days=2), TODAY - timedelta(days=3)]
    assert compute_streak(days, TODAY) == 3


def test_streak_breaks_on_two_missed_days() -> None:
    """Два пропущенных дня подряд обрывают серию — считается только хвост."""
    days = [TODAY, TODAY - timedelta(days=3), TODAY - timedelta(days=4)]
    assert compute_streak(days, TODAY) == 1


def test_streak_frozen_when_yesterday_missed() -> None:
    days = [TODAY - timedelta(days=2), TODAY - timedelta(days=3)]
    assert compute_streak(days, TODAY) == 2
    assert is_frozen(days, TODAY) is True


def test_streak_zero_after_two_idle_days() -> None:
    days = [TODAY - timedelta(days=3), TODAY - timedelta(days=4)]
    assert compute_streak(days, TODAY) == 0
    assert is_frozen(days, TODAY) is False


def test_streak_ignores_duplicates_and_future() -> None:
    days = [TODAY, TODAY, TODAY + timedelta(days=1), TODAY - timedelta(days=1)]
    assert compute_streak(days, TODAY) == 2


def test_streak_yesterday_only_is_alive() -> None:
    assert compute_streak([TODAY - timedelta(days=1)], TODAY) == 1
    assert is_frozen([TODAY - timedelta(days=1)], TODAY) is False


# --------------------------------------------------------------------------- сидинг


def test_parse_words_js() -> None:
    raw = 'window.TILASHAR_TOPICS=[{"id":"t","title":"Т","pic":"*",' \
          '"words":[["алма","🍎","ал-ма"]]}];'
    topics = parse_words_js(raw)
    assert topics[0]["id"] == "t"
    assert topics[0]["words"][0] == ["алма", "🍎", "ал-ма"]


# --------------------------------------------------------------------------- урок дня


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_today_returns_eight_new_words(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    response = client.get(f"{API}/children/{child['id']}/today", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 8
    assert body["done"] == 0
    assert body["streak"] == 0
    assert len(body["items"]) == 8
    assert {item["status"] for item in body["items"]} == {"new"}
    assert {item["topic_slug"] for item in body["items"]} == {"alpha"}
    assert [item["word_id"] for item in body["items"]] == content["alpha"][:8]


def test_today_is_stable_within_a_day(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    first = client.get(f"{API}/children/{child['id']}/today", headers=headers).json()
    second = client.get(f"{API}/children/{child['id']}/today", headers=headers).json()
    assert [item["word_id"] for item in first["items"]] == [
        item["word_id"] for item in second["items"]
    ]


def test_attempts_update_progress_and_stars(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    payload = [
        {"word_id": word_id, "stars": 3, "heard": "ok", "mode": "asr", "at": _now()}
        for word_id in content["alpha"][:3]
    ]
    response = client.post(
        f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stars_total"] == 9
    assert body["day_done"] is False

    today = client.get(f"{API}/children/{child['id']}/today", headers=headers).json()
    assert today["done"] == 3
    assert today["total"] == 8
    done_ids = {item["word_id"] for item in today["items"] if item["status"] == "done"}
    assert done_ids == set(content["alpha"][:3])

    progress = client.get(f"{API}/children/{child['id']}/progress", headers=headers).json()
    assert progress[content["alpha"][0]] == {"stars": 3, "attempts": 1}


def test_attempts_are_idempotent(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    moment = _now()
    payload = [
        {"word_id": content["alpha"][0], "stars": 2, "heard": None, "mode": "manual",
         "at": moment}
    ]
    first = client.post(
        f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
    )
    second = client.post(
        f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
    )
    assert first.status_code == second.status_code == 200
    progress = client.get(f"{API}/children/{child['id']}/progress", headers=headers).json()
    assert progress[content["alpha"][0]] == {"stars": 2, "attempts": 1}


def test_best_stars_never_decrease(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    word_id = content["alpha"][0]
    client.post(
        f"{API}/children/{child['id']}/attempts",
        json=[{"word_id": word_id, "stars": 3, "mode": "asr", "at": _now()}],
        headers=headers,
    )
    client.post(
        f"{API}/children/{child['id']}/attempts",
        json=[{"word_id": word_id, "stars": 1, "mode": "asr", "at": _now()}],
        headers=headers,
    )
    progress = client.get(f"{API}/children/{child['id']}/progress", headers=headers).json()
    assert progress[word_id] == {"stars": 3, "attempts": 2}


def test_day_done_sets_streak(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    today = client.get(f"{API}/children/{child['id']}/today", headers=headers).json()
    payload = [
        {"word_id": item["word_id"], "stars": 3, "mode": "asr", "at": _now()}
        for item in today["items"]
    ]
    response = client.post(
        f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
    )
    body = response.json()
    assert body["day_done"] is True
    assert body["streak"] == 1
    assert body["stars_total"] == 24

    listed = client.get(f"{API}/children", headers=headers).json()
    assert listed[0]["streak"] == 1
    assert listed[0]["stars_total"] == 24


def test_attempt_for_unknown_word_is_404(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
) -> None:
    response = client.post(
        f"{API}/children/{child['id']}/attempts",
        json=[{"word_id": "no-such-word", "stars": 1, "mode": "asr", "at": _now()}],
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "word_not_found"


def test_plan_mixes_new_and_review(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
    db: Session,
) -> None:
    """После слабых попыток по 8 словам план на завтра — 2 новых плюс 6 повторов."""
    payload = [
        {"word_id": word_id, "stars": 1, "mode": "asr", "at": _now()}
        for word_id in content["alpha"][:8]
    ]
    assert (
        client.post(
            f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
        ).status_code
        == 200
    )

    child_row = db.get(Child, child["id"])
    assert child_row is not None
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    plan = build_plan(db, child_row, tomorrow)

    assert len(plan) == 8
    statuses = [item["status"] for item in plan]
    assert statuses.count("new") == 2
    assert statuses.count("review") == 6
    new_ids = {item["word_id"] for item in plan if item["status"] == "new"}
    assert new_ids == set(content["alpha"][8:10])
    review_ids = {item["word_id"] for item in plan if item["status"] == "review"}
    assert review_ids <= set(content["alpha"][:8])

    # Тот же день — тот же результат: выбор повторов детерминирован.
    assert build_plan(db, child_row, tomorrow) == plan


def test_plan_moves_to_next_topic_when_first_is_closed(
    client: TestClient,
    headers: dict[str, str],
    child: dict[str, object],
    content: dict[str, list[str]],
    db: Session,
) -> None:
    payload = [
        {"word_id": word_id, "stars": 3, "mode": "asr", "at": _now()}
        for word_id in content["alpha"]
    ]
    assert (
        client.post(
            f"{API}/children/{child['id']}/attempts", json=payload, headers=headers
        ).status_code
        == 200
    )
    child_row = db.get(Child, child["id"])
    assert child_row is not None
    plan = build_plan(db, child_row, datetime.now(timezone.utc).date() + timedelta(days=1))
    assert [item["topic_slug"] for item in plan] == ["beta"] * 5
    assert [item["word_id"] for item in plan] == content["beta"]


def test_progress_is_empty_for_fresh_child(
    client: TestClient, headers: dict[str, str], child: dict[str, object]
) -> None:
    response = client.get(f"{API}/children/{child['id']}/progress", headers=headers)
    assert response.status_code == 200
    assert response.json() == {}
