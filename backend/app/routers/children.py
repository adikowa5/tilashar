"""CRUD детей. Удаление мягкое, лимит активных детей — MAX_CHILDREN."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import build_child_out, current_family, get_db, owned_child
from app.models import Child, Family, utcnow
from app.schemas import ChildCreate, ChildOut, ChildPatch

router = APIRouter(prefix="/children", tags=["children"])

MIN_AGE = 6
MAX_AGE = 9


def _check_age(age: int) -> None:
    """Возраст вне 6-9 запрещён контрактом."""
    if age < MIN_AGE or age > MAX_AGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="age_out_of_range")


@router.get("", response_model=list[ChildOut])
def list_children(
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> list[ChildOut]:
    """Активные дети семьи в порядке создания."""
    children = db.execute(
        select(Child)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
        .order_by(Child.created_at)
    ).scalars().all()
    return [build_child_out(db, child) for child in children]


@router.post("", response_model=ChildOut, status_code=status.HTTP_201_CREATED)
def create_child(
    payload: ChildCreate,
    db: Session = Depends(get_db),
    family: Family = Depends(current_family),
) -> ChildOut:
    """Создаёт ребёнка. Больше MAX_CHILDREN активных — 409 too_many_children."""
    _check_age(payload.age)
    active = db.execute(
        select(func.count())
        .select_from(Child)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
    ).scalar_one()
    if active >= settings.max_children:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="too_many_children")

    child = Child(
        family_id=family.id,
        name=payload.name.strip(),
        age=payload.age,
        avatar=payload.avatar,
        locale=payload.locale,
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    return build_child_out(db, child)


@router.patch("/{child_id}", response_model=ChildOut)
def patch_child(
    payload: ChildPatch,
    db: Session = Depends(get_db),
    child: Child = Depends(owned_child),
) -> ChildOut:
    """Обновляет любое подмножество полей ребёнка."""
    if payload.age is not None:
        _check_age(payload.age)
        child.age = payload.age
    if payload.name is not None:
        child.name = payload.name.strip()
    if payload.avatar is not None:
        child.avatar = payload.avatar
    if payload.locale is not None:
        child.locale = payload.locale
    db.commit()
    db.refresh(child)
    return build_child_out(db, child)


@router.delete("/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_child(
    db: Session = Depends(get_db),
    child: Child = Depends(owned_child),
) -> Response:
    """Мягкое удаление: ребёнок пропадает из списков, прогресс остаётся в БД."""
    child.deleted_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
