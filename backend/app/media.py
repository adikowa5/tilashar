"""Файлы в базе: проверка типа по содержимому, сохранение без дублей, адрес для клиента."""

from __future__ import annotations

import contextlib
import hashlib
import io
import wave

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Media

MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 1024 * 1024

# SVG намеренно не принимаем: внутри может быть скрипт.
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
)


def sniff_image(data: bytes) -> tuple[str, str] | None:
    for magic, ctype, ext in IMAGE_SIGNATURES:
        if data.startswith(magic):
            return ctype, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def sniff_audio(data: bytes) -> tuple[str, str] | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg", "mp3"
    return None


def wav_duration_ms(data: bytes) -> int:
    with contextlib.suppress(wave.Error, EOFError, ValueError):
        with wave.open(io.BytesIO(data), "rb") as handle:
            rate = handle.getframerate()
            if rate:
                return int(handle.getnframes() * 1000 / rate)
    return 0


def read_upload(file: UploadFile, limit: int) -> bytes:
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_empty")
    return data


def store(db: Session, data: bytes, kind: str, credit: str = "", source_url: str = "") -> Media:
    """Сохраняет файл (или возвращает уже сохранённый с тем же содержимым)."""
    sniffed = sniff_image(data) if kind == "image" else sniff_audio(data)
    if sniffed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="unsupported_media_type"
        )
    ctype, ext = sniffed
    digest = hashlib.sha256(data).hexdigest()
    existing = db.execute(select(Media).where(Media.sha256 == digest)).scalar_one_or_none()
    if existing is not None:
        if credit and not existing.credit:
            existing.credit, existing.source_url = credit, source_url
        return existing
    media = Media(
        sha256=digest,
        kind=kind,
        content_type=ctype,
        ext=ext,
        data=data,
        size_bytes=len(data),
        duration_ms=wav_duration_ms(data) if ext == "wav" else 0,
        credit=credit,
        source_url=source_url,
    )
    db.add(media)
    db.flush()
    return media


def url_of(media: Media | None) -> str | None:
    return f"/api/v1/media/{media.sha256}.{media.ext}" if media is not None else None
