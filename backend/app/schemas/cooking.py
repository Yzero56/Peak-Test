from pydantic import BaseModel


class CookingStatusResponse(BaseModel):
    can_cook: bool
    requires_confirmation: bool
    expiry_status: str
    days_remaining: int | None
    reason: str
