"""Профиль родителя и настройки семьи."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import build_child_out, current_family, current_user, get_db
from app.models import Child, Family, User
from app.schemas import FamilyOut, FamilyPatch, MeOut, UserOut, UserPatch

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
def read_me(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    family: Family = Depends(current_family),
) -> MeOut:
    """Пользователь, его семья и список активных детей — один запрос на старте приложения."""
    children = db.execute(
        select(Child)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
        .order_by(Child.created_at)
    ).scalars().all()
    return MeOut(
        user=UserOut.model_validate(user),
        family=FamilyOut.model_validate(family),
        children=[build_child_out(db, child) for child in children],
    )


@router.patch("/me", response_model=UserOut)
def patch_me(
    payload: UserPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UserOut:
    """Меняет настройки родителя (пока только язык интерфейса)."""
    if payload.locale is not None:
        user.locale = payload.locale
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/family", response_model=FamilyOut)
def patch_family(
    payload: FamilyPatch,
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> FamilyOut:
    """Меняет настройки семьи: включение эталонного (модельного) голоса."""
    if payload.model_voice is not None:
        family.model_voice = payload.model_voice
    db.commit()
    db.refresh(family)
    return FamilyOut.model_validate(family)
