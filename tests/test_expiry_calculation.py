from datetime import date

from app.models.food import DateSource, ShelfLifeRule, StorageType
from app.services.expiry_service import calculate_expiry


def make_rule(days: int = 7) -> ShelfLifeRule:
    return ShelfLifeRule(
        category="dairy",
        storage_type=StorageType.REFRIGERATOR,
        days_after_manufacture=days,
        active=True,
    )


def test_labeled_date_has_priority_over_estimation() -> None:
    expires_at, source = calculate_expiry(
        date(2026, 8, 30),
        date(2026, 8, 21),
        "dairy",
        StorageType.REFRIGERATOR,
        make_rule(),
    )

    assert expires_at == date(2026, 8, 30)
    assert source == DateSource.LABEL


def test_manufactured_date_is_estimated_from_matching_rule() -> None:
    expires_at, source = calculate_expiry(
        None,
        date(2026, 8, 21),
        "dairy",
        StorageType.REFRIGERATOR,
        make_rule(7),
    )

    assert expires_at == date(2026, 8, 28)
    assert source == DateSource.ESTIMATED


def test_missing_rule_keeps_expiry_unknown() -> None:
    expires_at, source = calculate_expiry(
        None,
        date(2026, 8, 21),
        "meat",
        StorageType.REFRIGERATOR,
        make_rule(),
    )

    assert expires_at is None
    assert source == DateSource.UNKNOWN
