"""add last_heartbeat to enrollment_runs

Liveness marker for stuck-run detection (F-ENRL-O01): the enrollment
pipeline refreshes run.last_heartbeat while it makes progress; a periodic
in-process sweeper marks runs failed when the heartbeat is older than
STALE_RUN_TIMEOUT_MINUTES. Nullable — pre-existing runs are treated as
stale by the sweeper until the pipeline writes a heartbeat.

Revision ID: c01d021a9e02
Revises: c01d021a9e01
Create Date: 2026-08-13 08:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c01d021a9e02"
down_revision = "c01d021a9e01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrollment_runs", sa.Column("last_heartbeat", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("enrollment_runs", "last_heartbeat")
