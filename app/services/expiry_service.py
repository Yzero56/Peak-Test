from datetime import date, timedelta

from app.models.food import DateSource, ShelfLifeRule, StorageType


def get_expiry_status(expires_at: date | None, today: date | None = None) -> tuple[int | None, str]:
    if expires_at is None:
        return None, "unknown"

    reference_date = today or date.today()
    days_remaining = (expires_at - reference_date).days

    if days_remaining < 0:
        return days_remaining, "expired"
    if days_remaining <= 3:
        return days_remaining, "expiring_soon"
    return days_remaining, "fresh"


def calculate_expiry(
    labeled_expires_at: date | None,
    manufactured_at: date | None,
    category: str | None,
    storage_type: StorageType,
    rule: ShelfLifeRule | None,
) -> tuple[date | None, DateSource]:
    if labeled_expires_at is not None:
        return labeled_expires_at, DateSource.LABEL

    if (
        manufactured_at is not None
        and category is not None
        and rule is not None
        and rule.category == category
        and rule.storage_type == storage_type
        and rule.days_after_manufacture is not None
    ):
        return manufactured_at + timedelta(days=rule.days_after_manufacture), DateSource.ESTIMATED

    return None, DateSource.UNKNOWN
