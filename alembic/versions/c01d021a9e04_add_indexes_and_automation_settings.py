"""add indexes and automation settings

Revision ID: c01d021a9e04
Revises: c01d021a9e03
Create Date: 2026-10-03 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "c01d021a9e04"
down_revision: Union[str, None] = "c01d021a9e03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "enrolled_courses" in tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("enrolled_courses")}
        if "idx_enrolled_courses_run_status" not in existing_indexes:
            op.create_index(
                "idx_enrolled_courses_run_status",
                "enrolled_courses",
                ["enrollment_run_id", "status"],
            )
        if "idx_enrolled_courses_slug" not in existing_indexes:
            op.create_index(
                "idx_enrolled_courses_slug",
                "enrolled_courses",
                ["slug"],
            )

    if "user_settings" in tables:
        existing_cols = {c["name"] for c in inspector.get_columns("user_settings")}
        if "webhook_url" not in existing_cols:
            op.add_column(
                "user_settings",
                sa.Column("webhook_url", sa.String(500), nullable=True),
            )
        if "webhook_service" not in existing_cols:
            op.add_column(
                "user_settings",
                sa.Column(
                    "webhook_service",
                    sa.String(50),
                    nullable=True,
                    server_default="generic",
                ),
            )
        if "schedule_interval_hours" not in existing_cols:
            op.add_column(
                "user_settings",
                sa.Column(
                    "schedule_interval_hours",
                    sa.Integer(),
                    nullable=True,
                    server_default="0",
                ),
            )
        if "last_scheduled_run" not in existing_cols:
            op.add_column(
                "user_settings",
                sa.Column("last_scheduled_run", sa.DateTime(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "enrolled_courses" in tables:
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("enrolled_courses")}
        if "idx_enrolled_courses_slug" in existing_indexes:
            op.drop_index("idx_enrolled_courses_slug", table_name="enrolled_courses")
        if "idx_enrolled_courses_run_status" in existing_indexes:
            op.drop_index(
                "idx_enrolled_courses_run_status", table_name="enrolled_courses"
            )

    if "user_settings" in tables:
        columns = {c["name"] for c in inspector.get_columns("user_settings")}
        to_drop = [
            col
            for col in (
                "webhook_url",
                "webhook_service",
                "schedule_interval_hours",
                "last_scheduled_run",
            )
            if col in columns
        ]
        if to_drop:
            with op.batch_alter_table("user_settings") as batch_op:
                for col in to_drop:
                    batch_op.drop_column(col)
