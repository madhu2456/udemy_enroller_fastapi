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
    
    def get_inspector():
        return inspect(conn)
    
    # MASTER REPAIR: Ensure all tables exist first
    existing_tables = get_inspector().get_table_names()
    
    # 1. users
    if 'users' not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    
    # 2. user_sessions
    if 'user_sessions' not in existing_tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index(op.f("ix_user_sessions_id"), "user_sessions", ["id"], unique=False)
        op.create_index(op.f("ix_user_sessions_token"), "user_sessions", ["token"], unique=False)

    # 3. user_settings
    if 'user_settings' not in existing_tables:
        op.create_table(
            "user_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index(op.f("ix_user_settings_id"), "user_settings", ["id"], unique=False)

    # 4. enrollment_runs
    if 'enrollment_runs' not in existing_tables:
        op.create_table(
            "enrollment_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_enrollment_runs_id"), "enrollment_runs", ["id"], unique=False)

    # 5. enrolled_courses
    if 'enrolled_courses' not in existing_tables:
        op.create_table(
            "enrolled_courses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("enrollment_run_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.ForeignKeyConstraint(["enrollment_run_id"], ["enrollment_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_enrolled_courses_id"), "enrolled_courses", ["id"], unique=False)

    # NOW REPAIR COLUMNS (ensure all columns from latest models exist)
    
    # users
    columns = [c['name'] for c in get_inspector().get_columns('users')]
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

    # user_sessions
    columns = [c['name'] for c in get_inspector().get_columns('user_sessions')]
    if 'created_at' not in columns: op.add_column('user_sessions', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    if 'expires_at' not in columns: op.add_column('user_sessions', sa.Column('expires_at', sa.DateTime(), nullable=True))

    # user_settings
    columns = [c['name'] for c in get_inspector().get_columns('user_settings')]
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

    # enrollment_runs
    columns = [c['name'] for c in get_inspector().get_columns('enrollment_runs')]
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

    # enrolled_courses
    columns = [c['name'] for c in get_inspector().get_columns('enrolled_courses')]
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
