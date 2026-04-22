"""add firecrawl_api_key to user_settings

Revision ID: 153b1e83e42f
Revises: 6f7e8d9c0a1b
Create Date: 2026-04-22 12:17:39.529839
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '153b1e83e42f'
down_revision = '6f7e8d9c0a1b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('enrolled_courses') as batch_op:
        batch_op.alter_column('status',
               existing_type=sa.VARCHAR(length=50),
               nullable=True,
               existing_server_default=sa.text("'enrolled'"))
        batch_op.alter_column('enrolled_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))

    with op.batch_alter_table('enrollment_runs') as batch_op:
        batch_op.alter_column('status',
               existing_type=sa.VARCHAR(length=50),
               nullable=True,
               existing_server_default=sa.text("'pending'"))
        for col in ['total_courses_found', 'total_processed', 'successfully_enrolled', 'already_enrolled', 'expired', 'excluded']:
            batch_op.alter_column(col,
                   existing_type=sa.INTEGER(),
                   nullable=True,
                   existing_server_default=sa.text("'0'"))
        batch_op.alter_column('amount_saved',
               existing_type=sa.FLOAT(),
               nullable=True,
               existing_server_default=sa.text("'0.0'"))
        batch_op.alter_column('currency',
               existing_type=sa.VARCHAR(length=10),
               nullable=True,
               existing_server_default=sa.text("'usd'"))
        batch_op.alter_column('started_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))

    with op.batch_alter_table('user_sessions') as batch_op:
        batch_op.alter_column('created_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.drop_index('ix_user_sessions_token')
        batch_op.create_index('ix_user_sessions_token', ['token'], unique=True)

    with op.batch_alter_table('user_settings') as batch_op:
        batch_op.add_column(sa.Column('firecrawl_api_key', sa.String(length=255), nullable=True))
        batch_op.alter_column('min_rating',
               existing_type=sa.FLOAT(),
               nullable=True,
               existing_server_default=sa.text("'0.0'"))
        batch_op.alter_column('course_update_threshold_months',
               existing_type=sa.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'24'"))
        batch_op.alter_column('save_txt',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('0'))
        batch_op.alter_column('discounted_only',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('0'))
        batch_op.alter_column('enable_headless',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('0'))
        batch_op.alter_column('created_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('updated_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('currency',
               existing_type=sa.VARCHAR(length=10),
               nullable=True,
               existing_server_default=sa.text("'usd'"))
        batch_op.alter_column('is_active',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('1'))
        batch_op.alter_column('created_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('updated_at',
               existing_type=sa.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.drop_index('ix_users_email')
        batch_op.create_index('ix_users_email', ['email'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.create_index('ix_users_email', ['email'], unique=False)
        for col in ['updated_at', 'created_at']:
             batch_op.alter_column(col, existing_type=sa.DATETIME(), nullable=False, existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('is_active', existing_type=sa.BOOLEAN(), nullable=False, existing_server_default=sa.text('1'))
        batch_op.alter_column('currency', existing_type=sa.VARCHAR(length=10), nullable=False, existing_server_default=sa.text("'usd'"))

    with op.batch_alter_table('user_settings') as batch_op:
        for col in ['updated_at', 'created_at']:
             batch_op.alter_column(col, existing_type=sa.DATETIME(), nullable=False, existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('enable_headless', existing_type=sa.BOOLEAN(), nullable=False, existing_server_default=sa.text('0'))
        batch_op.alter_column('discounted_only', existing_type=sa.BOOLEAN(), nullable=False, existing_server_default=sa.text('0'))
        batch_op.alter_column('save_txt', existing_type=sa.BOOLEAN(), nullable=False, existing_server_default=sa.text('0'))
        batch_op.alter_column('course_update_threshold_months', existing_type=sa.INTEGER(), nullable=False, existing_server_default=sa.text("'24'"))
        batch_op.alter_column('min_rating', existing_type=sa.FLOAT(), nullable=False, existing_server_default=sa.text("'0.0'"))
        batch_op.drop_column('firecrawl_api_key')

    with op.batch_alter_table('user_sessions') as batch_op:
        batch_op.drop_index('ix_user_sessions_token')
        batch_op.create_index('ix_user_sessions_token', ['token'], unique=False)
        batch_op.alter_column('created_at', existing_type=sa.DATETIME(), nullable=False, existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))

    with op.batch_alter_table('enrollment_runs') as batch_op:
        batch_op.alter_column('started_at', existing_type=sa.DATETIME(), nullable=False, existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('currency', existing_type=sa.VARCHAR(length=10), nullable=False, existing_server_default=sa.text("'usd'"))
        batch_op.alter_column('amount_saved', existing_type=sa.FLOAT(), nullable=False, existing_server_default=sa.text("'0.0'"))
        for col in ['excluded', 'expired', 'already_enrolled', 'successfully_enrolled', 'total_processed', 'total_courses_found']:
             batch_op.alter_column(col, existing_type=sa.INTEGER(), nullable=False, existing_server_default=sa.text("'0'"))
        batch_op.alter_column('status', existing_type=sa.VARCHAR(length=50), nullable=False, existing_server_default=sa.text("'pending'"))

    with op.batch_alter_table('enrolled_courses') as batch_op:
        batch_op.alter_column('enrolled_at', existing_type=sa.DATETIME(), nullable=False, existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.alter_column('status', existing_type=sa.VARCHAR(length=50), nullable=False, existing_server_default=sa.text("'enrolled'"))
