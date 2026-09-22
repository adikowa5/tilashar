"""Ограничение частоты по IP. Счётчики в базе: процессы на Vercel короткоживущие."""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RateHit, utcnow


def client_ip(request: Request) -> str:
    """IP клиента. За прокси Vercel настоящий адрес — первый в X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    real = request.headers.get("x-real-ip", "")
    if real:
        return real.strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def recent_hits(db: Session, key: str, window: timedelta) -> int:
    since = utcnow() - window
    return db.execute(
        select(func.count(RateHit.id)).where(RateHit.key == key, RateHit.at >= since)
    ).scalar_one()


def check(db: Session, key: str, limit: int, window: timedelta = timedelta(hours=1)) -> None:
    """429 too_many_attempts, если за окно уже было limit отметок."""
    if recent_hits(db, key, window) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too_many_attempts")


def hit(db: Session, key: str) -> None:
    """Добавляет отметку и сразу фиксирует её — даже если дальше запрос упадёт."""
    db.add(RateHit(key=key))
    db.commit()
