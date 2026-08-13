"""add cookies_salt to users

Per-session Fernet envelope (F-ENRL-C01): users.cookies_salt stores the salt
that binds the encrypted udemy_cookies blob to the session that wrote it.
Nullable — legacy rows keep NULL until scripts/migrate_cookies_per_session.py
re-encrypts them.

Revision ID: c01d021a9e01
Revises: 0bd117e7d36c
Create Date: 2026-08-12 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c01d021a9e01"
down_revision = "0bd117e7d36c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cookies_salt", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "cookies_salt")
