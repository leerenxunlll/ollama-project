"""Add Phase 8C review, revision, and atomic Script publication data.

Revision ID: 20261011_phase8c
Revises: 20261008_phase8b
Create Date: 2026-10-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261011_phase8c"
down_revision = "20261008_phase8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "characters" in tables:
        columns = {column["name"] for column in inspector.get_columns("characters")}
        with op.batch_alter_table("characters") as batch:
            if "personal_history" not in columns:
                batch.add_column(
                    sa.Column("personal_history", sa.Text(), nullable=True)
                )
            if "relationship_to_victim" not in columns:
                batch.add_column(
                    sa.Column("relationship_to_victim", sa.Text(), nullable=True)
                )
            if "pre_case_experience" not in columns:
                batch.add_column(
                    sa.Column("pre_case_experience", sa.Text(), nullable=True)
                )
            if "private_secrets_json" not in columns:
                batch.add_column(
                    sa.Column("private_secrets_json", sa.JSON(), nullable=True)
                )
            if "initial_knowledge_json" not in columns:
                batch.add_column(
                    sa.Column("initial_knowledge_json", sa.JSON(), nullable=True)
                )

    if "script_canonical_data" not in tables:
        op.create_table(
            "script_canonical_data",
            sa.Column("script_id", sa.Integer(), nullable=False),
            sa.Column("case_truth_json", sa.JSON(), nullable=False),
            sa.Column("timeline_json", sa.JSON(), nullable=False),
            sa.Column("role_character_ids_json", sa.JSON(), nullable=False),
            sa.Column("clue_ids_json", sa.JSON(), nullable=False),
            sa.Column("clue_event_keys_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["script_id"], ["scripts.id"]),
            sa.PrimaryKeyConstraint("script_id"),
        )

    if "script_review_runs" not in tables:
        op.create_table(
            "script_review_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("draft_id", sa.Integer(), nullable=False),
            sa.Column("content_revision", sa.Integer(), nullable=False),
            sa.Column("review_status", sa.String(length=20), nullable=False),
            sa.Column("report_json", sa.JSON(), nullable=True),
            sa.Column("error_type", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "review_status IN ('completed', 'failed', 'stale')",
                name="ck_script_review_runs_status",
            ),
            sa.ForeignKeyConstraint(["draft_id"], ["script_drafts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_script_review_runs_draft_id",
            "script_review_runs",
            ["draft_id"],
            unique=False,
        )

    if "script_revision_records" not in tables:
        op.create_table(
            "script_revision_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("draft_id", sa.Integer(), nullable=False),
            sa.Column("from_revision", sa.Integer(), nullable=False),
            sa.Column("to_revision", sa.Integer(), nullable=False),
            sa.Column("phase", sa.String(length=20), nullable=False),
            sa.Column("related_review_id", sa.Integer(), nullable=False),
            sa.Column("issues_addressed_json", sa.JSON(), nullable=False),
            sa.Column("previous_chapter_pack_json", sa.JSON(), nullable=False),
            sa.Column("new_chapter_pack_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["draft_id"], ["script_drafts.id"]),
            sa.ForeignKeyConstraint(["related_review_id"], ["script_review_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_script_revision_records_draft_id",
            "script_revision_records",
            ["draft_id"],
            unique=False,
        )

    if "script_drafts" in tables:
        columns = {
            column["name"] for column in inspect(bind).get_columns("script_drafts")
        }
        with op.batch_alter_table("script_drafts") as batch:
            if "content_revision" not in columns:
                batch.add_column(
                    sa.Column(
                        "content_revision",
                        sa.Integer(),
                        server_default=sa.text("1"),
                        nullable=False,
                    )
                )
            if "approved_revision" not in columns:
                batch.add_column(sa.Column("approved_revision", sa.Integer()))
            if "approved_review_run_id" not in columns:
                batch.add_column(sa.Column("approved_review_run_id", sa.Integer()))
            if "approved_at" not in columns:
                batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True)))
            if "accepted_medium_issue_indexes_json" not in columns:
                batch.add_column(
                    sa.Column(
                        "accepted_medium_issue_indexes_json",
                        sa.JSON(),
                        server_default=sa.text("'[]'"),
                        nullable=False,
                    )
                )
            if "publication_status" not in columns:
                batch.add_column(
                    sa.Column(
                        "publication_status",
                        sa.String(length=20),
                        server_default=sa.text("'unpublished'"),
                        nullable=False,
                    )
                )
            if "published_script_id" not in columns:
                batch.add_column(
                    sa.Column("published_script_id", sa.Integer(), nullable=True)
                )
                batch.create_foreign_key(
                    "fk_script_drafts_published_script_id_scripts",
                    "scripts",
                    ["published_script_id"],
                    ["id"],
                )
                batch.create_unique_constraint(
                    "uq_script_drafts_published_script_id", ["published_script_id"]
                )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "script_drafts" in tables:
        columns = {
            column["name"] for column in inspect(bind).get_columns("script_drafts")
        }
        with op.batch_alter_table("script_drafts") as batch:
            if "published_script_id" in columns:
                batch.drop_constraint(
                    "uq_script_drafts_published_script_id", type_="unique"
                )
                batch.drop_constraint(
                    "fk_script_drafts_published_script_id_scripts", type_="foreignkey"
                )
                batch.drop_column("published_script_id")
            for column in (
                "publication_status",
                "accepted_medium_issue_indexes_json",
                "approved_at",
                "approved_review_run_id",
                "approved_revision",
                "content_revision",
            ):
                if column in columns:
                    batch.drop_column(column)
    for table_name in (
        "script_revision_records",
        "script_review_runs",
        "script_canonical_data",
    ):
        if table_name in tables:
            op.drop_table(table_name)
    if "characters" in tables:
        columns = {column["name"] for column in inspect(bind).get_columns("characters")}
        with op.batch_alter_table("characters") as batch:
            for column in (
                "initial_knowledge_json",
                "private_secrets_json",
                "pre_case_experience",
                "relationship_to_victim",
                "personal_history",
            ):
                if column in columns:
                    batch.drop_column(column)
