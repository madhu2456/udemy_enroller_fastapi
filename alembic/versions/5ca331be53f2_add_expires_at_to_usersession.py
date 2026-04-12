"""Add expires_at to UserSession

Revision ID: 5ca331be53f2
Revises: 20260411_0001
Create Date: 2026-04-12 09:53:43.781015
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5ca331be53f2'
down_revision = '20260411_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch mode for SQLite to support dropping indexes safely if needed,
    # but add_column is supported directly.
    op.add_column('user_sessions', sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_sessions') as batch_op:
        batch_op.drop_column('expires_at')
