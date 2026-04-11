"""Migration: 001_initial_schema - Creates initial database tables."""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


def upgrade():
    """Create initial schema."""
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('udemy_display_name', sa.String(255), nullable=True),
        sa.Column('udemy_cookies', sa.JSON(), nullable=True),
        sa.Column('currency', sa.String(10), nullable=False, server_default='usd'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('total_enrolled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_already_enrolled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_expired', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_excluded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_amount_saved', sa.Float(), nullable=False, server_default='0.0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'])

    # User sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_user_sessions_token'), 'user_sessions', ['token'])

    # User settings table
    op.create_table(
        'user_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('sites', sa.JSON()),
        sa.Column('languages', sa.JSON()),
        sa.Column('categories', sa.JSON()),
        sa.Column('instructor_exclude', sa.JSON()),
        sa.Column('title_exclude', sa.JSON()),
        sa.Column('min_rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('course_update_threshold_months', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('save_txt', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('discounted_only', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('proxy_url', sa.String(500), nullable=True),
        sa.Column('enable_headless', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('schedule_interval', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id')
    )

    # Enrollment runs table
    op.create_table(
        'enrollment_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('total_courses_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successfully_enrolled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('already_enrolled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expired', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('excluded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('amount_saved', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='usd'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )

    # Enrolled courses table
    op.create_table(
        'enrolled_courses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enrollment_run_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('url', sa.String(1000), nullable=False),
        sa.Column('slug', sa.String(255), nullable=True),
        sa.Column('course_id', sa.String(50), nullable=True),
        sa.Column('coupon_code', sa.String(100), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('language', sa.String(50), nullable=True),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('site_source', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='enrolled'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('enrolled_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['enrollment_run_id'], ['enrollment_runs.id'])
    )


def downgrade():
    """Drop all tables."""
    op.drop_table('enrolled_courses')
    op.drop_table('enrollment_runs')
    op.drop_table('user_settings')
    op.drop_table('user_sessions')
    op.drop_table('users')
