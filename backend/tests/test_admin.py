"""Редактор автора, публичный каталог, файлы, уборка."""

from __future__ import annotations

import io
import struct
import wave
import zlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Attempt, Child, Family, Media, Phrase, utcnow
from app.routers.internal import cleanup
from tests.conftest import API

PASSWORD = "correct horse battery"


def wav(ms: int = 300) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as h:
        h.setnchannels(1); h.setsampwidth(2); h.setframerate(8000)
        h.writeframes(b"\x01\x00" * int(8 * ms))
    return buf.getvalue()


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture()
def admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    response = client.post(f"{API}/admin/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-Admin-Token": response.json()["token"]}


def test_admin_disabled_without_password(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_password", "")
    assert client.post(f"{API}/admin/login", json={"password": "x"}).status_code == 503
    assert client.get(f"{API}/admin/catalog").status_code == 503


def test_wrong_password_and_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    for _ in range(10):
        assert client.post(f"{API}/admin/login", json={"password": "nope"}).status_code == 401
    assert client.post(f"{API}/admin/login", json={"password": PASSWORD}).status_code == 429


def test_admin_requires_token(client: TestClient, monkeypatch: pytest.MonkeyPatch, headers: dict) -> None:
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    assert client.get(f"{API}/admin/catalog").status_code == 401
    # токен семьи не годится для редактора
    family_token = headers["Authorization"].split()[1]
    assert client.get(f"{API}/admin/catalog", headers={"X-Admin-Token": family_token}).status_code == 401


def test_password_change_kills_tokens(client: TestClient, admin: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.get(f"{API}/admin/catalog", headers=admin).status_code == 200
    monkeypatch.setattr(settings, "admin_password", "another password")
    assert client.get(f"{API}/admin/catalog", headers=admin).status_code == 401


def test_topic_and_words_lifecycle(client: TestClient, admin: dict) -> None:
    topic = client.post(f"{API}/admin/topics", json={"title_kk": "Көлік", "title_ru": "Транспорт", "pic": "🚗"},
                        headers=admin)
    assert topic.status_code == 201, topic.text
    tid = topic.json()["id"]
    assert topic.json()["is_published"] is False

    # неопубликованную категорию семьи не видят
    assert all(t["id"] != tid for t in client.get(f"{API}/content/catalog").json()["topics"])

    word = client.post(f"{API}/admin/topics/{tid}/words", json={"text_kk": "машина", "text_ru": "машина"},
                       headers=admin).json()
    assert word["syllables"] == "машина"
    bulk = client.post(f"{API}/admin/topics/{tid}/words/bulk", headers=admin, json={"words": [
        {"text_kk": "пойыз", "text_ru": "поезд", "syllables": "по-йыз"},
        {"text_kk": "машина"},                       # дубль пропускается
        {"text_kk": "ұшақ", "text_ru": "самолёт", "syllables": "ұ-шақ"},
    ]})
    assert bulk.status_code == 201
    words = bulk.json()["words"]
    assert [w["text_kk"] for w in words] == ["машина", "пойыз", "ұшақ"]

    patched = client.patch(f"{API}/admin/words/{words[1]['id']}", json={"syllables": "пой-ыз"}, headers=admin)
    assert patched.json()["syllables"] == "пой-ыз"

    reordered = client.post(f"{API}/admin/topics/{tid}/words/order", headers=admin,
                            json={"ids": [words[2]["id"], words[0]["id"], words[1]["id"]]})
    assert [w["text_kk"] for w in reordered.json()["words"]] == ["ұшақ", "машина", "пойыз"]

    client.patch(f"{API}/admin/topics/{tid}", json={"is_published": True}, headers=admin)
    public = client.get(f"{API}/content/catalog").json()
    assert any(t["id"] == tid and len(t["words"]) == 3 for t in public["topics"])

    assert client.delete(f"{API}/admin/words/{words[0]['id']}", headers=admin).status_code == 204
    assert client.delete(f"{API}/admin/topics/{tid}", headers=admin).status_code == 204
    assert all(t["id"] != tid for t in client.get(f"{API}/admin/catalog", headers=admin).json()["topics"])


def test_word_audio_and_image(client: TestClient, admin: dict, content: dict) -> None:
    word_id = content["alpha"][0]
    audio = client.put(f"{API}/admin/words/{word_id}/audio", headers=admin,
                       files={"file": ("a.wav", wav(), "audio/wav")})
    assert audio.status_code == 200, audio.text
    url = audio.json()["audio_url"]
    assert url.endswith(".wav")
    served = client.get(url)
    assert served.status_code == 200 and served.content == wav()
    assert "immutable" in served.headers["cache-control"]

    image = client.put(f"{API}/admin/words/{word_id}/image", headers=admin,
                       files={"file": ("p.png", png(), "image/png")})
    assert image.status_code == 200
    assert image.json()["image_url"].endswith(".png")
    assert client.get(image.json()["image_url"]).headers["content-type"] == "image/png"

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    bad = client.put(f"{API}/admin/words/{word_id}/image", headers=admin,
                     files={"file": ("x.svg", svg, "image/svg+xml")})
    assert bad.status_code == 415

    cleared = client.delete(f"{API}/admin/words/{word_id}/audio", headers=admin)
    assert cleared.json()["audio_url"] is None


def test_catalog_etag(client: TestClient, content: dict) -> None:
    first = client.get(f"{API}/content/catalog")
    assert first.status_code == 200
    etag = first.headers["etag"]
    again = client.get(f"{API}/content/catalog", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_phrase_audio(client: TestClient, admin: dict, db: Session) -> None:
    db.add(Phrase(key="p:great", text_kk="Керемет!", text_ru="Отлично!"))
    db.commit()
    out = client.put(f"{API}/admin/phrases/p:great/audio", headers=admin,
                     files={"file": ("a.wav", wav(), "audio/wav")})
    assert out.status_code == 200
    phrases = client.get(f"{API}/content/catalog").json()["phrases"]
    assert phrases[0]["audio_url"] == out.json()["audio_url"]


def test_stats(client: TestClient, admin: dict, child: dict) -> None:
    stats = client.get(f"{API}/admin/stats", headers=admin).json()
    assert stats["families"] == 1 and stats["children"] == 1


def test_cleanup_removes_abandoned_families(client: TestClient, db: Session, headers: dict, child: dict,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    old = utcnow() - timedelta(days=90)
    active = db.query(Family).one()                                  # семья из фикстуры headers
    empty = Family(created_at=old, last_seen_at=old)
    busy = Family(created_at=old, last_seen_at=old)
    db.add_all([empty, busy])
    db.flush()
    kid = Child(family_id=busy.id, name="Ә", age=7)
    db.add(kid)
    db.flush()
    db.add(Media(sha256="f" * 64, kind="audio", content_type="audio/wav", ext="wav", data=b"x",
                 created_at=old))
    db.commit()
    from app.models import Word, Topic
    topic = Topic(slug="t", title_kk="t", title_ru="t")
    db.add(topic); db.flush()
    word = Word(topic_id=topic.id, text_kk="w")
    db.add(word); db.flush()
    db.add(Attempt(child_id=kid.id, word_id=word.id, stars=3, at=old, day=old.date()))
    db.commit()

    active_id, busy_id, empty_id = active.id, busy.id, empty.id
    result = cleanup(db)
    db.expire_all()
    ids = {f.id for f in db.query(Family).all()}
    assert active_id in ids and busy_id in ids and empty_id not in ids
    assert result["media"] == 1

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    assert client.get(f"{API}/internal/cleanup").status_code == 401
    assert client.get(f"{API}/internal/cleanup", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_photo_search_needs_key(client: TestClient, admin: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pexels_api_key", "")
    response = client.get(f"{API}/admin/photos", params={"q": "кошка"}, headers=admin)
    assert response.status_code == 503
    assert response.json()["detail"] == "photos_disabled"


def test_photo_search_and_attach(client: TestClient, admin: dict, content: dict,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers import admin as admin_router
    from app.schemas import PhotoOut

    monkeypatch.setattr(settings, "pexels_api_key", "test-key")
    monkeypatch.setattr(
        admin_router, "search_photos",
        lambda q, per_page=24: [PhotoOut(id=77, thumb="https://x/t.jpg", alt=q, photographer="Айгүл", page_url="https://p/77")],
    )
    found = client.get(f"{API}/admin/photos", params={"q": "мысық"}, headers=admin)
    assert found.status_code == 200
    assert found.json()[0]["photographer"] == "Айгүл"

    monkeypatch.setattr(admin_router, "fetch_photo", lambda pid: (png(), "Фото: Айгүл / Pexels", "https://p/77"))
    word_id = content["alpha"][0]
    out = client.post(f"{API}/admin/words/{word_id}/image/pexels", json={"photo_id": 77}, headers=admin)
    assert out.status_code == 200, out.text
    assert out.json()["image_credit"] == "Фото: Айгүл / Pexels"

    public = client.get(f"{API}/content/catalog").json()
    word = next(w for t in public["topics"] for w in t["words"] if w["id"] == word_id)
    assert word["image_credit"] == "Фото: Айгүл / Pexels"
    assert client.get(word["image_url"]).status_code == 200
