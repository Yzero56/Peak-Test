from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ExpiryResponse(BaseModel):
    expires_at: date | None
    days_remaining: int | None
    expiry_status: str
    date_source: str
    confidence: Decimal | None
