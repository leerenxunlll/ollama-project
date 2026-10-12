"""Add shared and private script chapters plus intro acknowledgement."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261008_phase8a"
down_revision = "20261007_phase7_atomic_apply"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Phase 8A data while tolerating schemas created from current metadata."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "game_sessions" in tables:
        columns = {column["name"] for column in inspector.get_columns("game_sessions")}
        if "human_intro_acknowledged_at" not in columns:
            op.add_column(
                "game_sessions",
                sa.Column(
                    "human_intro_acknowledged_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )

    if "shared_script_chapters" not in tables:
        op.create_table(
            "shared_script_chapters",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("script_id", sa.Integer(), nullable=False),
            sa.Column("chapter_order", sa.Integer(), nullable=False),
            sa.Column("unlock_phase", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "unlock_phase IN ('intro', 'act_1', 'act_2')",
                name="ck_shared_script_chapters_unlock_phase",
            ),
            sa.CheckConstraint(
                "chapter_order > 0",
                name="ck_shared_script_chapters_order_positive",
            ),
            sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "script_id",
                "chapter_order",
                name="uq_shared_script_chapters_script_order",
            ),
        )

    if "character_script_chapters" not in tables:
        op.create_table(
            "character_script_chapters",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("character_id", sa.Integer(), nullable=False),
            sa.Column("chapter_order", sa.Integer(), nullable=False),
            sa.Column("unlock_phase", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "unlock_phase IN ('intro', 'act_1', 'act_2')",
                name="ck_character_script_chapters_unlock_phase",
            ),
            sa.CheckConstraint(
                "chapter_order > 0",
                name="ck_character_script_chapters_order_positive",
            ),
            sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "character_id",
                "chapter_order",
                name="uq_character_script_chapters_character_order",
            ),
        )


def downgrade() -> None:
    """Remove Phase 8A tables and the intro acknowledgement column."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "character_script_chapters" in tables:
        op.drop_table("character_script_chapters")
    if "shared_script_chapters" in tables:
        op.drop_table("shared_script_chapters")

    if "game_sessions" in tables:
        columns = {column["name"] for column in inspector.get_columns("game_sessions")}
        if "human_intro_acknowledged_at" in columns:
            with op.batch_alter_table("game_sessions") as batch_op:
                batch_op.drop_column("human_intro_acknowledged_at")
