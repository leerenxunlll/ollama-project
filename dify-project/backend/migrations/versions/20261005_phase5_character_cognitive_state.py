"""Add private character thoughts and per-game character memories.

Revision ID: 20261005_phase5
Revises: 20261005_phase3
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261005_phase5"
down_revision = "20261005_phase3"
branch_labels = None
depends_on = None


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    """Create a current-schema index only when the database does not have it."""
    bind = op.get_bind()
    indexes = {index["name"] for index in inspect(bind).get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    """Create Phase 5 tables while supporting empty and Phase 3 databases."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "game_characters" in tables:
        _create_index_if_missing(
            "uq_game_characters_session_id_id",
            "game_characters",
            ["game_session_id", "id"],
            unique=True,
        )
    if "messages" in tables:
        _create_index_if_missing(
            "uq_messages_session_id_id",
            "messages",
            ["game_session_id", "id"],
            unique=True,
        )
        _create_index_if_missing(
            "uq_messages_session_id_id_sender",
            "messages",
            ["game_session_id", "id", "sender_game_character_id"],
            unique=True,
        )

    if "character_thoughts" not in tables:
        op.create_table(
            "character_thoughts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("game_character_id", sa.Integer(), nullable=False),
            sa.Column("ai_message_id", sa.Integer(), nullable=False),
            sa.Column("inner_os", sa.Text(), nullable=False),
            sa.Column("emotion", sa.String(length=20), nullable=False),
            sa.Column("intent", sa.String(length=30), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "emotion IN ('calm', 'nervous', 'angry', 'afraid', 'sad', "
                "'confident', 'suspicious', 'confused')",
                name="ck_character_thoughts_emotion",
            ),
            sa.CheckConstraint(
                "intent IN ('cooperate', 'hide_information', 'seek_information', "
                "'accuse', 'deflect', 'persuade', 'observe', 'other')",
                name="ck_character_thoughts_intent",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id"],
                ["game_sessions.id"],
                name="fk_character_thoughts_game_session_id_game_sessions",
            ),
            sa.ForeignKeyConstraint(
                ["game_character_id"],
                ["game_characters.id"],
                name="fk_character_thoughts_game_character_id_game_characters",
            ),
            sa.ForeignKeyConstraint(
                ["ai_message_id"],
                ["messages.id"],
                name="fk_character_thoughts_ai_message_id_messages",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_character_thoughts_game_character_session",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "ai_message_id", "game_character_id"],
                [
                    "messages.game_session_id",
                    "messages.id",
                    "messages.sender_game_character_id",
                ],
                name="fk_character_thoughts_ai_message_sender",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "ai_message_id", name="uq_character_thought_ai_message"
            ),
        )

    if "character_memories" not in tables:
        op.create_table(
            "character_memories",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("game_session_id", sa.Integer(), nullable=False),
            sa.Column("game_character_id", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("importance", sa.Integer(), nullable=False),
            sa.Column("source_message_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "importance BETWEEN 1 AND 5",
                name="ck_character_memories_importance",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id"],
                ["game_sessions.id"],
                name="fk_character_memories_game_session_id_game_sessions",
            ),
            sa.ForeignKeyConstraint(
                ["game_character_id"],
                ["game_characters.id"],
                name="fk_character_memories_game_character_id_game_characters",
            ),
            sa.ForeignKeyConstraint(
                ["source_message_id"],
                ["messages.id"],
                name="fk_character_memories_source_message_id_messages",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "game_character_id"],
                ["game_characters.game_session_id", "game_characters.id"],
                name="fk_character_memories_game_character_session",
            ),
            sa.ForeignKeyConstraint(
                ["game_session_id", "source_message_id"],
                ["messages.game_session_id", "messages.id"],
                name="fk_character_memories_source_message_session",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        "ix_character_thoughts_character_created",
        "character_thoughts",
        ["game_character_id", "created_at"],
    )
    _create_index_if_missing(
        "ix_character_memories_character_importance_created",
        "character_memories",
        ["game_character_id", "importance", "created_at"],
    )


def downgrade() -> None:
    """Remove only the Phase 5 state and supporting indexes."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "character_memories" in tables:
        op.drop_table("character_memories")
    if "character_thoughts" in tables:
        op.drop_table("character_thoughts")

    indexes = {
        "game_characters": "uq_game_characters_session_id_id",
        "messages": "uq_messages_session_id_id",
        "messages_sender": "uq_messages_session_id_id_sender",
    }
    if "game_characters" in tables:
        existing = {
            item["name"] for item in inspect(bind).get_indexes("game_characters")
        }
        if indexes["game_characters"] in existing:
            op.drop_index(indexes["game_characters"], table_name="game_characters")
    if "messages" in tables:
        existing = {item["name"] for item in inspect(bind).get_indexes("messages")}
        for index_name in (indexes["messages"], indexes["messages_sender"]):
            if index_name in existing:
                op.drop_index(index_name, table_name="messages")
