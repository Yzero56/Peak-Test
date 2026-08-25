from datetime import date, timedelta
from decimal import Decimal
import uuid
from datetime import datetime, timezone

from app.api.routes.food_items import to_response
from app.models.food import DateSource, FoodItem, FoodItemStatus


def test_food_item_response_exposes_expiry_and_cooking_fields() -> None:
    item = FoodItem(
        id=uuid.uuid4(),
        display_name="김치",
        quantity=Decimal("1"),
        storage_type="refrigerator",
        expires_at=date.today() + timedelta(days=2),
        date_source=DateSource.ESTIMATED,
        status=FoodItemStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    response = to_response(item)

    assert response.expiry_status == "expiring_soon"
    assert response.days_remaining == 2
    assert response.can_cook is True
    assert response.requires_confirmation is True
