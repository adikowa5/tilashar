"""Без телефонов: код семьи, редактор автора, файлы в базе, фразы похвалы.

- families: join_code (код семьи), last_seen_at (для уборки брошенных семей);
- users: колонка phone удалена, таблица auth_codes удалена — номера телефонов больше не храним;
- rate_hits: счётчики ограничения частоты;
- media: записи голоса и картинки в базе;
- topics: картинка, публикация, updated_at; words: голос автора, голос модели, картинка;
- phrases: фразы похвалы с голосом автора и модели.

Revision ID: 0002_no_phone_author_content
Revises: 0001_initial
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_no_phone_author_content"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("ext", sa.String(length=8), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256", name="uq_media_sha256"),
    )

    op.create_table(
        "rate_hits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_hits_key", "rate_hits", ["key"])
    op.create_index("ix_rate_hits_at", "rate_hits", ["at"])

    op.create_table(
        "phrases",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("text_kk", sa.String(length=128), nullable=False),
        sa.Column("text_ru", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_id", sa.String(length=36), nullable=True),
        sa.Column("model_audio_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["audio_id"], ["media.id"], name="fk_phrases_audio", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_audio_id"], ["media.id"], name="fk_phrases_model_audio", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    with op.batch_alter_table("families") as batch:
        batch.add_column(sa.Column("join_code", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch.create_unique_constraint("uq_families_join_code", ["join_code"])
    op.create_index("ix_families_last_seen_at", "families", ["last_seen_at"])

    with op.batch_alter_table("users") as batch:
        batch.drop_column("phone")
    op.drop_table("auth_codes")

    with op.batch_alter_table("topics") as batch:
        batch.add_column(sa.Column("image_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.create_foreign_key("fk_topics_image", "media", ["image_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("words") as batch:
        batch.add_column(sa.Column("audio_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("model_audio_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("image_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.create_foreign_key("fk_words_audio", "media", ["audio_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_words_model_audio", "media", ["model_audio_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_words_image", "media", ["image_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("words") as batch:
        batch.drop_constraint("fk_words_image", type_="foreignkey")
        batch.drop_constraint("fk_words_model_audio", type_="foreignkey")
        batch.drop_constraint("fk_words_audio", type_="foreignkey")
        batch.drop_column("updated_at")
        batch.drop_column("image_id")
        batch.drop_column("model_audio_id")
        batch.drop_column("audio_id")
    with op.batch_alter_table("topics") as batch:
        batch.drop_constraint("fk_topics_image", type_="foreignkey")
        batch.drop_column("updated_at")
        batch.drop_column("is_published")
        batch.drop_column("image_id")
    op.create_table(
        "auth_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_codes_phone", "auth_codes", ["phone"])
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("phone", sa.String(length=20), nullable=True))
    op.drop_index("ix_families_last_seen_at", table_name="families")
    with op.batch_alter_table("families") as batch:
        batch.drop_constraint("uq_families_join_code", type_="unique")
        batch.drop_column("last_seen_at")
        batch.drop_column("join_code")
    op.drop_table("phrases")
    op.drop_index("ix_rate_hits_at", table_name="rate_hits")
    op.drop_index("ix_rate_hits_key", table_name="rate_hits")
    op.drop_table("rate_hits")
    op.drop_table("media")
