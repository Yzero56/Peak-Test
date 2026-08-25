from datetime import date, timedelta

from app.models.food import FoodItem, FoodItemStatus
from app.services.cooking_service import get_cooking_status


def make_item(expires_at: date | None) -> FoodItem:
    return FoodItem(
        display_name="test",
        storage_type="refrigerator",
        expires_at=expires_at,
        status=FoodItemStatus.ACTIVE,
    )


def test_fresh_item_can_be_cooked() -> None:
    result = get_cooking_status(make_item(date.today() + timedelta(days=5)))

    assert result["can_cook"] is True
    assert result["requires_confirmation"] is False


def test_expired_item_cannot_be_cooked() -> None:
    result = get_cooking_status(make_item(date.today() - timedelta(days=1)))

    assert result["can_cook"] is False
    assert result["expiry_status"] == "expired"


def test_unknown_expiry_requires_confirmation() -> None:
    result = get_cooking_status(make_item(None))

    assert result["can_cook"] is False
    assert result["requires_confirmation"] is True
