"""Вход без регистрации: гость, код семьи, refresh, logout, ограничения частоты."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import API, auth_header, login_as_guest


def test_guest_gets_tokens_and_empty_family(client: TestClient) -> None:
    tokens = login_as_guest(client)
    assert tokens["token_type"] == "bearer"
    me = client.get(f"{API}/me", headers=auth_header(tokens))
    assert me.status_code == 200
    body = me.json()
    assert body["children"] == []
    assert "phone" not in body["user"]


def test_me_requires_token(client: TestClient) -> None:
    assert client.get(f"{API}/me").status_code == 401
    bad = client.get(f"{API}/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "token_invalid"


def test_phone_login_is_gone(client: TestClient) -> None:
    assert client.post(f"{API}/auth/code", json={"phone": "+77011234567"}).status_code in (404, 405)
    assert client.post(f"{API}/auth/token", json={"phone": "+77011234567", "code": "000000"}).status_code in (404, 405)


def test_family_code_joins_second_device(client: TestClient, headers: dict[str, str], child: dict) -> None:
    code = client.get(f"{API}/family/code", headers=headers).json()["code"]
    assert len(code) == 9 and code[4] == "-"
    # тот же код при повторном запросе
    assert client.get(f"{API}/family/code", headers=headers).json()["code"] == code

    joined = client.post(f"{API}/auth/join", json={"code": code.lower().replace("-", " ")})
    assert joined.status_code == 200, joined.text
    second = auth_header(joined.json())
    kids = client.get(f"{API}/me", headers=second).json()["children"]
    assert [k["id"] for k in kids] == [child["id"]]


def test_wrong_family_code(client: TestClient) -> None:
    response = client.post(f"{API}/auth/join", json={"code": "ABCD-EFGH"})
    assert response.status_code == 404
    assert response.json()["detail"] == "code_invalid"


def test_rotated_code_stops_working(client: TestClient, headers: dict[str, str]) -> None:
    old = client.get(f"{API}/family/code", headers=headers).json()["code"]
    new = client.post(f"{API}/family/code", headers=headers).json()["code"]
    assert new != old
    assert client.post(f"{API}/auth/join", json={"code": old}).status_code == 404
    assert client.post(f"{API}/auth/join", json={"code": new}).status_code == 200


def test_join_attempts_are_limited(client: TestClient) -> None:
    for _ in range(12):
        assert client.post(f"{API}/auth/join", json={"code": "AAAA-AAAA"}).status_code == 404
    limited = client.post(f"{API}/auth/join", json={"code": "AAAA-AAAA"})
    assert limited.status_code == 429
    assert limited.json()["detail"] == "too_many_attempts"


def test_guest_creation_is_limited(client: TestClient) -> None:
    for _ in range(20):
        assert client.post(f"{API}/auth/guest").status_code == 200
    assert client.post(f"{API}/auth/guest").status_code == 429


def test_refresh_rotates_and_revokes_old(client: TestClient) -> None:
    tokens = login_as_guest(client)
    fresh = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert fresh.status_code == 200
    again = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401


def test_logout_revokes_refresh(client: TestClient) -> None:
    tokens = login_as_guest(client)
    assert client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_config_endpoint(client: TestClient) -> None:
    body = client.get(f"{API}/config").json()
    assert body["max_children"] == 4
    assert "sms_provider" not in body
