"""Поиск фотографий на Pexels для редактора автора.

Ключ живёт только на сервере. Клиент присылает номер выбранной фотографии,
сервер сам спрашивает её у Pexels и скачивает файл — так в базу не попадёт
ссылка на произвольный адрес.
"""

from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.schemas import PhotoOut

API = "https://api.pexels.com/v1"
TIMEOUT = httpx.Timeout(12.0)
# Размер medium — высота 350 px: на плитке смотрится чётко, весит около 40 КБ.
PICK_SIZE = "medium"


def _client() -> httpx.Client:
    if not settings.pexels_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="photos_disabled")
    return httpx.Client(timeout=TIMEOUT, headers={"Authorization": settings.pexels_api_key})


def _fail() -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="photos_unavailable")


def search(query: str, per_page: int = 24) -> list[PhotoOut]:
    query = (query or "").strip()
    if not query:
        return []
    try:
        with _client() as client:
            response = client.get(f"{API}/search", params={"query": query, "per_page": per_page, "orientation": "square"})
            response.raise_for_status()
            data = response.json()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — сеть или чужой формат ответа
        raise _fail() from None
    return [
        PhotoOut(
            id=item["id"],
            thumb=item["src"]["tiny"],
            alt=(item.get("alt") or "")[:200],
            photographer=item.get("photographer") or "",
            page_url=item.get("url") or "",
        )
        for item in data.get("photos", [])
    ]


def fetch(photo_id: int) -> tuple[bytes, str, str]:
    """Скачивает выбранную фотографию. Возвращает (байты, подпись, ссылка на страницу)."""
    try:
        with _client() as client:
            meta = client.get(f"{API}/photos/{photo_id}")
            if meta.status_code == 404:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo_not_found")
            meta.raise_for_status()
            photo = meta.json()
            src = photo["src"][PICK_SIZE]
            # Файл лежит на images.pexels.com; заголовок с ключом ему не нужен.
            file = httpx.get(src, timeout=TIMEOUT, follow_redirects=True)
            file.raise_for_status()
            data = file.content
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise _fail() from None
    author = photo.get("photographer") or "Pexels"
    return data, f"Фото: {author} / Pexels"[:200], photo.get("url") or ""
