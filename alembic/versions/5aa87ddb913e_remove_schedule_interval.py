"""remove schedule_interval

Revision ID: 5aa87ddb913e
Revises: 5ca331be53f2
Create Date: 2026-04-12 12:31:17.014747
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5aa87ddb913e'
down_revision = '5ca331be53f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('user_settings')]
    
    if 'schedule_interval' in columns:
        with op.batch_alter_table('user_settings') as batch_op:
            batch_op.drop_column('schedule_interval')


def downgrade() -> None:
    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.add_column(sa.Column('schedule_interval', sa.INTEGER(), server_default=sa.text("'0'"), nullable=False))
