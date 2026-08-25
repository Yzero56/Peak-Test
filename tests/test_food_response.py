from datetime import date, timedelta
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.api.routes.food_items import to_response
from app.models.food import DateSource, FoodItem, FoodItemStatus


def test_food_response_includes_cooking_decision() -> None:
    item = FoodItem(
        display_name="우유",
        storage_type="refrigerator",
        expires_at=date.today() + timedelta(days=5),
        status=FoodItemStatus.ACTIVE,
        id=uuid.uuid4(),
        quantity=Decimal("1"),
        date_source=DateSource.MANUAL,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    response = to_response(item)

    assert response.expiry_status == "fresh"
    assert response.can_cook is True
    assert response.requires_confirmation is False
