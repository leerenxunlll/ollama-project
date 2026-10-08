"""Allow an atomic in-progress claim for Director recommendations.

Revision ID: 20261007_phase7_atomic_apply
Revises: 20261006_phase7
Create Date: 2026-10-07
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "20261007_phase7_atomic_apply"
down_revision = "20261006_phase7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the applying state without editing the already released migration."""
    bind = op.get_bind()
    if "director_recommendations" not in inspect(bind).get_table_names():
        return

    with op.batch_alter_table("director_recommendations") as batch_op:
        batch_op.drop_constraint("ck_director_recommendations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_director_recommendations_status",
            "status IN ('pending', 'applying', 'applied', 'rejected', 'advisory')",
        )


def downgrade() -> None:
    """Resolve interrupted claims before restoring the older status constraint."""
    bind = op.get_bind()
    if "director_recommendations" not in inspect(bind).get_table_names():
        return

    op.execute(
        text(
            "UPDATE director_recommendations SET status = 'rejected' "
            "WHERE status = 'applying'"
        )
    )
    with op.batch_alter_table("director_recommendations") as batch_op:
        batch_op.drop_constraint("ck_director_recommendations_status", type_="check")
        batch_op.create_check_constraint(
            "ck_director_recommendations_status",
            "status IN ('pending', 'applied', 'rejected', 'advisory')",
        )
