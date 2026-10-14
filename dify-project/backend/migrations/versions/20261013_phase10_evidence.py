"""Add clue knowledge and disclosure records for Phase 10.

Revision ID: 20261013_phase10_evidence
Revises: 20261012_phase9_runtime
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261013_phase10_evidence"
down_revision = "20261012_phase9_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create evidence tables and backfill direct knowledge from prior clues."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "game_runtime_states" in tables:
        columns = {
            column["name"] for column in inspector.get_columns("game_runtime_states")
        }
        if "last_processed_public_clue_disclosure_id" not in columns:
            op.add_column(
                "game_runtime_states",
                sa.Column("last_processed_public_clue_disclosure_id", sa.Integer()),
            )

    if "game_clue_disclosures" not in tables:
        op.create_table(
            "game_clue_disclosures",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("clue_id", sa.Integer(), nullable=False),
            sa.Column("source_game_character_id", sa.Integer(), nullable=False),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("target_game_character_id", sa.Integer(), nullable=True),
            sa.Column("related_message_id", sa.Integer(), nullable=True),
            sa.Column("client_request_id", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "visibility IN ('private', 'public')",
                name="ck_game_clue_disclosures_visibility",
            ),
            sa.CheckConstraint(
                "(visibility = 'private' AND target_game_character_id IS NOT NULL) "
                "OR (visibility = 'public' AND target_game_character_id IS NULL)",
                name="ck_game_clue_disclosures_target_visibility",
            ),
            sa.CheckConstraint(
                "target_game_character_id IS NULL OR "
                "target_game_character_id != source_game_character_id",
                name="ck_game_clue_disclosures_not_self",
            ),
            sa.ForeignKeyConstraint(["clue_id"], ["clues.id"]),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.ForeignKeyConstraint(
                ["game_session_id", "source_game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_game_clue_disclosures_source_session",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "target_game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_game_clue_disclosures_target_session",
            ),
            sa.ForeignKeyConstraint(["related_message_id"], ["messages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id",
                "client_request_id",
                name="uq_clue_disclosure_request",
            ),
        )
    disclosure_indexes = {
        index["name"] for index in inspect(bind).get_indexes("game_clue_disclosures")
    }
    if "uq_public_clue_disclosure" not in disclosure_indexes:
        op.create_index(
            "uq_public_clue_disclosure",
            "game_clue_disclosures",
            ["game_session_id", "clue_id"],
            unique=True,
            sqlite_where=sa.text("visibility = 'public'"),
        )
    if "uq_private_clue_disclosure" not in disclosure_indexes:
        op.create_index(
            "uq_private_clue_disclosure",
            "game_clue_disclosures",
            [
                "game_session_id",
                "clue_id",
                "source_game_character_id",
                "target_game_character_id",
            ],
            unique=True,
            sqlite_where=sa.text("visibility = 'private'"),
        )
    if "ix_game_clue_disclosures_game_created" not in disclosure_indexes:
        op.create_index(
            "ix_game_clue_disclosures_game_created",
            "game_clue_disclosures",
            ["game_session_id", "created_at"],
        )

    if "game_character_clue_knowledge" not in tables:
        op.create_table(
            "game_character_clue_knowledge",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("game_character_id", sa.Integer(), nullable=False),
            sa.Column("clue_id", sa.Integer(), nullable=False),
            sa.Column("knowledge_source", sa.String(length=30), nullable=False),
            sa.Column("source_disclosure_id", sa.Integer(), nullable=True),
            sa.Column("first_known_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "knowledge_source IN ('direct_acquisition', 'private_disclosure', "
                "'public_disclosure')",
                name="ck_game_character_clue_knowledge_source",
            ),
            sa.ForeignKeyConstraint(["clue_id"], ["clues.id"]),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.ForeignKeyConstraint(
                ["game_session_id", "game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_game_character_clue_knowledge_character_session",
            ),
            sa.ForeignKeyConstraint(
                ["source_disclosure_id"], ["game_clue_disclosures.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id",
                "game_character_id",
                "clue_id",
                name="uq_game_character_clue_knowledge",
            ),
        )
    knowledge_indexes = {
        index["name"]
        for index in inspect(bind).get_indexes("game_character_clue_knowledge")
    }
    if "ix_game_character_clue_knowledge_clue" not in knowledge_indexes:
        op.create_index(
            "ix_game_character_clue_knowledge_clue",
            "game_character_clue_knowledge",
            ["game_session_id", "clue_id"],
        )

    if "game_clue_disclosure_attempts" not in tables:
        op.create_table(
            "game_clue_disclosure_attempts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("game_character_id", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("requested_clue_id", sa.Integer(), nullable=True),
            sa.Column("reason_code", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
            sa.ForeignKeyConstraint(
                ["game_session_id", "message_id", "game_character_id"],
                [
                    "messages.game_session_id",
                    "messages.id",
                    "messages.sender_game_character_id",
                ],
                name="fk_clue_disclosure_attempt_message_sender",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "game_session_id",
                "message_id",
                name="uq_clue_disclosure_attempt_message",
            ),
        )
    attempt_indexes = {
        index["name"]
        for index in inspect(bind).get_indexes("game_clue_disclosure_attempts")
    }
    if "ix_clue_disclosure_attempt_game_created" not in attempt_indexes:
        op.create_index(
            "ix_clue_disclosure_attempt_game_created",
            "game_clue_disclosure_attempts",
            ["game_session_id", "created_at"],
        )

    bind.execute(
        sa.text(
            "INSERT OR IGNORE INTO game_character_clue_knowledge "
            "(game_session_id, game_character_id, clue_id, knowledge_source, "
            "source_disclosure_id, first_known_at) "
            "SELECT gc.game_session_id, gcc.game_character_id, gcc.clue_id, "
            "'direct_acquisition', NULL, gcc.discovered_at "
            "FROM game_character_clues AS gcc "
            "JOIN game_characters AS gc ON gc.id = gcc.game_character_id "
            "JOIN game_sessions AS gs ON gs.id = gc.game_session_id "
            "JOIN clues AS c ON c.id = gcc.clue_id AND c.script_id = gs.script_id"
        )
    )


def downgrade() -> None:
    """Remove Phase 10 evidence records while preserving Phase 0-9 data."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table, index_name in (
        ("game_clue_disclosure_attempts", "ix_clue_disclosure_attempt_game_created"),
        ("game_character_clue_knowledge", "ix_game_character_clue_knowledge_clue"),
        ("game_clue_disclosures", "ix_game_clue_disclosures_game_created"),
    ):
        if table in tables:
            indexes = {index["name"] for index in inspect(bind).get_indexes(table)}
            if index_name in indexes:
                op.drop_index(index_name, table_name=table)
    if "game_clue_disclosure_attempts" in tables:
        op.drop_table("game_clue_disclosure_attempts")
    if "game_character_clue_knowledge" in tables:
        op.drop_table("game_character_clue_knowledge")
    if "game_clue_disclosures" in tables:
        indexes = {
            index["name"]
            for index in inspect(bind).get_indexes("game_clue_disclosures")
        }
        for index_name in ("uq_private_clue_disclosure", "uq_public_clue_disclosure"):
            if index_name in indexes:
                op.drop_index(index_name, table_name="game_clue_disclosures")
        op.drop_table("game_clue_disclosures")
    if "game_runtime_states" in tables:
        columns = {
            column["name"]
            for column in inspect(bind).get_columns("game_runtime_states")
        }
        if "last_processed_public_clue_disclosure_id" in columns:
            op.drop_column(
                "game_runtime_states", "last_processed_public_clue_disclosure_id"
            )
