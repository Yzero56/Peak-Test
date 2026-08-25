import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FoodImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_item_id: uuid.UUID | None
    object_key: str
    content_type: str
    sha256: str
    created_at: datetime
