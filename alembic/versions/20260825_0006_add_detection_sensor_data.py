"""add detection and sensor integration tables

Revision ID: 20260825_0006
Revises: 20260824_0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0006"
down_revision: Union[str, Sequence[str], None] = "20260824_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("food_items", sa.Column("container_id", sa.String(length=64), nullable=True))
    op.create_table(
        "detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("container_id", sa.String(length=64), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("bbox_x", sa.Numeric(6, 4), nullable=True),
        sa.Column("bbox_y", sa.Numeric(6, 4), nullable=True),
        sa.Column("bbox_width", sa.Numeric(6, 4), nullable=True),
        sa.Column("bbox_height", sa.Numeric(6, 4), nullable=True),
        sa.Column("motion_direction", sa.String(length=10), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["food_images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_detections_image_label", "detections", ["image_id", "label"])
    op.create_table(
        "sensor_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Numeric(5, 2), nullable=True),
        sa.Column("humidity", sa.Numeric(5, 2), nullable=True),
        sa.Column("gas_resistance_ohm", sa.Integer(), nullable=True),
        sa.Column("door_open", sa.Boolean(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_readings_device_recorded", "sensor_readings", ["device_id", "recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_sensor_readings_device_recorded", table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_index("ix_detections_image_label", table_name="detections")
    op.drop_table("detections")
    op.drop_column("food_items", "container_id")
