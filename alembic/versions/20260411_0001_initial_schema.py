"""Initial schema.

Revision ID: 20260411_0001
Revises:
Create Date: 2026-04-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260411_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("udemy_display_name", sa.String(length=255), nullable=True),
            sa.Column("udemy_cookies", sa.JSON(), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="usd"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("total_enrolled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_already_enrolled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_expired", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_excluded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_amount_saved", sa.Float(), nullable=False, server_default="0.0"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    else:
        # Table exists, check for missing columns (e.g. from legacy DB)
        existing_columns = [c['name'] for c in inspector.get_columns('users')]
        if 'password_hash' not in existing_columns:
            op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
        if 'udemy_display_name' not in existing_columns:
            op.add_column('users', sa.Column('udemy_display_name', sa.String(length=255), nullable=True))
        if 'udemy_cookies' not in existing_columns:
            op.add_column('users', sa.Column('udemy_cookies', sa.JSON(), nullable=True))
        if 'currency' not in existing_columns:
            op.add_column('users', sa.Column('currency', sa.String(length=10), nullable=False, server_default="usd"))
        if 'total_enrolled' not in existing_columns:
            op.add_column('users', sa.Column('total_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_already_enrolled' not in existing_columns:
            op.add_column('users', sa.Column('total_already_enrolled', sa.Integer(), nullable=False, server_default="0"))
        if 'total_expired' not in existing_columns:
            op.add_column('users', sa.Column('total_expired', sa.Integer(), nullable=False, server_default="0"))
        if 'total_excluded' not in existing_columns:
            op.add_column('users', sa.Column('total_excluded', sa.Integer(), nullable=False, server_default="0"))
        if 'total_amount_saved' not in existing_columns:
            op.add_column('users', sa.Column('total_amount_saved', sa.Float(), nullable=False, server_default="0.0"))

    if "user_sessions" not in existing_tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index(op.f("ix_user_sessions_id"), "user_sessions", ["id"], unique=False)
        op.create_index(op.f("ix_user_sessions_token"), "user_sessions", ["token"], unique=False)
    else:
        existing_columns = [c['name'] for c in inspector.get_columns('user_sessions')]
        # expires_at is handled in a separate migration, but good to be safe if it's missing here
        # Actually, best to stick to what this migration SHOULD have.
        pass

    if "user_settings" not in existing_tables:
        op.create_table(
            "user_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("sites", sa.JSON(), nullable=True),
            sa.Column("languages", sa.JSON(), nullable=True),
            sa.Column("categories", sa.JSON(), nullable=True),
            sa.Column("instructor_exclude", sa.JSON(), nullable=True),
            sa.Column("title_exclude", sa.JSON(), nullable=True),
            sa.Column("min_rating", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("course_update_threshold_months", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("save_txt", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("discounted_only", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("proxy_url", sa.String(length=500), nullable=True),
            sa.Column("enable_headless", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("schedule_interval", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index(op.f("ix_user_settings_id"), "user_settings", ["id"], unique=False)
    else:
        existing_columns = [c['name'] for c in inspector.get_columns('user_settings')]
        if 'sites' not in existing_columns:
            op.add_column('user_settings', sa.Column('sites', sa.JSON(), nullable=True))
        if 'languages' not in existing_columns:
            op.add_column('user_settings', sa.Column('languages', sa.JSON(), nullable=True))
        if 'categories' not in existing_columns:
            op.add_column('user_settings', sa.Column('categories', sa.JSON(), nullable=True))
        if 'min_rating' not in existing_columns:
            op.add_column('user_settings', sa.Column('min_rating', sa.Float(), nullable=False, server_default="0.0"))
        if 'save_txt' not in existing_columns:
            op.add_column('user_settings', sa.Column('save_txt', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'discounted_only' not in existing_columns:
            op.add_column('user_settings', sa.Column('discounted_only', sa.Boolean(), nullable=False, server_default=sa.text("0")))
        if 'proxy_url' not in existing_columns:
            op.add_column('user_settings', sa.Column('proxy_url', sa.String(length=500), nullable=True))
        if 'enable_headless' not in existing_columns:
            op.add_column('user_settings', sa.Column('enable_headless', sa.Boolean(), nullable=False, server_default=sa.text("0")))

    if "enrollment_runs" not in existing_tables:
        op.create_table(
            "enrollment_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("total_courses_found", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_processed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("successfully_enrolled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("already_enrolled", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expired", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("excluded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("amount_saved", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="usd"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("progress_data", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_enrollment_runs_id"), "enrollment_runs", ["id"], unique=False)
    else:
        existing_columns = [c['name'] for c in inspector.get_columns('enrollment_runs')]
        if 'progress_data' not in existing_columns:
            op.add_column('enrollment_runs', sa.Column('progress_data', sa.JSON(), nullable=True))

    if "enrolled_courses" not in existing_tables:
        op.create_table(
            "enrolled_courses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("enrollment_run_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=True),
            sa.Column("course_id", sa.String(length=50), nullable=True),
            sa.Column("coupon_code", sa.String(length=100), nullable=True),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("category", sa.String(length=100), nullable=True),
            sa.Column("language", sa.String(length=50), nullable=True),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.Column("site_source", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="enrolled"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("enrolled_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["enrollment_run_id"], ["enrollment_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_enrolled_courses_id"), "enrolled_courses", ["id"], unique=False)
    else:
        existing_columns = [c['name'] for c in inspector.get_columns('enrolled_courses')]
        if 'rating' not in existing_columns:
            op.add_column('enrolled_courses', sa.Column('rating', sa.Float(), nullable=True))
        if 'site_source' not in existing_columns:
            op.add_column('enrolled_courses', sa.Column('site_source', sa.String(length=100), nullable=True))




def downgrade() -> None:
    """Drop initial schema."""
    op.drop_index(op.f("ix_enrolled_courses_id"), table_name="enrolled_courses")
    op.drop_table("enrolled_courses")

    op.drop_index(op.f("ix_enrollment_runs_id"), table_name="enrollment_runs")
    op.drop_table("enrollment_runs")

    op.drop_index(op.f("ix_user_settings_id"), table_name="user_settings")
    op.drop_table("user_settings")

    op.drop_index(op.f("ix_user_sessions_token"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_id"), table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
