"""seed initial shelf life rules

Revision ID: 20260824_0004
Revises: 20260821_0003
Create Date: 2026-08-24
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0004"
down_revision: Union[str, Sequence[str], None] = "20260821_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RULES = [
    ("dairy", "refrigerator", 7, 7),
    ("meat", "refrigerator", 3, 3),
    ("vegetable", "refrigerator", 5, 5),
    ("kimchi", "refrigerator", 30, 30),
    ("frozen_food", "freezer", 30, 30),
]


def upgrade() -> None:
    shelf_life_rules = sa.table(
        "shelf_life_rules",
        sa.column("id", sa.Uuid()),
        sa.column("category", sa.String()),
        sa.column("storage_type", sa.String()),
        sa.column("days_after_open", sa.Integer()),
        sa.column("days_after_manufacture", sa.Integer()),
        sa.column("source", sa.String()),
        sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(
        shelf_life_rules,
        [
            {
                "id": uuid.uuid4(),
                "category": category,
                "storage_type": storage,
                "days_after_open": after_open,
                "days_after_manufacture": after_manufacture,
                "source": "initial development rule; verify against product labeling",
                "active": True,
            }
            for category, storage, after_open, after_manufacture in RULES
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM shelf_life_rules WHERE source = 'initial development rule; verify against product labeling'")
