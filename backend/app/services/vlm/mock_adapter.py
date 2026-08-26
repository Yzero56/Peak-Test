from datetime import date, timedelta

from app.schemas.analysis import ExtractedFoodInfo


class MockVLMAdapter:
    """외부 VLM 없이 전체 분석 흐름을 검증하기 위한 adapter다."""

    async def extract_food_info(self, image: bytes, content_type: str) -> ExtractedFoodInfo:
        return ExtractedFoodInfo(
            food_name="우유",
            category="dairy",
            expiration_date_text=None,
            manufactured_date_text=None,
            manufactured_at=None,
            labeled_expires_at=date.today() + timedelta(days=7),
            storage_type="refrigerator",
            confidence=0.90,
            notes=f"mock result for {content_type}, {len(image)} bytes",
        )
