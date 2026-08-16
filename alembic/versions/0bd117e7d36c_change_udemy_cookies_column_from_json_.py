"""add last_checked_at and is_coupon_valid to enrolled_courses

Revision ID: 0bd117e7d36c
Revises: 1c7670167de7
Create Date: 2026-07-03 21:45:03.918938
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '0bd117e7d36c'
down_revision = '1c7670167de7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'enrolled_courses' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('enrolled_courses')]
    if 'last_checked_at' not in columns:
        op.add_column('enrolled_courses', sa.Column('last_checked_at', sa.DateTime(), nullable=True))
    if 'is_coupon_valid' not in columns:
        op.add_column('enrolled_courses', sa.Column('is_coupon_valid', sa.Boolean(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'enrolled_courses' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('enrolled_courses')]
    if 'is_coupon_valid' in columns:
        op.drop_column('enrolled_courses', 'is_coupon_valid')
    if 'last_checked_at' in columns:
        op.drop_column('enrolled_courses', 'last_checked_at')
