"""Аутентификация: SMS-код, обмен на токены, гостевой вход, claim, refresh, logout."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import current_user, get_db
from app.models import AuthCode, Family, User, utcnow
from app.schemas import CodeIn, CodeSent, PhoneIn, RefreshIn, TokenPair
from app.security import TokenError, hash_code, issue_token_pair, revoke_refresh_token
from app.security import rotate_refresh_token, verify_code
from app.sms import build_sender, generate_code

router = APIRouter(prefix="/auth", tags=["auth"])

# Телефон в международном формате: плюс, код страны, 9-14 цифр.
PHONE_RE = re.compile(r"^\+[1-9]\d{9,14}$")


def normalize_phone(raw: str) -> str:
    """Приводит номер к виду +7XXXXXXXXXX. Бросает 400 phone_invalid на мусоре.

    Принимаем распространённые записи: с пробелами и дефисами, с ведущей 8
    (казахстанский локальный формат) и без плюса.
    """
    cleaned = re.sub(r"[\s\-()]", "", raw or "")
    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = "+7" + cleaned[1:]
    elif not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    if not PHONE_RE.match(cleaned):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone_invalid")
    return cleaned


def _consume_code(db: Session, phone: str, code: str) -> None:
    """Проверяет и «сжигает» последний выданный код для номера.

    Ошибки контракта: code_not_found (404), code_expired (400),
    too_many_attempts (429), code_invalid (400).
    """
    row = db.execute(
        select(AuthCode)
        .where(AuthCode.phone == phone, AuthCode.consumed_at.is_(None))
        .order_by(AuthCode.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="code_not_found")
    if row.expires_at <= utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_expired")
    if row.attempts >= settings.code_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts"
        )
    if not verify_code(code, row.code_hash):
        row.attempts += 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_invalid")
    row.consumed_at = utcnow()
    db.flush()


@router.post("/code", response_model=CodeSent)
def request_code(payload: PhoneIn, db: Session = Depends(get_db)) -> CodeSent:
    """Выдаёт SMS-код. Не больше CODE_REQUESTS_PER_HOUR запросов на номер в час."""
    phone = normalize_phone(payload.phone)

    since = utcnow() - timedelta(hours=1)
    recent = db.execute(
        select(AuthCode).where(AuthCode.phone == phone, AuthCode.created_at >= since)
    ).scalars().all()
    if len(recent) >= settings.code_requests_per_hour:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts"
        )

    code = generate_code()
    db.add(
        AuthCode(
            phone=phone,
            code_hash=hash_code(code),
            expires_at=utcnow() + timedelta(seconds=settings.code_ttl_sec),
        )
    )
    db.commit()

    build_sender().send_code(phone, code)
    return CodeSent(
        sent=True,
        dev_code=code if settings.dev_mode else None,
        retry_after=settings.code_retry_after_sec,
    )


@router.post("/token", response_model=TokenPair)
def exchange_code(payload: CodeIn, db: Session = Depends(get_db)) -> TokenPair:
    """Обменивает код на пару токенов. Пользователь и семья создаются при первом входе."""
    phone = normalize_phone(payload.phone)
    _consume_code(db, phone, payload.code)

    user = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if user is None:
        family = Family(is_guest=False)
        db.add(family)
        db.flush()
        user = User(family_id=family.id, phone=phone)
        db.add(user)
        db.flush()

    pair = issue_token_pair(db, user)
    db.commit()
    return TokenPair(**pair)


@router.post("/guest", response_model=TokenPair)
def guest_login(db: Session = Depends(get_db)) -> TokenPair:
    """Создаёт гостевую семью без телефона и сразу выдаёт токены."""
    family = Family(is_guest=True)
    db.add(family)
    db.flush()
    user = User(family_id=family.id, phone=None)
    db.add(user)
    db.flush()
    pair = issue_token_pair(db, user)
    db.commit()
    return TokenPair(**pair)


@router.post("/claim", response_model=TokenPair)
def claim_guest(
    payload: CodeIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TokenPair:
    """Привязывает гостевую семью к телефону, сохраняя детей и прогресс.

    Уже привязанная семья или занятый другим аккаунтом номер → 409 already_claimed.
    """
    family = db.get(Family, user.family_id)
    if family is None or not family.is_guest or user.phone is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_claimed")

    phone = normalize_phone(payload.phone)
    taken = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if taken is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_claimed")

    _consume_code(db, phone, payload.code)
    user.phone = phone
    family.is_guest = False
    pair = issue_token_pair(db, user)
    db.commit()
    return TokenPair(**pair)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)) -> TokenPair:
    """Ротация refresh-токена: старый отзывается, выдаётся новая пара."""
    try:
        pair = rotate_refresh_token(db, payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token_invalid"
        ) from exc
    db.commit()
    return TokenPair(**pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshIn, db: Session = Depends(get_db)) -> Response:
    """Отзывает refresh-токен. Повторный вызов с тем же токеном даёт 401 token_invalid."""
    try:
        revoke_refresh_token(db, payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token_invalid"
        ) from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
