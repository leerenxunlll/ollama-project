"""Add role-selection states and per-character clue discoveries.

Revision ID: 20261005_phase2
Revises:
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app import models  # noqa: F401
from app.db.base import Base

revision = "20261005_phase2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade existing Phase 1 data or create the current schema if empty."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "game_sessions" not in tables:
        Base.metadata.create_all(bind=bind)
        return

    session_checks = inspector.get_check_constraints("game_sessions")
    status_constraint = next(
        (
            constraint
            for constraint in session_checks
            if constraint["name"] == "ck_game_sessions_status"
        ),
        None,
    )
    status_columns = {
        column["name"]: column for column in inspector.get_columns("game_sessions")
    }
    needs_status_constraint = status_constraint and (
        "waiting_for_character_selection"
        not in (status_constraint.get("sqltext") or "")
    )
    needs_status_width = (
        getattr(status_columns["status"]["type"], "length", 0) or 0
    ) < 50
    if needs_status_constraint or needs_status_width:
        with op.batch_alter_table("game_sessions", recreate="always") as batch:
            if needs_status_constraint:
                batch.drop_constraint("ck_game_sessions_status", type_="check")
                batch.create_check_constraint(
                    "ck_game_sessions_status",
                    "status IN ('waiting_for_character_selection', 'ready', "
                    "'in_progress', 'completed', 'abandoned')",
                )
            if needs_status_width:
                batch.alter_column(
                    "status",
                    existing_type=status_columns["status"]["type"],
                    type_=sa.String(length=50),
                    nullable=False,
                )

    character_columns = {
        column["name"]: column
        for column in inspect(bind).get_columns("game_characters")
    }
    controller_checks = inspect(bind).get_check_constraints("game_characters")
    controller_constraint = next(
        (
            constraint
            for constraint in controller_checks
            if constraint["name"] == "ck_game_characters_controller"
        ),
        None,
    )
    needs_controller_constraint = controller_constraint and (
        "IS NULL OR" not in (controller_constraint.get("sqltext") or "")
    )
    needs_nullable_controller = not character_columns["controller_type"]["nullable"]
    if needs_nullable_controller or needs_controller_constraint:
        with op.batch_alter_table("game_characters", recreate="always") as batch:
            if needs_controller_constraint:
                batch.drop_constraint("ck_game_characters_controller", type_="check")
                batch.create_check_constraint(
                    "ck_game_characters_controller",
                    "controller_type IS NULL OR controller_type IN ('human', 'ai')",
                )
            if needs_nullable_controller:
                batch.alter_column(
                    "controller_type",
                    existing_type=character_columns["controller_type"]["type"],
                    nullable=True,
                )

    if "game_character_clues" not in set(inspect(bind).get_table_names()):
        op.create_table(
            "game_character_clues",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_character_id", sa.Integer(), nullable=False),
            sa.Column("clue_id", sa.Integer(), nullable=False),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(length=80), nullable=True),
            sa.ForeignKeyConstraint(["clue_id"], ["clues.id"]),
            sa.ForeignKeyConstraint(["game_character_id"], ["game_characters.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_character_id", "clue_id", name="uq_game_character_clue"
            ),
        )


def downgrade() -> None:
    """Return existing data to the Phase 1 selection and controller schema."""
    bind = op.get_bind()
    if "game_character_clues" in set(inspect(bind).get_table_names()):
        op.drop_table("game_character_clues")

    op.execute(
        "UPDATE game_characters SET controller_type = 'ai' "
        "WHERE controller_type IS NULL"
    )
    with op.batch_alter_table("game_characters", recreate="always") as batch:
        batch.drop_constraint("ck_game_characters_controller", type_="check")
        batch.create_check_constraint(
            "ck_game_characters_controller",
            "controller_type IN ('human', 'ai')",
        )
        batch.alter_column(
            "controller_type",
            existing_type=sa.String(length=20),
            nullable=False,
        )

    op.execute(
        "UPDATE game_sessions SET status = 'in_progress' "
        "WHERE status IN ('waiting_for_character_selection', 'ready')"
    )
    with op.batch_alter_table("game_sessions", recreate="always") as batch:
        batch.drop_constraint("ck_game_sessions_status", type_="check")
        batch.create_check_constraint(
            "ck_game_sessions_status",
            "status IN ('in_progress', 'completed', 'abandoned')",
        )
        batch.alter_column(
            "status",
            existing_type=sa.String(length=50),
            type_=sa.String(length=20),
            nullable=False,
        )
