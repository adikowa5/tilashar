"""Аутентификация: код, токены, refresh, гостевой вход и claim."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import API, auth_header, login_by_phone

PHONE = "+77011234567"


def test_request_code_returns_dev_code(client: TestClient) -> None:
    response = client.post(f"{API}/auth/code", json={"phone": PHONE})
    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is True
    assert body["dev_code"] == "000000"
    assert body["retry_after"] == 60


def test_request_code_rejects_bad_phone(client: TestClient) -> None:
    response = client.post(f"{API}/auth/code", json={"phone": "12"})
    assert response.status_code == 400
    assert response.json()["detail"] == "phone_invalid"


def test_request_code_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        assert client.post(f"{API}/auth/code", json={"phone": PHONE}).status_code == 200
    response = client.post(f"{API}/auth/code", json={"phone": PHONE})
    assert response.status_code == 429
    assert response.json()["detail"] == "too_many_attempts"


def test_token_without_code_is_not_found(client: TestClient) -> None:
    response = client.post(f"{API}/auth/token", json={"phone": PHONE, "code": "000000"})
    assert response.status_code == 404
    assert response.json()["detail"] == "code_not_found"


def test_token_with_wrong_code(client: TestClient) -> None:
    client.post(f"{API}/auth/code", json={"phone": PHONE})
    response = client.post(f"{API}/auth/token", json={"phone": PHONE, "code": "111111"})
    assert response.status_code == 400
    assert response.json()["detail"] == "code_invalid"


def test_token_attempts_are_limited(client: TestClient) -> None:
    client.post(f"{API}/auth/code", json={"phone": PHONE})
    for _ in range(5):
        client.post(f"{API}/auth/token", json={"phone": PHONE, "code": "111111"})
    response = client.post(f"{API}/auth/token", json={"phone": PHONE, "code": "000000"})
    assert response.status_code == 429
    assert response.json()["detail"] == "too_many_attempts"


def test_login_gives_token_pair_and_me(client: TestClient) -> None:
    tokens = login_by_phone(client, PHONE)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 1800
    assert tokens["access_token"] and tokens["refresh_token"]

    response = client.get(f"{API}/me", headers=auth_header(tokens))
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["phone"] == PHONE
    assert body["family"]["is_guest"] is False
    assert body["children"] == []


def test_code_is_single_use(client: TestClient) -> None:
    login_by_phone(client, PHONE)
    response = client.post(f"{API}/auth/token", json={"phone": PHONE, "code": "000000"})
    assert response.status_code == 404


def test_me_requires_token(client: TestClient) -> None:
    assert client.get(f"{API}/me").status_code == 401
    response = client.get(f"{API}/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
    assert response.json()["detail"] == "token_invalid"


def test_refresh_rotates_and_revokes_old(client: TestClient) -> None:
    tokens = login_by_phone(client, PHONE)
    first = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    rotated = first.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["detail"] == "token_invalid"

    assert client.get(f"{API}/me", headers=auth_header(rotated)).status_code == 200


def test_logout_revokes_refresh(client: TestClient) -> None:
    tokens = login_by_phone(client, PHONE)
    response = client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204
    again = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401


def test_guest_login_creates_guest_family(client: TestClient) -> None:
    tokens = client.post(f"{API}/auth/guest").json()
    body = client.get(f"{API}/me", headers=auth_header(tokens)).json()
    assert body["family"]["is_guest"] is True
    assert body["user"]["phone"] is None


def test_guest_claim_keeps_children(client: TestClient) -> None:
    guest = client.post(f"{API}/auth/guest").json()
    guest_headers = auth_header(guest)
    created = client.post(
        f"{API}/children",
        json={"name": "Ерке", "age": 6},
        headers=guest_headers,
    )
    assert created.status_code == 201
    child_id = created.json()["id"]

    client.post(f"{API}/auth/code", json={"phone": PHONE})
    claimed = client.post(
        f"{API}/auth/claim",
        json={"phone": PHONE, "code": "000000"},
        headers=guest_headers,
    )
    assert claimed.status_code == 200

    body = client.get(f"{API}/me", headers=auth_header(claimed.json())).json()
    assert body["family"]["is_guest"] is False
    assert body["user"]["phone"] == PHONE
    assert [item["id"] for item in body["children"]] == [child_id]


def test_claim_twice_conflicts(client: TestClient) -> None:
    guest = client.post(f"{API}/auth/guest").json()
    guest_headers = auth_header(guest)
    client.post(f"{API}/auth/code", json={"phone": PHONE})
    assert (
        client.post(
            f"{API}/auth/claim",
            json={"phone": PHONE, "code": "000000"},
            headers=guest_headers,
        ).status_code
        == 200
    )
    client.post(f"{API}/auth/code", json={"phone": "+77019998877"})
    again = client.post(
        f"{API}/auth/claim",
        json={"phone": "+77019998877", "code": "000000"},
        headers=guest_headers,
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "already_claimed"


def test_claim_to_taken_phone_conflicts(client: TestClient) -> None:
    login_by_phone(client, PHONE)
    guest = client.post(f"{API}/auth/guest").json()
    client.post(f"{API}/auth/code", json={"phone": PHONE})
    response = client.post(
        f"{API}/auth/claim",
        json={"phone": PHONE, "code": "000000"},
        headers=auth_header(guest),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "already_claimed"


def test_config_endpoint(client: TestClient) -> None:
    body = client.get(f"{API}/config").json()
    assert body["sms_provider"] == "console"
    assert body["dev_mode"] is True
    assert body["max_children"] == 4
