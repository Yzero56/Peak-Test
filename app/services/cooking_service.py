from app.models.food import FoodItem, FoodItemStatus
from app.services.expiry_service import get_expiry_status


def get_cooking_status(item: FoodItem) -> dict:
    if item.status != FoodItemStatus.ACTIVE:
        return {
            "can_cook": False,
            "requires_confirmation": False,
            "expiry_status": "unavailable",
            "days_remaining": None,
            "reason": "Food item is not active",
        }

    days_remaining, expiry_status = get_expiry_status(item.expires_at)
    if expiry_status == "expired":
        return {
            "can_cook": False,
            "requires_confirmation": False,
            "expiry_status": expiry_status,
            "days_remaining": days_remaining,
            "reason": "Expiry date has passed",
        }
    if expiry_status == "unknown":
        return {
            "can_cook": False,
            "requires_confirmation": True,
            "expiry_status": expiry_status,
            "days_remaining": days_remaining,
            "reason": "Expiry date is unknown",
        }
    if expiry_status == "expiring_soon":
        return {
            "can_cook": True,
            "requires_confirmation": True,
            "expiry_status": expiry_status,
            "days_remaining": days_remaining,
            "reason": "Food is near its expiry date",
        }
    return {
        "can_cook": True,
        "requires_confirmation": False,
        "expiry_status": expiry_status,
        "days_remaining": days_remaining,
        "reason": "Food is within its expiry period",
    }
