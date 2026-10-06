"""Add phase timing, deterministic votes, and Director recommendations.

Revision ID: 20261006_phase7
Revises: 20261005_phase5
Create Date: 2026-10-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261006_phase7"
down_revision = "20261005_phase5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade Phase 6 databases while tolerating empty-database create_all."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "game_sessions" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("game_sessions")}
    if "phase_started_at" not in columns:
        op.add_column(
            "game_sessions",
            sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.execute(
            "UPDATE game_sessions SET phase_started_at = "
            "COALESCE(started_at, created_at) "
            "WHERE phase_started_at IS NULL AND status IN "
            "('in_progress', 'finished', 'completed', 'abandoned')"
        )

    if "votes" not in tables:
        op.create_table(
            "votes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("voter_game_character_id", sa.Integer(), nullable=False),
            sa.Column("target_game_character_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["game_session_id"],
                ["game_sessions.id"],
                name="fk_votes_game_session_id",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "voter_game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_votes_voter_game_character_session",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "target_game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_votes_target_game_character_session",
            ),
            sa.CheckConstraint(
                "voter_game_character_id != target_game_character_id",
                name="ck_vote_not_self",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id",
                "voter_game_character_id",
                name="uq_vote_per_game_character",
            ),
        )
        op.create_index("ix_votes_game_session_id", "votes", ["game_session_id"])

    if "director_recommendations" not in tables:
        op.create_table(
            "director_recommendations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("pace", sa.String(length=20), nullable=False),
            sa.Column("narrative_risk", sa.String(length=20), nullable=False),
            sa.Column("recommended_action", sa.String(length=40), nullable=False),
            sa.Column("target_game_character_id", sa.Integer(), nullable=True),
            sa.Column("clue_id", sa.Integer(), nullable=True),
            sa.Column("public_message_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "pace IN ('on_track', 'stalled', 'rushed', 'off_track')",
                name="ck_director_recommendations_pace",
            ),
            sa.CheckConstraint(
                "narrative_risk IN ('low', 'medium', 'high')",
                name="ck_director_recommendations_narrative_risk",
            ),
            sa.CheckConstraint(
                "recommended_action IN ('no_action', 'request_ai_speaker', "
                "'recommend_phase_advance', 'suggest_clue_hint', "
                "'highlight_public_fact')",
                name="ck_director_recommendations_action",
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'applied', 'rejected', 'advisory')",
                name="ck_director_recommendations_status",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id"],
                ["game_sessions.id"],
                name="fk_director_recommendations_game_session_id",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "target_game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_director_recommendations_target_session",
            ),
            sa.ForeignKeyConstraint(
                ["clue_id"], ["clues.id"], name="fk_director_recommendations_clue_id"
            ),
            sa.ForeignKeyConstraint(
                ["public_message_id"],
                ["messages.id"],
                name="fk_director_recommendations_public_message_id",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_director_recommendations_game_created",
            "director_recommendations",
            ["game_session_id", "created_at"],
        )


def downgrade() -> None:
    """Remove Phase 7 additions without changing earlier gameplay tables."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "director_recommendations" in tables:
        op.drop_index(
            "ix_director_recommendations_game_created",
            table_name="director_recommendations",
        )
        op.drop_table("director_recommendations")
    if "votes" in tables:
        op.drop_index("ix_votes_game_session_id", table_name="votes")
        op.drop_table("votes")

    if "game_sessions" in tables:
        columns = {
            column["name"] for column in inspect(bind).get_columns("game_sessions")
        }
        if "phase_started_at" in columns:
            with op.batch_alter_table("game_sessions") as batch:
                batch.drop_column("phase_started_at")
