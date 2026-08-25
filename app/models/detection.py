import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.food import FoodImage


class Detection(UUIDPrimaryKeyMixin, Base):
    """2번 파트(YOLOE/DINOv3)에서 전달되는 객체 탐지 결과 1건."""

    __tablename__ = "detections"
    __table_args__ = (Index("ix_detections_image_label", "image_id", "label"),)

    image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("food_images.id", ondelete="CASCADE")
    )
    device_id: Mapped[str | None] = mapped_column(String(64))
    container_id: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    # bounding_box는 0~1로 정규화된 값을 저장한다.
    bbox_x: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    bbox_y: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    bbox_width: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    bbox_height: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    # 1번 파트의 IN/OUT 모션 판정 결과를 함께 받을 수 있게 둔다.
    motion_direction: Mapped[str | None] = mapped_column(String(10))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    image: Mapped[FoodImage | None] = relationship()


class SensorReading(UUIDPrimaryKeyMixin, Base):
    """4번 파트 BME680 센서 측정값."""

    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_sensor_readings_device_recorded", "device_id", "recorded_at"),)

    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    gas_resistance_ohm: Mapped[int | None] = mapped_column()
    door_open: Mapped[bool | None] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
