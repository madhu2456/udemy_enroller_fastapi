"""drop firecrawl_api_key and enable_headless from user_settings

Remove columns that no longer exist in the UserSettings ORM model
(F-ENRL-C11). Both were added by 153b1e83e42f and are unused by the
application since the firecrawl integration was removed; the ORM model
dropped them, so this migration aligns the live SQLite schema. Batch mode
is required for SQLite ALTER TABLE support.

Revision ID: c01d021a9e03
Revises: c01d021a9e02
Create Date: 2026-08-14 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c01d021a9e03"
down_revision = "c01d021a9e02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode for SQLite compatibility (drop_column needs table rebuild).
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("firecrawl_api_key")
        batch_op.drop_column("enable_headless")


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(
            sa.Column("firecrawl_api_key", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("enable_headless", sa.Boolean(), nullable=True)
        )
