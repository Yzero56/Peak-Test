from datetime import date
from decimal import Decimal

import pytest

from app.services.vlm.mock_adapter import MockVLMAdapter


@pytest.mark.asyncio
async def test_mock_vlm_returns_structured_food_result() -> None:
    result = await MockVLMAdapter().extract_food_info(b"image", "image/jpeg")

    assert result.food_name == "우유"
    assert result.storage_type == "refrigerator"
    assert result.labeled_expires_at is not None
    assert result.labeled_expires_at > date.today()
    assert result.confidence == Decimal("0.90")
