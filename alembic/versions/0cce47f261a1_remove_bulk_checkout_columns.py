"""remove_bulk_checkout_columns

Revision ID: 0cce47f261a1
Revises: 20260423_0001
Create Date: 2026-04-25 11:58:02.223051
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '0cce47f261a1'
down_revision = '20260423_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'user_settings' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('user_settings')}
    to_drop = [name for name in ('enrollment_mode', 'batch_size') if name in columns]
    if not to_drop:
        return
    with op.batch_alter_table('user_settings') as batch_op:
        for name in to_drop:
            batch_op.drop_column(name)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if 'user_settings' not in inspector.get_table_names():
        return
    columns = {c['name'] for c in inspector.get_columns('user_settings')}
    to_add = []
    if 'enrollment_mode' not in columns:
        to_add.append(sa.Column('enrollment_mode', sa.String(20), server_default='bulk'))
    if 'batch_size' not in columns:
        to_add.append(sa.Column('batch_size', sa.Integer(), server_default='5'))
    if not to_add:
        return
    with op.batch_alter_table('user_settings') as batch_op:
        for column in to_add:
            batch_op.add_column(column)
