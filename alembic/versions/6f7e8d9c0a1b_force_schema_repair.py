"""force schema repair

Revision ID: 6f7e8d9c0a1b
Revises: eb426d9d141e
Create Date: 2026-04-21 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '6f7e8d9c0a1b'
down_revision = 'eb426d9d141e'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # 1. users
    if 'users' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('users')]
        if 'password_hash' not in columns: op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
        if 'udemy_display_name' not in columns: op.add_column('users', sa.Column('udemy_display_name', sa.String(length=255), nullable=True))
        if 'udemy_cookies' not in columns: op.add_column('users', sa.Column('udemy_cookies', sa.JSON(), nullable=True))
        if 'currency' not in columns: op.add_column('users', sa.Column('currency', sa.String(length=10), nullable=False, server_default="usd"))
        if 'is_active' not in columns: op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("1")))
        if 'created_at' not in columns: op.add_column('users', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        if 'updated_at' not in columns: op.add_column('users', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        if 'total_enrolled' not in columns: op.add_column('users', sa.Column('total_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_already_enrolled' not in columns: op.add_column('users', sa.Column('total_already_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_expired' not in columns: op.add_column('users', sa.Column('total_expired', sa.Integer(), nullable=False, server_default="0"))
        if 'total_excluded' not in columns: op.add_column('users', sa.Column('total_excluded', sa.Integer(), nullable=False, server_default="0"))
        if 'total_amount_saved' not in columns: op.add_column('users', sa.Column('total_amount_saved', sa.Float(), nullable=False, server_default="0.0"))

    # 2. user_sessions
    if 'user_sessions' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('user_sessions')]
        if 'token' not in columns: op.add_column('user_sessions', sa.Column('token', sa.String(64), nullable=False))
        if 'user_id' not in columns: op.add_column('user_sessions', sa.Column('user_id', sa.Integer(), nullable=False))
        if 'created_at' not in columns: op.add_column('user_sessions', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        if 'expires_at' not in columns: op.add_column('user_sessions', sa.Column('expires_at', sa.DateTime(), nullable=True))

    # 3. user_settings
    if 'user_settings' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('user_settings')]
        if 'sites' not in columns: op.add_column('user_settings', sa.Column('sites', sa.JSON(), nullable=True))
        if 'languages' not in columns: op.add_column('user_settings', sa.Column('languages', sa.JSON(), nullable=True))
        if 'categories' not in columns: op.add_column('user_settings', sa.Column('categories', sa.JSON(), nullable=True))
        if 'instructor_exclude' not in columns: op.add_column('user_settings', sa.Column('instructor_exclude', sa.JSON(), nullable=True))
        if 'title_exclude' not in columns: op.add_column('user_settings', sa.Column('title_exclude', sa.JSON(), nullable=True))
        if 'min_rating' not in columns: op.add_column('user_settings', sa.Column('min_rating', sa.Float(), nullable=False, server_default="0.0"))
        if 'course_update_threshold_months' not in columns: op.add_column('user_settings', sa.Column('course_update_threshold_months', sa.Integer(), nullable=False, server_default="24"))
        if 'save_txt' not in columns: op.add_column('user_settings', sa.Column('save_txt', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'discounted_only' not in columns: op.add_column('user_settings', sa.Column('discounted_only', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'proxy_url' not in columns: op.add_column('user_settings', sa.Column('proxy_url', sa.String(length=500), nullable=True))
        if 'enable_headless' not in columns: op.add_column('user_settings', sa.Column('enable_headless', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'created_at' not in columns: op.add_column('user_settings', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        if 'updated_at' not in columns: op.add_column('user_settings', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

    # 4. enrollment_runs
    if 'enrollment_runs' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('enrollment_runs')]
        if 'status' not in columns: op.add_column('enrollment_runs', sa.Column('status', sa.String(length=50), nullable=False, server_default="pending"))
        if 'total_courses_found' not in columns: op.add_column('enrollment_runs', sa.Column('total_courses_found', sa.Integer(), nullable=False, server_default="0"))
        if 'total_processed' not in columns: op.add_column('enrollment_runs', sa.Column('total_processed', sa.Integer(), nullable=False, server_default="0"))
        if 'successfully_enrolled' not in columns: op.add_column('enrollment_runs', sa.Column('successfully_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'already_enrolled' not in columns: op.add_column('enrollment_runs', sa.Column('already_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'expired' not in columns: op.add_column('enrollment_runs', sa.Column('expired', sa.Integer(), nullable=False, server_default="0"))
        if 'excluded' not in columns: op.add_column('enrollment_runs', sa.Column('excluded', sa.Integer(), nullable=False, server_default="0"))
        if 'amount_saved' not in columns: op.add_column('enrollment_runs', sa.Column('amount_saved', sa.Float(), nullable=False, server_default="0.0"))
        if 'currency' not in columns: op.add_column('enrollment_runs', sa.Column('currency', sa.String(length=10), nullable=False, server_default="usd"))
        if 'error_message' not in columns: op.add_column('enrollment_runs', sa.Column('error_message', sa.Text(), nullable=True))
        if 'started_at' not in columns: op.add_column('enrollment_runs', sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
        if 'completed_at' not in columns: op.add_column('enrollment_runs', sa.Column('completed_at', sa.DateTime(), nullable=True))
        if 'progress_data' not in columns: op.add_column('enrollment_runs', sa.Column('progress_data', sa.JSON(), nullable=True))

    # 5. enrolled_courses
    if 'enrolled_courses' in existing_tables:
        columns = [c['name'] for c in inspector.get_columns('enrolled_courses')]
        if 'slug' not in columns: op.add_column('enrolled_courses', sa.Column('slug', sa.String(length=255), nullable=True))
        if 'course_id' not in columns: op.add_column('enrolled_courses', sa.Column('course_id', sa.String(length=50), nullable=True))
        if 'coupon_code' not in columns: op.add_column('enrolled_courses', sa.Column('coupon_code', sa.String(length=100), nullable=True))
        if 'price' not in columns: op.add_column('enrolled_courses', sa.Column('price', sa.Float(), nullable=True))
        if 'category' not in columns: op.add_column('enrolled_courses', sa.Column('category', sa.String(length=100), nullable=True))
        if 'language' not in columns: op.add_column('enrolled_courses', sa.Column('language', sa.String(length=50), nullable=True))
        if 'rating' not in columns: op.add_column('enrolled_courses', sa.Column('rating', sa.Float(), nullable=True))
        if 'site_source' not in columns: op.add_column('enrolled_courses', sa.Column('site_source', sa.String(length=100), nullable=True))
        if 'status' not in columns: op.add_column('enrolled_courses', sa.Column('status', sa.String(length=50), nullable=False, server_default="enrolled"))
        if 'error_message' not in columns: op.add_column('enrolled_courses', sa.Column('error_message', sa.Text(), nullable=True))
        if 'enrolled_at' not in columns: op.add_column('enrolled_courses', sa.Column('enrolled_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))

def downgrade() -> None:
    pass
