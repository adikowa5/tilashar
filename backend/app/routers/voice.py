"""Родительские записи голоса: список, загрузка и удаление.

Файлы лежат в MEDIA_ROOT/<family_id>/<sha256>.wav и отдаются статикой по /media/...
Записи ребёнка на сервере не хранятся вообще — распознавание идёт в браузере.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import wave
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import current_family, get_db
from app.models import Family, VoiceRecord, utcnow
from app.schemas import VoiceOut

router = APIRouter(tags=["voice"])

# Ключ записи: w:<слово> или p:<фраза>.
KEY_RE = re.compile(r"^[wp]:.{1,64}$", re.DOTALL)

ALLOWED_CONTENT_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}


def _check_key(key: str) -> str:
    """Проверяет ключ по регулярке контракта."""
    key = (key or "").strip()
    if not KEY_RE.match(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voice_key_invalid")
    return key


def _wav_duration_ms(payload: bytes) -> int:
    """Оценивает длительность WAV по заголовку. При нечитаемом файле возвращает 0."""
    with contextlib.suppress(wave.Error, EOFError, ValueError):
        with wave.open(io.BytesIO(payload), "rb") as handle:
            rate = handle.getframerate()
            if rate:
                return int(handle.getnframes() * 1000 / rate)
    return 0


def _to_out(record: VoiceRecord) -> VoiceOut:
    return VoiceOut(
        key=record.key,
        url=record.url,
        duration_ms=record.duration_ms,
        updated_at=record.updated_at,
    )


def _drop_file(path: str) -> None:
    """Удаляет файл, молча игнорируя отсутствие и проблемы доступа."""
    with contextlib.suppress(OSError):
        Path(path).unlink()


@router.get("/voices", response_model=list[VoiceOut])
def list_voices(
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> list[VoiceOut]:
    """Все записи семьи."""
    rows = db.execute(
        select(VoiceRecord)
        .where(VoiceRecord.family_id == family.id)
        .order_by(VoiceRecord.key)
    ).scalars().all()
    return [_to_out(row) for row in rows]


@router.put("/voices", response_model=VoiceOut)
def put_voice(
    key: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> VoiceOut:
    """Загружает или заменяет запись для ключа. WAV до MAX_VOICE_BYTES."""
    key = _check_key(key)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="unsupported_media_type"
        )

    payload = file.file.read(settings.max_voice_bytes + 1)
    if len(payload) > settings.max_voice_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file_too_large"
        )
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_empty")

    digest = hashlib.sha256(payload).hexdigest()
    folder = Path(settings.media_root) / family.id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest}.wav"
    target.write_bytes(payload)

    url = f"/media/{family.id}/{digest}.wav"
    record = db.execute(
        select(VoiceRecord).where(
            VoiceRecord.family_id == family.id, VoiceRecord.key == key
        )
    ).scalar_one_or_none()

    if record is None:
        record = VoiceRecord(family_id=family.id, key=key)
        db.add(record)
    elif record.sha256 != digest:
        _drop_file(record.path)  # старое содержимое больше не нужно

    record.sha256 = digest
    record.path = str(target)
    record.url = url
    record.size_bytes = len(payload)
    record.duration_ms = _wav_duration_ms(payload)
    record.updated_at = utcnow()
    db.commit()
    db.refresh(record)
    return _to_out(record)


@router.delete("/voices/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice(
    key: str,
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> Response:
    """Удаляет запись вместе с файлом."""
    key = _check_key(key)
    record = db.execute(
        select(VoiceRecord).where(
            VoiceRecord.family_id == family.id, VoiceRecord.key == key
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="voice_not_found")
    _drop_file(record.path)
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
