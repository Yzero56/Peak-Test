"""track applied analysis results

Revision ID: 20260821_0003
Revises: 20260821_0002
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260821_0003"
down_revision: Union[str, Sequence[str], None] = "20260821_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("applied_food_item_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("analysis_jobs", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_analysis_jobs_applied_food_item_id",
        "analysis_jobs",
        "food_items",
        ["applied_food_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_analysis_jobs_applied_food_item_id", "analysis_jobs", type_="foreignkey")
    op.drop_column("analysis_jobs", "applied_at")
    op.drop_column("analysis_jobs", "applied_food_item_id")
