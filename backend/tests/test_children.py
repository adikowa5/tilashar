"""CRUD детей, лимит на количество и изоляция чужих детей."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import API, auth_header, login_by_phone


def test_create_and_list_child(
    client: TestClient, headers: dict[str, str], child: dict[str, object]
) -> None:
    assert child["name"] == "Айша"
    assert child["age"] == 7
    assert child["stars_total"] == 0
    assert child["streak"] == 0

    listed = client.get(f"{API}/children", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [child["id"]]


def test_age_out_of_range(client: TestClient, headers: dict[str, str]) -> None:
    for age in (5, 10):
        response = client.post(
            f"{API}/children", json={"name": "Бота", "age": age}, headers=headers
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "age_out_of_range"


def test_limit_four_children(client: TestClient, headers: dict[str, str]) -> None:
    for index in range(4):
        response = client.post(
            f"{API}/children", json={"name": f"Бала {index}", "age": 7}, headers=headers
        )
        assert response.status_code == 201, response.text

    fifth = client.post(f"{API}/children", json={"name": "Бесінші", "age": 7}, headers=headers)
    assert fifth.status_code == 409
    assert fifth.json()["detail"] == "too_many_children"


def test_deleted_child_frees_a_slot(client: TestClient, headers: dict[str, str]) -> None:
    ids = []
    for index in range(4):
        ids.append(
            client.post(
                f"{API}/children", json={"name": f"Бала {index}", "age": 7}, headers=headers
            ).json()["id"]
        )
    assert client.delete(f"{API}/children/{ids[0]}", headers=headers).status_code == 204

    listed = client.get(f"{API}/children", headers=headers).json()
    assert ids[0] not in [item["id"] for item in listed]
    assert len(listed) == 3

    response = client.post(f"{API}/children", json={"name": "Жаңа", "age": 8}, headers=headers)
    assert response.status_code == 201


def test_patch_child(
    client: TestClient, headers: dict[str, str], child: dict[str, object]
) -> None:
    response = client.patch(
        f"{API}/children/{child['id']}",
        json={"name": "Айгерім", "age": 9, "avatar": "bear"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Айгерім"
    assert body["age"] == 9
    assert body["avatar"] == "bear"

    bad = client.patch(f"{API}/children/{child['id']}", json={"age": 3}, headers=headers)
    assert bad.status_code == 400
    assert bad.json()["detail"] == "age_out_of_range"


def test_deleted_child_is_not_reachable(
    client: TestClient, headers: dict[str, str], child: dict[str, object]
) -> None:
    assert client.delete(f"{API}/children/{child['id']}", headers=headers).status_code == 204
    response = client.patch(
        f"{API}/children/{child['id']}", json={"name": "X"}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "child_not_found"


def test_other_family_child_is_404(
    client: TestClient, headers: dict[str, str], child: dict[str, object]
) -> None:
    """Чужой ребёнок отвечает 404, а не 403 — чтобы не подтверждать его существование."""
    stranger = auth_header(login_by_phone(client, "+77019998877"))
    child_id = child["id"]

    assert client.patch(
        f"{API}/children/{child_id}", json={"name": "Hack"}, headers=stranger
    ).status_code == 404
    assert client.delete(f"{API}/children/{child_id}", headers=stranger).status_code == 404
    assert client.get(f"{API}/children/{child_id}/today", headers=stranger).status_code == 404
    assert client.get(f"{API}/children/{child_id}/progress", headers=stranger).status_code == 404
    assert (
        client.post(f"{API}/children/{child_id}/attempts", json=[], headers=stranger).status_code
        == 404
    )
    assert client.get(f"{API}/children", headers=stranger).json() == []


def test_children_require_auth(client: TestClient) -> None:
    assert client.get(f"{API}/children").status_code == 401


def test_patch_me_and_family(client: TestClient, headers: dict[str, str]) -> None:
    user = client.patch(f"{API}/me", json={"locale": "kk"}, headers=headers)
    assert user.status_code == 200
    assert user.json()["locale"] == "kk"

    family = client.patch(f"{API}/family", json={"model_voice": False}, headers=headers)
    assert family.status_code == 200
    assert family.json()["model_voice"] is False
