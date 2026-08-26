from typing import Protocol

from app.schemas.analysis import ExtractedFoodInfo


class VLMAdapter(Protocol):
    async def extract_food_info(self, image: bytes, content_type: str) -> ExtractedFoodInfo:
        ...
