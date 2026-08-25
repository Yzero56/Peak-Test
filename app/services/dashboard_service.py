from collections.abc import Iterable

from app.models.food import FoodItem
from app.services.expiry_service import get_expiry_status


def build_dashboard_summary(items: Iterable[FoodItem]) -> dict:
    summary = {
        "total_active": 0,
        "fresh": 0,
        "expiring_soon": 0,
        "expired": 0,
        "unknown_expiry": 0,
        "items": [],
    }

    for item in items:
        _, expiry_status = get_expiry_status(item.expires_at)
        summary["total_active"] += 1
        summary[expiry_status if expiry_status != "unknown" else "unknown_expiry"] += 1
        summary["items"].append(item)

    return summary
