import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AnalysisJobStatus
from app.models.food import StorageType


class ExtractedFoodInfo(BaseModel):
    food_name: str | None = None
    category: str | None = None
    manufactured_date_text: str | None = None
    expiration_date_text: str | None = None
    manufactured_at: date | None = None
    labeled_expires_at: date | None = None
    storage_type: StorageType | None = None
    confidence: Decimal = Field(ge=0, le=1)
    notes: str | None = None


class AnalysisJobCreate(BaseModel):
    image_id: uuid.UUID
    food_item_id: uuid.UUID | None = None


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    status: AnalysisJobStatus
    model: str
    result: ExtractedFoodInfo | None
    needs_review: bool
    applied_food_item_id: uuid.UUID | None
    applied_at: datetime | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AnalysisJobAccepted(BaseModel):
    job_id: uuid.UUID
    status: Literal["queued"]
