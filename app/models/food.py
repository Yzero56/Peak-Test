import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StorageType(str, enum.Enum):
    ROOM = "room"
    REFRIGERATOR = "refrigerator"
    FREEZER = "freezer"


class FoodItemStatus(str, enum.Enum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    DISCARDED = "discarded"


class DateSource(str, enum.Enum):
    LABEL = "label"
    ESTIMATED = "estimated"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class FoodProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50))
    default_storage: Mapped[StorageType | None] = mapped_column(String(30))

    items: Mapped[list["FoodItem"]] = relationship(back_populates="product")


class FoodItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_items"
    __table_args__ = (
        Index("ix_food_items_status_expires_at", "status", "expires_at"),
        Index("ix_food_items_storage_status", "storage_type", "status"),
    )

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("food_products.id", ondelete="SET NULL")
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    # 2번 파트가 판정한 용기 식별자. 하드웨어 연동 전에는 비어 있을 수 있다.
    container_id: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit: Mapped[str | None] = mapped_column(String(20))
    storage_type: Mapped[StorageType] = mapped_column(String(30), nullable=False)
    purchased_at: Mapped[date | None] = mapped_column(Date)
    opened_at: Mapped[date | None] = mapped_column(Date)
    manufactured_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    date_source: Mapped[DateSource] = mapped_column(
        String(20), nullable=False, default=DateSource.UNKNOWN
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[FoodItemStatus] = mapped_column(
        String(20), nullable=False, default=FoodItemStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text)

    product: Mapped[FoodProduct | None] = relationship(back_populates="items")
    images: Mapped[list["FoodImage"]] = relationship(
        back_populates="food_item", cascade="all, delete-orphan"
    )


class FoodImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_images"

    food_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("food_items.id", ondelete="SET NULL")
    )
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    food_item: Mapped[FoodItem | None] = relationship(back_populates="images")


class ShelfLifeRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shelf_life_rules"

    category: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_type: Mapped[StorageType] = mapped_column(String(30), nullable=False)
    days_after_open: Mapped[int | None] = mapped_column(Integer)
    days_after_manufacture: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
