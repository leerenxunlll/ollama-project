"""Persist AI vote reasons, message phases, and one result per game.

Revision ID: 20261015_phase11_voting_replay
Revises: 20261013_phase10_evidence
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261015_phase11_voting_replay"
down_revision = "20261013_phase10_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the small set of Phase 11 persistence fields and result table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    additions = {
        "messages": sa.Column("phase", sa.String(length=40), nullable=True),
        "votes": sa.Column("decision_reason", sa.Text(), nullable=True),
        "game_character_clues": sa.Column("phase", sa.String(length=40), nullable=True),
        "game_clue_disclosures": sa.Column(
            "phase", sa.String(length=40), nullable=True
        ),
    }
    for table_name, column in additions.items():
        columns = {item["name"] for item in inspector.get_columns(table_name)}
        if column.name not in columns:
            op.add_column(table_name, column)

    if "game_resolutions" in set(inspector.get_table_names()):
        return

    op.create_table(
        "game_resolutions",
        sa.Column("game_session_id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("culprit_game_character_id", sa.Integer(), nullable=False),
        sa.Column("vote_result", sa.String(length=30), nullable=False),
        sa.Column("accused_game_character_id", sa.Integer(), nullable=True),
        sa.Column("is_tie", sa.Boolean(), nullable=False),
        sa.Column("human_vote_target_id", sa.Integer(), nullable=False),
        sa.Column("human_identified_culprit", sa.Boolean(), nullable=False),
        sa.Column("case_outcome", sa.String(length=30), nullable=False),
        sa.Column("ending_narrative", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "vote_result IN ('culprit_identified', 'wrong_accusation', 'tie')",
            name="ck_game_resolutions_vote_result",
        ),
        sa.CheckConstraint(
            "case_outcome IN ('culprit_identified', 'wrong_accusation', 'tie')",
            name="ck_game_resolutions_case_outcome",
        ),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
        sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
        sa.ForeignKeyConstraint(
            ["game_session_id", "culprit_game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_game_resolutions_culprit_session",
        ),
        sa.ForeignKeyConstraint(
            ["game_session_id", "accused_game_character_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_game_resolutions_accused_session",
        ),
        sa.ForeignKeyConstraint(
            ["game_session_id", "human_vote_target_id"],
            ["game_characters.game_session_id", "game_characters.id"],
            name="fk_game_resolutions_human_target_session",
        ),
        sa.PrimaryKeyConstraint("game_session_id"),
    )


def downgrade() -> None:
    """Remove Phase 11 additions without changing earlier migrations."""
    op.drop_table("game_resolutions")
    with op.batch_alter_table("votes") as batch_op:
        batch_op.drop_column("decision_reason")
    with op.batch_alter_table("game_clue_disclosures") as batch_op:
        batch_op.drop_column("phase")
    with op.batch_alter_table("game_character_clues") as batch_op:
        batch_op.drop_column("phase")
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("phase")
