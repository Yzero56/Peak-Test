from datetime import date, timedelta

from app.models.food import FoodItem
from app.services.dashboard_service import build_dashboard_summary


def make_item(expires_at: date | None) -> FoodItem:
    item = FoodItem(display_name="test", storage_type="refrigerator")
    item.expires_at = expires_at
    return item


def test_dashboard_summary_counts_expiry_states() -> None:
    today = date.today()
    summary = build_dashboard_summary(
        [
            make_item(today + timedelta(days=10)),
            make_item(today + timedelta(days=2)),
            make_item(today - timedelta(days=1)),
            make_item(None),
        ]
    )

    assert summary["total_active"] == 4
    assert summary["fresh"] == 1
    assert summary["expiring_soon"] == 1
    assert summary["expired"] == 1
    assert summary["unknown_expiry"] == 1
