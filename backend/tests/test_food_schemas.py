from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.food import StorageType
from app.schemas.food import FoodItemCreate


def test_food_item_schema_accepts_valid_dates() -> None:
    item = FoodItemCreate(
        display_name="우유",
        storage_type=StorageType.REFRIGERATOR,
        quantity=Decimal("1"),
        purchased_at=date(2026, 8, 20),
        opened_at=date(2026, 8, 21),
        expires_at=date(2026, 8, 28),
    )

    assert item.display_name == "우유"
    assert item.expires_at == date(2026, 8, 28)


def test_opened_date_cannot_be_before_purchased_date() -> None:
    with pytest.raises(ValidationError, match="opened_at"):
        FoodItemCreate(
            display_name="우유",
            storage_type=StorageType.REFRIGERATOR,
            purchased_at=date(2026, 8, 21),
            opened_at=date(2026, 8, 20),
        )


def test_expiry_date_cannot_be_before_manufactured_date() -> None:
    with pytest.raises(ValidationError, match="expires_at"):
        FoodItemCreate(
            display_name="김치",
            storage_type=StorageType.REFRIGERATOR,
            manufactured_at=date(2026, 8, 21),
            expires_at=date(2026, 8, 20),
        )
