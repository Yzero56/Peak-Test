"""store container re-identification metadata"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260825_0008"
down_revision: Union[str, Sequence[str], None] = "20260825_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("detections", sa.Column("recognition_status", sa.String(length=20), nullable=True))
    op.add_column("detections", sa.Column("similarity", sa.Numeric(5, 4), nullable=True))
    op.add_column("detections", sa.Column("embedding_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("detections", "embedding_model")
    op.drop_column("detections", "similarity")
    op.drop_column("detections", "recognition_status")
