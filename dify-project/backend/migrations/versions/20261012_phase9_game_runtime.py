"""Add bounded per-game runtime state, read acknowledgements, and audit logs.

Revision ID: 20261012_phase9_runtime
Revises: 20261012_phase8c_mapping
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261012_phase9_runtime"
down_revision = "20261012_phase8c_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the Phase 9 runtime tables and bind recommendations to a phase."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "director_recommendations" in tables:
        columns = {
            column["name"]
            for column in inspector.get_columns("director_recommendations")
        }
        additions = (
            ("source_phase", sa.String(length=40)),
            ("source_phase_started_at", sa.DateTime(timezone=True)),
            ("source_last_public_message_id", sa.Integer()),
        )
        for name, column_type in additions:
            if name not in columns:
                op.add_column(
                    "director_recommendations",
                    sa.Column(name, column_type, nullable=True),
                )

    if "game_runtime_states" not in tables:
        op.create_table(
            "game_runtime_states",
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "last_director_analysis_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column("last_processed_public_message_id", sa.Integer(), nullable=True),
            sa.Column(
                "last_processed_phase_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "last_inactivity_phase_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column("ready_phase", sa.String(length=40), nullable=True),
            sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claim_token", sa.String(length=80), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_phase", sa.String(length=40), nullable=True),
            sa.Column(
                "claimed_phase_started_at", sa.DateTime(timezone=True), nullable=True
            ),
            sa.Column("action_status", sa.String(length=20), nullable=False),
            sa.Column("last_action_type", sa.String(length=40), nullable=True),
            sa.Column("last_error_code", sa.String(length=80), nullable=True),
            sa.CheckConstraint(
                "action_status IN ('idle', 'processing', 'failed')",
                name="ck_game_runtime_states_action_status",
            ),
            sa.CheckConstraint(
                "ready_phase IS NULL OR ready_phase IN "
                "('investigation_1', 'discussion_1', 'investigation_2', "
                "'discussion_2', 'final_discussion')",
                name="ck_game_runtime_states_ready_phase",
            ),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.PrimaryKeyConstraint("game_session_id"),
        )

    if "game_phase_acknowledgements" not in tables:
        op.create_table(
            "game_phase_acknowledgements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("phase", sa.String(length=40), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "phase IN ('act_1', 'act_2')",
                name="ck_game_phase_acknowledgements_phase",
            ),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id", "phase", name="uq_game_phase_acknowledgement"
            ),
        )

    if "game_runtime_action_logs" not in tables:
        op.create_table(
            "game_runtime_action_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("event_key", sa.String(length=200), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("action_type", sa.String(length=40), nullable=True),
            sa.Column("execution_status", sa.String(length=20), nullable=False),
            sa.Column("reason_code", sa.String(length=80), nullable=True),
            sa.Column("claim_token", sa.String(length=80), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("related_message_id", sa.Integer(), nullable=True),
            sa.Column("related_recommendation_id", sa.Integer(), nullable=True),
            sa.CheckConstraint(
                "execution_status IN ('processing', 'completed', 'failed', 'skipped')",
                name="ck_game_runtime_action_execution_status",
            ),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.ForeignKeyConstraint(["related_message_id"], ["messages.id"]),
            sa.ForeignKeyConstraint(
                ["related_recommendation_id"], ["director_recommendations.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id", "event_key", name="uq_game_runtime_action_event"
            ),
        )

    index_names = {
        index["name"] for index in inspect(bind).get_indexes("game_runtime_action_logs")
    }
    if "ix_game_runtime_action_game_started" not in index_names:
        op.create_index(
            "ix_game_runtime_action_game_started",
            "game_runtime_action_logs",
            ["game_session_id", "started_at"],
        )


def downgrade() -> None:
    """Drop Phase 9 runtime tables while leaving all prior game data intact."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "game_runtime_action_logs" in tables:
        indexes = {
            index["name"] for index in inspector.get_indexes("game_runtime_action_logs")
        }
        if "ix_game_runtime_action_game_started" in indexes:
            op.drop_index(
                "ix_game_runtime_action_game_started",
                table_name="game_runtime_action_logs",
            )
        op.drop_table("game_runtime_action_logs")
    if "game_phase_acknowledgements" in tables:
        op.drop_table("game_phase_acknowledgements")
    if "game_runtime_states" in tables:
        op.drop_table("game_runtime_states")

    if "director_recommendations" in tables:
        columns = {
            column["name"]
            for column in inspect(bind).get_columns("director_recommendations")
        }
        for name in (
            "source_last_public_message_id",
            "source_phase_started_at",
            "source_phase",
        ):
            if name in columns:
                op.drop_column("director_recommendations", name)
