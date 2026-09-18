"""Загрузка, замена и удаление родительских записей голоса."""

from __future__ import annotations

import io
import wave

from fastapi.testclient import TestClient

from tests.conftest import API, auth_header, login_by_phone

KEY = "w:алма"


def make_wav(duration_ms: int = 500, sample_rate: int = 8000) -> bytes:
    """Собирает минимальный валидный моно-WAV нужной длительности (тишина)."""
    frames = int(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def upload(client: TestClient, headers: dict[str, str], key: str, payload: bytes,
           content_type: str = "audio/wav"):
    return client.put(
        f"{API}/voices",
        data={"key": key},
        files={"file": ("voice.wav", payload, content_type)},
        headers=headers,
    )


def test_upload_and_list_voice(client: TestClient, headers: dict[str, str]) -> None:
    response = upload(client, headers, KEY, make_wav())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == KEY
    assert body["url"].startswith("/api/v1/voices/audio/")
    assert body["url"].endswith(".wav")
    assert body["duration_ms"] == 500

    listed = client.get(f"{API}/voices", headers=headers)
    assert listed.status_code == 200
    assert [item["key"] for item in listed.json()] == [KEY]


def test_uploaded_audio_is_served_by_hash(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Содержимое отдаётся по capability-URL — без токена, но по неугадываемому хешу."""
    payload = make_wav()
    body = upload(client, headers, KEY, payload).json()
    audio = client.get(body["url"])  # заголовков намеренно нет
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content == payload

    missing = client.get(f"{API}/voices/audio/{'0' * 64}.wav")
    assert missing.status_code == 404


def test_reupload_replaces_record(client: TestClient, headers: dict[str, str]) -> None:
    first = upload(client, headers, KEY, make_wav(200)).json()
    second = upload(client, headers, KEY, make_wav(900)).json()
    assert second["url"] != first["url"]
    assert second["duration_ms"] == 900

    listed = client.get(f"{API}/voices", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["duration_ms"] == 900


def test_delete_voice(client: TestClient, headers: dict[str, str]) -> None:
    upload(client, headers, KEY, make_wav())
    response = client.delete(f"{API}/voices/{KEY}", headers=headers)
    assert response.status_code == 204
    assert client.get(f"{API}/voices", headers=headers).json() == []


def test_delete_unknown_voice_is_404(client: TestClient, headers: dict[str, str]) -> None:
    response = client.delete(f"{API}/voices/{KEY}", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "voice_not_found"


def test_bad_key_is_rejected(client: TestClient, headers: dict[str, str]) -> None:
    response = upload(client, headers, "x:алма", make_wav())
    assert response.status_code == 400
    assert response.json()["detail"] == "voice_key_invalid"

    assert upload(client, headers, "w:", make_wav()).status_code == 400


def test_phrase_key_is_allowed(client: TestClient, headers: dict[str, str]) -> None:
    response = upload(client, headers, "p:сәлеметсіз бе", make_wav())
    assert response.status_code == 200
    assert response.json()["key"] == "p:сәлеметсіз бе"


def test_too_large_file_is_rejected(client: TestClient, headers: dict[str, str]) -> None:
    payload = b"RIFF" + b"\x00" * (2 * 1024 * 1024 + 1)
    response = upload(client, headers, KEY, payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "file_too_large"


def test_wrong_content_type_is_rejected(client: TestClient, headers: dict[str, str]) -> None:
    response = upload(client, headers, KEY, make_wav(), content_type="audio/mpeg")
    assert response.status_code == 415
    assert response.json()["detail"] == "unsupported_media_type"


def test_voices_are_scoped_to_family(client: TestClient, headers: dict[str, str]) -> None:
    upload(client, headers, KEY, make_wav())
    stranger = auth_header(login_by_phone(client, "+77019998877"))
    assert client.get(f"{API}/voices", headers=stranger).json() == []
    assert client.delete(f"{API}/voices/{KEY}", headers=stranger).status_code == 404


def test_voices_require_auth(client: TestClient) -> None:
    assert client.get(f"{API}/voices").status_code == 401
