"""add category to food items

Revision ID: 20260824_0005
Revises: 20260824_0004
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0005"
down_revision: Union[str, Sequence[str], None] = "20260824_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("food_items", sa.Column("category", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("food_items", "category")
