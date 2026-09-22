"""Ежедневная уборка. Её вызывает Vercel Cron с заголовком Authorization: Bearer <CRON_SECRET>."""

from __future__ import annotations

import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import delete, exists, func, or_, select, union
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import Attempt, Child, Family, Media, Phrase, RateHit, RefreshToken, Topic, Word, utcnow

router = APIRouter(prefix="/internal", tags=["service"])


def _check_cron(authorization: str | None) -> None:
    expected = f"Bearer {settings.cron_secret}"
    if not settings.cron_secret or not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="cron_unauthorized")


def cleanup(db: Session) -> dict[str, int]:
    now = utcnow()
    seen = func.coalesce(Family.last_seen_at, Family.created_at)
    has_attempts = exists().where(Attempt.child_id == Child.id, Child.family_id == Family.id)

    stale = select(Family.id).where(
        or_(
            (seen < now - timedelta(days=settings.inactive_empty_days)) & ~has_attempts,
            seen < now - timedelta(days=settings.inactive_days),
        )
    )
    family_ids = list(db.execute(stale).scalars())
    removed_families = 0
    if family_ids:
        # Дети, устройства, прогресс и записи уходят каскадом внешних ключей (ON DELETE CASCADE).
        removed_families = db.execute(delete(Family).where(Family.id.in_(family_ids))).rowcount or 0

    rate = db.execute(delete(RateHit).where(RateHit.at < now - timedelta(days=2))).rowcount or 0
    tokens = db.execute(
        delete(RefreshToken).where(
            or_(RefreshToken.expires_at < now, RefreshToken.revoked_at < now - timedelta(days=7))
        )
    ).rowcount or 0

    used = union(
        select(Word.audio_id), select(Word.model_audio_id), select(Word.image_id),
        select(Topic.image_id), select(Phrase.audio_id), select(Phrase.model_audio_id),
    ).subquery()
    orphans = db.execute(
        delete(Media).where(
            Media.id.not_in(select(used.c[0]).where(used.c[0].is_not(None))),
            Media.created_at < now - timedelta(days=1),
        )
    ).rowcount or 0
    db.commit()
    return {"families": removed_families, "rate_hits": rate, "tokens": tokens, "media": orphans}


@router.get("/cleanup")
def run_cleanup(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, int]:
    _check_cron(authorization)
    return cleanup(db)
