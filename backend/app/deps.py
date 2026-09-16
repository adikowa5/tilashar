"""Зависимости FastAPI: сессия БД, текущий пользователь/семья, проверка владения ребёнком.

Здесь же лежат маленькие общие хелперы сериализации, которые нужны сразу
нескольким роутерам (`/me`, `/children`, урок дня).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import Child, Family, LessonDay, User
from app.schemas import ChildOut
from app.security import TOKEN_TYPE_ACCESS, TokenError, decode_token
from app.streaks import compute_streak

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    """Сессия БД на время запроса."""
    yield from session_scope()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="token_invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Пользователь из access-токена. 401 token_invalid, если токена нет или он плохой."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        payload = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    except TokenError as exc:
        raise _unauthorized() from exc
    user = db.get(User, payload["sub"])
    if user is None:
        raise _unauthorized()
    return user


def current_family(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Family:
    """Семья текущего пользователя."""
    family = db.get(Family, user.family_id)
    if family is None:
        raise _unauthorized()
    return family


def owned_child(
    child_id: str = Path(...),
    family: Family = Depends(current_family),
    db: Session = Depends(get_db),
) -> Child:
    """Ребёнок из пути, если он принадлежит семье вызывающего.

    Чужой или удалённый ребёнок даёт 404 (а не 403), чтобы не подтверждать
    существование идентификатора — так требует контракт.
    """
    child = db.get(Child, child_id)
    if child is None or child.family_id != family.id or child.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="child_not_found")
    return child


def active_days(db: Session, child_id: str) -> list[date]:
    """Даты, в которые ребёнок закрыл урок. Основа для расчёта серии."""
    rows = db.execute(
        select(LessonDay.day).where(
            LessonDay.child_id == child_id,
            LessonDay.completed.is_(True),
        )
    ).scalars()
    return list(rows)


def streak_for_child(db: Session, child_id: str, today: date | None = None) -> int:
    """Текущая серия ребёнка с учётом правила заморозки."""
    today = today or date.today()
    return compute_streak(active_days(db, child_id), today)


def build_child_out(db: Session, child: Child, today: date | None = None) -> ChildOut:
    """Собирает ответ Child: поля модели плюс вычисляемая серия."""
    return ChildOut(
        id=child.id,
        name=child.name,
        age=child.age,
        avatar=child.avatar,
        locale=child.locale,
        stars_total=child.stars_total,
        streak=streak_for_child(db, child.id, today),
        created_at=child.created_at,
    )
