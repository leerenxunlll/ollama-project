"""Fit the new game-selection status in the SQLite status column.

Revision ID: 20261005_status_width
Revises: 20261005_phase2
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261005_status_width"
down_revision = "20261005_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Align early Phase 2 databases with the final role-selection schema."""
    bind = op.get_bind()
    status_column = next(
        column
        for column in inspect(bind).get_columns("game_sessions")
        if column["name"] == "status"
    )
    current_length = getattr(status_column["type"], "length", 0) or 0
    if current_length < 50:
        with op.batch_alter_table("game_sessions", recreate="always") as batch:
            batch.alter_column(
                "status",
                existing_type=status_column["type"],
                type_=sa.String(length=50),
                nullable=False,
            )

    controller_constraint = next(
        (
            constraint
            for constraint in inspect(bind).get_check_constraints("game_characters")
            if constraint["name"] == "ck_game_characters_controller"
        ),
        None,
    )
    if controller_constraint and "IS NULL OR" not in (
        controller_constraint.get("sqltext") or ""
    ):
        with op.batch_alter_table("game_characters", recreate="always") as batch:
            batch.drop_constraint("ck_game_characters_controller", type_="check")
            batch.create_check_constraint(
                "ck_game_characters_controller",
                "controller_type IS NULL OR controller_type IN ('human', 'ai')",
            )


def downgrade() -> None:
    """Keep the wider SQLite column so stored status values are not truncated."""
    pass
