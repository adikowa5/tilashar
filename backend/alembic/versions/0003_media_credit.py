"""Подпись и ссылка на источник у файла — для фотографий из Pexels.

Revision ID: 0003_media_credit
Revises: 0002_no_phone_author_content
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_media_credit"
down_revision: str | None = "0002_no_phone_author_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media") as batch:
        batch.add_column(sa.Column("credit", sa.String(length=200), nullable=False, server_default=""))
        batch.add_column(sa.Column("source_url", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("media") as batch:
        batch.drop_column("source_url")
        batch.drop_column("credit")
