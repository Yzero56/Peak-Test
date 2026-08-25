"""add numeric compatibility IDs for the existing mobile app"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260825_0007"
down_revision: Union[str, Sequence[str], None] = "20260825_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("food_items", sa.Column("legacy_id", sa.Integer(), nullable=True))
    op.execute("UPDATE food_items SET legacy_id = row_number FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS row_number FROM food_items) numbered WHERE food_items.id = numbered.id")
    op.create_index("ix_food_items_legacy_id", "food_items", ["legacy_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_food_items_legacy_id", table_name="food_items")
    op.drop_column("food_items", "legacy_id")
