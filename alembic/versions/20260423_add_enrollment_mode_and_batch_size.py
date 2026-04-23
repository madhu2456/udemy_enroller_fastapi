"""Add enrollment_mode and batch_size to user_settings

Revision ID: 20260423_0001
Revises: 153b1e83e42f
Create Date: 2026-04-23 14:31:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260423_0001'
down_revision = '153b1e83e42f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.add_column(sa.Column('enrollment_mode', sa.String(length=20), server_default='bulk'))
        batch_op.add_column(sa.Column('batch_size', sa.Integer(), server_default='5'))


def downgrade() -> None:
    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.drop_column('batch_size')
        batch_op.drop_column('enrollment_mode')
