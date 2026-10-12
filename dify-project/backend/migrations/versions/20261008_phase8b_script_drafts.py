"""Add isolated storage for generated Script drafts.

Revision ID: 20261008_phase8b
Revises: 20261008_phase8a
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261008_phase8b"
down_revision = "20261008_phase8a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "script_drafts" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "script_drafts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("generation_request_json", sa.JSON(), nullable=False),
            sa.Column("blueprint_json", sa.JSON(), nullable=True),
            sa.Column("chapter_packs_json", sa.JSON(), nullable=False),
            sa.Column("step_durations_seconds_json", sa.JSON(), nullable=False),
            sa.Column("failed_step", sa.String(length=32), nullable=True),
            sa.Column("last_error_type", sa.String(length=64), nullable=True),
            sa.Column("generation_token", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('created', 'generating_blueprint', 'blueprint_ready', "
                "'generating_intro', 'intro_ready', 'generating_act_1', "
                "'act_1_ready', 'generating_act_2', 'draft_complete', "
                "'generation_failed')",
                name="ck_script_drafts_status",
            ),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("script_drafts")
