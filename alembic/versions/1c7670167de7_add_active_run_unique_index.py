"""add_active_run_unique_index

Revision ID: 1c7670167de7
Revises: 0cce47f261a1
Create Date: 2026-05-31 14:03:46.234443
"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '1c7670167de7'
down_revision = '0cce47f261a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Deterministic cleanup of duplicate active runs per user (keep only the newest one active)
    op.execute(
        """
        UPDATE enrollment_runs
        SET status = 'failed',
            completed_at = CURRENT_TIMESTAMP,
            error_message = 'Marked inactive during schema migration cleanup'
        WHERE status IN ('pending', 'scraping', 'enrolling')
          AND id NOT IN (
              SELECT max(id)
              FROM enrollment_runs
              WHERE status IN ('pending', 'scraping', 'enrolling')
              GROUP BY user_id
          )
        """
    )

    # 2. Create partial unique index to restrict only one active run per user at any time
    op.create_index(
        'idx_active_run_per_user',
        'enrollment_runs',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'scraping', 'enrolling')"),
        sqlite_where=sa.text("status IN ('pending', 'scraping', 'enrolling')")
    )


def downgrade() -> None:
    op.drop_index(
        'idx_active_run_per_user',
        table_name='enrollment_runs',
        postgresql_where=sa.text("status IN ('pending', 'scraping', 'enrolling')"),
        sqlite_where=sa.text("status IN ('pending', 'scraping', 'enrolling')")
    )
