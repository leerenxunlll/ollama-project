"""Add the Phase 3 finished lifecycle status and normalize the intro phase.

Revision ID: 20261005_phase3
Revises: 20261005_status_width
Create Date: 2026-10-05
"""

from alembic import op
from sqlalchemy import inspect

revision = "20261005_phase3"
down_revision = "20261005_status_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing rows while allowing finished games in SQLite."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "game_sessions" not in tables:
        return

    status_constraint = next(
        (
            constraint
            for constraint in inspect(bind).get_check_constraints("game_sessions")
            if constraint["name"] == "ck_game_sessions_status"
        ),
        None,
    )
    status_check = (status_constraint or {}).get("sqltext") or ""
    if "'finished'" not in status_check:
        with op.batch_alter_table("game_sessions", recreate="always") as batch:
            if status_constraint is not None:
                batch.drop_constraint("ck_game_sessions_status", type_="check")
            batch.create_check_constraint(
                "ck_game_sessions_status",
                "status IN ("
                "'waiting_for_character_selection', 'ready', 'in_progress', "
                "'finished', 'completed', 'abandoned')",
            )

    op.execute(
        "UPDATE game_sessions SET current_phase = 'intro' "
        "WHERE current_phase = 'introduction'"
    )


def downgrade() -> None:
    """Map new finished states to the former completed state before rollback."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "game_sessions" not in tables:
        return

    status_constraint = next(
        (
            constraint
            for constraint in inspect(bind).get_check_constraints("game_sessions")
            if constraint["name"] == "ck_game_sessions_status"
        ),
        None,
    )
    status_check = (status_constraint or {}).get("sqltext") or ""
    if "'finished'" not in status_check:
        return

    op.execute(
        "UPDATE game_sessions SET status = 'completed' WHERE status = 'finished'"
    )
    op.execute(
        "UPDATE game_sessions SET current_phase = 'introduction' "
        "WHERE current_phase = 'intro'"
    )
    with op.batch_alter_table("game_sessions", recreate="always") as batch:
        batch.drop_constraint("ck_game_sessions_status", type_="check")
        batch.create_check_constraint(
            "ck_game_sessions_status",
            "status IN ("
            "'waiting_for_character_selection', 'ready', 'in_progress', "
            "'completed', 'abandoned')",
        )
