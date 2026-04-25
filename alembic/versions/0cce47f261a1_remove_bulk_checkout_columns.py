"""remove_bulk_checkout_columns

Revision ID: 0cce47f261a1
Revises: 20260423_0001
Create Date: 2026-04-25 11:58:02.223051
"""

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '0cce47f261a1'
down_revision = '20260423_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.drop_column('enrollment_mode')
        batch_op.drop_column('batch_size')


def downgrade() -> None:
    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.add_column(sa.Column('enrollment_mode', sa.String(20), server_default='bulk'))
        batch_op.add_column(sa.Column('batch_size', sa.Integer(), server_default='5'))
