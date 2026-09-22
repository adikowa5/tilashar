"""Вход без регистрации: новое устройство создаёт семью (гость) или подключается по коду семьи.

Телефонов и паролей у семей нет. Сессия устройства — пара JWT с ротацией refresh-токена.
"""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ratelimit
from app.config import settings
from app.deps import current_family, get_db
from app.models import Family, User, utcnow
from app.schemas import FamilyCodeOut, JoinIn, RefreshIn, TokenPair
from app.security import TokenError, issue_token_pair, revoke_refresh_token, rotate_refresh_token

router = APIRouter(tags=["auth"])

# Без похожих друг на друга символов (0/O, 1/I/L), чтобы код легко продиктовать.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


def normalize_code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def new_join_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        taken = db.execute(select(Family.id).where(Family.join_code == code)).first()
        if taken is None:
            return code


def pretty(code: str) -> str:
    return f"{code[:4]}-{code[4:]}" if len(code) == CODE_LENGTH else code


def _new_device(db: Session, family: Family) -> TokenPair:
    user = User(family_id=family.id)
    db.add(user)
    db.flush()
    family.last_seen_at = utcnow()
    pair = issue_token_pair(db, user)
    db.commit()
    return TokenPair(**pair)


@router.post("/auth/guest", response_model=TokenPair)
def guest_login(request: Request, db: Session = Depends(get_db)) -> TokenPair:
    """Новая семья на этом устройстве. Не больше GUEST_PER_HOUR семей в час с одного IP."""
    key = "guest:" + ratelimit.client_ip(request)
    ratelimit.check(db, key, settings.guest_per_hour)
    ratelimit.hit(db, key)
    family = Family(is_guest=True)
    db.add(family)
    db.flush()
    return _new_device(db, family)


@router.post("/auth/join", response_model=TokenPair)
def join_family(payload: JoinIn, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    """Подключает устройство к семье по коду. Неверный код → 404 code_invalid."""
    key = "join:" + ratelimit.client_ip(request)
    ratelimit.check(db, key, settings.join_attempts_per_hour)
    code = normalize_code(payload.code)
    family = None
    if len(code) == CODE_LENGTH:
        family = db.execute(select(Family).where(Family.join_code == code)).scalar_one_or_none()
    if family is None:
        ratelimit.hit(db, key)          # считаем только промахи: подбор кода упирается в лимит
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="code_invalid")
    return _new_device(db, family)


@router.get("/family/code", response_model=FamilyCodeOut)
def read_family_code(db: Session = Depends(get_db), family: Family = Depends(current_family)) -> FamilyCodeOut:
    """Код семьи для второго устройства. Создаётся при первом запросе."""
    if not family.join_code:
        family.join_code = new_join_code(db)
        db.commit()
    return FamilyCodeOut(code=pretty(family.join_code))


@router.post("/family/code", response_model=FamilyCodeOut)
def rotate_family_code(db: Session = Depends(get_db), family: Family = Depends(current_family)) -> FamilyCodeOut:
    """Новый код: старый перестаёт работать (уже подключённые устройства остаются)."""
    family.join_code = new_join_code(db)
    db.commit()
    return FamilyCodeOut(code=pretty(family.join_code))


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(payload: RefreshIn, db: Session = Depends(get_db)) -> TokenPair:
    """Ротация refresh-токена: старый отзывается, выдаётся новая пара."""
    try:
        pair = rotate_refresh_token(db, payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_invalid") from exc
    db.commit()
    return TokenPair(**pair)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshIn, db: Session = Depends(get_db)) -> Response:
    """Отзывает refresh-токен. Повторный вызов с тем же токеном даёт 401 token_invalid."""
    try:
        revoke_refresh_token(db, payload.refresh_token)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_invalid") from exc
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
