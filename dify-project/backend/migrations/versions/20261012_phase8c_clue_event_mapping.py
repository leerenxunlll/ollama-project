"""Ensure canonical clue-to-event mappings exist on upgraded databases.

Revision ID: 20261012_phase8c_mapping
Revises: 20261011_phase8c
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20261012_phase8c_mapping"
down_revision = "20261011_phase8c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "script_canonical_data" not in inspector.get_table_names():
        return

    columns = {
        column["name"] for column in inspector.get_columns("script_canonical_data")
    }
    if "clue_event_keys_json" not in columns:
        with op.batch_alter_table("script_canonical_data") as batch:
            batch.add_column(
                sa.Column(
                    "clue_event_keys_json",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                )
            )
            batch.alter_column("clue_event_keys_json", server_default=None)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "script_canonical_data" not in inspector.get_table_names():
        return

    columns = {
        column["name"] for column in inspector.get_columns("script_canonical_data")
    }
    if "clue_event_keys_json" in columns:
        with op.batch_alter_table("script_canonical_data") as batch:
            batch.drop_column("clue_event_keys_json")
