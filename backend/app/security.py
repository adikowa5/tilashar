"""Криптография: выпуск и проверка JWT, ротация refresh-токенов, токен автора."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import RefreshToken, User, utcnow

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_ADMIN = "admin"


class TokenError(Exception):
    """Токен невалиден, истёк, отозван или имеет неверный тип."""


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, now: datetime | None = None) -> str:
    """Короткоживущий access-токен."""
    issued = now or datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=settings.access_ttl_min)
    return _encode(
        {
            "sub": user_id,
            "type": TOKEN_TYPE_ACCESS,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid.uuid4()),
        }
    )


def create_refresh_token(user_id: str, jti: str, now: datetime | None = None) -> tuple[str, datetime]:
    """Refresh-токен и его момент истечения (naive UTC — как хранится в БД)."""
    issued = now or datetime.now(timezone.utc)
    expires = issued + timedelta(days=settings.refresh_ttl_days)
    token = _encode(
        {
            "sub": user_id,
            "type": TOKEN_TYPE_REFRESH,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": jti,
        }
    )
    return token, expires.replace(tzinfo=None)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Разбирает и проверяет подпись/срок токена. Бросает TokenError при любой проблеме."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError("wrong token type")
    if not payload.get("sub"):
        raise TokenError("no subject")
    return payload


def issue_token_pair(db: Session, user: User) -> dict[str, Any]:
    """Выпускает пару токенов и регистрирует jti refresh-токена в БД."""
    jti = str(uuid.uuid4())
    refresh, expires_at = create_refresh_token(user.id, jti)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    db.flush()
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_ttl_min * 60,
    }


def _load_live_refresh(db: Session, token: str) -> tuple[RefreshToken, User]:
    """Находит незотозванную и неистёкшую запись refresh-токена вместе с пользователем."""
    payload = decode_token(token, TOKEN_TYPE_REFRESH)
    row = db.get(RefreshToken, payload["jti"])
    if row is None or row.revoked_at is not None:
        raise TokenError("refresh revoked or unknown")
    if row.expires_at <= utcnow():
        raise TokenError("refresh expired")
    user = db.execute(select(User).where(User.id == row.user_id)).scalar_one_or_none()
    if user is None:
        raise TokenError("user gone")
    return row, user


def rotate_refresh_token(db: Session, token: str) -> dict[str, Any]:
    """Отзывает предъявленный refresh и выпускает новую пару (ротация одноразовая)."""
    row, user = _load_live_refresh(db, token)
    row.revoked_at = utcnow()
    return issue_token_pair(db, user)


def revoke_refresh_token(db: Session, token: str) -> None:
    """Отзывает refresh-токен (logout). Невалидный токен приводит к TokenError."""
    row, _user = _load_live_refresh(db, token)
    row.revoked_at = utcnow()


# --------------------------------------------------------------------------- автор


def _admin_key() -> str:
    """Ключ подписи токена автора зависит и от пароля: сменили пароль — старые токены умерли."""
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        ("admin:" + settings.admin_password).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def check_admin_password(password: str) -> bool:
    if not settings.admin_password:
        return False
    return hmac.compare_digest(
        hashlib.sha256(password.encode("utf-8")).digest(),
        hashlib.sha256(settings.admin_password.encode("utf-8")).digest(),
    )


def create_admin_token() -> tuple[str, int]:
    issued = datetime.now(timezone.utc)
    ttl = settings.admin_ttl_hours * 3600
    token = jwt.encode(
        {"sub": "author", "type": TOKEN_TYPE_ADMIN, "iat": int(issued.timestamp()),
         "exp": int(issued.timestamp()) + ttl},
        _admin_key(),
        algorithm=settings.jwt_algorithm,
    )
    return token, ttl


def verify_admin_token(token: str) -> bool:
    if not settings.admin_enabled:
        return False
    try:
        payload = jwt.decode(token, _admin_key(), algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return False
    return payload.get("type") == TOKEN_TYPE_ADMIN
