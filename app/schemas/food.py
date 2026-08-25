import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.food import DateSource, FoodItemStatus, StorageType


class FoodItemCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    container_id: str | None = Field(default=None, max_length=64)
    product_id: uuid.UUID | None = None
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str | None = Field(default=None, max_length=20)
    storage_type: StorageType
    purchased_at: date | None = None
    opened_at: date | None = None
    manufactured_at: date | None = None
    expires_at: date | None = None
    date_source: DateSource = DateSource.UNKNOWN
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "FoodItemCreate":
        if self.opened_at and self.purchased_at and self.opened_at < self.purchased_at:
            raise ValueError("opened_at must not be earlier than purchased_at")
        if self.expires_at and self.manufactured_at and self.expires_at < self.manufactured_at:
            raise ValueError("expires_at must not be earlier than manufactured_at")
        return self


class FoodItemUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    container_id: str | None = Field(default=None, max_length=64)
    product_id: uuid.UUID | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=20)
    storage_type: StorageType | None = None
    purchased_at: date | None = None
    opened_at: date | None = None
    manufactured_at: date | None = None
    expires_at: date | None = None
    date_source: DateSource | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    status: FoodItemStatus | None = None
    notes: str | None = None


class FoodItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None
    display_name: str
    category: str | None
    quantity: Decimal
    unit: str | None
    storage_type: StorageType
    purchased_at: date | None
    opened_at: date | None
    manufactured_at: date | None
    expires_at: date | None
    date_source: DateSource
    confidence: Decimal | None
    status: FoodItemStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    container_id: str | None = None
    days_remaining: int | None = None
    expiry_status: str
    can_cook: bool = False
    requires_confirmation: bool = False
    # 파트 간 공통 필드 별칭. 기존 필드는 그대로 유지해 호환성을 지킨다.
    food_id: uuid.UUID | None = None
    food_name: str | None = None
    expiration_date: date | None = None
    stored_at: datetime | None = None
    d_day: int | None = None
