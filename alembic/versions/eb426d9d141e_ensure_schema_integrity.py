"""ensure schema integrity

Revision ID: eb426d9d141e
Revises: 5aa87ddb913e
Create Date: 2026-04-18 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'eb426d9d141e'
down_revision = '5aa87ddb913e'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Repair 'users' table
    if 'users' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('users')]
        if 'password_hash' not in columns:
            op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
        if 'udemy_display_name' not in columns:
            op.add_column('users', sa.Column('udemy_display_name', sa.String(length=255), nullable=True))
        if 'udemy_cookies' not in columns:
            op.add_column('users', sa.Column('udemy_cookies', sa.JSON(), nullable=True))
        if 'currency' not in columns:
            op.add_column('users', sa.Column('currency', sa.String(length=10), nullable=False, server_default="usd"))
        if 'total_enrolled' not in columns:
            op.add_column('users', sa.Column('total_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_already_enrolled' not in columns:
            op.add_column('users', sa.Column('total_already_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_expired' not in columns:
            op.add_column('users', sa.Column('total_expired', sa.Integer(), nullable=False, server_default="0"))
        if 'total_excluded' not in columns:
            op.add_column('users', sa.Column('total_excluded', sa.Integer(), nullable=False, server_default="0"))
        if 'total_amount_saved' not in columns:
            op.add_column('users', sa.Column('total_amount_saved', sa.Float(), nullable=False, server_default="0.0"))

    # Repair 'user_settings' table
    if 'user_settings' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('user_settings')]
        if 'sites' not in columns:
            op.add_column('user_settings', sa.Column('sites', sa.JSON(), nullable=True))
        if 'languages' not in columns:
            op.add_column('user_settings', sa.Column('languages', sa.JSON(), nullable=True))
        if 'categories' not in columns:
            op.add_column('user_settings', sa.Column('categories', sa.JSON(), nullable=True))
        if 'min_rating' not in columns:
            op.add_column('user_settings', sa.Column('min_rating', sa.Float(), nullable=False, server_default="0.0"))
        if 'save_txt' not in columns:
            op.add_column('user_settings', sa.Column('save_txt', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'discounted_only' not in columns:
            op.add_column('user_settings', sa.Column('discounted_only', sa.Boolean(), nullable=False, server_default=sa.text("0")))

    # Repair 'enrollment_runs' table
    if 'enrollment_runs' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('enrollment_runs')]
        if 'progress_data' not in columns:
            op.add_column('enrollment_runs', sa.Column('progress_data', sa.JSON(), nullable=True))

def downgrade() -> None:
    # This is a repair migration, no need to undo column additions as they bring DB to valid state
    pass
