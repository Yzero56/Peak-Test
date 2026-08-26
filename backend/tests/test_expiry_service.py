from datetime import date, timedelta

from app.services.expiry_service import get_expiry_status


REFERENCE_DATE = date(2026, 8, 21)


def test_missing_expiry_date_is_unknown() -> None:
    assert get_expiry_status(None, REFERENCE_DATE) == (None, "unknown")


def test_expired_item_has_negative_days_remaining() -> None:
    expires_at = REFERENCE_DATE - timedelta(days=1)

    assert get_expiry_status(expires_at, REFERENCE_DATE) == (-1, "expired")


def test_expiry_date_today_is_expiring_soon() -> None:
    assert get_expiry_status(REFERENCE_DATE, REFERENCE_DATE) == (0, "expiring_soon")


def test_three_days_remaining_is_expiring_soon() -> None:
    expires_at = REFERENCE_DATE + timedelta(days=3)

    assert get_expiry_status(expires_at, REFERENCE_DATE) == (3, "expiring_soon")


def test_four_days_remaining_is_fresh() -> None:
    expires_at = REFERENCE_DATE + timedelta(days=4)

    assert get_expiry_status(expires_at, REFERENCE_DATE) == (4, "fresh")
