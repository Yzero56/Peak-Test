import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.food import StorageType


class ShelfLifeRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    storage_type: StorageType
    days_after_open: int | None
    days_after_manufacture: int | None
    source: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
